from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Iterable
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4
import webbrowser

from .persistence import atomic_write_json
from .action_types import ACTION_TYPES, SUPPORTED_ACTION_TYPES
from .workspace_transforms import WORKSPACE_TRANSFORMS


ACTIVE_STATE = "Active"
ARCHIVED_STATE = "Archived"
VISIBLE_STATES = {ACTIVE_STATE}
LEGACY_ACTIVE_STATES = {"Draft", "Trusted"}
class ActionError(Exception):
    """Raised when an action cannot be loaded or executed safely."""


@dataclass(frozen=True)
class Action:
    id: str
    title: str
    context: str
    type: str
    value: str
    state: str = ACTIVE_STATE
    arguments: tuple[str, ...] = ()
    working_directory: str | None = None
    technology: str = ""
    task: str = ""
    contexts: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    description: str = ""

    @property
    def effective_contexts(self) -> tuple[str, ...]:
        source = self.contexts or ((self.context,) if self.context else ())
        return normalize_contexts(source)

    @property
    def effective_tags(self) -> tuple[str, ...]:
        return normalize_tags((*self.tags, self.technology, self.task))

    def belongs_to_context(self, context: str) -> bool:
        if context.strip().casefold() == "general":
            return True
        key = context.strip().casefold()
        return any(item.casefold() == key for item in self.effective_contexts)

    @property
    def display_text(self) -> str:
        parts = [*self.effective_contexts, *self.effective_tags, self.title]
        return " > ".join(dict.fromkeys(parts))

    @property
    def compact_display_text(self) -> str:
        title = self.title.strip()
        commands = ("Open", "Copy", "Convert", "Search", "Arrange", "Restore")
        for command in commands:
            prefix = command + " "
            if title.casefold().startswith(prefix.casefold()):
                title = title[len(prefix):].strip()
                break
        return f"{ACTION_TYPES[self.type].icon} {title}"


