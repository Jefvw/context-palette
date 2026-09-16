"""Opt-in drop routing; a trigger never grants authority to a changed Action."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Iterable

from .actions import (
    ACTIVE_STATE,
    CLIPBOARD_TEMPLATE_TOKENS,
    Action,
    ActionError,
    validate_action_value,
    validate_text_transform,
)
from .excel_automation import EXCEL_AUTOMATION_ID


@dataclass(frozen=True)
class DropActionSettings:
    mode: str = "show"
    action_id: str = ""
    action_fingerprint: str = ""


@dataclass(frozen=True)
class DropActionEligibility:
    eligible: bool
    effect: str = ""
    reason: str = ""


@dataclass(frozen=True)
class DropActionResolution:
    action: Action | None = None
    reason: str = ""
    effect: str = "Show dropped content in Context Palette."


def drop_action_fingerprint(action: Action) -> str:
    """Bind explicit approval to the exact reviewed record, not just its ID."""
    payload = json.dumps(
        {
            field: getattr(action, field)
            for field in ("id", "title", "state", "type", "value", "arguments", "working_directory")
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def drop_action_eligibility(action: Action) -> DropActionEligibility:
    if action.state != ACTIVE_STATE:
        return DropActionEligibility(False, reason="Only Active Actions can run on drop.")
    try:
        validate_action_value(action.type, action.value, inspect_external_paths=False)
        if action.type == "transform_text":
            validate_text_transform(action.value, action.arguments)
    except ActionError as exc:
        return DropActionEligibility(False, reason=f"Invalid Action: {exc}")

    if action.type in {"transform_text", "transform_list_csv", "transform_slashes"}:
        return DropActionEligibility(
            True,
            "Transform the dropped text; show the result in Input / Output and copy it to the clipboard.",
        )
    if action.type == "build_url_selection_open":
        return DropActionEligibility(
            True,
            "Build a URL from the dropped text, copy it to the clipboard, and open it in the browser.",
        )
    if action.type == "send_files_to_folder":
        if action.arguments or action.working_directory:
            return DropActionEligibility(False, reason="Send files accepts a destination folder only.")
        return DropActionEligibility(
            True,
            f"Copy dropped files to {action.value}. Originals stay unchanged. "
            "Conflict-free copies start automatically; existing name conflicts use "
            "the Send-to review, with overwrite off by default. No automatic rollback.",
        )
    if action.type == "excel_automation":
        if action.value == EXCEL_AUTOMATION_ID:
            return DropActionEligibility(
                True,
                "Use dropped workbook paths to open Excel CSV export review. Files are written only after its existing confirmation.",
            )
        return DropActionEligibility(
            False, reason="Live Excel Actions choose open workbooks, not dropped input. Run them from the Palette.",
        )
    if action.type == "save_edge_score_pdf":
        return DropActionEligibility(
            False, reason="Score PDF uses the Edge window captured with F9, not dropped input. Run it from the Palette.",
        )
    if action.type in {"workspace_template", "ai_prompt", "open_url", "open_folder"}:
        if not any(token in action.value for token in CLIPBOARD_TEMPLATE_TOKENS):
            return DropActionEligibility(False, reason="This Action does not consume dropped input. Use a supported input placeholder first.")
        effect = {
            "workspace_template": "Fill the template with dropped text; show it in Input / Output and copy it to the clipboard.",
            "ai_prompt": "Fill the prompt with dropped text; show it in Input / Output and copy it. It is not submitted to AI.",
            "open_url": "Fill the website address with dropped text and open it in the browser.",
            "open_folder": "Fill the folder path with dropped text and open the resulting folder in Explorer.",
        }[action.type]
        return DropActionEligibility(True, effect)
    reasons = {
        "copy_text": "Saved-text paste uses a captured destination. Drop must not paste into an unrelated application.",
        "paste_credential": "Credential paste requires a fresh captured destination and must be run manually.",
        "sequence": "Sequences do not accept dropped input and must retain their manual step review.",
        "transform_file_text": "This Action reads its configured file, not dropped input.",
        "build_url_open": "This Action asks for separate input. Choose the selection-based URL builder for drops.",
        "open_file": "Opening a dropped file can run an associated script. Use the Palette to open it manually.",
        "open_windows_target": "Arbitrary Windows targets can execute code and are not enabled for drop execution.",
        "launch_app": "Application launching is not enabled for drop execution.",
    }
    return DropActionEligibility(False, reason=reasons.get(action.type, "This Action type is not enabled for dropped-input execution."))


def approve_drop_action(action: Action) -> DropActionSettings:
    eligibility = drop_action_eligibility(action)
    if not eligibility.eligible:
        raise ActionError(eligibility.reason)
    return DropActionSettings("action", action.id, drop_action_fingerprint(action))


def resolve_drop_action(
    settings: DropActionSettings, actions: Iterable[Action],
) -> DropActionResolution:
    if settings.mode == "show":
        return DropActionResolution()
    if settings.mode != "action":
        return DropActionResolution(reason="Unknown drop behaviour. Choose it again in Drop settings.")
    matches = [action for action in actions if action.id.casefold() == settings.action_id.casefold()]
    if len(matches) != 1:
        return DropActionResolution(reason="The configured drop Action is missing or ambiguous. Choose it again in Drop settings.")
    action = matches[0]
    eligibility = drop_action_eligibility(action)
    if not eligibility.eligible:
        return DropActionResolution(reason=eligibility.reason)
    if action.id != settings.action_id or drop_action_fingerprint(action) != settings.action_fingerprint:
        return DropActionResolution(reason="The configured drop Action changed since approval. Review and save it again in Drop settings.")
    return DropActionResolution(action, effect=eligibility.effect)


def parse_drop_action_settings(raw: object) -> DropActionSettings:
    if not isinstance(raw, dict):
        raise ActionError("Palette drop settings must be an object.")
    if set(raw) - {"mode", "action_id", "action_fingerprint"}:
        raise ActionError("Palette drop settings contain unknown fields.")
    mode = raw.get("mode", "show")
    action_id = raw.get("action_id", "")
    fingerprint = raw.get("action_fingerprint", "")
    if mode not in ("show", "action") or not isinstance(action_id, str) or not isinstance(fingerprint, str):
        raise ActionError("Palette drop settings require a supported mode and text Action identity.")
    if mode == "show":
        if action_id or fingerprint:
            raise ActionError("Show-only drop settings cannot grant Action authority.")
    elif not action_id.strip() or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ActionError("Run-on-drop requires an exact Action ID and approval fingerprint.")
    return DropActionSettings(mode, action_id, fingerprint)


def drop_action_settings_data(settings: DropActionSettings) -> dict[str, str]:
    data = asdict(settings)
    parse_drop_action_settings(data)
    return data
