from __future__ import annotations

from dataclasses import dataclass

from .actions import Action
from .action_types import ACTION_TYPES
from .workspace_transforms import WORKSPACE_TRANSFORMS


_CLIPBOARD_TOKENS = (
    "%CLIPBOARD%",
    "%CLIPBOARD_URL%",
    "%pptxt%",
    "%cpy_txt_urlencode%",
)


@dataclass(frozen=True)
class ActionPreview:
    """Structured, side-effect-free explanation of one Action."""

    input_text: str
    effect_text: str
    details: tuple[tuple[str, str], ...]
    limitations: str

    @property
    def summary(self) -> str:
        return format_preview_summary(self.input_text, self.effect_text)

    def full_text(self, action: Action) -> str:
        definition = ACTION_TYPES[action.type]
        sections = [
            action.display_text,
            f"Type\n{definition.display_label}",
        ]
        if action.description:
            sections.append(f"Description\n{action.description}")
        sections.extend(
            (
                f"Input\n{self.input_text}",
                f"Effect\n{self.effect_text}",
            )
        )
        sections.extend(f"{label}\n{value}" for label, value in self.details)
        sections.append(f"Recovery / limitations\n{self.limitations}")
        return "\n\n".join(sections)


def build_action_preview(
    action: Action,
    *,
    workspace_has_text: bool = False,
    captured_selection_available: bool = False,
    destination_available: bool = False,
) -> ActionPreview:
    """Describe current Action input and effect without reading runtime data."""

    definition = ACTION_TYPES[action.type]
    configured_input = _configured_input(action)
    details = _configured_details(action)
    limitations = definition.portability

    if action.type == "copy_text":
        effect = (
            "paste into the captured app; clipboard fallback"
            if destination_available
            else "copy to the clipboard for manual paste"
        )
        return ActionPreview(
            _saved_content_input(action, "saved text"),
            effect,
            details,
            limitations,
        )
    if action.type == "workspace_template":
        return ActionPreview(
            _saved_content_input(action, "saved template"),
            "replace Input / Output and copy the template",
            details,
            limitations,
        )
    if action.type == "ai_prompt":
        return ActionPreview(
            _saved_content_input(action, "saved prompt"),
            "load the prompt into Input / Output and copy it; nothing is submitted",
            details,
            limitations,
        )
    if action.type == "open_url":
        return ActionPreview(
            configured_input,
            f"open website: {compact_preview_value(action.value)}",
            details,
            limitations,
        )
    if action.type == "open_windows_target":
        return ActionPreview(
            configured_input,
            "open or run the configured Windows target; may execute code and is not sandboxed",
            details,
            limitations,
        )
    if action.type == "open_file":
        return ActionPreview(
            configured_input,
            f"open file: {compact_preview_value(action.value)}",
            details,
            limitations,
        )
    if action.type == "open_folder":
        return ActionPreview(
            configured_input,
            f"open folder: {compact_preview_value(action.value)}",
            details,
            limitations,
        )
    if action.type == "launch_app":
        return ActionPreview(
            configured_input,
            f"start application: {compact_preview_value(action.value)}",
            details,
            limitations,
        )
    if action.type == "paste_credential":
        if not destination_available:
            return ActionPreview(
                "needed: a fresh hotkey destination is missing",
                "Run will stop without changes",
                details,
                limitations,
            )
        return ActionPreview(
            "Credential Manager + captured destination",
            "confirm, paste, then clear the protected clipboard",
            details,
            limitations,
        )
    if action.type == "build_url_open":
        return ActionPreview(
            "an ID you enter",
            "copy the built URL and open it",
            details,
            limitations,
        )
    if action.type == "build_url_selection_open":
        if workspace_has_text:
            runtime_input = "Input / Output"
        elif captured_selection_available:
            runtime_input = "captured selection"
        else:
            runtime_input = "text clipboard fallback, checked on Run"
        return ActionPreview(
            runtime_input,
            "copy the built URL and open it",
            details,
            limitations,
        )
    if action.type == "transform_file_text":
        return ActionPreview(
            "configured text file",
            "show and copy a reviewed result; source unchanged until explicit replacement",
            details,
            limitations,
        )
    if action.type == "transform_list_csv":
        return ActionPreview(
            "Input / Output" if workspace_has_text else "Input / Output (currently empty)",
            "replace the field with a comma list and copy it",
            details,
            limitations,
        )
    if action.type == "transform_text":
        return _workspace_transform_preview(
            details,
            limitations,
            workspace_has_text=workspace_has_text,
            effect="transform, replace the field, and copy the result",
        )
    if action.type == "transform_slashes":
        return _workspace_transform_preview(
            details,
            limitations,
            workspace_has_text=workspace_has_text,
            effect="convert slashes, replace the field, and copy the result",
        )
    raise ValueError(f"Unsupported Action preview type: {action.type}")


