from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .actions import (
    Action,
    ActionError,
    LIVE_FORMAT_PROFILE_AUTOMATION_ID,
    LIVE_TEXT_CONVERSION_AUTOMATION_ID,
    action_uses_clipboard_template,
    build_url,
    expanded_action,
    list_to_comma_separated,
    transform_text,
    validate_action_value,
)
from .action_types import ACTION_TYPES
from .action_sequences import (
    ActionSequenceError,
    ResolvedActionStep,
    resolve_sequence_steps,
)
from .workspace_transforms import WORKSPACE_TRANSFORMS


_CLIPBOARD_TOKENS = (
    "%CLIPBOARD%",
    "%CLIPBOARD_URL%",
    "%pptxt%",
    "%cpy_txt_urlencode%",
)

_MAX_PREVIEW_INPUT = 100_000
_MAX_PREVIEW_RESULT = 1_000_000
_MAX_DISPLAY_VALUE = 20_000


@dataclass(frozen=True)
class ExecutionPreview:
    """Snapshot-only report, not an executable plan or permission to run."""

    title: str
    input_source: str
    input_value: str | None
    resolved_target: str
    effect_text: str
    recovery_text: str
    output_text: str | None = None
    details: tuple[tuple[str, str], ...] = ()
    notices: tuple[str, ...] = ()

    def full_text(self) -> str:
        sections = [
            self.title,
            "Preview only — nothing has been run or changed.",
            f"Input source\n{self.input_source}",
        ]
        if self.input_value is not None:
            sections.append(f"Input snapshot\n{_display_snapshot(self.input_value)}")
        sections.extend((
            f"Resolved target / destination\n{_display_snapshot(self.resolved_target)}",
            f"Effect on Run\n{self.effect_text}",
            f"Recovery on Run\n{self.recovery_text}",
        ))
        if self.output_text is not None:
            sections.append(f"Computed result\n{_display_snapshot(self.output_text)}")
        sections.extend(
            f"{label}\n{_display_snapshot(value)}" for label, value in self.details
        )
        if self.notices:
            sections.append("Notes\n" + "\n".join(self.notices))
        sections.append(
            "This is a snapshot, not a reservation. Run uses current input and "
            "rechecks its normal requirements and confirmations."
        )
        report = "\n\n".join(sections)
        if len(report) > 32_768:
            return report[:32_600] + "\n\n[Preview display truncated. Nothing was run or changed; Run still uses current input.]"
        return report


