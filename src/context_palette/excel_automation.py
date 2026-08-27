"""Isolated process boundary for reviewed Python Excel automations.

This module deliberately contains no Tk code and no workbook implementation.
It validates machine-local host configuration, builds the versioned JSON
requests owned by Python Excel, and delivers immutable process outcomes for the
launcher to present on the main thread.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
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
EXCEL_AUTOMATION_VERSION = "2.0"
DESCRIBE_OPERATION = "describe_automations"
PLAN_OPERATION = "plan_automation"
EXECUTE_OPERATION = "execute_automation"
LIVE_INVENTORY_OPERATION = "inventory_live_excel"
LIVE_FORMAT_PROFILE_OPERATION = "apply_live_format_profile"
DESCRIBE_CAPABILITIES_OPERATION = "describe_capabilities"
LIVE_PREFLIGHT_OPERATION = "preflight_live_columns"
LIVE_CONVERSION_PLAN_OPERATION = "plan_live_column_conversion"
LIVE_CONVERSION_EXECUTE_OPERATION = "convert_live_column_representation"
OPERATION_VERSION = "1.0"
MAX_WORKBOOKS = 100
MAX_REQUEST_BYTES = 1024 * 1024
DEFAULT_MAX_STDOUT_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_STDERR_BYTES = 256 * 1024
PYTHON_EXCEL_SIBLING_DIRECTORY = "python-excel"
PYTHON_EXCEL_LAUNCHER_NAME = "python-excel.bat"
LIVE_TEXT_CONVERSION_AUTOMATION_ID = "excel.convert_live_column_representation"
LIVE_TEXT_CONVERSION_UAT_ENV = "CONTEXT_PALETTE_UAT_LIVE_TEXT_CONVERSION"
LIVE_HEADER_ROW = 1
LIVE_MAXIMUM_COLUMNS = 100
LIVE_MAXIMUM_DATA_ROWS = 10_000
LIVE_MAXIMUM_SAMPLES_PER_COLUMN = 10
LIVE_TEXT_LIMIT = 200
LIVE_MAXIMUM_EXCEL_COLUMN = 16_384

AutomationPhase = Literal[
    "describe",
    "plan",
    "execute",
    "inventory",
    "apply",
    "capabilities",
    "preflight",
    "conversion_plan",
    "conversion_execute",
]
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
    "inventory_succeeded",
    "inventory_failed",
    "apply_succeeded",
    "apply_failed",
    "apply_partial_failure",
    "apply_unknown",
    "capabilities_succeeded",
    "capabilities_failed",
    "preflight_succeeded",
    "preflight_failed",
    "conversion_plan_blocked",
    "conversion_plan_ready",
    "conversion_plan_failed",
    "conversion_execute_succeeded",
    "conversion_execute_failed",
    "conversion_execute_partial_failure",
    "conversion_execute_unknown",
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


def discover_direct_sibling_python_excel_launcher(
    application_root: Path,
) -> Path | None:
    """Return the one supported sibling launcher candidate when it exists.

    Discovery is deliberately limited to the direct ``python-excel`` sibling
    of the Context Palette application root. It never searches PATH, descends
    through folders, or persists the detected machine-local path.
    """

    root = Path(application_root)
    if not root.is_absolute():
        return None
    candidate = (
        root.parent
        / PYTHON_EXCEL_SIBLING_DIRECTORY
        / PYTHON_EXCEL_LAUNCHER_NAME
    )
    try:
        return candidate if candidate.is_file() else None
    except OSError:
        return None


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
    allow_overwrite: bool = False

    def __post_init__(self) -> None:
        if not 1 <= len(self.inputs) <= MAX_WORKBOOKS:
            raise ExcelAutomationInputError(
                f"An Excel automation requires 1 through {MAX_WORKBOOKS} workbooks."
            )
        if len({item.input_id for item in self.inputs}) != len(self.inputs):
            raise ExcelAutomationInputError("Workbook input IDs must be unique.")
        if self.output_directory is not None and not self.output_directory.is_absolute():
            raise ExcelAutomationInputError("The output directory must be absolute.")
        if not isinstance(self.allow_overwrite, bool):
            raise ExcelAutomationInputError("Allow overwrite must be a boolean.")


def csv_invocation(
    paths: tuple[Path, ...],
    *,
    output_directory: Path | None = None,
    worksheets: Mapping[str, str] | None = None,
    allow_overwrite: bool = False,
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
    return CsvAutomationInvocation(
        inputs,
        output_directory,
        allow_overwrite=allow_overwrite,
    )


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


@dataclass(frozen=True, slots=True)
class LiveExcelInventoryLimits:
    """Bounded inventory limits accepted by Python Excel 1.0."""

    maximum_applications: int = 16
    maximum_workbooks_per_application: int = 100
    maximum_sheets_per_workbook: int = 250

    def __post_init__(self) -> None:
        _live_limit(
            self.maximum_applications,
            maximum=64,
            label="maximum_applications",
        )
        _live_limit(
            self.maximum_workbooks_per_application,
            maximum=256,
            label="maximum_workbooks_per_application",
        )
        _live_limit(
            self.maximum_sheets_per_workbook,
            maximum=1000,
            label="maximum_sheets_per_workbook",
        )


def live_text_conversion_uat_enabled(
    environment: Mapping[str, str] | None = None,
) -> bool:
    """Return true only for the exact opt-in value accepted by the UAT gate."""

    selected = os.environ if environment is None else environment
    return selected.get(LIVE_TEXT_CONVERSION_UAT_ENV) == "1"


@dataclass(frozen=True, slots=True)
class LiveColumnPreflightInvocation:
    """One bounded, read-only physical-column inspection."""

    workbook_token: str
    worksheet: str
    columns: tuple[int, ...] | None = None
    column_offset: int = 0

    def __post_init__(self) -> None:
        _validate_live_target(self.workbook_token, self.worksheet)
        if (
            isinstance(self.column_offset, bool)
            or not isinstance(self.column_offset, int)
            or not 0 <= self.column_offset < LIVE_MAXIMUM_EXCEL_COLUMN
        ):
            raise ExcelAutomationInputError(
                "The live column offset must be an integer from 0 through 16383."
            )
        if self.columns is not None:
            _validate_live_columns(self.columns)
            if self.column_offset != 0:
                raise ExcelAutomationInputError(
                    "An explicit live column selection must use offset zero."
                )


@dataclass(frozen=True, slots=True)
class LiveColumnConversionPlanInvocation:
    """Exact attended text-conversion choices before engine review."""

    workbook_token: str
    worksheet: str
    columns: tuple[int, ...]
    recovery_path: str | None = None
    target: Literal["text"] = "text"

    def __post_init__(self) -> None:
        _validate_live_target(self.workbook_token, self.worksheet)
        _validate_live_columns(self.columns)
        if self.target != "text":
            raise ExcelAutomationInputError(
                "Live column conversion version 1.0 supports text only."
            )
        if self.recovery_path is not None:
            _validate_live_recovery_path(self.recovery_path)


@dataclass(frozen=True, slots=True)
class LiveColumnConversionInvocation:
    """One reviewed, UAT-gated live text mutation request."""

    workbook_token: str
    worksheet: str
    columns: tuple[int, ...]
    expected_plan_fingerprint: str
    recovery_path: str
    acknowledge_irreversible_precision_risk: bool = False
    target: Literal["text"] = "text"

    def __post_init__(self) -> None:
        _validate_live_target(self.workbook_token, self.worksheet)
        _validate_live_columns(self.columns)
        if self.target != "text":
            raise ExcelAutomationInputError(
                "Live column conversion version 1.0 supports text only."
            )
        if not _is_prefixed_sha256(self.expected_plan_fingerprint):
            raise ExcelAutomationInputError(
                "The reviewed live plan fingerprint is not a valid SHA-256 value."
            )
        _validate_live_recovery_path(self.recovery_path)
        if not isinstance(self.acknowledge_irreversible_precision_risk, bool):
            raise ExcelAutomationInputError(
                "The irreversible precision-risk acknowledgement must be boolean."
            )


@dataclass(frozen=True, slots=True)
class LiveFormatProfileInvocation:
    """One attended direct-format target; its token is intentionally opaque."""

    workbook_token: str
    scope: Literal["worksheet", "workbook"] = "worksheet"
    worksheet: str | None = None
    profile_id: str = "standard_data"
    profile_version: str = "1.0"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.workbook_token, str)
            or not self.workbook_token.strip()
        ):
            raise ExcelAutomationInputError("The live workbook token must be text.")
        if self.scope not in {"worksheet", "workbook"}:
            raise ExcelAutomationInputError(
                "The live format scope must be worksheet or workbook."
            )
        if self.scope == "worksheet" and (
            not isinstance(self.worksheet, str) or not self.worksheet
        ):
            raise ExcelAutomationInputError(
                "A worksheet name is required for worksheet scope."
            )
        if self.scope == "workbook" and self.worksheet is not None:
            raise ExcelAutomationInputError(
                "Workbook scope must not include a worksheet name."
            )
        if (self.profile_id, self.profile_version) != ("standard_data", "1.0"):
            raise ExcelAutomationInputError(
                "The selected live format profile is unsupported."
            )


def build_inventory_live_excel_request(
    request_id: str,
    limits: LiveExcelInventoryLimits | None = None,
) -> dict[str, object]:
    """Build the bounded read-only inventory request for the Tk chooser."""

    selected = limits or LiveExcelInventoryLimits()
    return _request(
        request_id,
        LIVE_INVENTORY_OPERATION,
        {
            "maximum_applications": selected.maximum_applications,
            "maximum_workbooks_per_application": (
                selected.maximum_workbooks_per_application
            ),
            "maximum_sheets_per_workbook": selected.maximum_sheets_per_workbook,
        },
    )


def build_describe_capabilities_request(request_id: str) -> dict[str, object]:
    """Build the side-effect-free operation catalogue handshake."""

    return _request(request_id, DESCRIBE_CAPABILITIES_OPERATION, {})


def build_preflight_live_columns_request(
    request_id: str,
    invocation: LiveColumnPreflightInvocation,
) -> dict[str, object]:
    """Build the fixed-bound read-only preflight request."""

    return _request(
        request_id,
        LIVE_PREFLIGHT_OPERATION,
        {
            "workbook_token": invocation.workbook_token,
            "worksheet": invocation.worksheet,
            "columns": (
                None if invocation.columns is None else list(invocation.columns)
            ),
            "header_row": LIVE_HEADER_ROW,
            "column_offset": invocation.column_offset,
            "maximum_columns": LIVE_MAXIMUM_COLUMNS,
            "maximum_data_rows": LIVE_MAXIMUM_DATA_ROWS,
            "maximum_samples_per_column": LIVE_MAXIMUM_SAMPLES_PER_COLUMN,
            "text_limit": LIVE_TEXT_LIMIT,
        },
    )


def build_plan_live_column_conversion_request(
    request_id: str,
    invocation: LiveColumnConversionPlanInvocation,
) -> dict[str, object]:
    """Build the zero-write live text-conversion plan request."""

    return _request(
        request_id,
        LIVE_CONVERSION_PLAN_OPERATION,
        {
            "workbook_token": invocation.workbook_token,
            "worksheet": invocation.worksheet,
            "columns": list(invocation.columns),
            "target": invocation.target,
            "header_row": LIVE_HEADER_ROW,
            "recovery_path": invocation.recovery_path,
            "maximum_data_rows": LIVE_MAXIMUM_DATA_ROWS,
            "maximum_samples_per_column": LIVE_MAXIMUM_SAMPLES_PER_COLUMN,
            "text_limit": LIVE_TEXT_LIMIT,
        },
    )


def build_convert_live_column_representation_request(
    request_id: str,
    invocation: LiveColumnConversionInvocation,
) -> dict[str, object]:
    """Build one reviewed conversion request without altering its fingerprint."""

    return _request(
        request_id,
        LIVE_CONVERSION_EXECUTE_OPERATION,
        {
            "workbook_token": invocation.workbook_token,
            "worksheet": invocation.worksheet,
            "columns": list(invocation.columns),
            "target": invocation.target,
            "expected_plan_fingerprint": invocation.expected_plan_fingerprint,
            "recovery_path": invocation.recovery_path,
            "acknowledge_irreversible_precision_risk": (
                invocation.acknowledge_irreversible_precision_risk
            ),
            "header_row": LIVE_HEADER_ROW,
            "maximum_data_rows": LIVE_MAXIMUM_DATA_ROWS,
            "maximum_samples_per_column": LIVE_MAXIMUM_SAMPLES_PER_COLUMN,
            "text_limit": LIVE_TEXT_LIMIT,
        },
    )


def build_apply_live_format_profile_request(
    request_id: str,
    invocation: LiveFormatProfileInvocation,
) -> dict[str, object]:
    """Build one direct profile application request without a retry protocol."""

    return _request(
        request_id,
        LIVE_FORMAT_PROFILE_OPERATION,
        {
            "workbook_token": invocation.workbook_token,
            "scope": invocation.scope,
            "worksheet": invocation.worksheet,
            "profile_id": invocation.profile_id,
            "profile_version": invocation.profile_version,
        },
    )


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
            "allow_overwrite": invocation.allow_overwrite,
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
class DestinationState:
    exists: bool
    size_bytes: int | None
    modified_ns: int | None
    created_ns: int | None
    device: int | None
    inode: int | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class PlannedWorkbook:
    input_id: str
    original_path: str
    resolved_path: str
    worksheet: str
    physical_columns: tuple[int, ...]
    rows_to_write: int
    output_path: str
    output_disposition: Literal["create", "replace"]
    destination_state: DestinationState


@dataclass(frozen=True, slots=True)
class PlanEffect:
    mutates_inputs: bool
    output_policy: str
    input_files: int
    output_files: int
    rows_to_write: int
    outputs_to_create: int
    outputs_to_replace: int


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
    outputs_replaced: tuple[str, ...]
    outputs_overwritten: int
    artifacts: tuple[AutomationArtifact, ...]
    warnings: tuple[AutomationWarning, ...]
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class LiveExcelWarning:
    code: str
    message: str
    details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LiveExcelSheet:
    position: int
    name: str
    state: Literal["visible", "hidden", "very_hidden", "unknown"]


@dataclass(frozen=True, slots=True)
class LiveExcelWorkbook:
    token: str
    process_id: int
    name: str
    full_path: str | None
    saved: bool
    read_only: bool
    autosave_enabled: bool | None
    active_sheet: str | None
    sheets_total: int
    sheets_truncated: bool
    sheets: tuple[LiveExcelSheet, ...]


@dataclass(frozen=True, slots=True)
class LiveExcelApplication:
    process_id: int
    foreground: bool
    visible: bool
    workbooks_total: int
    workbooks_truncated: bool
    workbooks: tuple[LiveExcelWorkbook, ...]


@dataclass(frozen=True, slots=True)
class LiveExcelInventoryResult:
    applications_total: int
    applications_truncated: bool
    applications: tuple[LiveExcelApplication, ...]
    warnings: tuple[LiveExcelWarning, ...]


@dataclass(frozen=True, slots=True)
class ExcelCapabilityAvailability:
    available: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class ExcelCapabilitySupports:
    worksheet_selection: bool
    column_selection: bool
    in_place: bool
    planning: bool


@dataclass(frozen=True, slots=True)
class ExcelCapability:
    operation: str
    operation_version: str
    title: str
    description: str
    backend: Literal["openpyxl", "xlwings"]
    input_context: Literal["closed_workbook_files", "live_excel"]
    input_extensions: tuple[str, ...]
    minimum_inputs: int
    maximum_inputs: int
    effect_class: Literal[
        "read_only", "creates_output", "may_replace_input", "live_mutation"
    ]
    output_class: Literal["none", "xlsx", "csv"]
    supports: ExcelCapabilitySupports
    plan_operation: str | None
    plan_operation_version: str | None
    requires_excel: bool
    availability: ExcelCapabilityAvailability


@dataclass(frozen=True, slots=True)
class DescribeCapabilitiesResult:
    capabilities: tuple[ExcelCapability, ...]

    def find(
        self,
        operation: str,
        operation_version: str = OPERATION_VERSION,
    ) -> ExcelCapability | None:
        return next(
            (
                item
                for item in self.capabilities
                if item.operation == operation
                and item.operation_version == operation_version
            ),
            None,
        )

    @property
    def live_text_conversion(self) -> ExcelCapability | None:
        return self.find(LIVE_CONVERSION_EXECUTE_OPERATION)


LiveScalar = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class LiveUsedRange:
    first_row: int
    last_row: int
    first_column: int
    last_column: int


@dataclass(frozen=True, slots=True)
class LiveDataRows:
    first: int | None
    last: int | None
    total: int
    examined: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class LiveValueClassifications:
    blank: int
    text: int
    numeric: int
    boolean: int
    date_time: int
    error: int
    unsupported: int
    formula: int


@dataclass(frozen=True, slots=True)
class LiveFormulaSample:
    row: int
    formula: str


@dataclass(frozen=True, slots=True)
class LivePrecisionRisk:
    row: int
    code: str
    value_preview: LiveScalar


@dataclass(frozen=True, slots=True)
class LiveColumnFormulas:
    count: int
    samples: tuple[LiveFormulaSample, ...]
    samples_truncated: bool


@dataclass(frozen=True, slots=True)
class LiveColumnPrecisionRisks:
    cells: int
    samples: tuple[LivePrecisionRisk, ...]
    samples_truncated: bool


@dataclass(frozen=True, slots=True)
class LiveColumnPreflightColumn:
    column_index: int
    column_letter: str
    header_value: LiveScalar
    first_used_row: int | None
    last_used_row: int | None
    cells_examined: int
    classifications: LiveValueClassifications
    formulas: LiveColumnFormulas
    precision_risks: LiveColumnPrecisionRisks


@dataclass(frozen=True, slots=True)
class LivePreflightWorkbook:
    token: str
    process_id: int
    name: str
    full_path: str | None
    saved: bool
    read_only: bool
    autosave_enabled: bool | None


@dataclass(frozen=True, slots=True)
class LiveColumnPreflightResult:
    workbook: LivePreflightWorkbook
    worksheet: str
    header_row: int
    used_range: LiveUsedRange
    data_rows: LiveDataRows
    columns_total: int
    columns_truncated: bool
    next_column_offset: int | None
    columns: tuple[LiveColumnPreflightColumn, ...]
    warnings: tuple[LiveExcelWarning, ...]


@dataclass(frozen=True, slots=True)
class LiveConversionCounts:
    cells_examined: int
    blank: int
    already_compliant: int
    eligible: int
    blocked_formula: int
    blocked_unsupported: int
    precision_risk_cells: int


@dataclass(frozen=True, slots=True)
class LiveConversionSample:
    row: int
    input_preview: LiveScalar
    output_text: str


@dataclass(frozen=True, slots=True)
class LiveConversionPlanColumn:
    column_index: int
    column_letter: str
    header_value: LiveScalar
    counts: LiveConversionCounts
    conversion_samples: tuple[LiveConversionSample, ...]
    conversion_samples_truncated: bool
    precision_risks: tuple[LivePrecisionRisk, ...]
    precision_risks_truncated: bool


@dataclass(frozen=True, slots=True)
class LiveConversionEffect:
    target_type: Literal["text", "number"]
    cells_examined: int
    eligible: int
    already_compliant: int
    blank: int
    blocked: int
    formulas: int
    unsupported: int
    precision_risk_cells: int


@dataclass(frozen=True, slots=True)
class LiveConversionRecoveryPlan:
    required: bool
    strategy: str
    path: str | None
    will_overwrite: bool


@dataclass(frozen=True, slots=True)
class LiveConversionBlocker:
    code: str
    message: str
    details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LiveConversionPlanTarget:
    process_id: int
    workbook_token: str
    workbook_name: str
    full_path: str | None
    saved: bool
    read_only: bool
    autosave_enabled: bool | None
    workbook_protected: bool | None
    worksheet: str
    worksheet_protected: bool | None
    physical_columns: tuple[int, ...]
    header_row: int
    used_range: LiveUsedRange
    data_first_row: int | None
    data_last_row: int | None
    data_rows_total: int
    data_rows_examined: int
    data_rows_truncated: bool


@dataclass(frozen=True, slots=True)
class LiveColumnConversionPlanResult:
    can_execute: bool
    writes_performed: int
    scope_fingerprint: str
    plan_fingerprint: str
    target: LiveConversionPlanTarget
    effect: LiveConversionEffect
    recovery: LiveConversionRecoveryPlan
    columns: tuple[LiveConversionPlanColumn, ...]
    blockers: tuple[LiveConversionBlocker, ...]
    warnings: tuple[LiveExcelWarning, ...]


@dataclass(frozen=True, slots=True)
class LiveConversionExecutionTarget:
    process_id: int
    workbook_token: str
    workbook_name: str
    full_path: str
    worksheet: str
    physical_columns: tuple[int, ...]
    data_first_row: int | None
    data_last_row: int | None


@dataclass(frozen=True, slots=True)
class LiveConversionExecutionRecovery:
    path: str
    verified: bool


@dataclass(frozen=True, slots=True)
class LiveConversionFailure:
    code: str
    message: str
    stage: Literal["revalidate", "recovery", "write"]
    column_index: int | None
    exception_type: str | None
    com_hresult: int | None


@dataclass(frozen=True, slots=True)
class LiveColumnConversionResult:
    state: Literal["succeeded", "failed", "partial_failure"]
    target: LiveConversionExecutionTarget
    reviewed_plan_fingerprint: str
    changed_cells: int
    already_compliant_cells: int
    blank_cells: int
    columns_completed: tuple[int, ...]
    recovery: LiveConversionExecutionRecovery
    mutation_started: bool
    workbook_dirty: bool
    workbook_saved: bool
    workbook_closed: bool
    application_closed: bool
    failure: LiveConversionFailure | None
    warnings: tuple[LiveExcelWarning, ...]


@dataclass(frozen=True, slots=True)
class LiveFormatFailure:
    worksheet: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LiveFormatProfileResult:
    state: Literal["succeeded", "failed", "partial_failure"]
    workbook_token: str
    workbook_name: str
    scope: Literal["worksheet", "workbook"]
    profile_id: str
    profile_version: str
    formatted_sheets: tuple[str, ...]
    skipped_hidden_sheets: tuple[str, ...]
    filter_added_sheets: tuple[str, ...]
    existing_filter_sheets: tuple[str, ...]
    failures: tuple[LiveFormatFailure, ...]
    workbook_saved: bool
    workbook_closed: bool
    application_closed: bool
    warnings: tuple[LiveExcelWarning, ...]


AutomationResult = (
    DescribeAutomationsResult
    | DescribeCapabilitiesResult
    | PlanAutomationResult
    | ExecuteAutomationResult
    | LiveExcelInventoryResult
    | LiveColumnPreflightResult
    | LiveColumnConversionPlanResult
    | LiveColumnConversionResult
    | LiveFormatProfileResult
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
        return self.classification in {
            "execute_unknown",
            "apply_unknown",
            "conversion_execute_unknown",
        }


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
        paths = _object(document.get("paths"), "paths")
        if phase in {
            "inventory",
            "apply",
            "capabilities",
            "preflight",
            "conversion_plan",
            "conversion_execute",
        } and (
            set(paths) != {"input", "output", "backup"}
            or any(value is not None for value in paths.values())
        ):
            raise _ProtocolError(
                "The live Excel response unexpectedly reported a file path."
            )
        envelope_warnings = _array(document.get("warnings"), "warnings")
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
        result, classification = _parse_success_result(
            phase,
            result_document,
            envelope_warnings,
        )
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
    envelope_warnings: list[object],
) -> tuple[AutomationResult, CallClassification]:
    if phase == "describe":
        result = _parse_describe_result(document)
        return result, "describe_succeeded"
    if phase == "capabilities":
        return _parse_capabilities_result(document), "capabilities_succeeded"
    if phase == "plan":
        result = _parse_plan_result(document)
        return result, {
            "needs_parameters": "plan_needs_parameters",
            "blocked": "plan_blocked",
            "ready": "plan_ready",
        }[result.state]
    if phase == "inventory":
        return (
            _parse_live_inventory_result(document, envelope_warnings),
            "inventory_succeeded",
        )
    if phase == "preflight":
        return (
            _parse_live_preflight_result(document, envelope_warnings),
            "preflight_succeeded",
        )
    if phase == "conversion_plan":
        result = _parse_live_conversion_plan_result(document, envelope_warnings)
        return result, (
            "conversion_plan_ready"
            if result.can_execute
            else "conversion_plan_blocked"
        )
    if phase == "conversion_execute":
        result = _parse_live_conversion_result(document, envelope_warnings)
        return result, {
            "succeeded": "conversion_execute_succeeded",
            "failed": "conversion_execute_failed",
            "partial_failure": "conversion_execute_partial_failure",
        }[result.state]
    if phase == "apply":
        result = _parse_live_format_profile_result(document, envelope_warnings)
        return result, {
            "succeeded": "apply_succeeded",
            "failed": "apply_failed",
            "partial_failure": "apply_partial_failure",
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


def _parse_capabilities_result(
    document: dict[str, object],
) -> DescribeCapabilitiesResult:
    capabilities = tuple(
        _parse_capability(value, index)
        for index, value in enumerate(
            _array(document.get("capabilities"), "capabilities")
        )
    )
    identities = {
        (item.operation, item.operation_version) for item in capabilities
    }
    if len(identities) != len(capabilities):
        raise _ProtocolError("The capability catalogue contains duplicate identities.")
    return DescribeCapabilitiesResult(capabilities)


def _parse_capability(value: object, index: int) -> ExcelCapability:
    label = f"capabilities[{index}]"
    item = _object(value, label)
    backend = _text(item.get("backend"), f"{label}.backend")
    if backend not in {"openpyxl", "xlwings"}:
        raise _ProtocolError("The capability backend is unsupported.")
    input_context = _text(item.get("input_context"), f"{label}.input_context")
    if input_context not in {"closed_workbook_files", "live_excel"}:
        raise _ProtocolError("The capability input context is unsupported.")
    input_count = _object(item.get("input_count"), f"{label}.input_count")
    minimum = _nonnegative_int(input_count.get("minimum"), "input_count.minimum")
    maximum = _nonnegative_int(input_count.get("maximum"), "input_count.maximum")
    if minimum > maximum:
        raise _ProtocolError("The capability input count is contradictory.")
    effect_class = _text(item.get("effect_class"), f"{label}.effect_class")
    if effect_class not in {
        "read_only",
        "creates_output",
        "may_replace_input",
        "live_mutation",
    }:
        raise _ProtocolError("The capability effect class is unsupported.")
    output_class = _text(item.get("output_class"), f"{label}.output_class")
    if output_class not in {"none", "xlsx", "csv"}:
        raise _ProtocolError("The capability output class is unsupported.")
    support_document = _object(item.get("supports"), f"{label}.supports")
    supports = ExcelCapabilitySupports(
        _boolean(
            support_document.get("worksheet_selection"),
            "supports.worksheet_selection",
        ),
        _boolean(
            support_document.get("column_selection"),
            "supports.column_selection",
        ),
        _boolean(support_document.get("in_place"), "supports.in_place"),
        _boolean(support_document.get("planning"), "supports.planning"),
    )
    plan_operation = _optional_text(
        item.get("plan_operation"), f"{label}.plan_operation"
    )
    plan_version = _optional_text(
        item.get("plan_operation_version"), f"{label}.plan_operation_version"
    )
    if (
        (plan_operation is None) != (plan_version is None)
        or supports.planning != (plan_operation is not None)
    ):
        raise _ProtocolError("The capability planning metadata is contradictory.")
    availability_document = _object(
        item.get("availability"), f"{label}.availability"
    )
    available = _boolean(
        availability_document.get("available"), "availability.available"
    )
    reason = _optional_text(
        availability_document.get("reason"), "availability.reason"
    )
    if available and reason is not None:
        raise _ProtocolError("An available capability reported an unavailable reason.")
    return ExcelCapability(
        _text(item.get("operation"), f"{label}.operation"),
        _text(item.get("operation_version"), f"{label}.operation_version"),
        _text(item.get("title"), f"{label}.title"),
        _text(item.get("description"), f"{label}.description"),
        backend,  # type: ignore[arg-type]
        input_context,  # type: ignore[arg-type]
        _text_tuple(item.get("input_extensions"), f"{label}.input_extensions"),
        minimum,
        maximum,
        effect_class,  # type: ignore[arg-type]
        output_class,  # type: ignore[arg-type]
        supports,
        plan_operation,
        plan_version,
        _boolean(item.get("requires_excel"), f"{label}.requires_excel"),
        ExcelCapabilityAvailability(available, reason),
    )


def _parse_live_inventory_result(
    document: dict[str, object],
    warnings: list[object],
) -> LiveExcelInventoryResult:
    applications = tuple(
        _parse_live_application(value, index)
        for index, value in enumerate(_array(document.get("applications"), "applications"))
    )
    returned = _nonnegative_int(
        document.get("applications_returned"), "applications_returned"
    )
    total = _nonnegative_int(
        document.get("applications_total"), "applications_total"
    )
    truncated = _boolean(document.get("applications_truncated"), "applications_truncated")
    if (
        returned != len(applications)
        or total < returned
        or (truncated and total == returned)
    ):
        raise _ProtocolError("The live inventory application counts are inconsistent.")
    return LiveExcelInventoryResult(
        total,
        truncated,
        applications,
        _parse_live_warnings(warnings),
    )


def _parse_live_preflight_result(
    document: dict[str, object],
    warnings: list[object],
) -> LiveColumnPreflightResult:
    workbook_document = _object(document.get("workbook"), "result.workbook")
    workbook = LivePreflightWorkbook(
        _text(workbook_document.get("token"), "workbook.token"),
        _positive_int(workbook_document.get("process_id"), "workbook.process_id"),
        _text(workbook_document.get("name"), "workbook.name"),
        _optional_text(workbook_document.get("full_path"), "workbook.full_path"),
        _boolean(workbook_document.get("saved"), "workbook.saved"),
        _boolean(workbook_document.get("read_only"), "workbook.read_only"),
        _optional_boolean(
            workbook_document.get("autosave_enabled"), "workbook.autosave_enabled"
        ),
    )
    columns = tuple(
        _parse_live_preflight_column(value, index)
        for index, value in enumerate(_array(document.get("columns"), "columns"))
    )
    returned = _nonnegative_int(document.get("columns_returned"), "columns_returned")
    total = _nonnegative_int(document.get("columns_total"), "columns_total")
    truncated = _boolean(document.get("columns_truncated"), "columns_truncated")
    next_offset = _optional_nonnegative_int(
        document.get("next_column_offset"), "next_column_offset"
    )
    if (
        returned != len(columns)
        or total < returned
        or truncated != (next_offset is not None)
        or (truncated and total == returned)
        or len({item.column_index for item in columns}) != len(columns)
    ):
        raise _ProtocolError("The live preflight column counts are inconsistent.")
    return LiveColumnPreflightResult(
        workbook,
        _text(document.get("worksheet"), "worksheet"),
        _positive_int(document.get("header_row"), "header_row"),
        _parse_used_range(document.get("used_range")),
        _parse_data_rows(document.get("data_rows")),
        total,
        truncated,
        next_offset,
        columns,
        _parse_live_warnings(warnings),
    )


def _parse_live_preflight_column(
    value: object,
    index: int,
) -> LiveColumnPreflightColumn:
    label = f"columns[{index}]"
    item = _object(value, label)
    column_index = _positive_int(item.get("column_index"), f"{label}.column_index")
    column_letter = _text(item.get("column_letter"), f"{label}.column_letter")
    if column_index > LIVE_MAXIMUM_EXCEL_COLUMN or column_letter != _column_letter(
        column_index
    ):
        raise _ProtocolError("The live preflight physical column is inconsistent.")
    used_rows = _object(item.get("used_rows"), f"{label}.used_rows")
    first_used = _optional_positive_int(used_rows.get("first"), "used_rows.first")
    last_used = _optional_positive_int(used_rows.get("last"), "used_rows.last")
    if (first_used is None) != (last_used is None) or (
        first_used is not None and last_used is not None and first_used > last_used
    ):
        raise _ProtocolError("The live preflight used-row bounds are inconsistent.")
    classifications_document = _object(
        item.get("classifications"), f"{label}.classifications"
    )
    classifications = LiveValueClassifications(
        *(
            _nonnegative_int(classifications_document.get(field), field)
            for field in (
                "blank",
                "text",
                "numeric",
                "boolean",
                "date_time",
                "error",
                "unsupported",
                "formula",
            )
        )
    )
    cells_examined = _nonnegative_int(
        item.get("cells_examined"), f"{label}.cells_examined"
    )
    if cells_examined != sum(
        (
            classifications.blank,
            classifications.text,
            classifications.numeric,
            classifications.boolean,
            classifications.date_time,
            classifications.error,
            classifications.unsupported,
        )
    ):
        raise _ProtocolError("The live preflight classifications do not reconcile.")
    formulas_document = _object(item.get("formulas"), f"{label}.formulas")
    formula_samples = tuple(
        LiveFormulaSample(
            _positive_int(_object(raw, "formula sample").get("row"), "formula.row"),
            _text(
                _object(raw, "formula sample").get("formula"), "formula.formula"
            ),
        )
        for raw in _array(formulas_document.get("samples"), "formulas.samples")
    )
    formula_count = _nonnegative_int(formulas_document.get("count"), "formulas.count")
    formula_truncated = _boolean(
        formulas_document.get("samples_truncated"), "formulas.samples_truncated"
    )
    if (
        formula_count != classifications.formula
        or formula_count < len(formula_samples)
        or formula_truncated != (formula_count > len(formula_samples))
    ):
        raise _ProtocolError("The live preflight formula samples are inconsistent.")
    risk_document = _object(item.get("precision_risks"), f"{label}.precision_risks")
    risks = tuple(
        _parse_precision_risk(raw, risk_index)
        for risk_index, raw in enumerate(
            _array(risk_document.get("samples"), "precision_risks.samples")
        )
    )
    risk_cells = _nonnegative_int(risk_document.get("cells"), "precision_risks.cells")
    risks_truncated = _boolean(
        risk_document.get("samples_truncated"),
        "precision_risks.samples_truncated",
    )
    if len({risk.row for risk in risks}) > risk_cells:
        raise _ProtocolError("The live preflight precision risks are inconsistent.")
    return LiveColumnPreflightColumn(
        column_index,
        column_letter,
        _scalar(item.get("header_value"), f"{label}.header_value"),
        first_used,
        last_used,
        cells_examined,
        classifications,
        LiveColumnFormulas(formula_count, formula_samples, formula_truncated),
        LiveColumnPrecisionRisks(risk_cells, risks, risks_truncated),
    )


def _parse_live_conversion_plan_result(
    document: dict[str, object],
    warnings: list[object],
) -> LiveColumnConversionPlanResult:
    can_execute = _boolean(document.get("can_execute"), "can_execute")
    writes = _nonnegative_int(document.get("writes_performed"), "writes_performed")
    if writes != 0:
        raise _ProtocolError("The live conversion plan unexpectedly reported a write.")
    scope_fingerprint = _text(document.get("scope_fingerprint"), "scope_fingerprint")
    plan_fingerprint = _text(document.get("plan_fingerprint"), "plan_fingerprint")
    if not _is_prefixed_sha256(scope_fingerprint) or not _is_prefixed_sha256(
        plan_fingerprint
    ):
        raise _ProtocolError("The live conversion plan fingerprint is invalid.")
    target = _parse_live_conversion_plan_target(document.get("target"))
    effect = _parse_live_conversion_effect(document.get("effect"))
    recovery = _parse_live_conversion_recovery_plan(document.get("recovery"))
    columns = tuple(
        _parse_live_conversion_plan_column(value, index)
        for index, value in enumerate(_array(document.get("columns"), "columns"))
    )
    blockers = tuple(
        _parse_live_conversion_blocker(value, index)
        for index, value in enumerate(_array(document.get("blockers"), "blockers"))
    )
    if can_execute == bool(blockers):
        raise _ProtocolError("The live conversion plan readiness is contradictory.")
    if tuple(item.column_index for item in columns) != target.physical_columns:
        raise _ProtocolError("The live conversion plan columns contradict its target.")
    if target.data_rows_truncated != (
        target.data_rows_examined < target.data_rows_total
    ):
        raise _ProtocolError("The live conversion plan row coverage is contradictory.")
    totals = LiveConversionEffect(
        effect.target_type,
        sum(item.counts.cells_examined for item in columns),
        sum(item.counts.eligible for item in columns),
        sum(item.counts.already_compliant for item in columns),
        sum(item.counts.blank for item in columns),
        sum(
            item.counts.blocked_formula + item.counts.blocked_unsupported
            for item in columns
        ),
        sum(item.counts.blocked_formula for item in columns),
        sum(item.counts.blocked_unsupported for item in columns),
        sum(item.counts.precision_risk_cells for item in columns),
    )
    if totals != effect:
        raise _ProtocolError("The live conversion plan effect counts do not reconcile.")
    if (
        not recovery.required
        or recovery.will_overwrite
        or recovery.strategy != "excel_save_copy_as"
        or (can_execute and recovery.path is None)
        or (can_execute and effect.target_type != "text")
        or (can_execute and effect.eligible == 0)
        or (can_execute and target.data_rows_truncated)
    ):
        raise _ProtocolError("The live conversion plan safety contract is contradictory.")
    return LiveColumnConversionPlanResult(
        can_execute,
        writes,
        scope_fingerprint,
        plan_fingerprint,
        target,
        effect,
        recovery,
        columns,
        blockers,
        _parse_live_warnings(warnings),
    )


def _parse_live_conversion_plan_target(
    value: object,
) -> LiveConversionPlanTarget:
    target = _object(value, "result.target")
    columns = _positive_int_tuple(
        target.get("physical_columns"), "target.physical_columns"
    )
    if len(columns) > LIVE_MAXIMUM_COLUMNS or any(
        column > LIVE_MAXIMUM_EXCEL_COLUMN for column in columns
    ):
        raise _ProtocolError("The live conversion target has unsupported columns.")
    total = _nonnegative_int(target.get("data_rows_total"), "target.data_rows_total")
    examined = _nonnegative_int(
        target.get("data_rows_examined"), "target.data_rows_examined"
    )
    first = _optional_positive_int(
        target.get("data_first_row"), "target.data_first_row"
    )
    last = _optional_positive_int(target.get("data_last_row"), "target.data_last_row")
    if (
        examined > total
        or (first is None) != (last is None)
        or (first is None) != (total == 0)
        or (first is not None and last is not None and last - first + 1 != total)
    ):
        raise _ProtocolError("The live conversion target row bounds are inconsistent.")
    header_row = _positive_int(target.get("header_row"), "target.header_row")
    if header_row != LIVE_HEADER_ROW:
        raise _ProtocolError("The live conversion target header row did not match.")
    return LiveConversionPlanTarget(
        _positive_int(target.get("process_id"), "target.process_id"),
        _text(target.get("workbook_token"), "target.workbook_token"),
        _text(target.get("workbook_name"), "target.workbook_name"),
        _optional_text(target.get("full_path"), "target.full_path"),
        _boolean(target.get("saved"), "target.saved"),
        _boolean(target.get("read_only"), "target.read_only"),
        _optional_boolean(target.get("autosave_enabled"), "target.autosave_enabled"),
        _optional_boolean(
            target.get("workbook_protected"), "target.workbook_protected"
        ),
        _text(target.get("worksheet"), "target.worksheet"),
        _optional_boolean(
            target.get("worksheet_protected"), "target.worksheet_protected"
        ),
        columns,
        header_row,
        _parse_used_range(target.get("used_range")),
        first,
        last,
        total,
        examined,
        _boolean(target.get("data_rows_truncated"), "target.data_rows_truncated"),
    )


def _parse_live_conversion_effect(value: object) -> LiveConversionEffect:
    item = _object(value, "result.effect")
    target_type = _text(item.get("target_type"), "effect.target_type")
    if target_type not in {"text", "number"}:
        raise _ProtocolError("The live conversion effect target is unsupported.")
    counts = tuple(
        _nonnegative_int(item.get(field), f"effect.{field}")
        for field in (
            "cells_examined",
            "eligible",
            "already_compliant",
            "blank",
            "blocked",
            "formulas",
            "unsupported",
            "precision_risk_cells",
        )
    )
    result = LiveConversionEffect(target_type, *counts)  # type: ignore[arg-type]
    if (
        result.blocked != result.formulas + result.unsupported
        or result.cells_examined
        != result.eligible
        + result.already_compliant
        + result.blank
        + result.blocked
        or result.precision_risk_cells > result.cells_examined
    ):
        raise _ProtocolError("The live conversion effect is contradictory.")
    return result


def _parse_live_conversion_recovery_plan(
    value: object,
) -> LiveConversionRecoveryPlan:
    item = _object(value, "result.recovery")
    return LiveConversionRecoveryPlan(
        _boolean(item.get("required"), "recovery.required"),
        _text(item.get("strategy"), "recovery.strategy"),
        _optional_text(item.get("path"), "recovery.path"),
        _boolean(item.get("will_overwrite"), "recovery.will_overwrite"),
    )


def _parse_live_conversion_plan_column(
    value: object,
    index: int,
) -> LiveConversionPlanColumn:
    label = f"columns[{index}]"
    item = _object(value, label)
    column_index = _positive_int(item.get("column_index"), f"{label}.column_index")
    column_letter = _text(item.get("column_letter"), f"{label}.column_letter")
    if column_index > LIVE_MAXIMUM_EXCEL_COLUMN or column_letter != _column_letter(
        column_index
    ):
        raise _ProtocolError("The live conversion physical column is inconsistent.")
    count_document = _object(item.get("counts"), f"{label}.counts")
    counts = LiveConversionCounts(
        *(
            _nonnegative_int(count_document.get(field), f"counts.{field}")
            for field in (
                "cells_examined",
                "blank",
                "already_compliant",
                "eligible",
                "blocked_formula",
                "blocked_unsupported",
                "precision_risk_cells",
            )
        )
    )
    if (
        counts.cells_examined
        != counts.blank
        + counts.already_compliant
        + counts.eligible
        + counts.blocked_formula
        + counts.blocked_unsupported
        or counts.precision_risk_cells > counts.cells_examined
    ):
        raise _ProtocolError("The live conversion column counts do not reconcile.")
    samples = tuple(
        _parse_live_conversion_sample(raw, sample_index)
        for sample_index, raw in enumerate(
            _array(item.get("conversion_samples"), "conversion_samples")
        )
    )
    samples_truncated = _boolean(
        item.get("conversion_samples_truncated"),
        "conversion_samples_truncated",
    )
    if (
        len(samples) > counts.eligible
        or samples_truncated != (counts.eligible > len(samples))
    ):
        raise _ProtocolError("The live conversion samples are inconsistent.")
    risks = tuple(
        _parse_precision_risk(raw, risk_index)
        for risk_index, raw in enumerate(
            _array(item.get("precision_risks"), "precision_risks")
        )
    )
    risks_truncated = _boolean(
        item.get("precision_risks_truncated"), "precision_risks_truncated"
    )
    if len({risk.row for risk in risks}) > counts.precision_risk_cells:
        raise _ProtocolError("The live conversion precision risks are inconsistent.")
    return LiveConversionPlanColumn(
        column_index,
        column_letter,
        _scalar(item.get("header_value"), f"{label}.header_value"),
        counts,
        samples,
        samples_truncated,
        risks,
        risks_truncated,
    )


def _parse_live_conversion_sample(
    value: object,
    index: int,
) -> LiveConversionSample:
    item = _object(value, f"conversion_samples[{index}]")
    return LiveConversionSample(
        _positive_int(item.get("row"), "conversion_sample.row"),
        _scalar(item.get("input_preview"), "conversion_sample.input_preview"),
        _text(item.get("output_text"), "conversion_sample.output_text"),
    )


def _parse_live_conversion_blocker(
    value: object,
    index: int,
) -> LiveConversionBlocker:
    item = _object(value, f"blockers[{index}]")
    details = _object(item.get("details"), "blocker.details")
    return LiveConversionBlocker(
        _text(item.get("code"), "blocker.code"),
        _text(item.get("message"), "blocker.message"),
        MappingProxyType(dict(details)),
    )


def _parse_live_conversion_result(
    document: dict[str, object],
    warnings: list[object],
) -> LiveColumnConversionResult:
    state = _text(document.get("state"), "result.state")
    if state not in {"succeeded", "failed", "partial_failure"}:
        raise _ProtocolError("The live conversion result state is unsupported.")
    target = _parse_live_conversion_execution_target(document.get("target"))
    fingerprint = _text(
        document.get("reviewed_plan_fingerprint"), "reviewed_plan_fingerprint"
    )
    if not _is_prefixed_sha256(fingerprint):
        raise _ProtocolError("The reviewed live plan fingerprint is invalid.")
    changed = _nonnegative_int(document.get("changed_cells"), "changed_cells")
    compliant = _nonnegative_int(
        document.get("already_compliant_cells"), "already_compliant_cells"
    )
    blank = _nonnegative_int(document.get("blank_cells"), "blank_cells")
    completed = _positive_int_tuple_or_empty(
        document.get("columns_completed"), "columns_completed"
    )
    if not set(completed).issubset(target.physical_columns):
        raise _ProtocolError("The completed live columns contradict the target.")
    recovery_document = _object(document.get("recovery"), "result.recovery")
    recovery = LiveConversionExecutionRecovery(
        _text(recovery_document.get("path"), "recovery.path"),
        _boolean(recovery_document.get("verified"), "recovery.verified"),
    )
    mutation_started = _boolean(
        document.get("mutation_started"), "mutation_started"
    )
    dirty = _boolean(document.get("workbook_dirty"), "workbook_dirty")
    lifecycle = (
        _boolean(document.get("workbook_saved"), "workbook_saved"),
        _boolean(document.get("workbook_closed"), "workbook_closed"),
        _boolean(document.get("application_closed"), "application_closed"),
    )
    if any(lifecycle):
        raise _ProtocolError("The live conversion lifecycle is contradictory.")
    failure = (
        None
        if document.get("failure") is None
        else _parse_live_conversion_failure(document.get("failure"))
    )
    if (
        (state == "succeeded" and (failure is not None or not mutation_started))
        or (
            state == "failed"
            and (failure is None or mutation_started)
        )
        or (
            state == "partial_failure"
            and (failure is None or not mutation_started)
        )
        or (mutation_started and not recovery.verified)
        or (mutation_started and not dirty)
        or (state == "succeeded" and completed != target.physical_columns)
    ):
        raise _ProtocolError("The live conversion state contradicts its effects.")
    if failure is not None:
        if failure.column_index is not None and failure.column_index not in (
            target.physical_columns
        ):
            raise _ProtocolError("The live conversion failure column is not targeted.")
        if (
            failure.stage == "recovery"
            and (recovery.verified or mutation_started or completed)
        ) or (
            failure.stage == "revalidate"
            and (not recovery.verified or mutation_started or completed)
        ) or (failure.stage == "write" and not recovery.verified):
            raise _ProtocolError("The live conversion failure stage is contradictory.")
    if target.data_first_row is not None and target.data_last_row is not None:
        completed_cells = (
            target.data_last_row - target.data_first_row + 1
        ) * len(completed)
        if changed + compliant + blank != completed_cells:
            raise _ProtocolError("The completed live conversion counts do not reconcile.")
    elif changed or compliant or blank or completed:
        raise _ProtocolError("An empty live conversion scope reported effects.")
    return LiveColumnConversionResult(
        state,  # type: ignore[arg-type]
        target,
        fingerprint,
        changed,
        compliant,
        blank,
        completed,
        recovery,
        mutation_started,
        dirty,
        *lifecycle,
        failure,
        _parse_live_warnings(warnings),
    )


def _parse_live_conversion_execution_target(
    value: object,
) -> LiveConversionExecutionTarget:
    item = _object(value, "result.target")
    columns = _positive_int_tuple(item.get("physical_columns"), "target.physical_columns")
    if len(columns) > LIVE_MAXIMUM_COLUMNS or any(
        column > LIVE_MAXIMUM_EXCEL_COLUMN for column in columns
    ):
        raise _ProtocolError("The live conversion target has unsupported columns.")
    first = _optional_positive_int(item.get("data_first_row"), "target.data_first_row")
    last = _optional_positive_int(item.get("data_last_row"), "target.data_last_row")
    if (first is None) != (last is None) or (
        first is not None and last is not None and first > last
    ):
        raise _ProtocolError("The live conversion result row bounds are inconsistent.")
    return LiveConversionExecutionTarget(
        _positive_int(item.get("process_id"), "target.process_id"),
        _text(item.get("workbook_token"), "target.workbook_token"),
        _text(item.get("workbook_name"), "target.workbook_name"),
        _text(item.get("full_path"), "target.full_path"),
        _text(item.get("worksheet"), "target.worksheet"),
        columns,
        first,
        last,
    )


def _parse_live_conversion_failure(value: object) -> LiveConversionFailure:
    item = _object(value, "result.failure")
    stage = _text(item.get("stage"), "failure.stage")
    if stage not in {"revalidate", "recovery", "write"}:
        raise _ProtocolError("The live conversion failure stage is unsupported.")
    return LiveConversionFailure(
        _text(item.get("code"), "failure.code"),
        _text(item.get("message"), "failure.message"),
        stage,  # type: ignore[arg-type]
        _optional_positive_int(item.get("column_index"), "failure.column_index"),
        _optional_text(item.get("exception_type"), "failure.exception_type"),
        _optional_int(item.get("com_hresult"), "failure.com_hresult"),
    )


def _parse_live_application(value: object, index: int) -> LiveExcelApplication:
    item = _object(value, f"applications[{index}]")
    workbooks = tuple(
        _parse_live_workbook(raw, index, workbook_index)
        for workbook_index, raw in enumerate(
            _array(item.get("workbooks"), f"applications[{index}].workbooks")
        )
    )
    returned = _nonnegative_int(
        item.get("workbooks_returned"), "workbooks_returned"
    )
    total = _nonnegative_int(item.get("workbooks_total"), "workbooks_total")
    truncated = _boolean(item.get("workbooks_truncated"), "workbooks_truncated")
    if (
        returned != len(workbooks)
        or total < returned
        or (truncated and total == returned)
    ):
        raise _ProtocolError("The live inventory workbook counts are inconsistent.")
    return LiveExcelApplication(
        _positive_int(item.get("process_id"), "application.process_id"),
        _boolean(item.get("foreground"), "application.foreground"),
        _boolean(item.get("visible"), "application.visible"),
        total,
        truncated,
        workbooks,
    )


def _parse_live_workbook(
    value: object,
    application_index: int,
    workbook_index: int,
) -> LiveExcelWorkbook:
    label = f"applications[{application_index}].workbooks[{workbook_index}]"
    item = _object(value, label)
    sheets = tuple(
        _parse_live_sheet(raw, label, sheet_index)
        for sheet_index, raw in enumerate(_array(item.get("sheets"), f"{label}.sheets"))
    )
    returned = _nonnegative_int(item.get("sheets_returned"), "sheets_returned")
    total = _nonnegative_int(item.get("sheets_total"), "sheets_total")
    truncated = _boolean(item.get("sheets_truncated"), "sheets_truncated")
    if (
        returned != len(sheets)
        or total < returned
        or (truncated and total == returned)
    ):
        raise _ProtocolError("The live inventory worksheet counts are inconsistent.")
    return LiveExcelWorkbook(
        _text(item.get("token"), "workbook.token"),
        _positive_int(item.get("process_id"), "workbook.process_id"),
        _text(item.get("name"), "workbook.name"),
        _optional_text(item.get("full_path"), "workbook.full_path"),
        _boolean(item.get("saved"), "workbook.saved"),
        _boolean(item.get("read_only"), "workbook.read_only"),
        _optional_boolean(item.get("autosave_enabled"), "workbook.autosave_enabled"),
        _optional_text(item.get("active_sheet"), "workbook.active_sheet"),
        total,
        truncated,
        sheets,
    )


def _parse_live_sheet(value: object, label: str, index: int) -> LiveExcelSheet:
    item = _object(value, f"{label}.sheets[{index}]")
    state = _text(item.get("state"), "worksheet.state")
    if state not in {"visible", "hidden", "very_hidden", "unknown"}:
        raise _ProtocolError("The live inventory worksheet state is unsupported.")
    return LiveExcelSheet(
        _positive_int(item.get("position"), "worksheet.position"),
        _text(item.get("name"), "worksheet.name"),
        state,  # type: ignore[arg-type]
    )


def _parse_live_format_profile_result(
    document: dict[str, object],
    warnings: list[object],
) -> LiveFormatProfileResult:
    state = _text(document.get("state"), "result.state")
    if state not in {"succeeded", "failed", "partial_failure"}:
        raise _ProtocolError("The live format result state is unsupported.")
    target = _object(document.get("target"), "result.target")
    scope = _text(target.get("scope"), "target.scope")
    if scope not in {"worksheet", "workbook"}:
        raise _ProtocolError("The live format result scope is unsupported.")
    profile = _object(document.get("profile"), "result.profile")
    if (profile.get("profile_id"), profile.get("profile_version")) != (
        "standard_data",
        "1.0",
    ):
        raise _ProtocolError("The live format profile is unsupported.")
    formatted = _text_tuple(document.get("formatted_sheets"), "formatted_sheets")
    hidden = _text_tuple(document.get("skipped_hidden_sheets"), "skipped_hidden_sheets")
    filters_added = _text_tuple(document.get("filter_added_sheets"), "filter_added_sheets")
    existing_filters = _text_tuple(
        document.get("existing_filter_sheets"), "existing_filter_sheets"
    )
    failures = tuple(
        _parse_live_format_failure(value, index)
        for index, value in enumerate(_array(document.get("failures"), "failures"))
    )
    if (
        not set(filters_added).issubset(formatted)
        or not set(existing_filters).issubset(formatted)
        or set(formatted) & set(hidden)
        or set(formatted) & {item.worksheet for item in failures}
    ):
        raise _ProtocolError("The live format worksheet effects are contradictory.")
    if (
        state == "succeeded" and failures
        or state == "failed" and (not failures or formatted)
        or state == "partial_failure" and (not failures or not formatted)
    ):
        raise _ProtocolError("The live format result state contradicts its effects.")
    lifecycle = (
        _boolean(document.get("workbook_saved"), "workbook_saved"),
        _boolean(document.get("workbook_closed"), "workbook_closed"),
        _boolean(document.get("application_closed"), "application_closed"),
    )
    if any(lifecycle):
        raise _ProtocolError("The live format response contradicted its lifecycle contract.")
    return LiveFormatProfileResult(
        state,  # type: ignore[arg-type]
        _text(target.get("workbook_token"), "target.workbook_token"),
        _text(target.get("workbook_name"), "target.workbook_name"),
        scope,  # type: ignore[arg-type]
        "standard_data",
        "1.0",
        formatted,
        hidden,
        filters_added,
        existing_filters,
        failures,
        *lifecycle,
        _parse_live_warnings(warnings),
    )


def _parse_live_format_failure(value: object, index: int) -> LiveFormatFailure:
    item = _object(value, f"failures[{index}]")
    return LiveFormatFailure(
        _text(item.get("worksheet"), "failure.worksheet"),
        _text(item.get("code"), "failure.code"),
        _text(item.get("message"), "failure.message"),
    )


def _parse_live_warnings(values: list[object]) -> tuple[LiveExcelWarning, ...]:
    return tuple(
        LiveExcelWarning(
            _text(_object(value, "warning").get("code"), "warning.code"),
            _text(_object(value, "warning").get("message"), "warning.message"),
            MappingProxyType(
                dict(_object(_object(value, "warning").get("details"), "warning.details"))
            ),
        )
        for value in values
    )


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
        parameters = _object(document.get("parameters"), "parameters")
        allow_overwrite = _boolean(
            parameters.get("allow_overwrite"), "parameters.allow_overwrite"
        )
        parameter_policy = _text(
            parameters.get("output_policy"), "parameters.output_policy"
        )
        if parameter_policy not in {"create_only", "explicit_replace"}:
            raise _ProtocolError("The plan returned an unsupported output policy.")
        if (
            parameter_policy != effect.output_policy
            or allow_overwrite != (parameter_policy == "explicit_replace")
        ):
            raise _ProtocolError("The plan returned contradictory overwrite semantics.")
        creates = sum(item.output_disposition == "create" for item in inputs)
        replacements = sum(item.output_disposition == "replace" for item in inputs)
        if (
            creates != effect.outputs_to_create
            or replacements != effect.outputs_to_replace
            or creates + replacements != effect.output_files
        ):
            raise _ProtocolError("The plan returned contradictory output totals.")
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
    disposition = item.get("output_disposition")
    if disposition not in {"create", "replace"}:
        raise _ProtocolError("The plan returned an unsupported output disposition.")
    destination = _parse_destination_state(item.get("destination_state"))
    if (disposition == "replace") != destination.exists:
        raise _ProtocolError(
            "The plan returned a contradictory destination disposition."
        )
    return PlannedWorkbook(
        _text(item.get("input_id"), "input.input_id"),
        _text(item.get("original_path"), "input.original_path"),
        _text(item.get("resolved_path"), "input.resolved_path"),
        _text(item.get("worksheet"), "input.worksheet"),
        _positive_int_tuple(item.get("physical_columns"), "input.physical_columns"),
        _nonnegative_int(item.get("rows_to_write"), "input.rows_to_write"),
        _text(item.get("output_path"), "input.output_path"),
        disposition,  # type: ignore[arg-type]
        destination,
    )


def _parse_destination_state(value: object) -> DestinationState:
    item = _object(value, "input.destination_state")
    state = DestinationState(
        _boolean(item.get("exists"), "destination_state.exists"),
        _optional_nonnegative_int(
            item.get("size_bytes"), "destination_state.size_bytes"
        ),
        _optional_nonnegative_int(
            item.get("modified_ns"), "destination_state.modified_ns"
        ),
        _optional_nonnegative_int(
            item.get("created_ns"), "destination_state.created_ns"
        ),
        _optional_nonnegative_int(
            item.get("device"), "destination_state.device"
        ),
        _optional_nonnegative_int(
            item.get("inode"), "destination_state.inode"
        ),
        _optional_text(item.get("sha256"), "destination_state.sha256"),
    )
    details = (
        state.size_bytes,
        state.modified_ns,
        state.created_ns,
        state.device,
        state.inode,
        state.sha256,
    )
    if state.exists:
        if any(detail is None for detail in details) or not _is_sha256(state.sha256):
            raise _ProtocolError(
                "An existing destination omitted its reviewed identity."
            )
    elif any(detail is not None for detail in details):
        raise _ProtocolError(
            "A missing destination unexpectedly reported file identity."
        )
    return state


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
        _nonnegative_int(
            item.get("outputs_to_create"), "effect.outputs_to_create"
        ),
        _nonnegative_int(
            item.get("outputs_to_replace"), "effect.outputs_to_replace"
        ),
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
    created = tuple(
        _text(value, "outputs_created")
        for value in _array(document.get("outputs_created"), "outputs_created")
    )
    replaced = tuple(
        _text(value, "outputs_replaced")
        for value in _array(document.get("outputs_replaced"), "outputs_replaced")
    )
    writes = _nonnegative_int(document.get("writes_performed"), "writes_performed")
    effects_started = _boolean(document.get("effects_started"), "effects_started")
    overwritten = _nonnegative_int(
        document.get("outputs_overwritten"), "outputs_overwritten"
    )
    normalized_created = {os.path.normcase(value) for value in created}
    normalized_replaced = {os.path.normcase(value) for value in replaced}
    if (
        len(normalized_created) != len(created)
        or len(normalized_replaced) != len(replaced)
        or normalized_created & normalized_replaced
        or overwritten != len(replaced)
        or writes != len(created) + len(replaced)
    ):
        raise _ProtocolError("Execution output counts are contradictory.")
    completed_outputs = created + replaced
    if state == "succeeded" and (not effects_started or not completed_outputs):
        raise _ProtocolError("Successful execution reported no effect.")
    if state == "failed_before_effect" and (
        effects_started or completed_outputs or writes
    ):
        raise _ProtocolError("A before-effect failure reported an output effect.")
    if state == "failed_after_partial_effect" and (
        not effects_started or not completed_outputs
    ):
        raise _ProtocolError("A partial-effect failure reported no completed output.")
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
    receipt_created: set[str] = set()
    receipt_replaced: set[str] = set()
    for item in succeeded_inputs:
        if item.output_path is None:
            raise _ProtocolError("A successful execution input omitted its output.")
        key = os.path.normcase(item.output_path)
        if item.code == "automation.output_created":
            receipt_created.add(key)
        elif item.code == "automation.output_replaced":
            receipt_replaced.add(key)
        else:
            raise _ProtocolError(
                "A successful execution input returned an unsupported effect code."
            )
    if (
        receipt_created != normalized_created
        or receipt_replaced != normalized_replaced
    ):
        raise _ProtocolError(
            "Execution input receipts contradict the published output lists."
        )
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
        created,
        replaced,
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
        "inventory": LIVE_INVENTORY_OPERATION,
        "apply": LIVE_FORMAT_PROFILE_OPERATION,
        "capabilities": DESCRIBE_CAPABILITIES_OPERATION,
        "preflight": LIVE_PREFLIGHT_OPERATION,
        "conversion_plan": LIVE_CONVERSION_PLAN_OPERATION,
        "conversion_execute": LIVE_CONVERSION_EXECUTE_OPERATION,
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


def _optional_boolean(value: object, label: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, label)


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _ProtocolError(f"{label} must be a non-negative integer.")
    return value


def _positive_int(value: object, label: str) -> int:
    result = _nonnegative_int(value, label)
    if result < 1:
        raise _ProtocolError(f"{label} must be a positive integer.")
    return result


def _text_tuple(value: object, label: str) -> tuple[str, ...]:
    return tuple(_text(item, label) for item in _array(value, label))


def _live_limit(value: object, *, maximum: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ExcelAutomationInputError(
            f"{label} must be an integer from 1 through {maximum}."
        )


def _optional_nonnegative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, label)


def _optional_positive_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, label)


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _ProtocolError(f"{label} must be an integer or null.")
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


def _is_prefixed_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and _is_sha256(value.removeprefix("sha256:"))
    )


def _scalar(value: object, label: str) -> LiveScalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise _ProtocolError(f"{label} must be a finite JSON scalar or null.")


def _parse_used_range(value: object) -> LiveUsedRange:
    item = _object(value, "used_range")
    result = LiveUsedRange(
        _positive_int(item.get("first_row"), "used_range.first_row"),
        _positive_int(item.get("last_row"), "used_range.last_row"),
        _positive_int(item.get("first_column"), "used_range.first_column"),
        _positive_int(item.get("last_column"), "used_range.last_column"),
    )
    if (
        result.first_row > result.last_row
        or result.first_column > result.last_column
        or result.last_column > LIVE_MAXIMUM_EXCEL_COLUMN
    ):
        raise _ProtocolError("The live used range is inconsistent.")
    return result


def _parse_data_rows(value: object) -> LiveDataRows:
    item = _object(value, "data_rows")
    first = _optional_positive_int(item.get("first"), "data_rows.first")
    last = _optional_positive_int(item.get("last"), "data_rows.last")
    total = _nonnegative_int(item.get("total"), "data_rows.total")
    examined = _nonnegative_int(item.get("examined"), "data_rows.examined")
    truncated = _boolean(item.get("truncated"), "data_rows.truncated")
    if (
        examined > total
        or truncated != (examined < total)
        or (first is None) != (last is None)
        or (first is None) != (total == 0)
        or (first is not None and last is not None and last - first + 1 != total)
    ):
        raise _ProtocolError("The live data-row bounds are inconsistent.")
    return LiveDataRows(first, last, total, examined, truncated)


def _parse_precision_risk(value: object, index: int) -> LivePrecisionRisk:
    item = _object(value, f"precision_risks[{index}]")
    return LivePrecisionRisk(
        _positive_int(item.get("row"), "precision_risk.row"),
        _text(item.get("code"), "precision_risk.code"),
        _scalar(item.get("value_preview"), "precision_risk.value_preview"),
    )


def _column_letter(column: int) -> str:
    letters = ""
    current = column
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _validate_live_target(workbook_token: object, worksheet: object) -> None:
    if (
        not isinstance(workbook_token, str)
        or not workbook_token.strip()
        or len(workbook_token) > 8192
    ):
        raise ExcelAutomationInputError(
            "The live workbook token must contain 1 through 8192 characters."
        )
    if (
        not isinstance(worksheet, str)
        or not worksheet
        or len(worksheet) > 31
    ):
        raise ExcelAutomationInputError(
            "The live worksheet name must contain 1 through 31 characters."
        )


def _validate_live_columns(columns: object) -> None:
    if (
        not isinstance(columns, tuple)
        or not columns
        or len(columns) > LIVE_MAXIMUM_COLUMNS
        or any(
            isinstance(column, bool)
            or not isinstance(column, int)
            or not 1 <= column <= LIVE_MAXIMUM_EXCEL_COLUMN
            for column in columns
        )
        or len(set(columns)) != len(columns)
    ):
        raise ExcelAutomationInputError(
            "Choose 1 through 100 unique physical Excel columns."
        )


def _validate_live_recovery_path(value: object) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ExcelAutomationInputError("The live recovery path must be text.")
    path = Path(value)
    if not path.is_absolute() or path.suffix.casefold() != ".xlsx":
        raise ExcelAutomationInputError(
            "The live recovery path must be an absolute .xlsx path."
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
        "inventory": "inventory_failed",
        "apply": "apply_unknown",
        "capabilities": "capabilities_failed",
        "preflight": "preflight_failed",
        "conversion_plan": "conversion_plan_failed",
        "conversion_execute": "conversion_execute_unknown",
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