def _workspace_transform_preview(
    details: tuple[tuple[str, str], ...],
    limitations: str,
    *,
    workspace_has_text: bool,
    effect: str,
) -> ActionPreview:
    if not workspace_has_text:
        return ActionPreview(
            "needed: Input / Output is empty",
            "Run will stop without changes",
            details,
            limitations,
        )
    return ActionPreview("Input / Output", effect, details, limitations)


def _configured_input(action: Action) -> str:
    values = [action.value, *action.arguments]
    if action.working_directory:
        values.append(action.working_directory)
    return (
        "text clipboard variables in the configured value"
        if any(token in value for value in values for token in _CLIPBOARD_TOKENS)
        else "none"
    )


def _saved_content_input(action: Action, label: str) -> str:
    return (
        f"{label} + text clipboard variables"
        if _configured_input(action) != "none"
        else label
    )


def _configured_details(action: Action) -> tuple[tuple[str, str], ...]:
    if action.type == "copy_text":
        return (("Saved content", action.value),)
    if action.type == "workspace_template":
        return (("Saved template", action.value),)
    if action.type == "ai_prompt":
        return (("Saved prompt", action.value),)
    if action.type in {"open_url", "build_url_open", "build_url_selection_open"}:
        return (("Configured URL", action.value),)
    if action.type == "open_windows_target":
        label = "Configured Windows target"
    elif action.type == "open_file":
        label = "Configured file"
    elif action.type == "open_folder":
        label = "Configured folder"
    elif action.type == "launch_app":
        label = "Configured application"
    elif action.type == "paste_credential":
        return (("Credential target", action.value),)
    elif action.type == "transform_file_text":
        details: list[tuple[str, str]] = [("Configured text file", action.value)]
        if action.arguments:
            transform = WORKSPACE_TRANSFORMS.get(action.arguments[0])
            details.append(
                (
                    "Operation",
                    transform.label.rstrip("…") if transform else "Unavailable",
                )
            )
            if transform is not None:
                details.extend(
                    (label, value or "(empty)")
                    for label, value in zip(
                        transform.parameter_labels,
                        action.arguments[1:],
                    )
                )
        return tuple(details)
    elif action.type == "transform_text":
        transform = WORKSPACE_TRANSFORMS.get(action.value)
        details = [
            (
                "Operation",
                transform.label.rstrip("…") if transform else "Unavailable",
            )
        ]
        if transform is not None:
            details.extend(
                (label, value or "(empty)")
                for label, value in zip(transform.parameter_labels, action.arguments)
            )
        return tuple(details)
    elif action.type == "transform_list_csv":
        mode = (
            "Quoted SQL strings"
            if action.value == "sql_strings"
            else "Comma-separated values"
        )
        return (("Operation", mode),)
    elif action.type == "transform_slashes":
        direction = "/ to \\" if action.value == "forward_to_back" else "\\ to /"
        return (("Operation", f"Convert {direction}"),)
    else:
        return (("Configured value", action.value),)

    details = [(label, action.value)]
    if action.arguments:
        details.append(("Arguments", "\n".join(action.arguments)))
    if action.working_directory:
        details.append(("Working folder", action.working_directory))
    return tuple(details)


def compact_preview_value(value: str, limit: int = 64) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def format_preview_summary(
    input_text: str,
    effect_text: str,
    *,
    limit: int = 220,
) -> str:
    summary = f"Input: {input_text} → Effect: {effect_text}"
    if len(summary) <= limit:
        return summary
    return summary[: limit - 1].rstrip() + "…"