def normalize_contexts(values: Iterable[str]) -> tuple[str, ...]:
    """Return distinct specific contexts; General is the implicit root."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        key = clean.casefold()
        if not clean or key == "general" or key in seen:
            continue
        seen.add(key)
        normalized.append(clean)
    return tuple(normalized)


def normalize_tags(values: Iterable[str]) -> tuple[str, ...]:
    """Return distinct lower-case tags suitable for filtering and persistence."""
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(value.strip().split()).casefold()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    return tuple(normalized)


def validate_context_memberships(
    values: Iterable[str],
    available_contexts: Iterable[str],
) -> tuple[str, ...]:
    """Return canonical specific contexts or reject undefined memberships."""
    contexts = normalize_contexts(values)
    canonical_by_key = {
        context.strip().casefold(): context.strip()
        for context in available_contexts
        if context.strip() and context.strip().casefold() != "general"
    }
    unknown = [
        context
        for context in contexts
        if context.casefold() not in canonical_by_key
    ]
    if unknown:
        label = "context" if len(unknown) == 1 else "contexts"
        raise ActionError(
            f"Unknown specific {label}: {', '.join(unknown)}. "
            "Create the context first or correct its name. "
            "Leave this field empty for General only."
        )
    return tuple(canonical_by_key[context.casefold()] for context in contexts)


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


def copy_text_action(
    *,
    title: str,
    context: str,
    value: str,
    technology: str = "",
    task: str = "",
    contexts: Iterable[str] = (),
    tags: Iterable[str] = (),
    description: str = "",
) -> Action:
    clean_title = title.strip()
    clean_contexts = normalize_contexts((*contexts, context))
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    if not clean_value:
        raise ActionError("Action text cannot be empty.")

    return Action(
        id=f"action-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_contexts[0] if clean_contexts else "General",
        type="copy_text",
        value=clean_value,
        state=ACTIVE_STATE,
        technology=technology.strip(),
        task=task.strip(),
        contexts=clean_contexts,
        tags=normalize_tags(tags),
        description=description.strip(),
    )


def open_url_action(
    *,
    title: str,
    context: str,
    value: str,
    technology: str = "",
    task: str = "",
    contexts: Iterable[str] = (),
    tags: Iterable[str] = (),
    description: str = "",
) -> Action:
    clean_title = title.strip()
    clean_contexts = normalize_contexts((*contexts, context))
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    validate_http_url(clean_value, label="Action URL")
    return Action(
        id=f"action-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_contexts[0] if clean_contexts else "General",
        type="open_url",
        value=clean_value,
        state=ACTIVE_STATE,
        technology=technology.strip(),
        task=task.strip(),
        contexts=clean_contexts,
        tags=normalize_tags(tags),
        description=description.strip(),
    )


def build_url_action(
    *,
    title: str,
    context: str,
    template: str,
    action_type: str = "build_url_selection_open",
    technology: str = "",
    task: str = "",
    contexts: Iterable[str] = (),
    tags: Iterable[str] = (),
    description: str = "",
) -> Action:
    allowed_types = {"build_url_copy", "build_url_open", "build_url_selection_open"}
    if action_type not in allowed_types:
        raise ActionError("Unsupported URL-builder action type.")
    clean_title = title.strip()
    clean_contexts = normalize_contexts((*contexts, context))
    clean_template = template.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    build_url(clean_template, "example")
    return Action(
        id=f"action-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_contexts[0] if clean_contexts else "General",
        type=action_type,
        value=clean_template,
        state=ACTIVE_STATE,
        technology=technology.strip(),
        task=task.strip(),
        contexts=clean_contexts,
        tags=normalize_tags(tags),
        description=description.strip(),
    )


def configured_action(
    *,
    title: str,
    context: str,
    action_type: str,
    value: str,
    technology: str = "",
    task: str = "",
    contexts: Iterable[str] = (),
    tags: Iterable[str] = (),
    arguments: Iterable[str] = (),
    working_directory: str = "",
    description: str = "",
) -> Action:
    """Create a validated active action from the built-in action catalogue."""
    clean_title = title.strip()
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise ActionError(f"Unsupported action type: {action_type}")
    validate_action_value(action_type, clean_value)
    clean_contexts = normalize_contexts((*contexts, context))

    clean_arguments = (
        tuple(arguments)
        if action_type == "transform_text"
        else tuple(argument.strip() for argument in arguments if argument.strip())
    )
    if action_type == "transform_text":
        validate_text_transform(clean_value, clean_arguments)

    return Action(
        id=f"action-{uuid4().hex[:12]}",
        title=clean_title,
        context=clean_contexts[0] if clean_contexts else "General",
        type=action_type,
        value=clean_value,
        state=ACTIVE_STATE,
        arguments=clean_arguments,
        working_directory=working_directory.strip() or None,
        technology=technology.strip(),
        task=task.strip(),
        contexts=clean_contexts,
        tags=normalize_tags(tags),
        description=description.strip(),
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
    contexts: Iterable[str] = (),
    tags: Iterable[str] = (),
    arguments: Iterable[str] = (),
    working_directory: str = "",
    description: str = "",
) -> Action:
    """Validate edits while preserving an action's stable identity and maturity."""
    validated = configured_action(
        title=title,
        context=context,
        action_type=action_type,
        value=value,
        technology=technology,
        task=task,
        contexts=contexts,
        tags=tags,
        arguments=arguments,
        working_directory=working_directory,
        description=description,
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
        contexts=validated.contexts,
        tags=validated.tags,
        description=validated.description,
    )


def edited_copy_text_action(
    action: Action,
    *,
    title: str,
    context: str = "General",
    value: str,
    contexts: Iterable[str] = (),
    tags: Iterable[str] = (),
    description: str | None = None,
) -> Action:
    if action.type != "copy_text":
        raise ActionError("This editor supports saved-text actions only.")

    clean_title = title.strip()
    clean_contexts = normalize_contexts((*contexts, context))
    clean_value = value.strip()
    if not clean_title:
        raise ActionError("Action title cannot be empty.")
    if not clean_value:
        raise ActionError("Action text cannot be empty.")

    return Action(
        id=action.id,
        title=clean_title,
        context=clean_contexts[0] if clean_contexts else "General",
        type=action.type,
        value=clean_value,
        state=action.state,
        arguments=action.arguments,
        working_directory=action.working_directory,
        contexts=clean_contexts,
        tags=normalize_tags(tags),
        description=action.description if description is None else description.strip(),
    )


