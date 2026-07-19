from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Iterable
from urllib.parse import quote, urlparse
from uuid import uuid4
import webbrowser

from .persistence import atomic_write_json
from .action_types import SUPPORTED_ACTION_TYPES


VISIBLE_STATES = {"Draft", "Trusted"}
class ActionError(Exception):
    """Raised when an action cannot be loaded or executed safely."""


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    context: str
    type: str
    value: str
    state: str = "Draft"
    arguments: tuple[str, ...] = ()
    working_directory: str | None = None
    technology: str = ""
    task: str = ""

    @property
    def display_text(self) -> str:
        parts = [part for part in (self.technology, self.task, self.context, self.title) if part]
        return " > ".join(dict.fromkeys(parts))

    @property
    def compact_display_text(self) -> str:
        title = self.title.strip()
        commands = ("Open", "Copy", "Convert", "Search", "Arrange", "Restore")
        for command in commands:
            prefix = command + " "
            if title.casefold().startswith(prefix.casefold()):
                return f"{command} → {title[len(prefix):].strip()}"

        inferred_command = {
            "copy_text": "Copy",
            "workspace_template": "Copy",
            "transform_list_csv": "Convert",
            "open_url": "Open",
            "open_file": "Open",
            "open_folder": "Open",
            "launch_app": "Open",
            "paste_credential": "Paste",
            "build_url_copy": "Copy",
            "build_url_open": "Open",
            "build_url_selection_open": "Open",
        }.get(self.type)
        return f"{inferred_command} → {title}" if inferred_command else title


