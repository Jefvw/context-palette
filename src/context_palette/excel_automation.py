"""Isolated process boundary for reviewed Python Excel automations.

This module deliberately contains no Tk code and no workbook implementation.
It validates machine-local host configuration, builds the versioned JSON
requests owned by Python Excel, and delivers immutable process outcomes for the
launcher to present on the main thread.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from types import MappingProxyType
from typing import Callable, Literal, Mapping

from .persistence import atomic_write_json


SCHEMA_VERSION = "1.0"
AUTOMATION_CONTRACT_VERSION = "1.0"
EXCEL_AUTOMATION_ID = "excel.export_workbooks_to_csv"
EXCEL_AUTOMATION_VERSION = "1.0"
DESCRIBE_OPERATION = "describe_automations"
PLAN_OPERATION = "plan_automation"
EXECUTE_OPERATION = "execute_automation"
OPERATION_VERSION = "1.0"
MAX_WORKBOOKS = 100
MAX_REQUEST_BYTES = 1024 * 1024
DEFAULT_MAX_STDOUT_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_STDERR_BYTES = 256 * 1024

AutomationPhase = Literal["describe", "plan", "execute"]
CallClassification = Literal[
    "start_failed",
    "outer_error",
    "describe_succeeded",
    "describe_failed",
    "plan_needs_parameters",
    "plan_blocked",
    "plan_ready",
    "plan_failed",
    "execute_succeeded",
    "execute_failed_before_effect",
    "execute_failed_after_partial_effect",
    "execute_unknown",
]


class ExcelAutomationError(ValueError):
    """Local Excel automation input or configuration is invalid."""


class ExcelAutomationSettingsError(ExcelAutomationError):
    """Machine-local Python Excel settings could not be interpreted."""


class ExcelAutomationInputError(ExcelAutomationError):
    """Input / Output is not an exact supported workbook batch."""


@dataclass(frozen=True, slots=True)
class ExcelAutomationSettings:
    launcher_path: Path | None = None


def load_excel_automation_settings(path: Path) -> ExcelAutomationSettings:
    """Load an optional machine-local launcher path without probing it."""

    settings_path = Path(path)
    if not settings_path.exists():
        return ExcelAutomationSettings()
    try:
        document = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise ExcelAutomationSettingsError(
            "Excel automation settings could not be read."
        ) from exc
    if not isinstance(document, dict) or set(document) != {"launcher_path"}:
        raise ExcelAutomationSettingsError(
            "Excel automation settings must contain launcher_path text only."
        )
    value = document["launcher_path"]
    if not isinstance(value, str):
        raise ExcelAutomationSettingsError(
            "Excel automation launcher_path must be text."
        )
    clean = value.strip()
    if not clean:
        return ExcelAutomationSettings()
    launcher = Path(clean)
    _validate_launcher_path(launcher)
    return ExcelAutomationSettings(launcher)


def save_excel_automation_settings(
    path: Path,
    settings: ExcelAutomationSettings,
) -> None:
    launcher = settings.launcher_path
    if launcher is not None:
        _validate_launcher_path(Path(launcher))
    atomic_write_json(
        Path(path),
        {"launcher_path": str(launcher) if launcher is not None else ""},
    )


def _validate_launcher_path(path: Path) -> None:
    if not path.is_absolute():
        raise ExcelAutomationSettingsError(
            "The Python Excel launcher path must be absolute."
        )
    if path.suffix.casefold() != ".bat":
        raise ExcelAutomationSettingsError(
            "The Python Excel launcher must be a .bat file."
        )


def workbook_paths_from_workspace(value: str) -> tuple[Path, ...]:
    """Return 1-100 exact existing absolute .xlsx paths in workspace order."""

    if not isinstance(value, str):
        raise ExcelAutomationInputError("Input / Output must contain text paths.")
    raw_lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not raw_lines:
        raise ExcelAutomationInputError(
            "Input / Output does not contain an Excel workbook path."
        )
    if len(raw_lines) > MAX_WORKBOOKS:
        raise ExcelAutomationInputError(
            f"Choose no more than {MAX_WORKBOOKS} Excel workbooks."
        )

    paths: list[Path] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_lines, start=1):
        candidate = _strip_matching_quotes(raw)
        if not candidate or "\x00" in candidate:
            raise ExcelAutomationInputError(
                f"Workbook line {index} is not an exact usable path."
            )
        path = Path(candidate)
        if not path.is_absolute():
            raise ExcelAutomationInputError(
                f"Workbook line {index} must be an absolute path."
            )
        if path.suffix.casefold() != ".xlsx":
            raise ExcelAutomationInputError(
                f"Workbook line {index} must identify a .xlsx file."
            )
        if not path.is_file():
            raise ExcelAutomationInputError(
                f"Workbook line {index} does not identify an existing file."
            )
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ExcelAutomationInputError(
                f"Workbook line {index} could not be resolved."
            ) from exc
        key = os.path.normcase(str(resolved))
        if key in seen:
            raise ExcelAutomationInputError(
                f"Workbook line {index} duplicates an earlier workbook."
            )
        seen.add(key)
        paths.append(resolved)
    return tuple(paths)


def _strip_matching_quotes(value: str) -> str:
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'"}
    ):
        return value[1:-1].strip()
    return value


@dataclass(frozen=True, slots=True)
class AutomationWorkbookInput:
    input_id: str
    path: Path
    worksheet: str | None = None


@dataclass(frozen=True, slots=True)
class CsvAutomationInvocation:
    inputs: tuple[AutomationWorkbookInput, ...]
    output_directory: Path | None = None
    delimiter: str = ","
    encoding: str = "utf-8-sig"
    formula_mode: str = "formulas"
    excel_safe: bool = True

    def __post_init__(self) -> None:
        if not 1 <= len(self.inputs) <= MAX_WORKBOOKS:
            raise ExcelAutomationInputError(
                f"An Excel automation requires 1 through {MAX_WORKBOOKS} workbooks."
            )
        if len({item.input_id for item in self.inputs}) != len(self.inputs):
            raise ExcelAutomationInputError("Workbook input IDs must be unique.")
        if self.output_directory is not None and not self.output_directory.is_absolute():
            raise ExcelAutomationInputError("The output directory must be absolute.")


def csv_invocation(
    paths: tuple[Path, ...],
    *,
    output_directory: Path | None = None,
    worksheets: Mapping[str, str] | None = None,
) -> CsvAutomationInvocation:
    selections = worksheets or {}
    inputs = tuple(
        AutomationWorkbookInput(
            input_id=f"input-{index}",
            path=Path(path),
            worksheet=selections.get(f"input-{index}"),
        )
        for index, path in enumerate(paths, start=1)
    )
    return CsvAutomationInvocation(inputs, output_directory)


def build_describe_automations_request(request_id: str) -> dict[str, object]:
    return _request(
        request_id,
        DESCRIBE_OPERATION,
        {"contract_schema_version": AUTOMATION_CONTRACT_VERSION},
    )


def build_plan_automation_request(
    request_id: str,
    invocation: CsvAutomationInvocation,
) -> dict[str, object]:
    return _request(request_id, PLAN_OPERATION, _invocation_arguments(invocation))


def build_execute_automation_request(
    request_id: str,
    invocation: CsvAutomationInvocation,
    expected_plan_fingerprint: str,
) -> dict[str, object]:
    if not _is_sha256(expected_plan_fingerprint):
        raise ExcelAutomationInputError(
            "The reviewed plan fingerprint is not a valid SHA-256 value."
        )
    arguments = _invocation_arguments(invocation)
    arguments["expected_plan_fingerprint"] = expected_plan_fingerprint
    return _request(request_id, EXECUTE_OPERATION, arguments)


def _request(
    request_id: str,
    operation: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ExcelAutomationInputError(
            "The automation request ID must contain 1 through 128 characters."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "operation": operation,
        "operation_version": OPERATION_VERSION,
        "arguments": arguments,
    }


def _invocation_arguments(invocation: CsvAutomationInvocation) -> dict[str, object]:
    return {
        "automation_id": EXCEL_AUTOMATION_ID,
        "automation_version": EXCEL_AUTOMATION_VERSION,
        "inputs": [
            {
                "input_id": item.input_id,
                "kind": "closed_workbook_file",
                "path": str(item.path),
                "parameters": {
                    "worksheet": item.worksheet,
                    "physical_columns": None,
                },
            }
            for item in invocation.inputs
        ],
        "parameters": {
            "output_directory": (
                str(invocation.output_directory)
                if invocation.output_directory is not None
                else None
            ),
            "delimiter": invocation.delimiter,
            "encoding": invocation.encoding,
            "formula_mode": invocation.formula_mode,
            "excel_safe": invocation.excel_safe,
        },
    }


@dataclass(frozen=True, slots=True)
class AutomationCallError:
    code: str
    category: str
    message: str
    retryable: bool
    details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AutomationAvailability:
    automation_id: str
    automation_version: str
    available: bool
    supported_phases: tuple[str, ...]
    code: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class DescribeAutomationsResult:
    contract_schema_version: str
    automations: tuple[AutomationAvailability, ...]

    @property
    def csv_automation(self) -> AutomationAvailability | None:
        return next(
            (
                item
                for item in self.automations
                if item.automation_id == EXCEL_AUTOMATION_ID
                and item.automation_version == EXCEL_AUTOMATION_VERSION
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class PlanChoice:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class PlanRequirement:
    code: str
    message: str
    parameter_id: str
    input_id: str | None
    choices: tuple[PlanChoice, ...]
    choices_total: int
    choices_truncated: bool


@dataclass(frozen=True, slots=True)
class PlanBlocker:
    code: str
    message: str
    input_id: str | None
    path: str | None
    retryable: bool


@dataclass(frozen=True, slots=True)
class AutomationWarning:
    code: str
    message: str
    input_id: str | None


@dataclass(frozen=True, slots=True)
class PlannedWorkbook:
    input_id: str
    original_path: str
    resolved_path: str
    worksheet: str
    physical_columns: tuple[int, ...]
    rows_to_write: int
    output_path: str


@dataclass(frozen=True, slots=True)
class PlanEffect:
    mutates_inputs: bool
    output_policy: str
    input_files: int
    output_files: int
    rows_to_write: int


@dataclass(frozen=True, slots=True)
class AutomationArtifact:
    artifact_id: str
    kind: str
    path: str
    media_type: str | None
    input_id: str | None


@dataclass(frozen=True, slots=True)
class PlanAutomationResult:
    state: Literal["needs_parameters", "blocked", "ready"]
    requirements: tuple[PlanRequirement, ...]
    blockers: tuple[PlanBlocker, ...]
    inputs: tuple[PlannedWorkbook, ...]
    warnings: tuple[AutomationWarning, ...]
    effect: PlanEffect | None
    predicted_artifacts: tuple[AutomationArtifact, ...]
    plan_fingerprint: str | None
    writes_performed: int


@dataclass(frozen=True, slots=True)
class ExecutedWorkbook:
    input_id: str
    outcome: Literal["succeeded", "failed", "not_started"]
    code: str
    message: str
    source_path: str
    worksheet: str | None
    physical_columns: tuple[int, ...]
    output_path: str | None
    rows_written: int
    columns_written: int
    escaped_cells: int


@dataclass(frozen=True, slots=True)
class ExecuteAutomationResult:
    state: Literal[
        "succeeded", "failed_before_effect", "failed_after_partial_effect"
    ]
    reviewed_plan_fingerprint: str
    final_plan_fingerprint: str | None
    effects_started: bool
    writes_performed: int
    inputs: tuple[ExecutedWorkbook, ...]
    source_mutates_inputs: bool
    workbooks_saved: int
    outputs_created: tuple[str, ...]
    outputs_overwritten: int
    artifacts: tuple[AutomationArtifact, ...]
    warnings: tuple[AutomationWarning, ...]
    code: str
    message: str
    retryable: bool


AutomationResult = (
    DescribeAutomationsResult | PlanAutomationResult | ExecuteAutomationResult
)


@dataclass(frozen=True, slots=True)
class AutomationCallResult:
    phase: AutomationPhase
    classification: CallClassification
    process_started: bool
    return_code: int | None
    result: AutomationResult | None = None
    error: AutomationCallError | None = None
    diagnostic_present: bool = False
    reason: str = ""

    @property
    def unknown_outcome(self) -> bool:
        return self.classification == "execute_unknown"


class _ProtocolError(ValueError):
    pass


def parse_automation_response(
    *,
    phase: AutomationPhase,
    request_id: str,
    return_code: int,
    stdout: bytes,
    stderr: bytes = b"",
) -> AutomationCallResult:
    """Parse one completed child response and enforce request correlation."""

    try:
        document = _decode_envelope(stdout)
        operation = _operation_for_phase(phase)
        if document.get("schema_version") != SCHEMA_VERSION:
            raise _ProtocolError("The response schema version is unsupported.")
        if document.get("request_id") != request_id:
            raise _ProtocolError("The response request ID did not match.")
        if document.get("operation") != operation:
            raise _ProtocolError("The response operation did not match.")
        if document.get("operation_version") != OPERATION_VERSION:
            raise _ProtocolError("The response operation version did not match.")
        _nonnegative_int(document.get("duration_ms"), "duration_ms")
        _object(document.get("paths"), "paths")
        _array(document.get("warnings"), "warnings")
        status = document.get("status")
        if status == "error":
            if return_code == 0 or document.get("result") is not None:
                raise _ProtocolError("The error response contradicted its process status.")
            error = _parse_outer_error(document.get("error"))
            return AutomationCallResult(
                phase,
                "outer_error",
                True,
                return_code,
                error=error,
                diagnostic_present=bool(stderr),
            )
        if status != "success" or document.get("error") is not None:
            raise _ProtocolError("The response status was invalid.")
        if return_code != 0:
            raise _ProtocolError("The success response contradicted its exit code.")
        result_document = _object(document.get("result"), "result")
        result, classification = _parse_success_result(phase, result_document)
        return AutomationCallResult(
            phase,
            classification,
            True,
            return_code,
            result=result,
            diagnostic_present=bool(stderr),
        )
    except (UnicodeError, json.JSONDecodeError, _ProtocolError, ValueError) as exc:
        return _failed_protocol_result(phase, return_code, bool(stderr), str(exc))


def _decode_envelope(stdout: bytes) -> dict[str, object]:
    if not stdout:
        raise _ProtocolError("The process returned no JSON response.")
    text = stdout.decode("utf-8", errors="strict")
    decoder = json.JSONDecoder()
    document, end = decoder.raw_decode(text)
    if text[end:].strip():
        raise _ProtocolError("The process returned more than one JSON value.")
    return _object(document, "response")


def _parse_outer_error(value: object) -> AutomationCallError:
    document = _object(value, "error")
    details = _object(document.get("details"), "error.details")
    return AutomationCallError(
        _text(document.get("code"), "error.code"),
        _text(document.get("category"), "error.category"),
        _text(document.get("message"), "error.message"),
        _boolean(document.get("retryable"), "error.retryable"),
        MappingProxyType(dict(details)),
    )


def _parse_success_result(
    phase: AutomationPhase,
    document: dict[str, object],
) -> tuple[AutomationResult, CallClassification]:
    if phase == "describe":
        result = _parse_describe_result(document)
        return result, "describe_succeeded"
    if phase == "plan":
        result = _parse_plan_result(document)
        return result, {
            "needs_parameters": "plan_needs_parameters",
            "blocked": "plan_blocked",
            "ready": "plan_ready",
        }[result.state]
    result = _parse_execute_result(document)
    return result, {
        "succeeded": "execute_succeeded",
        "failed_before_effect": "execute_failed_before_effect",
        "failed_after_partial_effect": "execute_failed_after_partial_effect",
    }[result.state]


def _parse_describe_result(document: dict[str, object]) -> DescribeAutomationsResult:
    contract = _text(
        document.get("contract_schema_version"),
        "result.contract_schema_version",
    )
    if contract != AUTOMATION_CONTRACT_VERSION:
        raise _ProtocolError("The automation contract version is unsupported.")
    automations: list[AutomationAvailability] = []
    for index, raw in enumerate(_array(document.get("automations"), "automations")):
        item = _object(raw, f"automations[{index}]")
        availability = _object(item.get("availability"), "availability")
        phases = tuple(
            _text(value, "availability.supported_phases")
            for value in _array(
                availability.get("supported_phases"),
                "availability.supported_phases",
            )
        )
        automations.append(
            AutomationAvailability(
                _text(item.get("automation_id"), "automation_id"),
                _text(item.get("automation_version"), "automation_version"),
                _boolean(availability.get("available"), "availability.available"),
                phases,
                _optional_text(availability.get("code"), "availability.code"),
                _optional_text(availability.get("reason"), "availability.reason"),
            )
        )
    return DescribeAutomationsResult(contract, tuple(automations))


def _parse_plan_result(document: dict[str, object]) -> PlanAutomationResult:
    state = document.get("state")
    if state not in {"needs_parameters", "blocked", "ready"}:
        raise _ProtocolError("The plan result state is unsupported.")
    _validate_automation_identity(document.get("automation"))
    requirements = tuple(
        _parse_requirement(raw, index)
        for index, raw in enumerate(_array(document.get("requirements"), "requirements"))
    )
    blockers = tuple(
        _parse_blocker(raw, index)
        for index, raw in enumerate(_array(document.get("blockers"), "blockers"))
    )
    inputs = tuple(
        _parse_planned_workbook(raw, index)
        for index, raw in enumerate(_array(document.get("inputs"), "inputs"))
    )
    warnings = _parse_warnings(document.get("warnings"))
    raw_effect = document.get("effect")
    effect = None if raw_effect is None else _parse_effect(raw_effect)
    artifacts = _parse_artifacts(document.get("predicted_artifacts"))
    fingerprint = _optional_text(document.get("plan_fingerprint"), "plan_fingerprint")
    writes = _nonnegative_int(document.get("writes_performed"), "writes_performed")
    if writes != 0:
        raise _ProtocolError("Planning unexpectedly reported a write.")
    if state == "ready":
        if requirements or blockers or effect is None or not _is_sha256(fingerprint):
            raise _ProtocolError("The ready plan is incomplete or contradictory.")
    elif fingerprint is not None:
        raise _ProtocolError("A non-ready plan reported a fingerprint.")
    return PlanAutomationResult(
        state,  # type: ignore[arg-type]
        requirements,
        blockers,
        inputs,
        warnings,
        effect,
        artifacts,
        fingerprint,
        writes,
    )


def _parse_requirement(value: object, index: int) -> PlanRequirement:
    item = _object(value, f"requirements[{index}]")
    choices_document = _object(item.get("choices"), "requirement.choices")
    choices = tuple(
        PlanChoice(
            _text(_object(raw, "choice").get("value"), "choice.value"),
            _text(_object(raw, "choice").get("label"), "choice.label"),
        )
        for raw in _array(choices_document.get("items"), "choices.items")
    )
    returned = _nonnegative_int(choices_document.get("returned"), "choices.returned")
    if returned != len(choices):
        raise _ProtocolError("The requirement choice count is inconsistent.")
    return PlanRequirement(
        _text(item.get("code"), "requirement.code"),
        _text(item.get("message"), "requirement.message"),
        _text(item.get("parameter_id"), "requirement.parameter_id"),
        _optional_text(item.get("input_id"), "requirement.input_id"),
        choices,
        _nonnegative_int(choices_document.get("total"), "choices.total"),
        _boolean(choices_document.get("truncated"), "choices.truncated"),
    )


def _parse_blocker(value: object, index: int) -> PlanBlocker:
    item = _object(value, f"blockers[{index}]")
    return PlanBlocker(
        _text(item.get("code"), "blocker.code"),
        _text(item.get("message"), "blocker.message"),
        _optional_text(item.get("input_id"), "blocker.input_id"),
        _optional_text(item.get("path"), "blocker.path"),
        _boolean(item.get("retryable"), "blocker.retryable"),
    )


def _parse_planned_workbook(value: object, index: int) -> PlannedWorkbook:
    item = _object(value, f"inputs[{index}]")
    if item.get("kind") != "closed_workbook_file":
        raise _ProtocolError("The plan returned an unsupported input kind.")
    source_hash = _text(item.get("source_sha256"), "input.source_sha256")
    if not _is_sha256(source_hash):
        raise _ProtocolError("The plan returned an invalid source fingerprint.")
    _nonnegative_int(item.get("source_size_bytes"), "input.source_size_bytes")
    return PlannedWorkbook(
        _text(item.get("input_id"), "input.input_id"),
        _text(item.get("original_path"), "input.original_path"),
        _text(item.get("resolved_path"), "input.resolved_path"),
        _text(item.get("worksheet"), "input.worksheet"),
        _positive_int_tuple(item.get("physical_columns"), "input.physical_columns"),
        _nonnegative_int(item.get("rows_to_write"), "input.rows_to_write"),
        _text(item.get("output_path"), "input.output_path"),
    )


def _parse_effect(value: object) -> PlanEffect:
    item = _object(value, "effect")
    if item.get("effect_class") != "creates_output":
        raise _ProtocolError("The plan returned an unsupported effect class.")
    return PlanEffect(
        _boolean(item.get("mutates_inputs"), "effect.mutates_inputs"),
        _text(item.get("output_policy"), "effect.output_policy"),
        _nonnegative_int(item.get("input_files"), "effect.input_files"),
        _nonnegative_int(item.get("output_files"), "effect.output_files"),
        _nonnegative_int(item.get("rows_to_write"), "effect.rows_to_write"),
    )


def _parse_execute_result(document: dict[str, object]) -> ExecuteAutomationResult:
    state = document.get("state")
    if state not in {
        "succeeded",
        "failed_before_effect",
        "failed_after_partial_effect",
    }:
        raise _ProtocolError("The execution result state is unsupported.")
    _validate_automation_identity(document.get("automation"))
    reviewed = _text(
        document.get("reviewed_plan_fingerprint"),
        "reviewed_plan_fingerprint",
    )
    final = _optional_text(
        document.get("final_plan_fingerprint"),
        "final_plan_fingerprint",
    )
    if not _is_sha256(reviewed) or (final is not None and not _is_sha256(final)):
        raise _ProtocolError("Execution returned an invalid plan fingerprint.")
    inputs = tuple(
        _parse_executed_workbook(raw, index)
        for index, raw in enumerate(_array(document.get("inputs"), "inputs"))
    )
    source = _object(document.get("source_effect"), "source_effect")
    outputs = tuple(
        _text(value, "outputs_created")
        for value in _array(document.get("outputs_created"), "outputs_created")
    )
    writes = _nonnegative_int(document.get("writes_performed"), "writes_performed")
    effects_started = _boolean(document.get("effects_started"), "effects_started")
    overwritten = _nonnegative_int(
        document.get("outputs_overwritten"), "outputs_overwritten"
    )
    if overwritten != 0 or writes != len(outputs):
        raise _ProtocolError("Execution output counts are contradictory.")
    if state == "succeeded" and (not effects_started or not outputs):
        raise _ProtocolError("Successful execution reported no effect.")
    if state == "failed_before_effect" and (effects_started or outputs or writes):
        raise _ProtocolError("A before-effect failure reported an output effect.")
    if state == "failed_after_partial_effect" and (not effects_started or not outputs):
        raise _ProtocolError("A partial-effect failure reported no created output.")
    succeeded_inputs = tuple(item for item in inputs if item.outcome == "succeeded")
    if state == "succeeded" and (
        not inputs or len(succeeded_inputs) != len(inputs)
    ):
        raise _ProtocolError(
            "Successful execution reported an incomplete input outcome."
        )
    if state == "failed_before_effect" and succeeded_inputs:
        raise _ProtocolError("A before-effect failure reported a successful input.")
    if state == "failed_after_partial_effect" and not succeeded_inputs:
        raise _ProtocolError("A partial-effect failure reported no successful input.")
    mutates_inputs = _boolean(
        source.get("mutates_inputs"),
        "source_effect.mutates_inputs",
    )
    workbooks_saved = _nonnegative_int(
        source.get("workbooks_saved"),
        "workbooks_saved",
    )
    if mutates_inputs or workbooks_saved != 0:
        raise _ProtocolError(
            "Execution contradicted the no-source-mutation contract."
        )
    return ExecuteAutomationResult(
        state,  # type: ignore[arg-type]
        reviewed,
        final,
        effects_started,
        writes,
        inputs,
        mutates_inputs,
        workbooks_saved,
        outputs,
        overwritten,
        _parse_artifacts(document.get("artifacts")),
        _parse_warnings(document.get("warnings")),
        _text(document.get("code"), "code"),
        _text(document.get("message"), "message"),
        _boolean(document.get("retryable"), "retryable"),
    )


def _parse_executed_workbook(value: object, index: int) -> ExecutedWorkbook:
    item = _object(value, f"inputs[{index}]")
    outcome = _text(item.get("outcome"), "input.outcome")
    if outcome not in {"succeeded", "failed", "not_started"}:
        raise _ProtocolError("An execution input returned an unsupported outcome.")
    worksheet = _optional_text(item.get("worksheet"), "input.worksheet")
    physical_columns = _positive_int_tuple_or_empty(
        item.get("physical_columns"),
        "input.physical_columns",
    )
    output_path = _optional_text(item.get("output_path"), "input.output_path")
    if outcome == "succeeded" and (
        not worksheet or not physical_columns or not output_path
    ):
        raise _ProtocolError(
            "A successful execution input omitted its worksheet, columns, or output."
        )
    return ExecutedWorkbook(
        _text(item.get("input_id"), "input.input_id"),
        outcome,  # type: ignore[arg-type]
        _text(item.get("code"), "input.code"),
        _text(item.get("message"), "input.message"),
        _text(item.get("source_path"), "input.source_path"),
        worksheet,
        physical_columns,
        output_path,
        _nonnegative_int(item.get("rows_written"), "input.rows_written"),
        _nonnegative_int(item.get("columns_written"), "input.columns_written"),
        _nonnegative_int(item.get("escaped_cells"), "input.escaped_cells"),
    )


def _parse_warnings(value: object) -> tuple[AutomationWarning, ...]:
    return tuple(
        AutomationWarning(
            _text(_object(raw, "warning").get("code"), "warning.code"),
            _text(_object(raw, "warning").get("message"), "warning.message"),
            _optional_text(
                _object(raw, "warning").get("input_id"), "warning.input_id"
            ),
        )
        for raw in _array(value, "warnings")
    )


def _parse_artifacts(value: object) -> tuple[AutomationArtifact, ...]:
    return tuple(
        AutomationArtifact(
            _text(_object(raw, "artifact").get("artifact_id"), "artifact_id"),
            _text(_object(raw, "artifact").get("kind"), "artifact.kind"),
            _text(_object(raw, "artifact").get("path"), "artifact.path"),
            _optional_text(
                _object(raw, "artifact").get("media_type"), "artifact.media_type"
            ),
            _optional_text(
                _object(raw, "artifact").get("input_id"), "artifact.input_id"
            ),
        )
        for raw in _array(value, "artifacts")
    )


def _validate_automation_identity(value: object) -> None:
    automation = _object(value, "automation")
    if (
        automation.get("automation_id") != EXCEL_AUTOMATION_ID
        or automation.get("automation_version") != EXCEL_AUTOMATION_VERSION
    ):
        raise _ProtocolError("The response automation identity did not match.")


def _failed_protocol_result(
    phase: AutomationPhase,
    return_code: int | None,
    diagnostic_present: bool,
    reason: str,
) -> AutomationCallResult:
    return AutomationCallResult(
        phase,
        _failure_classification(phase),
        True,
        return_code,
        diagnostic_present=diagnostic_present,
        reason=reason,
    )


def _operation_for_phase(phase: AutomationPhase) -> str:
    return {
        "describe": DESCRIBE_OPERATION,
        "plan": PLAN_OPERATION,
        "execute": EXECUTE_OPERATION,
    }[phase]


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _ProtocolError(f"{label} must be an object.")
    return value


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise _ProtocolError(f"{label} must be an array.")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise _ProtocolError(f"{label} must be text.")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise _ProtocolError(f"{label} must be true or false.")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _ProtocolError(f"{label} must be a non-negative integer.")
    return value


def _positive_int_tuple(value: object, label: str) -> tuple[int, ...]:
    result = _positive_int_tuple_or_empty(value, label)
    if not result:
        raise _ProtocolError(f"{label} must contain unique positive integers.")
    return result


def _positive_int_tuple_or_empty(value: object, label: str) -> tuple[int, ...]:
    values = _array(value, label)
    result = tuple(_nonnegative_int(item, label) for item in values)
    if any(item < 1 for item in result) or len(set(result)) != len(result):
        raise _ProtocolError(f"{label} must contain unique positive integers.")
    return result


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(slots=True)
class _BoundedBuffer:
    maximum: int
    content: bytearray
    exceeded: bool = False

    @classmethod
    def create(cls, maximum: int) -> _BoundedBuffer:
        return cls(maximum, bytearray())

    def add(self, chunk: bytes) -> None:
        remaining = self.maximum - len(self.content)
        if remaining > 0:
            self.content.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.exceeded = True


class PythonExcelProcessClient:
    """Execute one bounded Python Excel machine request."""

    def __init__(
        self,
        *,
        maximum_stdout_bytes: int = DEFAULT_MAX_STDOUT_BYTES,
        maximum_stderr_bytes: int = DEFAULT_MAX_STDERR_BYTES,
        popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        terminate_process: Callable[[subprocess.Popen[bytes]], None] | None = None,
    ) -> None:
        if maximum_stdout_bytes < 1 or maximum_stderr_bytes < 1:
            raise ValueError("Process output limits must be positive.")
        self.maximum_stdout_bytes = maximum_stdout_bytes
        self.maximum_stderr_bytes = maximum_stderr_bytes
        self._popen_factory = popen_factory
        self._terminate_process = terminate_process or _terminate_process_tree

    def call(
        self,
        launcher_path: Path,
        request: Mapping[str, object],
        *,
        phase: AutomationPhase,
        timeout_seconds: float,
    ) -> AutomationCallResult:
        launcher = Path(launcher_path)
        try:
            _validate_launcher_path(launcher)
        except ExcelAutomationSettingsError as exc:
            return _start_failed(phase, str(exc))
        if not launcher.is_file():
            return _start_failed(phase, "The configured Python Excel launcher is unavailable.")
        if timeout_seconds <= 0:
            return _start_failed(phase, "The Python Excel timeout must be positive.")
        try:
            request_id = _text(request.get("request_id"), "request_id")
            if request.get("operation") != _operation_for_phase(phase):
                raise _ProtocolError("The request operation does not match its phase.")
            payload = (
                json.dumps(
                    dict(request),
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
        except (TypeError, ValueError, UnicodeError, _ProtocolError) as exc:
            return _start_failed(phase, f"The Python Excel request is invalid: {exc}")
        if len(payload) > MAX_REQUEST_BYTES:
            return _start_failed(phase, "The Python Excel request exceeds 1 MiB.")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = self._popen_factory(
                [str(launcher), "execute", "--request", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError):
            return _start_failed(phase, "The Python Excel process could not start.")

        stdout_buffer = _BoundedBuffer.create(self.maximum_stdout_bytes)
        stderr_buffer = _BoundedBuffer.create(self.maximum_stderr_bytes)
        write_errors: list[BaseException] = []
        threads = (
            threading.Thread(
                target=_write_request,
                args=(process, payload, write_errors),
                daemon=True,
                name="python-excel-stdin",
            ),
            threading.Thread(
                target=_drain_stream,
                args=(process.stdout, stdout_buffer),
                daemon=True,
                name="python-excel-stdout",
            ),
            threading.Thread(
                target=_drain_stream,
                args=(process.stderr, stderr_buffer),
                daemon=True,
                name="python-excel-stderr",
            ),
        )
        for thread in threads:
            thread.start()

        timed_out = False
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate_process(process)
            try:
                return_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    return_code = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    return_code = None

        for thread in threads:
            thread.join(timeout=2)
        _close_process_stream(process.stdout)
        _close_process_stream(process.stderr)
        diagnostic_present = bool(stderr_buffer.content) or stderr_buffer.exceeded
        if timed_out:
            return _process_failure(phase, return_code, diagnostic_present, "timed out")
        if any(thread.is_alive() for thread in threads):
            return _process_failure(
                phase, return_code, diagnostic_present, "did not close its process streams"
            )
        if write_errors:
            return _process_failure(
                phase, return_code, diagnostic_present, "could not receive its complete request"
            )
        if stdout_buffer.exceeded or stderr_buffer.exceeded:
            return _process_failure(
                phase, return_code, diagnostic_present, "exceeded a bounded output limit"
            )
        assert return_code is not None
        return parse_automation_response(
            phase=phase,
            request_id=request_id,
            return_code=return_code,
            stdout=bytes(stdout_buffer.content),
            stderr=bytes(stderr_buffer.content),
        )


def _write_request(
    process: subprocess.Popen[bytes],
    payload: bytes,
    errors: list[BaseException],
) -> None:
    stream = process.stdin
    if stream is None:
        errors.append(OSError("stdin unavailable"))
        return
    try:
        stream.write(payload)
        stream.flush()
    except (OSError, ValueError) as exc:
        errors.append(exc)
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _drain_stream(stream: object, buffer: _BoundedBuffer) -> None:
    if stream is None or not hasattr(stream, "read"):
        return
    try:
        while chunk := stream.read(64 * 1024):  # type: ignore[attr-defined]
            buffer.add(chunk)
    except (OSError, ValueError):
        return


def _close_process_stream(stream: object) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            close()
        except (OSError, ValueError):
            pass


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            killer = subprocess.Popen(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if killer.wait(timeout=5) == 0:
                return
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        process.kill()
    except OSError:
        pass


def _start_failed(phase: AutomationPhase, reason: str) -> AutomationCallResult:
    return AutomationCallResult(
        phase,
        "start_failed",
        False,
        None,
        reason=reason,
    )


def _process_failure(
    phase: AutomationPhase,
    return_code: int | None,
    diagnostic_present: bool,
    reason: str,
) -> AutomationCallResult:
    return AutomationCallResult(
        phase,
        _failure_classification(phase),
        True,
        return_code,
        diagnostic_present=diagnostic_present,
        reason=f"The Python Excel process {reason}.",
    )


def _failure_classification(phase: AutomationPhase) -> CallClassification:
    return {
        "describe": "describe_failed",
        "plan": "plan_failed",
        "execute": "execute_unknown",
    }[phase]


class ExcelAutomationCoordinator:
    """Run one process call off-thread and deliver completion during drain()."""

    def __init__(self, client: PythonExcelProcessClient | None = None) -> None:
        self._client = client or PythonExcelProcessClient()
        self._lock = threading.Lock()
        self._running = False
        self._completed: queue.SimpleQueue[
            tuple[AutomationCallResult, Callable[[AutomationCallResult], None]]
        ] = queue.SimpleQueue()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def completion_pending(self) -> bool:
        return not self._completed.empty()

    def start(
        self,
        launcher_path: Path,
        request: Mapping[str, object],
        *,
        phase: AutomationPhase,
        timeout_seconds: float,
        on_complete: Callable[[AutomationCallResult], None],
    ) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True

        def work() -> None:
            try:
                result = self._client.call(
                    launcher_path,
                    request,
                    phase=phase,
                    timeout_seconds=timeout_seconds,
                )
            except Exception:
                result = _process_failure(
                    phase,
                    None,
                    False,
                    "stopped because of an unexpected local error",
                )
            self._completed.put((result, on_complete))

        threading.Thread(
            target=work,
            daemon=True,
            name="python-excel-automation",
        ).start()
        return True

    def drain(self) -> bool:
        try:
            result, callback = self._completed.get_nowait()
        except queue.Empty:
            return False
        # Clear single-flight state before delivery so an attended callback can
        # immediately submit the next plan or reviewed execution phase.
        with self._lock:
            self._running = False
        callback(result)
        return True