def action_search_text(action: Action) -> str:
    """Return the canonical local search document for an action."""

    definition = ACTION_TYPES[action.type]
    contexts = action.effective_contexts or ("General",)
    return " ".join(
        (
            action.id,
            action.title,
            action.description,
            action.type,
            definition.label,
            definition.family,
            *contexts,
            *action.effective_tags,
            action.state,
            action.value,
            *action.arguments,
            action.working_directory or "",
        )
    )


def action_matches_search(
    action: Action,
    query: str,
    *,
    extra_terms: Iterable[str] = (),
) -> bool:
    """Return whether every query term occurs in canonical or supplied metadata."""

    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return True
    searchable = " ".join((action_search_text(action), *extra_terms)).casefold()
    return all(term in searchable for term in terms)


def search_actions(actions: Iterable[Action], query: str) -> list[Action]:
    return [
        action
        for action in actions
        if action_matches_search(action, query)
    ]


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
        if credential_paster is None:
            raise ActionError("Protected credential paste is unavailable.")
        return credential_paster(action)

    if action.type in {"workspace_template", "ai_prompt"}:
        expanded = expanded_action(action, clipboard_getter=clipboard_getter)
        if output_setter is not None:
            output_setter(expanded.value)
        if clipboard_setter is not None:
            clipboard_setter(expanded.value)
        return (
            "Loaded the AI prompt into Input / Output and copied it."
            if action.type == "ai_prompt"
            else "Loaded the template into Input / Output and copied it."
        )

    if action.type == "transform_list_csv":
        result = list_to_comma_separated(input_text or "", sql_strings=action.value == "sql_strings")
        if output_setter is not None:
            output_setter(result)
        if clipboard_setter is not None:
            clipboard_setter(result)
        return "Transformed the list and copied the result."

    if action.type == "transform_slashes":
        if not input_text:
            raise ActionError("The Input / Output field does not contain text.")
        result = transform_text(input_text, action.value)
        if output_setter is not None:
            output_setter(result)
        if clipboard_setter is not None:
            clipboard_setter(result)
        return "Converted path slashes and copied the result."

    if action.type == "transform_text":
        if not input_text:
            raise ActionError("The Input / Output field does not contain text.")
        result = transform_text(
            input_text,
            action.value,
            arguments=action.arguments,
        )
        if output_setter is not None:
            output_setter(result)
        if clipboard_setter is not None:
            clipboard_setter(result)
        return "Transformed Input / Output and copied the result."

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
            Action(
                action.id,
                action.title,
                action.context,
                "open_url",
                url,
                action.state,
                contexts=action.contexts,
                tags=action.tags,
                description=action.description,
            )
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
            Action(
                action.id,
                action.title,
                action.context,
                "open_url",
                url,
                action.state,
                contexts=action.contexts,
                tags=action.tags,
                description=action.description,
            )
        )
        return "Opened the built URL."

    expanded = expanded_action(action, clipboard_getter=clipboard_getter)
    if action.type == "copy_text":
        if clipboard_setter is None:
            raise ActionError("No clipboard is available for copying text.")
        clipboard_setter(expanded.value)
        return "Copied text to the clipboard."

    if action.type in {
        "open_url",
        "open_windows_target",
        "open_file",
        "open_folder",
        "launch_app",
    }:
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


def validate_windows_target(value: str) -> None:
    """Reject only values Windows cannot receive as a ShellExecute target."""
    if len(value) > 32_767:
        raise ActionError("Windows target is too long.")
    if "\x00" in value:
        raise ActionError("Windows target cannot contain a null character.")