def load_actions(path: Path) -> list[Action]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ActionError(f"Action file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ActionError(f"Action file is not valid JSON: {path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("actions"), list):
        raise ActionError("Action file must contain an 'actions' list.")

    actions = [_parse_action(item, index) for index, item in enumerate(raw["actions"], start=1)]
    _ensure_unique_action_ids(actions, path)
    return [action for action in actions if action.state in VISIBLE_STATES]


def load_combined_actions(shared_path: Path, local_path: Path) -> tuple[list[Action], set[str]]:
    shared_actions = load_actions(shared_path)
    local_actions = load_actions(local_path) if local_path.exists() else []
    shared_ids = {action.id.casefold(): action.id for action in shared_actions}
    local_ids_by_key = {action.id.casefold(): action.id for action in local_actions}
    duplicate_ids = shared_ids.keys() & local_ids_by_key.keys()
    if duplicate_ids:
        raise ActionError(
            "Local action IDs duplicate shared actions: "
            + ", ".join(sorted(local_ids_by_key[key] for key in duplicate_ids))
        )
    return shared_actions + local_actions, {action.id for action in local_actions}


def append_action(path: Path, action: Action) -> None:
    append_actions(path, [action])


def append_actions(path: Path, actions: Iterable[Action]) -> None:
    new_actions = list(actions)
    if not new_actions:
        return
    data = _load_action_data(path)
    existing_ids = {
        item.get("id").casefold()
        for item in data["actions"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    batch_ids: set[str] = set()
    for action in new_actions:
        action_key = action.id.casefold()
        if action_key in existing_ids or action_key in batch_ids:
            raise ActionError(f"Action ID already exists: {action.id}")
        batch_ids.add(action_key)
    data["actions"].extend(_action_to_dict(action) for action in new_actions)
    atomic_write_json(path, data)


def update_action(path: Path, updated_action: Action) -> None:
    data = _load_action_data(path)
    changed = False
    for index, raw_action in enumerate(data["actions"]):
        if isinstance(raw_action, dict) and raw_action.get("id") == updated_action.id:
            data["actions"][index] = _action_to_dict(updated_action)
            changed = True
            break

    if not changed:
        raise ActionError(f"Action was not found: {updated_action.id}")

    atomic_write_json(path, data)


def draft_copy_text_action(
    *,
    title: str,
    context: str,
    value: str,
    technology: str = "",
    task: str = "",
) -> Action:
    clean_title = title.strip()
    clean_context = context.strip() or "General"
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    if not clean_value:
        raise ActionError("Action text cannot be empty.")

    return Action(
        id=f"draft-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_context,
        type="copy_text",
        value=clean_value,
        state="Draft",
        technology=technology.strip(),
        task=task.strip(),
    )


def draft_open_url_action(
    *,
    title: str,
    context: str,
    value: str,
    technology: str = "",
    task: str = "",
) -> Action:
    clean_title = title.strip()
    clean_context = context.strip() or "General"
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    validate_http_url(clean_value, label="Action URL")
    return Action(
        id=f"draft-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_context,
        type="open_url",
        value=clean_value,
        state="Draft",
        technology=technology.strip(),
        task=task.strip(),
    )


def draft_build_url_action(
    *,
    title: str,
    context: str,
    template: str,
    action_type: str = "build_url_selection_open",
    technology: str = "",
    task: str = "",
) -> Action:
    allowed_types = {"build_url_copy", "build_url_open", "build_url_selection_open"}
    if action_type not in allowed_types:
        raise ActionError("Unsupported URL-builder action type.")
    clean_title = title.strip()
    clean_context = context.strip() or "General"
    clean_template = template.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    build_url(clean_template, "example")
    return Action(
        id=f"draft-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_context,
        type=action_type,
        value=clean_template,
        state="Draft",
        technology=technology.strip(),
        task=task.strip(),
    )


def configured_draft_action(
    *,
    title: str,
    context: str,
    action_type: str,
    value: str,
    technology: str = "",
    task: str = "",
    arguments: Iterable[str] = (),
    working_directory: str = "",
) -> Action:
    """Create a validated local Draft from the built-in action catalogue."""
    clean_title = title.strip()
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise ActionError(f"Unsupported action type: {action_type}")
    validate_action_value(action_type, clean_value)

    return Action(
        id=f"draft-{uuid4().hex[:12]}",
        title=clean_title,
        context=context.strip() or "General",
        type=action_type,
        value=clean_value,
        state="Draft",
        arguments=tuple(argument.strip() for argument in arguments if argument.strip()),
        working_directory=working_directory.strip() or None,
        technology=technology.strip(),
        task=task.strip(),
    )


def edited_configured_action(
    action: Action,
    *,
    title: str,
    context: str,
    action_type: str,
    value: str,
    technology: str = "",
    task: str = "",
    arguments: Iterable[str] = (),
    working_directory: str = "",
) -> Action:
    """Validate edits while preserving an action's stable identity and maturity."""
    validated = configured_draft_action(
        title=title,
        context=context,
        action_type=action_type,
        value=value,
        technology=technology,
        task=task,
        arguments=arguments,
        working_directory=working_directory,
    )
    return Action(
        id=action.id,
        title=validated.title,
        context=validated.context,
        type=validated.type,
        value=validated.value,
        state=action.state,
        arguments=validated.arguments,
        working_directory=validated.working_directory,
        technology=validated.technology,
        task=validated.task,
    )


def edited_copy_text_action(action: Action, *, title: str, context: str, value: str) -> Action:
    if action.type != "copy_text" or action.state != "Draft":
        raise ActionError("Only draft copy-text actions can be edited right now.")

    clean_title = title.strip()
    clean_context = context.strip() or "General"
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    if not clean_value:
        raise ActionError("Action text cannot be empty.")

    return Action(
        id=action.id,
        title=clean_title,
        context=clean_context,
        type=action.type,
        value=clean_value,
        state=action.state,
        arguments=action.arguments,
        working_directory=action.working_directory,
        technology=action.technology,
        task=action.task,
    )


def trusted_action(action: Action) -> Action:
    if action.state != "Draft":
        raise ActionError("Only draft actions can be marked Trusted.")

    return Action(
        id=action.id,
        title=action.title,
        context=action.context,
        type=action.type,
        value=action.value,
        state="Trusted",
        arguments=action.arguments,
        working_directory=action.working_directory,
        technology=action.technology,
        task=action.task,
    )


def search_actions(actions: Iterable[Action], query: str) -> list[Action]:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return list(actions)

    matches = []
    for action in actions:
        searchable = " ".join(
            [
                action.title,
                action.technology,
                action.task,
                action.context,
                action.type,
                action.value,
                action.state,
            ]
        ).casefold()
        if all(term in searchable for term in terms):
            matches.append(action)
    return matches


def execute_action(
    action: Action,
    *,
    clipboard_setter: Callable[[str], None] | None = None,
    clipboard_getter: Callable[[], str] | None = None,
    input_provider: Callable[[str], str | None] | None = None,
    selected_text: str | None = None,
    input_text: str | None = None,
    output_setter: Callable[[str], None] | None = None,
    credential_paster: Callable[[Action], str] | None = None,
    opener: Callable[[Action], None] | None = None,
) -> str:
    if action.type == "paste_credential":
        validate_credential_target(action.value)
        if action.state != "Trusted":
            raise ActionError("Credential actions must be marked Trusted before use.")
        if credential_paster is None:
            raise ActionError("Protected credential paste is unavailable.")
        return credential_paster(action)

    if action.type == "workspace_template":
        expanded = expanded_action(action, clipboard_getter=clipboard_getter)
        if output_setter is not None:
            output_setter(expanded.value)
        if clipboard_setter is not None:
            clipboard_setter(expanded.value)
        return "Loaded the template into Input / Output and copied it."

    if action.type == "transform_list_csv":
        result = list_to_comma_separated(input_text or "", sql_strings=action.value == "sql_strings")
        if output_setter is not None:
            output_setter(result)
        if clipboard_setter is not None:
            clipboard_setter(result)
        return "Transformed the list and copied the result."

    if action.type == "build_url_selection_open":
        identifier = selected_text
        if not identifier and clipboard_getter is not None:
            identifier = clipboard_getter()
        if not identifier:
            raise ActionError(
                "No input was found. Select or copy an ID, or place it in Input / Output."
            )
        url = build_url(action.value, identifier)
        if clipboard_setter is None:
            raise ActionError("No clipboard is available for copying the URL.")
        clipboard_setter(url)
        selected_opener = opener or open_action_target
        selected_opener(
            Action(action.id, action.title, action.context, "open_url", url, action.state)
        )
        return "Copied the built URL and opened it in the browser."

    if action.type in {"build_url_copy", "build_url_open"}:
        if input_provider is None:
            raise ActionError("No input dialog is available for entering an ID.")
        identifier = input_provider("Enter the ID:")
        if identifier is None:
            return "URL action cancelled."
        url = build_url(action.value, identifier)
        if action.type == "build_url_copy":
            if clipboard_setter is None:
                raise ActionError("No clipboard is available for copying the URL.")
            clipboard_setter(url)
            return "Copied the built URL to the clipboard."
        selected_opener = opener or open_action_target
        selected_opener(
            Action(action.id, action.title, action.context, "open_url", url, action.state)
        )
        return "Opened the built URL."

    expanded = expanded_action(action, clipboard_getter=clipboard_getter)
    if action.type == "copy_text":
        if clipboard_setter is None:
            raise ActionError("No clipboard is available for copying text.")
        clipboard_setter(expanded.value)
        return "Copied text to the clipboard."

    if action.type in {"open_url", "open_file", "open_folder", "launch_app"}:
        selected_opener = opener or open_action_target
        selected_opener(expanded)
        return "Opened selected target."

    raise ActionError(f"Unsupported action type: {action.type}")


def build_url(template: str, identifier: str) -> str:
    clean_identifier = identifier.strip()
    if not clean_identifier:
        raise ActionError("ID cannot be empty.")
    if "{id}" not in template and "{id_url}" not in template:
        raise ActionError("URL template must contain {id} or {id_url}.")

    result = template.replace("{id_url}", quote(clean_identifier, safe=""))
    result = result.replace("{id}", clean_identifier)
    validate_http_url(result, label="Built URL")
    return result


def validate_http_url(value: str, *, label: str = "URL") -> None:
    parsed = urlparse(value)
    try:
        hostname = parsed.hostname
    except ValueError as exc:
        raise ActionError(f"{label} has an invalid hostname.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ActionError(f"{label} must be a complete http:// or https:// address.")
    if parsed.username is not None or parsed.password is not None:
        raise ActionError(f"{label} must not include a username or password.")
    if "\\" in parsed.netloc or any(
        character.isspace() or ord(character) < 32 for character in parsed.netloc
    ):
        raise ActionError(f"{label} has an invalid or ambiguous hostname.")


def validate_credential_target(value: str) -> None:
    if not value.strip():
        raise ActionError("Windows credential target name cannot be empty.")
    if len(value) > 32_767:
        raise ActionError("Windows credential target name is too long.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ActionError("Windows credential target name cannot contain control characters.")


def validate_action_value(action_type: str, value: str) -> None:
    """Validate the configured value shared by guided creation and JSON loading."""
    clean_value = value.strip()
    if not clean_value:
        raise ActionError("The action value cannot be empty.")
    if action_type == "open_url":
        validate_http_url(clean_value, label="Action URL")
    elif action_type == "paste_credential":
        validate_credential_target(clean_value)
    elif action_type in {"build_url_copy", "build_url_open", "build_url_selection_open"}:
        build_url(clean_value, "example")
    elif action_type == "transform_list_csv" and clean_value not in {"csv", "sql_strings"}:
        raise ActionError("List conversion must use csv or sql_strings.")


def list_to_comma_separated(value: str, *, sql_strings: bool = False) -> str:
    items = [line.strip() for line in value.splitlines() if line.strip()]
    if not items:
        raise ActionError("The Input / Output field does not contain a list.")
    if sql_strings:
        items = [f"'{item.replace(chr(39), chr(39) * 2)}'" for item in items]
    return ", ".join(items)


def transform_text(
    value: str,
    operation: str,
    *,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """Apply a constrained, previewable transformation to workspace text."""
    if operation == "lowercase":
        return value.lower()
    if operation == "uppercase":
        return value.upper()
    if operation == "normalize_spaces":
        return re.sub(r"[ \t]+", " ", value)
    if operation == "prefix_suffix_lines":
        return _affix_each_line(value, prefix, suffix)
    if operation == "remove_duplicate_lines":
        return _remove_duplicate_lines(value)
    raise ActionError(f"Unsupported text transformation: {operation}")


def _affix_each_line(value: str, prefix: str, suffix: str) -> str:
    if not value:
        return value
    transformed: list[str] = []
    for chunk in value.splitlines(keepends=True):
        body = chunk.rstrip("\r\n")
        ending = chunk[len(body) :]
        transformed.append(prefix + body + suffix + ending)
    return "".join(transformed)


def _remove_duplicate_lines(value: str) -> str:
    if not value:
        return value
    lines = value.splitlines()
    seen: set[str] = set()
    unique = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    separator = "\r\n" if "\r\n" in value else "\r" if "\r" in value else "\n"
    result = separator.join(unique)
    if value.endswith(("\r", "\n")):
        result += separator
    return result


def expanded_action(
    action: Action,
    *,
    clipboard_getter: Callable[[], str] | None = None,
    now: datetime | None = None,
) -> Action:
    """Return an action with QuickTextPaste-style template variables resolved."""
    clipboard = ""
    template_values = [action.value, *action.arguments]
    if action.working_directory:
        template_values.append(action.working_directory)
    clipboard_tokens = ("%CLIPBOARD%", "%CLIPBOARD_URL%", "%pptxt%", "%cpy_txt_urlencode%")
    needs_clipboard = any(
        token in value for value in template_values for token in clipboard_tokens
    )
    if needs_clipboard and clipboard_getter is not None:
        try:
            clipboard = clipboard_getter()
        except Exception as exc:
            raise ActionError("The clipboard does not contain text.") from exc

    return Action(
        id=action.id,
        title=action.title,
        context=action.context,
        type=action.type,
        value=expand_template(action.value, clipboard=clipboard, now=now),
        state=action.state,
        arguments=tuple(expand_template(value, clipboard=clipboard, now=now) for value in action.arguments),
        working_directory=(
            expand_template(action.working_directory, clipboard=clipboard, now=now)
            if action.working_directory
            else None
        ),
        technology=action.technology,
        task=action.task,
    )


def expand_template(value: str, *, clipboard: str = "", now: datetime | None = None) -> str:
    """Expand portable dynamic-text variables, including useful QTP aliases."""
    moment = now or datetime.now()
    replacements = {
        "%CLIPBOARD%": clipboard,
        "%CLIPBOARD_URL%": quote(clipboard, safe=""),
        "%pptxt%": clipboard,
        "%cpy_txt_urlencode%": quote(clipboard, safe=""),
        "%YYYY%": moment.strftime("%Y"),
        "%YY%": moment.strftime("%y"),
        "%MMMM%": moment.strftime("%B"),
        "%MMM%": moment.strftime("%b"),
        "%MM%": moment.strftime("%m"),
        "%M%": str(moment.month),
        "%DDDD%": moment.strftime("%A"),
        "%DDD%": moment.strftime("%a"),
        "%DD%": moment.strftime("%d"),
        "%D%": str(moment.day),
        "%hh%": moment.strftime("%H"),
        "%mm%": moment.strftime("%M"),
        "%ss%": moment.strftime("%S"),
        "%LDF%": moment.strftime("%x"),
        "%LTF%": moment.strftime("%X"),
        "%CW%": str(moment.isocalendar().week),
        "%CWL%": f"{moment.isocalendar().week:02d}",
    }
    replacements.update(
        {
            "%MMM_UC%": replacements["%MMM%"].upper(),
            "%MM_UC%": replacements["%MMMM%"].upper(),
            "%DDD_UC%": replacements["%DDD%"].upper(),
            "%DDDD_UC%": replacements["%DDDD%"].upper(),
            "%LDF_UC%": replacements["%LDF%"].upper(),
        }
    )
    for token, replacement in replacements.items():
        value = value.replace(token, replacement)
    return os.path.expandvars(value.replace("\\n", "\n"))


def open_action_target(action: Action) -> None:
    if action.type == "open_url":
        _open_url(action.value)
        return

    target = Path(action.value).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target

    if action.type == "open_file":
        if not target.is_file():
            raise ActionError(f"File does not exist: {target}")
        os.startfile(target)  # type: ignore[attr-defined]
        return

    if action.type == "open_folder":
        if not target.is_dir():
            raise ActionError(f"Folder does not exist: {target}")
        os.startfile(target)  # type: ignore[attr-defined]
        return

    if action.type == "launch_app":
        if not target.is_file() or target.suffix.casefold() != ".exe":
            raise ActionError(f"Application must be an existing .exe file: {target}")
        cwd = _resolve_working_directory(action.working_directory)
        subprocess.Popen([str(target), *action.arguments], cwd=cwd)
        return

    raise ActionError(f"Unsupported action type: {action.type}")


def _parse_action(item: object, index: int) -> Action:
    if not isinstance(item, dict):
        raise ActionError(f"Action #{index} must be an object.")

    required = ["id", "title", "context", "type", "value"]
    missing = [field for field in required if not isinstance(item.get(field), str)]
    if missing:
        raise ActionError(f"Action #{index} is missing text fields: {', '.join(missing)}")

    action_type = item["type"]
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise ActionError(f"Action #{index} has unsupported type: {action_type}")
    try:
        validate_action_value(action_type, item["value"])
    except ActionError as exc:
        raise ActionError(f"Action #{index}: {exc}") from exc

    state = item.get("state", "Draft")
    if not isinstance(state, str):
        raise ActionError(f"Action #{index} has an invalid state.")

    arguments = item.get("arguments", [])
    if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
        raise ActionError(f"Action #{index} has invalid arguments.")

    working_directory = item.get("working_directory")
    if working_directory is not None and not isinstance(working_directory, str):
        raise ActionError(f"Action #{index} has an invalid working directory.")

    technology = item.get("technology", "")
    task = item.get("task", "")
    if not isinstance(technology, str) or not isinstance(task, str):
        raise ActionError(f"Action #{index} has invalid technology or task metadata.")

    return Action(
        id=item["id"],
        title=item["title"],
        context=item["context"],
        type=action_type,
        value=item["value"],
        state=state,
        arguments=tuple(arguments),
        working_directory=working_directory,
        technology=technology,
        task=task,
    )


def _ensure_unique_action_ids(actions: Iterable[Action], path: Path) -> None:
    seen: dict[str, str] = {}
    for action in actions:
        key = action.id.casefold()
        if key in seen:
            raise ActionError(
                f"Action IDs must be unique in {path}: {seen[key]} and {action.id}"
            )
        seen[key] = action.id


def _load_action_data(path: Path) -> dict[str, list[object]]:
    if not path.exists():
        return {"actions": []}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActionError(f"Action file is not valid JSON: {path}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("actions"), list):
        raise ActionError("Action file must contain an 'actions' list.")
    return raw


def _action_to_dict(action: Action) -> dict[str, object]:
    data: dict[str, object] = {
        "id": action.id,
        "title": action.title,
        "context": action.context,
        "type": action.type,
        "value": action.value,
        "state": action.state,
    }
    if action.arguments:
        data["arguments"] = list(action.arguments)
    if action.working_directory:
        data["working_directory"] = action.working_directory
    if action.technology:
        data["technology"] = action.technology
    if action.task:
        data["task"] = action.task
    return data


def _open_url(value: str) -> None:
    validate_http_url(value)
    webbrowser.open(value)


def _resolve_working_directory(value: str | None) -> str | None:
    if value is None:
        return None

    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_dir():
        raise ActionError(f"Working directory does not exist: {path}")
    return str(path)
