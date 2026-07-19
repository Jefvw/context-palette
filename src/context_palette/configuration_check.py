from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from .actions import Action, ActionError, load_combined_actions
from .cheatsheets import CheatSheetError, load_cheatsheets
from .command_surface import (
    CommandGroup,
    CommandSurfaceError,
    command_item_action_ids,
    load_combined_command_groups,
)
from .contexts import ContextDefinition, ContextError, load_combined_contexts
from .inbox import InboxError, load_inbox_items
from .palette_state import PaletteState, load_palette_state


@dataclass(frozen=True)
class ConfigurationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    counts: dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_project_configuration(root: Path) -> ConfigurationReport:
    data = root / "data"
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}

    actions: list[Action] = []
    contexts: list[ContextDefinition] = []
    groups: list[CommandGroup] = []
    palette = PaletteState()

    try:
        actions, _local_ids = load_combined_actions(
            data / "actions.json", data / "local_actions.json"
        )
        counts["actions"] = len(actions)
    except (ActionError, OSError) as exc:
        errors.append(f"Actions: {exc}")

    try:
        contexts = load_combined_contexts(
            data / "contexts.json", data / "local_contexts.json"
        )
        counts["contexts"] = len(contexts)
    except (ContextError, OSError) as exc:
        errors.append(f"Contexts: {exc}")

    try:
        groups = load_combined_command_groups(
            data / "command_surface.json", data / "local_command_surface.json"
        )
        counts["command_groups"] = len(groups)
    except (CommandSurfaceError, OSError) as exc:
        errors.append(f"Command surface: {exc}")

    try:
        palette = load_palette_state(data / "palette.json")
        counts["pinned_actions"] = len(palette.pinned_action_ids)
    except (ActionError, OSError) as exc:
        errors.append(f"Palette state: {exc}")

    try:
        counts["inbox_items"] = len(load_inbox_items(data / "inbox.json"))
    except (InboxError, OSError) as exc:
        errors.append(f"Inbox: {exc}")

    try:
        counts["cheatsheets"] = len(load_cheatsheets(data / "cheatsheets"))
    except (CheatSheetError, OSError) as exc:
        errors.append(f"Cheat sheets: {exc}")

    if actions:
        _validate_action_references(actions, contexts, groups, palette, errors)
    elif contexts or groups or palette.pinned_action_ids or palette.context_slots:
        warnings.append("Action references were not checked because actions could not be loaded.")

    return ConfigurationReport(tuple(errors), tuple(warnings), counts)


def _validate_action_references(
    actions: list[Action],
    contexts: list[ContextDefinition],
    groups: list[CommandGroup],
    palette: PaletteState,
    errors: list[str],
) -> None:
    action_ids = {action.id for action in actions}
    for context in contexts:
        for action_id in context.preferred_action_ids:
            if action_id not in action_ids:
                errors.append(
                    f"Context '{context.name}' references missing action: {action_id}"
                )
    for group in groups:
        for item in group.items:
            for action_id in command_item_action_ids(item):
                if action_id not in action_ids:
                    errors.append(
                        f"Command item '{group.label} / {item.label}' references missing action: "
                        f"{action_id}"
                    )
    for action_id in palette.pinned_action_ids:
        if action_id not in action_ids:
            errors.append(f"Pinned action is missing: {action_id}")
    for context, action_ids_for_context in (palette.context_slots or {}).items():
        for action_id in action_ids_for_context:
            if action_id not in action_ids:
                errors.append(
                    f"Palette context '{context}' references missing action: {action_id}"
                )


def format_configuration_report(report: ConfigurationReport) -> str:
    lines = ["Context Palette configuration check", "==================================="]
    for name, count in sorted(report.counts.items()):
        lines.append(f"{name.replace('_', ' ').title()}: {count}")
    if report.warnings:
        lines.append("\nWarnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    if report.errors:
        lines.append("\nErrors:")
        lines.extend(f"- {error}" for error in report.errors)
    else:
        lines.append("\nConfiguration is valid.")
    return "\n".join(lines)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    report = validate_project_configuration(root)
    print(format_configuration_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