def validate_text_transform(operation: str, arguments: tuple[str, ...] = ()) -> None:
    definition = WORKSPACE_TRANSFORMS.get(operation)
    if definition is None:
        raise ActionError("Choose a supported text operation.")
    required = len(definition.parameter_labels)
    if len(arguments) != required:
        raise ActionError(
            f"{definition.label} requires {required} parameter"
            f"{'s' if required != 1 else ''}."
        )
    if required and operation != "literal_replace" and not arguments[0]:
        raise ActionError(f"{definition.parameter_labels[0]} cannot be empty.")
    if operation == "literal_replace" and not arguments[0]:
        raise ActionError("Find cannot be empty.")


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
    elif action_type == "open_windows_target":
        validate_windows_target(clean_value)
    elif action_type == "transform_text":
        if clean_value not in WORKSPACE_TRANSFORMS:
            raise ActionError("Choose a supported text operation.")
    elif action_type == "paste_credential":
        validate_credential_target(clean_value)
    elif action_type in {"build_url_copy", "build_url_open", "build_url_selection_open"}:
        build_url(clean_value, "example")
    elif action_type == "transform_list_csv" and clean_value not in {"csv", "sql_strings"}:
        raise ActionError("List conversion must use csv or sql_strings.")
    elif action_type == "transform_slashes" and clean_value not in {
        "forward_to_back",
        "back_to_forward",
    }:
        raise ActionError(
            "Slash conversion must use forward_to_back or back_to_forward."
        )


def list_to_comma_separated(value: str, *, sql_strings: bool = False) -> str:
    items = [line.strip() for line in value.splitlines() if line.strip()]
    if not items:
        raise ActionError("The Input / Output field does not contain a list.")
    if sql_strings:
        items = [f"'{item.replace(chr(39), chr(39) * 2)}'" for item in items]
    return ", ".join(items)


def list_to_sql_values(value: str) -> str:
    """Format separated values as a parenthesized SQL value list."""
    items = [
        item.strip()
        for item in re.split(r"[\r\n\t,;]+", value)
        if item.strip()
    ]
    if not items:
        raise ActionError("The Input / Output field does not contain SQL values.")

    numeric_pattern = re.compile(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z"
    )
    formatted: list[str] = []
    for item in items:
        if numeric_pattern.fullmatch(item):
            formatted.append(item)
        elif item.casefold() == "null":
            formatted.append("NULL")
        else:
            formatted.append(f"'{item.replace(chr(39), chr(39) * 2)}'")
    return f"({', '.join(formatted)})"