def build_execution_preview(
    action: Action,
    *,
    workspace_text: str = "",
    captured_selection: str | None = None,
    clipboard_text: str | None = None,
    destination_available: bool = False,
    available_actions: tuple[Action, ...] | list[Action] = (),
    now: datetime | None = None,
) -> ExecutionPreview:
    """Explain Run using explicit snapshots, never reading or changing runtime data.

    A missing clipboard snapshot is different from an empty text clipboard.
    Input follows LauncherApp._execute_action: whole workspace first for a
    selection URL; transforms use only the whole workspace. Credentials and
    external file/app/Excel contents are never read, even for Preview.
    """
    description = build_action_preview(
        action,
        workspace_has_text=bool(workspace_text),
        captured_selection_available=bool(captured_selection),
        destination_available=destination_available,
        available_actions=available_actions,
    )
    source = description.input_text
    input_value = None
    target = "Chosen when Run opens its existing review workflow"
    effect = description.effect_text
    recovery = description.limitations
    output = None
    details = description.details
    notices: list[str] = []
    try:
        if action.type in {"transform_text", "transform_slashes", "transform_list_csv"}:
            source, input_value = "Input / Output (complete field)", workspace_text
            target = "Input / Output and the clipboard"
            recovery = (
                "Input / Output Undo/history can restore prior text. Ordinary "
                "clipboard changes are not automatically restored."
            )
            if not workspace_text and action.type != "transform_list_csv":
                raise ActionError("The Input / Output field does not contain text.")
            _check_preview_size(workspace_text, action.arguments)
            output = (
                list_to_comma_separated(workspace_text, sql_strings=action.value == "sql_strings")
                if action.type == "transform_list_csv"
                else transform_text(workspace_text, action.value, arguments=action.arguments)
            )
        elif action.type == "build_url_selection_open":
            if workspace_text:
                source, input_value = "Input / Output (complete field)", workspace_text
            elif captured_selection:
                source, input_value = "Captured selection", captured_selection
            else:
                source, input_value = "Text clipboard snapshot", clipboard_text
            target = "URL not resolved"
            recovery = "No automatic rollback; close the opened browser page if needed. Prior clipboard text is not restored."
            if input_value is None:
                raise ActionError("Clipboard text is unavailable; no URL was computed.")
            _check_preview_size(input_value, (action.value,))
            output = build_url(action.value, input_value)
            target = output
        elif action.type == "build_url_open":
            source = "An ID entered in the Run dialog (not yet supplied)"
            target = "URL not resolved — an ID is required"
            recovery = "No automatic rollback; close the opened browser page if needed. Prior clipboard text is not restored."
            notices.append("Preview does not prompt or substitute Input / Output for this Action's requested ID.")
        elif action.type == "paste_credential":
            source = "Windows Credential Manager (secret not read)"
            target = "Captured destination app" if destination_available else "No fresh captured destination"
            recovery = "Run confirms before pasting and conditionally restores prior plain-text clipboard content; pasted text itself cannot be rolled back."
            notices.append("Preview shows only the credential target reference, never retrieves or displays a password.")
        elif action.type == "sequence":
            source = "None — references to configured Actions"
            target = "The referenced targets listed below"
            recovery = "Stop remaining prevents later steps; already-opened targets are not rolled back. No automatic retry."
            notices.append("Run still requires the complete sequence confirmation. Target availability is not checked by Preview.")
        elif action.type == "send_files_to_folder":
            source, input_value = "Input / Output (exact file paths)", workspace_text
            _check_template_preview_size(action, "")
            resolved = expanded_action(action, now=now)
            validate_action_value(resolved.type, resolved.value, inspect_external_paths=False)
            target = resolved.value
            details = _configured_details(resolved)
            recovery = "Source files stay unchanged. Stop remaining prevents later copies; completed copies and replacements have no automatic rollback."
            notices.append("Preview does not inspect or copy files. Run checks every path and prepares the exact copy plan; name conflicts open the existing Send-to review.")
        elif action.type == "excel_automation":
            if action.value not in {LIVE_FORMAT_PROFILE_AUTOMATION_ID, LIVE_TEXT_CONVERSION_AUTOMATION_ID}:
                source, input_value = "Input / Output (exact workbook paths)", workspace_text
            notices.append("Preview does not start the Excel engine or inspect workbooks. Run provides the exact workbook/output review and existing confirmations.")
        elif action.type == "transform_file_text":
            target = action.value
            recovery = "Run prepares a reviewable result without changing the source. Source replacement is a separate explicit operation."
            notices.append("The configured file is not read by this Preview. Run checks availability and computes its bounded file result.")
        else:
            needs_clipboard = action_uses_clipboard_template(action)
            source = "Text clipboard snapshot + configured value" if needs_clipboard else "Configured value"
            input_value = clipboard_text if needs_clipboard else None
            target = "Configured target not resolved"
            if needs_clipboard and clipboard_text is None:
                raise ActionError("Clipboard text is unavailable; template variables were not substituted.")
            _check_template_preview_size(action, (clipboard_text or "") if needs_clipboard else "")
            resolved = expanded_action(action, clipboard_getter=lambda: clipboard_text or "", now=now)
            # Lexical validation only: no filesystem probes, app discovery or IO.
            validate_action_value(resolved.type, resolved.value, inspect_external_paths=False)
            details = _configured_details(resolved)
            effect = build_action_preview(resolved, destination_available=destination_available).effect_text
            if action.type in {"copy_text", "workspace_template", "ai_prompt"}:
                output = resolved.value
                target = (
                    "Captured destination app and clipboard"
                    if action.type == "copy_text" and destination_available
                    else "Clipboard"
                    if action.type == "copy_text"
                    else "Input / Output and clipboard"
                )
                recovery = "Ordinary clipboard changes are not automatically restored. Input / Output changes can be recovered through Undo/history; pasting into another app has no automatic rollback."
            else:
                target = resolved.value
                recovery = "No automatic rollback for opened or launched targets. Any effects of the destination application are outside Context Palette."
                notices.append("Template variables are resolved; filesystem availability, path selection, and Windows associations are checked only on Run.")
        if output is not None and len(output) > _MAX_PREVIEW_RESULT:
            output = None
            notices.append("Computed result exceeds the Preview limit; it is not displayed.")
    except (ActionError, ValueError) as exc:
        output = None
        notices.append(f"Preview could not compute a result: {exc}")
    return ExecutionPreview(
        title=action.title,
        input_source=source,
        input_value=input_value,
        resolved_target=target,
        effect_text=effect,
        recovery_text=recovery,
        output_text=output,
        details=details,
        notices=tuple(notices),
    )


