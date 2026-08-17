"""Pure validation and previewing for constrained reference-based Action sequences.

This module deliberately accepts action-shaped objects rather than importing the
application Action model.  Sequence execution and persistence remain outside
this reference model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


MIN_STEPS = 2
MAX_STEPS = 12
MIN_ACTION_STEPS = 2
MIN_WAIT_MILLISECONDS = 100
MAX_WAIT_MILLISECONDS = 10_000
MAX_TOTAL_WAIT_MILLISECONDS = 30_000
ALLOWED_ACTION_TYPES = frozenset(
    {
        "open_url",
        "open_file",
        "open_folder",
        "launch_app",
        "open_windows_target",
    }
)
_CLIPBOARD_TOKENS = ("%CLIPBOARD%", "%CLIPBOARD_URL%", "%pptxt%", "%cpy_txt_urlencode%")


class ActionSequenceError(ValueError):
    """Raised when a sequence is not a safe, bounded reference plan."""


class ActionLike(Protocol):
    id: str
    title: str
    type: str
    value: str
    state: str
    arguments: tuple[str, ...]
    working_directory: str | None
    sequence_steps: tuple[SequenceStep, ...]


@dataclass(frozen=True)
class SequenceStep:
    """One persisted reference or delay, with no executable command payload."""

    kind: str
    action_id: str = ""
    milliseconds: int = 0


@dataclass(frozen=True)
class ResolvedActionStep:
    action_id: str
    title: str
    action_type: str
    value: str
    arguments: tuple[str, ...]
    working_directory: str | None = None


@dataclass(frozen=True)
class ResolvedWaitStep:
    milliseconds: int


ResolvedSequenceStep = ResolvedActionStep | ResolvedWaitStep


@dataclass(frozen=True)
class SequenceRunPlan:
    steps: tuple[ResolvedSequenceStep, ...]
    preview_lines: tuple[str, ...]


def parse_sequence_steps(raw: object) -> tuple[SequenceStep, ...]:
    """Parse only the constrained persisted step shapes; resolve later."""

    if not isinstance(raw, list):
        raise ActionSequenceError("Sequence steps must be a list.")
    steps: list[SequenceStep] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ActionSequenceError(f"Step {index} must be an object.")
        kind = item.get("kind")
        if kind == "action":
            if set(item) != {"kind", "action_id"}:
                raise ActionSequenceError(f"Step {index} action has unsupported fields.")
            action_id = item.get("action_id")
            if not isinstance(action_id, str):
                raise ActionSequenceError(f"Step {index} Action ID must be text.")
            steps.append(SequenceStep(kind, action_id=action_id))
        elif kind == "wait":
            if set(item) != {"kind", "milliseconds"}:
                raise ActionSequenceError(f"Step {index} wait has unsupported fields.")
            milliseconds = item.get("milliseconds")
            if isinstance(milliseconds, bool) or not isinstance(milliseconds, int):
                raise ActionSequenceError(f"Step {index} wait must use whole milliseconds.")
            steps.append(SequenceStep(kind, milliseconds=milliseconds))
        else:
            raise ActionSequenceError(f"Step {index} has unsupported kind: {kind!r}")
    return tuple(steps)


def sequence_steps_to_data(steps: tuple[SequenceStep, ...]) -> list[dict[str, object]]:
    """Return the minimal, portable persisted representation of validated shapes."""

    return [
        {"kind": "action", "action_id": step.action_id}
        if step.kind == "action"
        else {"kind": "wait", "milliseconds": step.milliseconds}
        if step.kind == "wait"
        else _unsupported_step_data(step)
        for step in steps
    ]


def sequence_reference_ids(steps: tuple[SequenceStep, ...]) -> tuple[str, ...]:
    """Return reference IDs in user-defined order without resolving them."""

    return tuple(step.action_id for step in steps if step.kind == "action")


def dependent_sequences(
    actions: Iterable[ActionLike],
    action_id: str,
    *,
    include_archived: bool,
) -> tuple[ActionLike, ...]:
    key = action_id.casefold()
    return tuple(
        action
        for action in actions
        if action.type == "sequence"
        and action.id.casefold() != key
        and (include_archived or action.state != "Archived")
        and any(
            reference.casefold() == key
            for reference in sequence_reference_ids(action.sequence_steps)  # type: ignore[attr-defined]
        )
    )


def resolve_sequence_steps(
    steps: tuple[SequenceStep, ...],
    actions: Iterable[ActionLike],
    *,
    sequence_id: str = "",
) -> SequenceRunPlan:
    """Validate references against live Actions and return an immutable run plan.

    No action is executed and no storage is read or written here.
    """

    if not MIN_STEPS <= len(steps) <= MAX_STEPS:
        raise ActionSequenceError(
            f"A sequence must contain {MIN_STEPS} to {MAX_STEPS} steps."
        )

    actions_by_id: dict[str, ActionLike] = {}
    for action in actions:
        action_id = _nonblank_action_id(action.id, "Referenced Action")
        key = action_id.casefold()
        if key in actions_by_id:
            raise ActionSequenceError(f"Duplicate Action ID in the live list: {action_id}")
        actions_by_id[key] = action

    owner_key = sequence_id.strip().casefold() if sequence_id else None
    action_count = 0
    total_wait = 0
    resolved: list[ResolvedSequenceStep] = []
    previous_was_wait = False

    for index, step in enumerate(steps, start=1):
        if step.kind == "action":
            reference_id = _nonblank_action_id(step.action_id, f"Step {index} Action ID")
            if owner_key is not None and reference_id.casefold() == owner_key:
                raise ActionSequenceError(f"Step {index} cannot reference this sequence itself.")
            action = actions_by_id.get(reference_id.casefold())
            if action is None:
                raise ActionSequenceError(f"Step {index} references a missing Action: {reference_id}")
            if action.state == "Archived":
                raise ActionSequenceError(f"Step {index} references an Archived Action: {action.title}")
            if action.type == "sequence":
                raise ActionSequenceError(f"Step {index} cannot reference another sequence.")
            if action.type not in ALLOWED_ACTION_TYPES:
                raise ActionSequenceError(
                    f"Step {index} references unsupported Action type: {action.type}"
                )
            configured_values = (
                action.value,
                *action.arguments,
                action.working_directory or "",
            )
            if any(
                token in value
                for value in configured_values
                for token in _CLIPBOARD_TOKENS
            ):
                raise ActionSequenceError(
                    f"Step {index} depends on clipboard input and cannot run in a sequence."
                )
            resolved.append(
                ResolvedActionStep(
                    action_id=action.id,
                    title=action.title,
                    action_type=action.type,
                    value=action.value,
                    arguments=tuple(action.arguments),
                    working_directory=action.working_directory,
                )
            )
            action_count += 1
            previous_was_wait = False
            continue

        if step.kind == "wait":
            if not MIN_WAIT_MILLISECONDS <= step.milliseconds <= MAX_WAIT_MILLISECONDS:
                raise ActionSequenceError(
                    f"Step {index} wait must be {MIN_WAIT_MILLISECONDS} to "
                    f"{MAX_WAIT_MILLISECONDS} ms."
                )
            if index == 1 or index == len(steps) or previous_was_wait:
                raise ActionSequenceError("Wait steps cannot be leading, trailing, or adjacent.")
            total_wait += step.milliseconds
            if total_wait > MAX_TOTAL_WAIT_MILLISECONDS:
                raise ActionSequenceError(
                    f"Total wait cannot exceed {MAX_TOTAL_WAIT_MILLISECONDS} ms."
                )
            resolved.append(ResolvedWaitStep(step.milliseconds))
            previous_was_wait = True
            continue

        raise ActionSequenceError(f"Step {index} has an unsupported shape.")

    if action_count < MIN_ACTION_STEPS:
        raise ActionSequenceError(
            f"A sequence must reference at least {MIN_ACTION_STEPS} Actions."
        )
    resolved_steps = tuple(resolved)
    return SequenceRunPlan(resolved_steps, _preview_lines(resolved_steps))


def _preview_lines(steps: tuple[ResolvedSequenceStep, ...]) -> tuple[str, ...]:
    """Return side-effect-free, human-readable lines for resolved live Actions."""

    lines: list[str] = []
    for number, step in enumerate(steps, start=1):
        if isinstance(step, ResolvedWaitStep):
            lines.append(f"{number}. Wait {step.milliseconds} ms")
            continue
        type_label = {
            "open_url": "Open website",
            "open_file": "Open file",
            "open_folder": "Open folder",
            "launch_app": "Launch application",
            "open_windows_target": "Open Windows target",
        }[step.action_type]
        arguments = (
            " | Arguments: " + ", ".join(repr(argument) for argument in step.arguments)
            if step.arguments
            else ""
        )
        lines.append(
            f"{number}. {type_label}: {step.title} | Target: {step.value}{arguments}"
        )
    return tuple(lines)


def _unsupported_step_data(step: SequenceStep) -> dict[str, object]:
    raise ActionSequenceError(f"Unsupported sequence step kind: {step.kind!r}")


def _nonblank_action_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionSequenceError(f"{label} must be nonblank.")
    return value.strip()