def transform_text(
    value: str,
    operation: str,
    *,
    prefix: str = "",
    suffix: str = "",
    arguments: tuple[str, ...] = (),
) -> str:
    """Apply a constrained, previewable transformation to workspace text."""
    if operation == "lowercase":
        return value.lower()
    if operation == "uppercase":
        return value.upper()
    if operation == "proper_case":
        return re.sub(
            r"[^\W_]+(?:'[^\W_]+)?",
            lambda match: match.group(0)[:1].upper() + match.group(0)[1:].lower(),
            value,
        )
    if operation == "sentence_case":
        return _sentence_case(value)
    if operation == "invert_case":
        return value.swapcase()
    if operation == "normalize_spaces":
        return re.sub(r"[ \t]+", " ", value)
    if operation == "trim_lines":
        return _transform_line_bodies(value, lambda line: line.strip(" \t"))
    if operation == "collapse_blank_lines":
        return _collapse_blank_lines(value)
    if operation == "literal_replace":
        validate_text_transform(operation, arguments)
        return value.replace(arguments[0], arguments[1])
    if operation == "keep_lines_containing":
        validate_text_transform(operation, arguments)
        needle = arguments[0].casefold()
        return _filter_and_join_lines(value, lambda line: needle in line.casefold())
    if operation == "remove_lines_containing":
        validate_text_transform(operation, arguments)
        needle = arguments[0].casefold()
        return _filter_and_join_lines(value, lambda line: needle not in line.casefold())
    if operation == "prefix_suffix_lines":
        return _affix_each_line(value, prefix, suffix)
    if operation == "remove_blank_lines":
        return _filter_and_join_lines(
            value,
            lambda line: bool(line.strip(" \t")),
        )
    if operation == "sort_lines_ascending":
        return _reorder_lines(value, lambda lines: sorted(lines, key=str.casefold))
    if operation == "sort_lines_descending":
        return _reorder_lines(
            value,
            lambda lines: sorted(lines, key=str.casefold, reverse=True),
        )
    if operation == "join_lines":
        return re.sub(r"\r\n|\r|\n", " ", value)
    if operation == "split_delimiter":
        validate_text_transform(operation, arguments)
        delimiter = _decoded_delimiter(arguments[0])
        return _line_separator(value).join(value.split(delimiter))
    if operation == "join_delimiter":
        validate_text_transform(operation, arguments)
        return _decoded_delimiter(arguments[0]).join(value.splitlines())
    if operation == "sql_values":
        return list_to_sql_values(value)
    if operation == "remove_consecutive_duplicate_lines":
        return _remove_consecutive_duplicate_lines(value)
    if operation == "remove_duplicate_lines":
        return _remove_duplicate_lines(value)
    if operation == "forward_to_back":
        return value.replace("/", "\\")
    if operation == "back_to_forward":
        return value.replace("\\", "/")
    if operation in {
        "camel_case",
        "pascal_case",
        "snake_case",
        "screaming_snake_case",
        "kebab_case",
        "readable_words",
    }:
        return _transform_line_bodies(
            value,
            lambda line: _convert_naming_style(line, operation),
        )
    if operation in {"json_pretty", "json_minify"}:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ActionError(
                f"JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        if operation == "json_pretty":
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    if operation == "url_encode":
        return quote(value, safe="")
    if operation == "url_decode":
        return unquote(value)
    if operation == "sql_escape_quotes":
        return value.replace("'", "''")
    if operation == "path_to_file_uri":
        return _windows_path_to_file_uri(value)
    if operation == "file_uri_to_path":
        return _file_uri_to_windows_path(value)
    raise ActionError(f"Unsupported text transformation: {operation}")


def _sentence_case(value: str) -> str:
    result: list[str] = []
    capitalize_next = True
    for character in value.lower():
        if capitalize_next and character.isalpha():
            result.append(character.upper())
            capitalize_next = False
        else:
            result.append(character)
        if character in ".!?":
            capitalize_next = True
    return "".join(result)


def _decoded_delimiter(value: str) -> str:
    decoded = value.replace("\\t", "\t").replace("\\r", "\r").replace("\\n", "\n")
    if not decoded:
        raise ActionError("Delimiter cannot be empty.")
    return decoded


def _collapse_blank_lines(value: str) -> str:
    lines = value.splitlines()
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = blank
    return _join_reordered_lines(value, collapsed)


def _identifier_words(value: str) -> list[str]:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", separated)
    return re.findall(r"[A-Za-z0-9]+", separated)


def _convert_naming_style(value: str, operation: str) -> str:
    words = _identifier_words(value)
    if not words:
        return value
    lowered = [word.lower() for word in words]
    if operation == "camel_case":
        return lowered[0] + "".join(word.capitalize() for word in lowered[1:])
    if operation == "pascal_case":
        return "".join(word.capitalize() for word in lowered)
    if operation == "snake_case":
        return "_".join(lowered)
    if operation == "screaming_snake_case":
        return "_".join(lowered).upper()
    if operation == "kebab_case":
        return "-".join(lowered)
    readable = [
        word if word.isupper() and len(word) > 1 else word.lower()
        for word in words
    ]
    readable[0] = readable[0] if readable[0].isupper() else readable[0].capitalize()
    return " ".join(readable)


def _windows_path_to_file_uri(value: str) -> str:
    path = value.strip().strip('"')
    if path.startswith("\\\\"):
        parts = path[2:].replace("\\", "/").split("/", 1)
        if len(parts) != 2 or not all(parts):
            raise ActionError("Enter a complete UNC path such as \\\\server\\share\\file.")
        return f"file://{parts[0]}/{quote(parts[1], safe='/')}"
    if not re.match(r"^[A-Za-z]:[\\/]", path):
        raise ActionError("Enter an absolute Windows drive or UNC path.")
    normalized = path.replace("\\", "/")
    return "file:///" + quote(normalized, safe="/:")


def _file_uri_to_windows_path(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme.casefold() != "file":
        raise ActionError("Enter a complete file: URI.")
    path = unquote(parsed.path)
    if parsed.netloc:
        return "\\\\" + parsed.netloc + path.replace("/", "\\")
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    if not re.match(r"^[A-Za-z]:/", path):
        raise ActionError("The file URI does not contain a Windows drive or UNC path.")
    return path.replace("/", "\\")


def _transform_line_bodies(value: str, transform: Callable[[str], str]) -> str:
    transformed: list[str] = []
    for chunk in value.splitlines(keepends=True):
        body = chunk.rstrip("\r\n")
        ending = chunk[len(body) :]
        transformed.append(transform(body) + ending)
    return "".join(transformed)


def _affix_each_line(value: str, prefix: str, suffix: str) -> str:
    if not value:
        return value
    return _transform_line_bodies(value, lambda line: prefix + line + suffix)


def _line_separator(value: str) -> str:
    return "\r\n" if "\r\n" in value else "\r" if "\r" in value else "\n"


def _join_reordered_lines(value: str, lines: list[str]) -> str:
    if not lines:
        return ""
    separator = _line_separator(value)
    result = separator.join(lines)
    if value.endswith(("\r", "\n")):
        result += separator
    return result


def _filter_and_join_lines(
    value: str,
    keep: Callable[[str], bool],
) -> str:
    return _join_reordered_lines(
        value,
        [line for line in value.splitlines() if keep(line)],
    )


def _reorder_lines(
    value: str,
    reorder: Callable[[list[str]], list[str]],
) -> str:
    return _join_reordered_lines(value, reorder(value.splitlines()))


def _remove_consecutive_duplicate_lines(value: str) -> str:
    lines = value.splitlines()
    unique: list[str] = []
    for line in lines:
        if not unique or line != unique[-1]:
            unique.append(line)
    return _join_reordered_lines(value, unique)


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
    return _join_reordered_lines(value, unique)


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
        contexts=action.contexts,
        tags=action.tags,
        description=action.description,
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
    if action.type == "open_windows_target":
        validate_windows_target(action.value)
        target = action.value.strip()
        if len(target) >= 2 and target[0] == target[-1] == '"':
            target = target[1:-1]
        local_target = _existing_local_target_path(action.value)
        if local_target is not None:
            target = str(local_target)
        arguments = (
            subprocess.list2cmdline(action.arguments) if action.arguments else None
        )
        cwd = _resolve_working_directory(action.working_directory)
        try:
            os.startfile(  # type: ignore[attr-defined]
                target,
                "open",
                arguments,
                cwd,
            )
        except OSError as exc:
            raise ActionError(
                "Windows could not open or run this target. Check that the path "
                "exists or that an application is registered for the target."
            ) from exc
        return

    if action.type == "open_file":
        target = _resolve_local_path(action.value, Path.is_file)
        if not target.is_file():
            raise ActionError(f"File does not exist: {target}")
        os.startfile(target)  # type: ignore[attr-defined]
        return

    if action.type == "open_folder":
        target = _resolve_local_path(action.value, Path.is_dir)
        if not target.is_dir():
            raise ActionError(f"Folder does not exist: {target}")
        os.startfile(target)  # type: ignore[attr-defined]
        return

    if action.type == "launch_app":
        target = _resolve_local_path(action.value, Path.is_file)
        if not target.is_file() or target.suffix.casefold() != ".exe":
            raise ActionError(f"Application must be an existing .exe file: {target}")
        cwd = _resolve_working_directory(action.working_directory)
        subprocess.Popen([str(target), *action.arguments], cwd=cwd)
        return

    raise ActionError(f"Unsupported action type: {action.type}")


def _parse_action(item: object, index: int) -> Action:
    if not isinstance(item, dict):
        raise ActionError(f"Action #{index} must be an object.")

    required = ["id", "title", "type", "value"]
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

    state = item.get("state", ACTIVE_STATE)
    if not isinstance(state, str):
        raise ActionError(f"Action #{index} has an invalid state.")
    if state in LEGACY_ACTIVE_STATES:
        state = ACTIVE_STATE
    if state not in {ACTIVE_STATE, ARCHIVED_STATE}:
        raise ActionError(
            f"Action #{index} has unsupported state: {state}. "
            f"Use {ACTIVE_STATE} or {ARCHIVED_STATE}."
        )

    arguments = item.get("arguments", [])
    if not isinstance(arguments, list) or not all(isinstance(arg, str) for arg in arguments):
        raise ActionError(f"Action #{index} has invalid arguments.")
    if action_type == "transform_text":
        try:
            validate_text_transform(item["value"], tuple(arguments))
        except ActionError as exc:
            raise ActionError(f"Action #{index}: {exc}") from exc

    working_directory = item.get("working_directory")
    if working_directory is not None and not isinstance(working_directory, str):
        raise ActionError(f"Action #{index} has an invalid working directory.")

    technology = item.get("technology", "")
    task = item.get("task", "")
    if not isinstance(technology, str) or not isinstance(task, str):
        raise ActionError(f"Action #{index} has invalid technology or task metadata.")
    legacy_context = item.get("context", "General")
    if not isinstance(legacy_context, str):
        raise ActionError(f"Action #{index} has invalid context metadata.")
    raw_contexts = item.get("contexts", [])
    if not isinstance(raw_contexts, list) or not all(
        isinstance(value, str) for value in raw_contexts
    ):
        raise ActionError(f"Action #{index} has invalid contexts metadata.")
    raw_tags = item.get("tags", [])
    if not isinstance(raw_tags, list) or not all(
        isinstance(value, str) for value in raw_tags
    ):
        raise ActionError(f"Action #{index} has invalid tags metadata.")
    description = item.get("description", "")
    if not isinstance(description, str):
        raise ActionError(f"Action #{index} has an invalid description.")
    contexts = normalize_contexts(raw_contexts)
    primary_context = contexts[0] if contexts else legacy_context.strip() or "General"

    return Action(
        id=item["id"],
        title=item["title"],
        context=primary_context,
        type=action_type,
        value=item["value"],
        state=state,
        arguments=tuple(arguments),
        working_directory=working_directory,
        technology=technology,
        task=task,
        contexts=contexts,
        tags=normalize_tags(raw_tags),
        description=description.strip(),
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
        "type": action.type,
        "value": action.value,
        "state": action.state,
    }
    if action.arguments:
        data["arguments"] = list(action.arguments)
    if action.working_directory:
        data["working_directory"] = action.working_directory
    if action.effective_contexts:
        data["contexts"] = list(action.effective_contexts)
    if action.effective_tags:
        data["tags"] = list(action.effective_tags)
    if action.description:
        data["description"] = action.description
    return data


def _open_url(value: str) -> None:
    validate_http_url(value)
    webbrowser.open(value)


def _resolve_working_directory(value: str | None) -> str | None:
    if value is None:
        return None

    path = _resolve_local_path(value, Path.is_dir)
    if not path.is_dir():
        raise ActionError(f"Working directory does not exist: {path}")
    return str(path)


def _local_path_candidates(value: str) -> tuple[Path, ...]:
    """Return literal-first local path candidates."""

    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] == '"':
        clean = clean[1:-1]
    parsed = urlparse(clean)
    values = (
        (_file_uri_to_windows_path(clean),)
        if parsed.scheme.casefold() == "file"
        else tuple(dict.fromkeys((clean, unquote(clean))))
    )
    paths: list[Path] = []
    for item in values:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def _resolve_local_path(
    value: str,
    predicate: Callable[[Path], bool],
) -> Path:
    candidates = _local_path_candidates(value)
    for candidate in candidates:
        if predicate(candidate):
            return candidate
    return candidates[-1]


def _existing_local_target_path(value: str) -> Path | None:
    clean = value.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] == '"':
        clean = clean[1:-1]
    parsed = urlparse(clean)
    is_drive_path = bool(re.match(r"^[A-Za-z]:[\\/]", clean))
    is_absolute_path = (
        is_drive_path
        or clean.startswith("\\\\")
        or Path(clean).is_absolute()
    )
    if parsed.scheme and parsed.scheme.casefold() != "file" and not is_drive_path:
        return None
    if not parsed.scheme and not is_absolute_path:
        return None
    return next(
        (candidate for candidate in _local_path_candidates(value) if candidate.exists()),
        None,
    )