def _check_preview_size(value: str, arguments: tuple[str, ...] = ()) -> None:
    if len(value) > _MAX_PREVIEW_INPUT or any(len(item) > _MAX_PREVIEW_INPUT for item in arguments):
        raise ActionError("Input exceeds the Preview limit; Run remains unchanged.")
    # Conservative bound for parameterized replacement/line-affix operations.
    if (len(value) + 1) * (1 + sum(map(len, arguments))) > _MAX_PREVIEW_RESULT:
        raise ActionError("Possible result exceeds the Preview limit; Run remains unchanged.")


def _check_template_preview_size(action: Action, clipboard: str) -> None:
    values = (action.value, *action.arguments, action.working_directory or "")
    if len(clipboard) > _MAX_PREVIEW_INPUT or sum(map(len, values)) > _MAX_PREVIEW_INPUT:
        raise ActionError("Input exceeds the Preview limit; Run remains unchanged.")
    token_count = sum(value.count(token) for value in values for token in _CLIPBOARD_TOKENS)
    if token_count * len(clipboard) * 12 + sum(map(len, values)) > _MAX_PREVIEW_RESULT:
        raise ActionError("Possible template expansion exceeds the Preview limit; Run remains unchanged.")


def _display_snapshot(value: str) -> str:
    if len(value) > _MAX_DISPLAY_VALUE:
        return value[:_MAX_DISPLAY_VALUE] + f"\n[Display truncated; {len(value):,} characters total]"
    return value if value else "(empty)"


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
    available_actions: tuple[Action, ...] | list[Action] = (),
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
    if action.type == "send_files_to_folder":
        return ActionPreview(
            "exact file paths from Input / Output" if workspace_has_text else "needed: file paths in Input / Output",
            "copy files to the configured folder; conflict-free copies start automatically, name conflicts open Send-to review",
            details,
            "Source files stay unchanged. Overwrite is off by default; completed copies or explicit replacements have no automatic rollback.",
        )
    if action.type == "excel_automation":
        if action.value == LIVE_FORMAT_PROFILE_AUTOMATION_ID:
            return ActionPreview(
                "open Excel workbooks, then one worksheet or all visible worksheets you choose",
                "apply Standard data formatting directly; Excel is not saved or closed",
                details,
                (
                    "Changes the open workbook directly, may clear Excel Undo, "
                    "has no recovery or rollback. AutoSave must be off. Context "
                    "Palette never saves or closes Excel."
                ),
            )
        if action.value == LIVE_TEXT_CONVERSION_AUTOMATION_ID:
            return ActionPreview(
                "an already-open .xlsx workbook, exact worksheet, and physical columns you review",
                (
                    "plan selected scientific-notation and numeric cells, create "
                    "and verify a reviewed recovery copy, then convert eligible "
                    "cells to text"
                ),
                details,
                (
                    "Development/UAT workflow. Execute is disabled unless its "
                    "startup feature flag is enabled. Excel may already have lost "
                    "digits beyond its numeric precision; the engine never saves "
                    "or closes Excel."
                ),
            )
        csv_limitations = (
            "Source workbooks stay unchanged. Overwrite is off by default; "
            "checked replacements have no recovery backup or batch rollback."
        )
        if not workspace_has_text:
            return ActionPreview(
                "needed: exact .xlsx paths in Input / Output",
                "Run will stop without changes",
                details,
                csv_limitations,
            )
        return ActionPreview(
            "exact .xlsx paths from Input / Output",
            "plan exact CSV create or replace effects, show every output for review, then export only after confirmation",
            details,
            csv_limitations,
        )
    if action.type == "sequence":
        try:
            plan = resolve_sequence_steps(
                action.sequence_steps,
                available_actions,
                sequence_id=action.id,
            )
        except ActionSequenceError as exc:
            return ActionPreview(
                "needed: every sequence Action must be available",
                "Run will stop without changes",
                (*details, ("Sequence issue", str(exc))),
                limitations,
            )
        action_count = sum(
            isinstance(step, ResolvedActionStep) for step in plan.steps
        )
        wait_count = len(plan.steps) - action_count
        return ActionPreview(
            "none",
            f"start {action_count} Actions in order with {wait_count} bounded wait(s); no rollback",
            (*details, ("Steps", "\n".join(plan.preview_lines))),
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
            "confirm, paste, then restore prior clipboard text",
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
    elif action.type in {"open_folder", "send_files_to_folder"}:
        label = "Configured folder"
    elif action.type == "launch_app":
        label = "Configured application"
    elif action.type == "excel_automation":
        label = {
            LIVE_FORMAT_PROFILE_AUTOMATION_ID: "Apply Excel format template",
            LIVE_TEXT_CONVERSION_AUTOMATION_ID: (
                "UAT: Convert scientific-notation columns"
            ),
        }.get(action.value, "Export Excel files to CSV")
        return (("Automation", label),)
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
