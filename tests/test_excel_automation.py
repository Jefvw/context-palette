from __future__ import annotations

from dataclasses import FrozenInstanceError
from copy import deepcopy
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.excel_automation import (
    AUTOMATION_CONTRACT_VERSION,
    EXCEL_AUTOMATION_ID,
    EXCEL_AUTOMATION_VERSION,
    AutomationCallResult,
    CsvAutomationInvocation,
    DescribeCapabilitiesResult,
    DescribeAutomationsResult,
    ExcelAutomationCoordinator,
    ExcelAutomationInputError,
    ExcelAutomationSettings,
    ExcelAutomationSettingsError,
    ExcelCapabilitySupports,
    ExecuteAutomationResult,
    LiveExcelInventoryLimits,
    LiveExcelInventoryResult,
    LiveColumnConversionInvocation,
    LiveColumnConversionPlanInvocation,
    LiveColumnConversionPlanResult,
    LiveColumnConversionResult,
    LiveColumnPreflightInvocation,
    LiveColumnPreflightResult,
    LiveFormatProfileInvocation,
    LiveFormatProfileResult,
    LiveFormatAutoSave,
    LiveFormatFailure,
    LIVE_NATIVE_TEXT_OPERATION,
    LIVE_NATIVE_TEXT_AUTOMATION_ID,
    LiveTextToColumnsInvocation,
    LiveTextToColumnsResult,
    PlanAutomationResult,
    PythonExcelProcessClient,
    build_describe_automations_request,
    build_describe_capabilities_request,
    build_execute_automation_request,
    build_apply_live_format_profile_request,
    build_apply_live_text_to_columns_as_text_request,
    build_plan_automation_request,
    build_inventory_live_excel_request,
    build_preflight_live_columns_request,
    build_plan_live_column_conversion_request,
    build_convert_live_column_representation_request,
    csv_invocation,
    discover_direct_sibling_python_excel_launcher,
    load_excel_automation_settings,
    parse_automation_response,
    save_excel_automation_settings,
    workbook_paths_from_workspace,
)


FINGERPRINT = "a" * 64


def _envelope(
    operation: str,
    request_id: str,
    result: dict[str, object] | None,
    *,
    status: str = "success",
    error: dict[str, object] | None = None,
    warnings: list[dict[str, object]] | None = None,
) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": "1.0",
                "request_id": request_id,
                "operation": operation,
                "operation_version": "1.0",
                "status": status,
                "duration_ms": 3,
                "paths": {"input": None, "output": None, "backup": None},
                "result": result,
                "warnings": warnings or [],
                "error": error,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        + b"\n"
    )


def _describe_result(*, available: bool = True) -> dict[str, object]:
    return {
        "contract_schema_version": AUTOMATION_CONTRACT_VERSION,
        "automations": [
            {
                "automation_id": EXCEL_AUTOMATION_ID,
                "automation_version": EXCEL_AUTOMATION_VERSION,
                "availability": {
                    "available": available,
                    "supported_phases": ["describe", "plan", "execute"],
                    "code": None if available else "availability.missing",
                    "reason": None if available else "Not installed.",
                },
            }
        ],
    }


def _ready_plan_result(
    source: Path,
    output: Path,
    *,
    disposition: str = "create",
    allow_overwrite: bool = False,
) -> dict[str, object]:
    output_policy = "explicit_replace" if allow_overwrite else "create_only"
    return {
        "state": "ready",
        "automation": {
            "automation_id": EXCEL_AUTOMATION_ID,
            "automation_version": EXCEL_AUTOMATION_VERSION,
        },
        "requirements": [],
        "blockers": [],
        "inputs": [
            {
                "input_id": "input-1",
                "kind": "closed_workbook_file",
                "original_path": str(source),
                "resolved_path": str(source),
                "source_size_bytes": 12,
                "source_sha256": "b" * 64,
                "worksheet": "Données",
                "physical_columns": [1, 3],
                "rows_to_write": 20,
                "output_path": str(output / "book.csv"),
                "output_disposition": disposition,
                "destination_state": (
                    {
                        "exists": True,
                        "size_bytes": 19,
                        "modified_ns": 123456789,
                        "created_ns": 123456000,
                        "device": 7,
                        "inode": 11,
                        "sha256": "c" * 64,
                    }
                    if disposition == "replace"
                    else {
                        "exists": False,
                        "size_bytes": None,
                        "modified_ns": None,
                        "created_ns": None,
                        "device": None,
                        "inode": None,
                        "sha256": None,
                    }
                ),
            }
        ],
        "parameters": {
            "output_directory": str(output),
            "delimiter": ",",
            "encoding": "utf-8-sig",
            "formula_mode": "formulas",
            "excel_safe": True,
            "allow_overwrite": allow_overwrite,
            "worksheet_selector_policy": (
                "single_sheet_automatic_otherwise_exact_required"
            ),
            "physical_column_selector_policy": "all_used_physical_columns",
            "output_policy": output_policy,
        },
        "warnings": [],
        "effect": {
            "effect_class": "creates_output",
            "mutates_inputs": False,
            "output_policy": output_policy,
            "input_files": 1,
            "output_files": 1,
            "rows_to_write": 20,
            "outputs_to_create": int(disposition == "create"),
            "outputs_to_replace": int(disposition == "replace"),
        },
        "predicted_artifacts": [
            {
                "artifact_id": "csv_files",
                "kind": "file",
                "path": str(output / "book.csv"),
                "media_type": "text/csv",
                "input_id": "input-1",
            },
            {
                "artifact_id": "output_directory",
                "kind": "folder",
                "path": str(output),
                "media_type": None,
                "input_id": None,
            },
        ],
        "plan_fingerprint": FINGERPRINT,
        "writes_performed": 0,
    }


def _execution_result(
    source: Path,
    output: Path,
    *,
    state: str = "succeeded",
    replace: bool = False,
) -> dict[str, object]:
    completed = [str(output / "book.csv")] if state != "failed_before_effect" else []
    created = [] if replace else completed
    replaced = completed if replace else []
    effects_started = state != "failed_before_effect"
    inputs = (
        [
            {
                "input_id": "input-1",
                "outcome": "succeeded",
                "code": (
                    "automation.output_replaced"
                    if replace
                    else "automation.output_created"
                ),
                "message": (
                    "The reviewed CSV output was replaced."
                    if replace
                    else "The reviewed CSV output was created."
                ),
                "source_path": str(source),
                "worksheet": "Données",
                "physical_columns": [1, 3],
                "output_path": str(output / "book.csv"),
                "rows_written": 20,
                "columns_written": 2,
                "escaped_cells": 0,
            }
        ]
        if completed
        else []
    )
    return {
        "state": state,
        "automation": {
            "automation_id": EXCEL_AUTOMATION_ID,
            "automation_version": EXCEL_AUTOMATION_VERSION,
        },
        "reviewed_plan_fingerprint": FINGERPRINT,
        "final_plan_fingerprint": FINGERPRINT,
        "effects_started": effects_started,
        "writes_performed": len(completed),
        "inputs": inputs,
        "source_effect": {"mutates_inputs": False, "workbooks_saved": 0},
        "outputs_created": created,
        "outputs_replaced": replaced,
        "outputs_overwritten": len(replaced),
        "artifacts": (
            [
                {
                    "artifact_id": "csv_files",
                    "kind": "file",
                    "path": completed[0],
                    "media_type": "text/csv",
                    "input_id": "input-1",
                },
                {
                    "artifact_id": "output_directory",
                    "kind": "folder",
                    "path": str(output),
                    "media_type": None,
                    "input_id": None,
                },
            ]
            if completed
            else []
        ),
        "warnings": [],
        "code": (
            "automation.succeeded"
            if state == "succeeded"
            else "conflict.automation_plan_stale"
            if state == "failed_before_effect"
            else "automation.partial_commit"
        ),
        "message": "Reviewed execution result.",
        "retryable": state == "failed_before_effect",
    }


def _live_inventory_result() -> dict[str, object]:
    return {
        "applications_total": 1,
        "applications_returned": 1,
        "applications_truncated": False,
        "applications": [
            {
                "process_id": 7812,
                "foreground": True,
                "visible": True,
                "workbooks_total": 1,
                "workbooks_returned": 1,
                "workbooks_truncated": False,
                "workbooks": [
                    {
                        "token": "live-workbook-v1.classeur-é",
                        "process_id": 7812,
                        "name": "Classeur été.xlsx",
                        "full_path": "C:/Users/Élodie/Classeur été.xlsx",
                        "saved": True,
                        "read_only": False,
                        "autosave_enabled": False,
                        "active_sheet": "Données",
                        "sheets_total": 2,
                        "sheets_returned": 2,
                        "sheets_truncated": False,
                        "sheets": [
                            {"position": 1, "name": "Données", "state": "visible"},
                            {"position": 2, "name": "Caché", "state": "hidden"},
                        ],
                    }
                ],
            }
        ],
    }


def _live_format_result(*, state: str = "succeeded") -> dict[str, object]:
    formatted = ["Données"] if state != "failed" else []
    failures = (
        []
        if state == "succeeded"
        else [
            {
                "worksheet": "Résumé",
                "code": "operation.live_format_failed",
                "message": "Excel rejected the format profile.",
            }
        ]
    )
    return {
        "state": state,
        "target": {
            "workbook_token": "live-workbook-v1.classeur-é",
            "workbook_name": "Classeur été.xlsx",
            "scope": "workbook" if state == "partial_failure" else "worksheet",
        },
        "profile": {"profile_id": "standard_data", "profile_version": "1.0"},
        "formatted_sheets": formatted,
        "skipped_hidden_sheets": ["Caché"] if state == "partial_failure" else [],
        "filter_added_sheets": formatted,
        "existing_filter_sheets": [],
        "failures": failures,
        "workbook_saved": False,
        "workbook_closed": False,
        "application_closed": False,
    }


def _capabilities_result(
    *, available: bool = True, operation_version: str = "1.0"
) -> dict[str, object]:
    return {
        "capabilities": [
            {
                "operation": "convert_live_column_representation",
                "operation_version": operation_version,
                "title": "Convert open Excel columns to text",
                "description": "Convert reviewed physical columns to text.",
                "backend": "xlwings",
                "input_context": "live_excel",
                "input_extensions": [],
                "input_count": {"minimum": 0, "maximum": 0},
                "effect_class": "live_mutation",
                "output_class": "none",
                "supports": {
                    "worksheet_selection": True,
                    "column_selection": True,
                    "in_place": False,
                    "planning": True,
                },
                "plan_operation": "plan_live_column_conversion",
                "plan_operation_version": "1.0",
                "requires_excel": True,
                "availability": {
                    "available": available,
                    "reason": None if available else "Install the Excel extras.",
                },
            }
        ]
    }


def _live_preflight_result(*, truncated: bool = False) -> dict[str, object]:
    return {
        "workbook": {
            "token": "live-workbook-v1.classeur-é",
            "process_id": 7812,
            "name": "Classeur été.xlsx",
            "full_path": "C:/Users/Élodie/Classeur été.xlsx",
            "saved": True,
            "read_only": False,
            "autosave_enabled": False,
        },
        "worksheet": "Données",
        "header_row": 1,
        "used_range": {
            "first_row": 1,
            "last_row": 4,
            "first_column": 1,
            "last_column": 5,
        },
        "data_rows": {
            "first": 2,
            "last": 4,
            "total": 3,
            "examined": 2 if truncated else 3,
            "truncated": truncated,
        },
        "columns_total": 5,
        "columns_returned": 2,
        "columns_truncated": True,
        "next_column_offset": 2,
        "columns": [
            {
                "column_index": 2,
                "column_letter": "B",
                "header_value": "Identifier",
                "used_rows": {"first": 2, "last": 4},
                "cells_examined": 2 if truncated else 3,
                "classifications": {
                    "blank": 0,
                    "text": 1,
                    "numeric": 1 if truncated else 2,
                    "boolean": 0,
                    "date_time": 0,
                    "error": 0,
                    "unsupported": 0,
                    "formula": 0,
                },
                "formulas": {"count": 0, "samples": [], "samples_truncated": False},
                "precision_risks": {
                    "cells": 1,
                    "samples": [
                        {
                            "row": 3,
                            "code": "numeric.more_than_15_digits",
                            "value_preview": 1234567890123456,
                        }
                    ],
                    "samples_truncated": False,
                },
            },
            {
                "column_index": 5,
                "column_letter": "E",
                "header_value": "Identifier",
                "used_rows": {"first": None, "last": None},
                "cells_examined": 2 if truncated else 3,
                "classifications": {
                    "blank": 2 if truncated else 3,
                    "text": 0,
                    "numeric": 0,
                    "boolean": 0,
                    "date_time": 0,
                    "error": 0,
                    "unsupported": 0,
                    "formula": 0,
                },
                "formulas": {"count": 0, "samples": [], "samples_truncated": False},
                "precision_risks": {
                    "cells": 0,
                    "samples": [],
                    "samples_truncated": False,
                },
            },
        ],
    }


def _live_conversion_plan_result(*, ready: bool = True) -> dict[str, object]:
    return {
        "can_execute": ready,
        "writes_performed": 0,
        "scope_fingerprint": "sha256:" + "b" * 64,
        "plan_fingerprint": "sha256:" + "c" * 64,
        "target": {
            "process_id": 7812,
            "workbook_token": "live-workbook-v1.classeur-é",
            "workbook_name": "Classeur été.xlsx",
            "full_path": "C:/Users/Élodie/Classeur été.xlsx",
            "saved": ready,
            "read_only": False,
            "autosave_enabled": False,
            "workbook_protected": False,
            "worksheet": "Données",
            "worksheet_protected": False,
            "physical_columns": [2],
            "header_row": 1,
            "used_range": {
                "first_row": 1,
                "last_row": 4,
                "first_column": 1,
                "last_column": 2,
            },
            "data_first_row": 2,
            "data_last_row": 4,
            "data_rows_total": 3,
            "data_rows_examined": 3,
            "data_rows_truncated": False,
        },
        "effect": {
            "target_type": "text",
            "cells_examined": 3,
            "eligible": 2,
            "already_compliant": 1,
            "blank": 0,
            "blocked": 0,
            "formulas": 0,
            "unsupported": 0,
            "precision_risk_cells": 1,
        },
        "recovery": {
            "required": True,
            "strategy": "excel_save_copy_as",
            "path": "C:/Users/Élodie/Classeur été.python-excel-recovery.xlsx",
            "will_overwrite": False,
        },
        "columns": [
            {
                "column_index": 2,
                "column_letter": "B",
                "header_value": "Identifier",
                "counts": {
                    "cells_examined": 3,
                    "blank": 0,
                    "already_compliant": 1,
                    "eligible": 2,
                    "blocked_formula": 0,
                    "blocked_unsupported": 0,
                    "precision_risk_cells": 1,
                },
                "conversion_samples": [
                    {"row": 2, "input_preview": "1E+3", "output_text": "1000"},
                    {"row": 3, "input_preview": 123.0, "output_text": "123"},
                ],
                "conversion_samples_truncated": False,
                "precision_risks": [
                    {
                        "row": 3,
                        "code": "numeric.more_than_15_digits",
                        "value_preview": 123.0,
                    }
                ],
                "precision_risks_truncated": False,
            }
        ],
        "blockers": (
            []
            if ready
            else [
                {
                    "code": "input.live_workbook_dirty",
                    "message": "The live workbook has unsaved changes.",
                    "details": {},
                }
            ]
        ),
    }


def _live_conversion_execution_result(
    *, state: str = "succeeded"
) -> dict[str, object]:
    failed = state == "failed"
    partial = state == "partial_failure"
    completed = [2] if not failed else []
    return {
        "state": state,
        "target": {
            "process_id": 7812,
            "workbook_token": "live-workbook-v1.classeur-é",
            "workbook_name": "Classeur été.xlsx",
            "full_path": "C:/Users/Élodie/Classeur été.xlsx",
            "worksheet": "Données",
            "physical_columns": [2, 5] if partial else [2],
            "data_first_row": 2,
            "data_last_row": 4,
        },
        "reviewed_plan_fingerprint": "sha256:" + "c" * 64,
        "changed_cells": 0 if failed else 2,
        "already_compliant_cells": 0 if failed else 1,
        "blank_cells": 0,
        "columns_completed": completed,
        "recovery": {
            "path": "C:/Users/Élodie/Classeur été.python-excel-recovery.xlsx",
            "verified": not failed,
        },
        "mutation_started": partial or state == "succeeded",
        "workbook_dirty": partial or state == "succeeded",
        "workbook_saved": False,
        "workbook_closed": False,
        "application_closed": False,
        "failure": (
            None
            if state == "succeeded"
            else {
                "code": (
                    "operation.live_recovery_failed"
                    if failed
                    else "operation.live_text_conversion_failed"
                ),
                "message": "Excel rejected the reviewed operation.",
                "stage": "recovery" if failed else "write",
                "column_index": None if failed else 5,
                "exception_type": "com_error",
                "com_hresult": -2147352567,
            }
        ),
    }


def _live_native_text_result(*, state: str = "succeeded") -> dict[str, object]:
    scopes = [
        {
            "column_index": column,
            "column_letter": letter,
            "data_first_row": None if column == 5 else 2,
            "data_last_row": None if column == 5 else 15_001,
            "data_range": None if column == 5 else f"${letter}$2:${letter}$15001",
            "empty": column == 5,
        }
        for column, letter in ((3, "C"), (5, "E"), (7, "G"))
    ]
    succeeded = state == "succeeded"
    failed = state == "failed"
    unknown = state == "unknown"
    receipts = [
        {
            "column_index": scope["column_index"],
            "column_letter": scope["column_letter"],
            "data_range": scope["data_range"],
            "state": "skipped_empty" if scope["empty"] else "completed",
            "mutation_started": not scope["empty"],
        }
        for scope in (scopes if succeeded else [] if failed else scopes[:2])
    ]
    current = None if succeeded or failed else 7
    current_range = None if current is None else "$G$2:$G$15001"
    return {
        "state": state,
        "target": {
            "process_id": 7812,
            "workbook_token": "live-workbook-v1.classeur-é",
            "workbook_name": "Classeur été.xlsx",
            "full_path": "C:/Users/Élodie/Classeur été.xlsx",
            "worksheet": "Données",
            "header_row": 1,
            "physical_columns": [3, 5, 7],
        },
        "column_scopes": [] if failed else scopes,
        "column_receipts": receipts,
        "columns_completed": [3, 7] if succeeded else [] if failed else [3],
        "columns_skipped_empty": [] if failed else [5],
        "current_column": current,
        "current_range": current_range,
        "pending_columns": [3, 5, 7] if failed else [],
        "mutation_started": not failed,
        "workbook_dirty_before": True,
        "workbook_dirty": None if unknown else not failed,
        "recovery_created": False,
        "save_invoked": False,
        "workbook_saved": False,
        "workbook_closed": False,
        "application_closed": False,
        "failure": None if succeeded else {
            "code": (
                "operation.live_text_to_columns_outcome_unknown" if unknown
                else "conflict.live_excel_busy"
            ),
            "message": "The requested operation could not continue.",
            "stage": "preflight" if failed else "text_to_columns" if unknown else "revalidate",
            "retryable": not unknown,
            "mutation_started": unknown,
            "outcome_uncertain": unknown,
            "column_index": current,
            "data_range": current_range,
            "exception_type": "com_error" if unknown else None,
            "com_hresult": -2147352567 if unknown else None,
            "com_scode": -2147467259 if unknown else None,
        },
    }


def _headers_only_preflight_result() -> dict[str, object]:
    result = _live_preflight_result()
    result["headers_only"] = True
    result["data_rows"].update({"examined": 0, "truncated": True})
    for column in result["columns"]:
        column["cells_examined"] = 0
        column["classifications"] = dict.fromkeys(column["classifications"], 0)
        column["formulas"] = {"count": 0, "samples": [], "samples_truncated": False}
        column["precision_risks"] = {"cells": 0, "samples": [], "samples_truncated": False}
    return result


class ExcelNativeTextProtocolTests(unittest.TestCase):
    def parse(self, document: dict[str, object]) -> AutomationCallResult:
        return parse_automation_response(
            phase="native_text", request_id="native-1", return_code=0,
            stdout=_envelope(
                LIVE_NATIVE_TEXT_OPERATION, "native-1", document,
                warnings=[{
                    "code": "live.no_backup_undo_may_be_affected",
                    "message": "No backup is created; Excel Undo may be affected.",
                    "details": {},
                }],
            ),
        )

    def test_request_is_exact_native_schema_and_preserves_column_order(self) -> None:
        invocation = LiveTextToColumnsInvocation("opaque.é", "Données", (3, 5, 7))
        self.assertEqual(build_apply_live_text_to_columns_as_text_request("native", invocation), {
            "schema_version": "1.0", "request_id": "native",
            "operation": "apply_live_text_to_columns_as_text", "operation_version": "1.0",
            "arguments": {
                "workbook_token": "opaque.é", "worksheet": "Données",
                "columns": [3, 5, 7], "header_row": 1,
            },
        })
        ordered = build_apply_live_text_to_columns_as_text_request(
            "ordered", LiveTextToColumnsInvocation("opaque", "Data", (7, 3, 5), 2)
        )
        self.assertEqual(ordered["arguments"]["columns"], [7, 3, 5])
        self.assertEqual(ordered["arguments"]["header_row"], 2)
        self.assertEqual(LIVE_NATIVE_TEXT_AUTOMATION_ID, "excel.apply_live_text_to_columns_as_text")
        with self.assertRaises(FrozenInstanceError):
            invocation.columns = (1,)

    def test_native_request_enforces_its_separate_engine_limits(self) -> None:
        self.assertEqual(len(LiveTextToColumnsInvocation("opaque", "Data", tuple(range(1, 257))).columns), 256)
        LiveTextToColumnsInvocation("opaque", "Data", (16_384,), 1_048_575)
        for columns in ((), (3, 3), (True,), (0,), (16_385,), list(range(1, 3)), tuple(range(1, 258))):
            with self.subTest(columns=columns), self.assertRaises(ExcelAutomationInputError):
                LiveTextToColumnsInvocation("opaque", "Data", columns)
        for header in (0, True, 1_048_576, "1"):
            with self.subTest(header=header), self.assertRaises(ExcelAutomationInputError):
                LiveTextToColumnsInvocation("opaque", "Data", (3,), header)

    def test_authoritative_success_envelope_states_and_immutable_receipts(self) -> None:
        for state in ("succeeded", "failed", "partial_failure", "unknown"):
            with self.subTest(state=state):
                call = self.parse(_live_native_text_result(state=state))
                self.assertEqual(call.classification, f"native_text_{state}")
                self.assertIsInstance(call.result, LiveTextToColumnsResult)
                self.assertEqual(call.result.state, state)
                self.assertEqual(call.result.target.physical_columns, (3, 5, 7))
                self.assertEqual(call.unknown_outcome, state == "unknown")
                self.assertFalse(call.result.save_invoked)
                self.assertFalse(call.result.recovery_created)
                with self.assertRaises(FrozenInstanceError):
                    call.result.target.header_row = 2
        success = self.parse(_live_native_text_result()).result
        self.assertEqual(tuple(r.column_index for r in success.column_receipts), (3, 5, 7))
        self.assertEqual(success.columns_completed, (3, 7))
        self.assertEqual(success.columns_skipped_empty, (5,))
        self.assertEqual(success.column_scopes[0].data_last_row, 15_001)
        self.assertEqual(success.warnings[0].code, "live.no_backup_undo_may_be_affected")

    def test_successful_all_empty_columns_do_not_claim_mutation(self) -> None:
        document = _live_native_text_result()
        for scope, receipt in zip(document["column_scopes"], document["column_receipts"]):
            scope.update(data_first_row=None, data_last_row=None, data_range=None, empty=True)
            receipt.update(data_range=None, state="skipped_empty", mutation_started=False)
        document.update(columns_completed=[], columns_skipped_empty=[3, 5, 7], mutation_started=False, workbook_dirty=False)
        call = self.parse(document)
        self.assertEqual(call.classification, "native_text_succeeded")
        self.assertFalse(call.result.mutation_started)

    def test_preflight_prefix_scopes_keep_all_unattempted_columns_pending(self) -> None:
        for include_current in (False, True):
            document = _live_native_text_result(state="failed")
            current = 7 if include_current else 5
            current_range = "$G$2:$G$15001" if include_current else None
            pending = [3, 5] if include_current else [3, 7]
            document["column_scopes"] = _live_native_text_result()["column_scopes"][:3 if include_current else 1]
            document.update(current_column=current, current_range=current_range, pending_columns=pending)
            document["failure"].update(column_index=current, data_range=current_range)
            call = self.parse(document)
            self.assertEqual(call.classification, "native_text_failed")
            self.assertEqual(call.result.pending_columns, tuple(pending))
        document = _live_native_text_result(state="failed")
        document["column_scopes"] = _live_native_text_result()["column_scopes"][:1]
        document.update(current_column=3, current_range="$C$2:$C$9", pending_columns=[5, 7])
        document["failure"].update(column_index=3, data_range="$C$2:$C$9")
        self.assertIsNone(self.parse(document).result)
        document = _live_native_text_result(state="failed")
        document["column_scopes"] = _live_native_text_result()["column_scopes"][:2]
        document.update(current_column=5, current_range=None, pending_columns=[3, 7])
        document["failure"].update(column_index=5, data_range=None)
        self.assertIsNone(self.parse(document).result)

    def test_revalidation_failure_allows_skipped_receipts_and_changed_range(self) -> None:
        for changed_range in (None, "$G$2:$G$20000"):
            document = _live_native_text_result(state="partial_failure")
            document["current_range"] = changed_range
            document["failure"]["data_range"] = changed_range
            self.assertEqual(self.parse(document).classification, "native_text_partial_failure")
        document = _live_native_text_result(state="partial_failure")
        document["column_scopes"][0].update(data_first_row=None, data_last_row=None, data_range=None, empty=True)
        document["column_receipts"][0].update(data_range=None, state="skipped_empty", mutation_started=False)
        document.update(state="failed", columns_completed=[], columns_skipped_empty=[3, 5], mutation_started=False)
        self.assertEqual(self.parse(document).classification, "native_text_failed")

    def test_initially_empty_current_scope_cannot_report_an_execution_stop(self) -> None:
        for state in ("partial_failure", "failed"):
            document = _live_native_text_result(state="partial_failure")
            document["column_scopes"][2].update(data_first_row=None, data_last_row=None, data_range=None, empty=True)
            document["failure"]["data_range"] = None
            document["current_range"] = None
            if state == "failed":
                document["column_scopes"][0].update(data_first_row=None, data_last_row=None, data_range=None, empty=True)
                document["column_receipts"][0].update(data_range=None, state="skipped_empty", mutation_started=False)
                document.update(state="failed", columns_completed=[], columns_skipped_empty=[3, 5], mutation_started=False)
            with self.subTest(state=state):
                call = self.parse(document)
                self.assertEqual(call.classification, "native_text_unknown")
                self.assertIsNone(call.result)

    def test_scope_receipt_partition_range_state_and_lifecycle_contradictions_are_unknown(self) -> None:
        changes = {
            "receipt_order": lambda d: d["column_receipts"].reverse(),
            "scope_order": lambda d: d["column_scopes"].reverse(),
            "duplicate_receipt": lambda d: d["column_receipts"].append(d["column_receipts"][0]),
            "unrequested_scope": lambda d: d["column_scopes"][0].update(column_index=2, column_letter="B"),
            "column_letter": lambda d: d["column_scopes"][0].update(column_letter="G"),
            "receipt_range": lambda d: d["column_receipts"][0].update(data_range="$C$2:$C$9"),
            "multi_column_range": lambda d: d["column_scopes"][0].update(data_range="$C$2:$G$15001"),
            "header_included": lambda d: d["column_scopes"][0].update(data_first_row=1, data_range="$C$1:$C$15001"),
            "past_excel_rows": lambda d: d["column_scopes"][0].update(data_last_row=1_048_577, data_range="$C$2:$C$1048577"),
            "empty_range": lambda d: d["column_scopes"][1].update(data_range="$E$2:$E$3"),
            "completed_total": lambda d: d.update(columns_completed=[7, 3]),
            "skipped_total": lambda d: d.update(columns_skipped_empty=[3]),
            "pending_overlap": lambda d: d.update(pending_columns=[7]),
            "current_overlap": lambda d: d.update(current_column=3, current_range="$C$2:$C$15001"),
            "mutation_flag": lambda d: d.update(mutation_started=False),
            "receipt_mutation": lambda d: d["column_receipts"][0].update(mutation_started=False),
            "missing_nullable_field": lambda d: d.pop("current_range"),
            "wrong_state": lambda d: d.update(state="failed"),
        }
        for field in ("recovery_created", "save_invoked", "workbook_saved", "workbook_closed", "application_closed"):
            changes[field] = lambda d, key=field: d.update({key: True})
        for name, change in changes.items():
            with self.subTest(name=name):
                document = _live_native_text_result()
                change(document)
                call = self.parse(document)
                self.assertEqual(call.classification, "native_text_unknown")
                self.assertIsNone(call.result)
                self.assertTrue(call.unknown_outcome)

    def test_unknown_current_range_and_failure_facts_must_reconcile(self) -> None:
        clean_unknown = _live_native_text_result(state="unknown")
        clean_unknown["workbook_dirty"] = False
        clean_call = self.parse(clean_unknown)
        self.assertIsInstance(clean_call.result, LiveTextToColumnsResult)
        self.assertTrue(clean_call.unknown_outcome)
        changes = (
            lambda d: d.update(current_column=None, current_range=None, pending_columns=[7]),
            lambda d: d.update(current_range="$G$2:$G$9"),
            lambda d: d["failure"].update(column_index=3),
            lambda d: d["failure"].update(retryable=True),
            lambda d: d["failure"].update(mutation_started=False),
            lambda d: d["failure"].update(outcome_uncertain=False),
            lambda d: d["failure"].update(stage="revalidate"),
            lambda d: d["failure"].pop("com_scode"),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                document = _live_native_text_result(state="unknown")
                change(document)
                call = self.parse(document)
                self.assertEqual(call.classification, "native_text_unknown")
                self.assertIsNone(call.result)

    def test_missing_malformed_mismatched_and_nonzero_success_are_unknown(self) -> None:
        valid = _envelope(LIVE_NATIVE_TEXT_OPERATION, "native-1", _live_native_text_result())
        cases = [
            (b"", 0), (b"not json", 70), (b"\xff", 0), (valid + b"{}", 0), (valid, 5),
            (_envelope(LIVE_NATIVE_TEXT_OPERATION, "wrong-id", _live_native_text_result()), 0),
            (_envelope("convert_live_column_representation", "native-1", _live_native_text_result()), 0),
        ]
        for key, value in (
            ("schema_version", "2.0"), ("operation_version", "2.0"),
            ("duration_ms", -1), ("paths", {"input": "C:/book.xlsx", "output": None, "backup": None}),
            ("warnings", None), ("result", None), ("status", "unknown"),
        ):
            envelope = json.loads(valid)
            envelope[key] = value
            cases.append((json.dumps(envelope).encode(), 0))
        for key in ("operation", "request_id", "schema_version", "operation_version", "result", "warnings", "duration_ms"):
            envelope = json.loads(valid)
            del envelope[key]
            cases.append((json.dumps(envelope).encode(), 0))
        for stdout, code in cases:
            with self.subTest(stdout=stdout[:20], code=code):
                call = parse_automation_response(phase="native_text", request_id="native-1", return_code=code, stdout=stdout)
                self.assertEqual(call.classification, "native_text_unknown")
                self.assertIsNone(call.result)

    def test_only_exact_documented_outer_preparation_errors_prove_no_mutation(self) -> None:
        for code, category, exit_code, expected in (
            ("request.invalid_workbook_token", "invalid_request", 2, "native_text_failed"),
            ("conflict.live_workbook_stale", "conflict", 4, "native_text_failed"),
            ("operation.live_text_to_columns_prepare_failed", "operation_failed", 5, "native_text_failed"),
            ("internal.unexpected", "internal_error", 70, "native_text_unknown"),
            ("operation.live_text_to_columns_prepare_failed", "conflict", 4, "native_text_unknown"),
            ("conflict.live_workbook_stale", "conflict", 5, "native_text_unknown"),
        ):
            with self.subTest(code=code, category=category, exit_code=exit_code):
                call = parse_automation_response(
                    phase="native_text", request_id="native-1", return_code=exit_code,
                    stdout=_envelope(LIVE_NATIVE_TEXT_OPERATION, "native-1", None, status="error", error={
                        "code": code, "category": category, "message": "Preparation failed.", "retryable": True, "details": {},
                    }),
                )
                self.assertEqual(call.classification, expected)
                self.assertEqual(call.error.code, code)
                self.assertIsNone(call.result)

    def test_capability_property_requires_exact_native_operation_version(self) -> None:
        for version in ("1.0", "2.0"):
            document = _capabilities_result(operation_version=version)
            native = deepcopy(document["capabilities"][0])
            native.update(operation=LIVE_NATIVE_TEXT_OPERATION, plan_operation=None, plan_operation_version=None)
            native["supports"]["planning"] = False
            document["capabilities"].append(native)
            call = parse_automation_response(phase="capabilities", request_id="caps", return_code=0, stdout=_envelope("describe_capabilities", "caps", document))
            self.assertEqual(call.result.live_native_text is not None, version == "1.0")
            self.assertEqual(call.result.live_text_conversion is not None, version == "1.0")

    def test_headers_only_request_has_no_diagnostic_options_and_default_stays_unchanged(self) -> None:
        header_request = build_preflight_live_columns_request("header", LiveColumnPreflightInvocation("opaque", "Data", column_offset=100, headers_only=True))
        self.assertEqual(header_request["arguments"], {
            "workbook_token": "opaque", "worksheet": "Data", "columns": None,
            "header_row": 1, "column_offset": 100, "maximum_columns": 100, "headers_only": True,
        })
        default = build_preflight_live_columns_request("default", LiveColumnPreflightInvocation("opaque", "Data"))
        self.assertEqual(default["arguments"], {
            "workbook_token": "opaque", "worksheet": "Data", "columns": None,
            "header_row": 1, "column_offset": 0, "maximum_columns": 100,
            "maximum_data_rows": 10_000, "maximum_samples_per_column": 10, "text_limit": 200,
        })
        with self.assertRaises(ExcelAutomationInputError):
            LiveColumnPreflightInvocation("opaque", "Data", headers_only=1)

    def test_headers_only_zero_diagnostics_and_truncation_are_valid(self) -> None:
        for document, headers_only in ((_live_preflight_result(), False), (_headers_only_preflight_result(), True)):
            call = parse_automation_response(phase="preflight", request_id="header", return_code=0, stdout=_envelope("preflight_live_columns", "header", document))
            self.assertEqual(call.classification, "preflight_succeeded")
            self.assertEqual(call.result.headers_only, headers_only)
            if headers_only:
                self.assertTrue(call.result.data_rows.truncated)
                self.assertEqual(call.result.data_rows.examined, 0)

    def test_headers_only_cannot_claim_examined_data_or_samples(self) -> None:
        changes = (
            lambda d: d["data_rows"].update(examined=1),
            lambda d: d["columns"][0].update(cells_examined=1),
            lambda d: d["columns"][0]["classifications"].update(text=1),
            lambda d: d["columns"][0]["formulas"].update(count=1),
            lambda d: d["columns"][0]["precision_risks"].update(cells=1),
            lambda d: d["columns"][0]["precision_risks"].update(samples=[{"row": 2, "code": "risk", "value_preview": 1}]),
            lambda d: d["columns"][0]["precision_risks"].update(samples_truncated=True),
            lambda d: d.update(headers_only="true"),
        )
        for index, change in enumerate(changes):
            document = _headers_only_preflight_result()
            change(document)
            with self.subTest(index=index):
                call = parse_automation_response(phase="preflight", request_id="header", return_code=0, stdout=_envelope("preflight_live_columns", "header", document))
                self.assertEqual(call.classification, "preflight_failed")


class ExcelAutomationSettingsAndInputTests(unittest.TestCase):
    def test_missing_settings_are_optional_and_valid_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "settings.json"

            self.assertEqual(
                load_excel_automation_settings(settings_path),
                ExcelAutomationSettings(),
            )

            launcher = root / "python-excel.bat"
            settings = ExcelAutomationSettings(launcher)
            save_excel_automation_settings(settings_path, settings)

            self.assertEqual(load_excel_automation_settings(settings_path), settings)
            with self.assertRaises(FrozenInstanceError):
                settings.launcher_path = None

    def test_launcher_discovery_checks_only_the_exact_direct_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            application_root = root / "context-palette"
            application_root.mkdir()
            wrong_location = application_root / "python-excel" / "python-excel.bat"
            wrong_location.parent.mkdir()
            wrong_location.write_text("@echo off\n", encoding="utf-8")

            self.assertIsNone(
                discover_direct_sibling_python_excel_launcher(application_root)
            )
            self.assertIsNone(
                discover_direct_sibling_python_excel_launcher(
                    Path("relative-context-palette")
                )
            )

            expected = root / "python-excel" / "python-excel.bat"
            expected.parent.mkdir()
            expected.write_text("@echo off\n", encoding="utf-8")

            self.assertEqual(
                discover_direct_sibling_python_excel_launcher(application_root),
                expected,
            )

    def test_settings_reject_unknown_malformed_relative_and_non_batch_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            for payload in (
                {},
                {"launcher_path": "", "extra": True},
                {"launcher_path": 1},
                {"launcher_path": "relative/python-excel.bat"},
                {"launcher_path": str(Path(directory) / "python-excel.exe")},
            ):
                with self.subTest(payload=payload):
                    settings_path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaises(ExcelAutomationSettingsError):
                        load_excel_automation_settings(settings_path)

    def test_workspace_paths_preserve_order_and_accept_matching_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one book.xlsx"
            second = root / "two.xlsx"
            first.write_bytes(b"one")
            second.write_bytes(b"two")

            paths = workbook_paths_from_workspace(f'"{first}"\n\n\'{second}\'')

            self.assertEqual(paths, (first.resolve(), second.resolve()))

    def test_workspace_batch_rejects_empty_mixed_duplicate_and_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = root / "book.xlsx"
            workbook.write_bytes(b"xlsx")
            text = root / "notes.txt"
            text.write_text("notes", encoding="utf-8")
            for value in (
                "",
                "relative.xlsx",
                str(root / "missing.xlsx"),
                str(root),
                str(text),
                f"{workbook}\nnot a path",
                f"{workbook}\n{workbook}",
                "\n".join([str(workbook)] * 101),
            ):
                with self.subTest(value=value[:80]), self.assertRaises(
                    ExcelAutomationInputError
                ):
                    workbook_paths_from_workspace(value)


class ExcelAutomationRequestTests(unittest.TestCase):
    def test_live_format_autosave_opt_in_is_additive_explicit_and_boolean(self) -> None:
        legacy = LiveFormatProfileInvocation("opaque", "worksheet", "Data")
        self.assertFalse(legacy.allow_autosave_enabled)
        for requested in (False, True):
            with self.subTest(requested=requested):
                request = build_apply_live_format_profile_request(
                    "format-opt-in",
                    LiveFormatProfileInvocation(
                        "opaque", worksheet="Data", allow_autosave_enabled=requested
                    ),
                )
                self.assertEqual(request["operation_version"], "1.0")
                if requested:
                    self.assertIs(request["arguments"]["allow_autosave_enabled"], True)
                else:
                    self.assertNotIn("allow_autosave_enabled", request["arguments"])
        for invalid in (None, 0, 1, "true", [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(ExcelAutomationInputError):
                LiveFormatProfileInvocation(
                    "opaque", worksheet="Data", allow_autosave_enabled=invalid
                )

    def test_live_request_builders_preserve_opaque_unicode_tokens_and_scope(self) -> None:
        limits = LiveExcelInventoryLimits(2, 3, 4)
        inventory = build_inventory_live_excel_request("inventory-é", limits)
        apply = build_apply_live_format_profile_request(
            "apply-é",
            LiveFormatProfileInvocation(
                "live-workbook-v1.classeur-é",
                scope="workbook",
            ),
        )

        self.assertEqual(inventory["operation"], "inventory_live_excel")
        self.assertEqual(
            inventory["arguments"],
            {
                "maximum_applications": 2,
                "maximum_workbooks_per_application": 3,
                "maximum_sheets_per_workbook": 4,
            },
        )
        self.assertEqual(apply["operation"], "apply_live_format_profile")
        self.assertEqual(
            apply["arguments"],
            {
                "workbook_token": "live-workbook-v1.classeur-é",
                "scope": "workbook",
                "worksheet": None,
                "profile_id": "standard_data",
                "profile_version": "1.0",
            },
        )

    def test_live_request_builders_reject_invalid_bounds_and_scope(self) -> None:
        with self.assertRaises(ExcelAutomationInputError):
            LiveExcelInventoryLimits(maximum_applications=65)
        with self.assertRaises(ExcelAutomationInputError):
            LiveFormatProfileInvocation("token", scope="worksheet")
        with self.assertRaises(ExcelAutomationInputError):
            LiveFormatProfileInvocation("token", scope="workbook", worksheet="Data")
        with self.assertRaises(ExcelAutomationInputError):
            LiveFormatProfileInvocation(" \t ", worksheet="Data")

    def test_request_builders_use_generic_facade_stable_ids_and_all_columns(self) -> None:
        inputs = (Path("C:/data/one.xlsx"), Path("C:/data/two.xlsx"))
        invocation = csv_invocation(
            inputs,
            output_directory=Path("C:/data/csv"),
            worksheets={"input-2": "Données"},
        )

        describe = build_describe_automations_request("describe-1")
        plan = build_plan_automation_request("plan-1", invocation)
        execute = build_execute_automation_request("execute-1", invocation, FINGERPRINT)

        self.assertEqual(describe["operation"], "describe_automations")
        self.assertEqual(
            describe["arguments"],
            {"contract_schema_version": AUTOMATION_CONTRACT_VERSION},
        )
        arguments = plan["arguments"]
        assert isinstance(arguments, dict)
        self.assertEqual(arguments["automation_id"], EXCEL_AUTOMATION_ID)
        self.assertEqual(arguments["automation_version"], EXCEL_AUTOMATION_VERSION)
        self.assertEqual(arguments["automation_version"], "2.0")
        self.assertFalse(arguments["parameters"]["allow_overwrite"])
        self.assertEqual(
            [item["input_id"] for item in arguments["inputs"]],  # type: ignore[index]
            ["input-1", "input-2"],
        )
        self.assertEqual(
            arguments["inputs"][0]["parameters"],  # type: ignore[index]
            {"worksheet": None, "physical_columns": None},
        )
        self.assertEqual(
            arguments["inputs"][1]["parameters"],  # type: ignore[index]
            {"worksheet": "Données", "physical_columns": None},
        )
        self.assertEqual(
            execute["arguments"]["expected_plan_fingerprint"],  # type: ignore[index]
            FINGERPRINT,
        )

    def test_overwrite_choice_is_sent_identically_to_plan_and_execute(self) -> None:
        invocation = csv_invocation(
            (Path("C:/data/one.xlsx"),),
            output_directory=Path("C:/data/csv"),
            allow_overwrite=True,
        )

        plan = build_plan_automation_request("plan-overwrite", invocation)
        execute = build_execute_automation_request(
            "execute-overwrite", invocation, FINGERPRINT
        )

        self.assertTrue(plan["arguments"]["parameters"]["allow_overwrite"])  # type: ignore[index]
        self.assertTrue(execute["arguments"]["parameters"]["allow_overwrite"])  # type: ignore[index]

    def test_execute_builder_rejects_unreviewed_fingerprint(self) -> None:
        invocation = CsvAutomationInvocation(
            csv_invocation((Path("C:/data/one.xlsx"),)).inputs
        )
        with self.assertRaises(ExcelAutomationInputError):
            build_execute_automation_request("execute-1", invocation, "not-a-hash")

    def test_live_conversion_request_builders_pin_host_bounds_and_echo_fingerprint(
        self,
    ) -> None:
        token = "live-workbook-v1.opaque-é"
        preflight = build_preflight_live_columns_request(
            "preflight-1",
            LiveColumnPreflightInvocation(token, "Données", (2, 5)),
        )
        self.assertEqual(preflight["operation"], "preflight_live_columns")
        self.assertEqual(
            preflight["arguments"],
            {
                "workbook_token": token,
                "worksheet": "Données",
                "columns": [2, 5],
                "header_row": 1,
                "column_offset": 0,
                "maximum_columns": 100,
                "maximum_data_rows": 10000,
                "maximum_samples_per_column": 10,
                "text_limit": 200,
            },
        )
        plan = build_plan_live_column_conversion_request(
            "conversion-plan-1",
            LiveColumnConversionPlanInvocation(token, "Données", (2, 5)),
        )
        self.assertIsNone(plan["arguments"]["recovery_path"])  # type: ignore[index]
        fingerprint = "sha256:" + "d" * 64
        execute = build_convert_live_column_representation_request(
            "conversion-execute-1",
            LiveColumnConversionInvocation(
                token,
                "Données",
                (2, 5),
                fingerprint,
                "C:/work/book.python-excel-recovery.xlsx",
                True,
            ),
        )
        self.assertEqual(
            execute["arguments"]["expected_plan_fingerprint"],  # type: ignore[index]
            fingerprint,
        )
        self.assertEqual(
            build_describe_capabilities_request("capabilities-1")["operation"],
            "describe_capabilities",
        )

    def test_live_conversion_request_models_reject_unsafe_selectors_and_paths(
        self,
    ) -> None:
        token = "live-workbook-v1.opaque"
        for invocation in (
            lambda: LiveColumnPreflightInvocation(token, "Data", (2, 2)),
            lambda: LiveColumnPreflightInvocation(token, "Data", (2,), 1),
            lambda: LiveColumnConversionPlanInvocation(token, "Data", (0,)),
            lambda: LiveColumnConversionPlanInvocation(
                token, "Data", (2,), "relative.xlsx"
            ),
            lambda: LiveColumnConversionInvocation(
                token,
                "Data",
                (2,),
                "sha256:" + "x" * 64,
                "C:/work/recovery.xlsx",
            ),
        ):
            with self.subTest(invocation=invocation):
                with self.assertRaises(ExcelAutomationInputError):
                    invocation()


class ExcelAutomationResponseTests(unittest.TestCase):
    def test_live_format_capability_opt_in_defaults_to_unsupported_and_is_strict(self) -> None:
        self.assertFalse(ExcelCapabilitySupports(True, False, False, False).autosave_opt_in)
        for marker in ("missing", False, True, None, 0, 1, "true"):
            with self.subTest(marker=marker):
                document = _capabilities_result()
                capability = document["capabilities"][0]
                capability.update(
                    operation="apply_live_format_profile",
                    plan_operation=None,
                    plan_operation_version=None,
                )
                capability["supports"].update(column_selection=False, planning=False)
                if marker != "missing":
                    capability["supports"]["autosave_opt_in"] = marker
                call = parse_automation_response(
                    phase="capabilities", request_id="format-capability", return_code=0,
                    stdout=_envelope("describe_capabilities", "format-capability", document),
                )
                if marker == "missing" or isinstance(marker, bool):
                    self.assertEqual(call.classification, "capabilities_succeeded", call.reason)
                    self.assertIsInstance(call.result, DescribeCapabilitiesResult)
                    capability_result = call.result.find("apply_live_format_profile", "1.0")
                    self.assertIsNotNone(capability_result)
                    self.assertIs(capability_result.supports.autosave_opt_in, marker is True)
                    self.assertIsNone(call.result.find("apply_live_format_profile", "2.0"))
                else:
                    self.assertEqual(call.classification, "capabilities_failed")
                    self.assertIn("autosave_opt_in", call.reason)

    def test_live_format_autosave_metadata_preserves_execution_state_and_warnings(self) -> None:
        for enabled, opted_in in ((True, True), (False, True), (None, True), (False, False), (None, False)):
            with self.subTest(enabled=enabled, opted_in=opted_in):
                document = _live_format_result()
                document["autosave"] = {
                    "enabled_at_execution": enabled, "opt_in_requested": opted_in
                }
                code = (
                    "live.autosave_enabled" if enabled is True
                    else "live.autosave_state_unknown" if enabled is None else None
                )
                warnings = [] if code is None else [{
                    "code": code,
                    "message": "AutoSave may save these changes automatically; Excel Undo may be affected.",
                    "details": {},
                }]
                call = parse_automation_response(
                    phase="apply", request_id="format-autosave", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-autosave", document, warnings=warnings),
                )
                self.assertEqual(call.classification, "apply_succeeded", call.reason)
                self.assertEqual(call.result.autosave, LiveFormatAutoSave(enabled, opted_in))
                self.assertFalse(call.result.workbook_saved)
                self.assertEqual(tuple(item.code for item in call.result.warnings), () if code is None else (code,))
                with self.assertRaises(FrozenInstanceError):
                    call.result.autosave.opt_in_requested = False

    def test_live_format_legacy_results_and_positional_constructors_remain_compatible(self) -> None:
        call = parse_automation_response(
            phase="apply", request_id="format-legacy", return_code=0,
            stdout=_envelope("apply_live_format_profile", "format-legacy", _live_format_result()),
        )
        self.assertEqual(call.classification, "apply_succeeded", call.reason)
        self.assertIsNone(call.result.autosave)
        self.assertEqual(call.result.partially_modified_sheets, ())
        legacy = LiveFormatProfileResult(
            "succeeded", "opaque", "Book.xlsx", "worksheet", "standard_data", "1.0",
            ("Data",), (), (), (), (), False, False, False, (),
        )
        self.assertIsNone(legacy.autosave)
        self.assertEqual(legacy.partially_modified_sheets, ())
        legacy_failure = LiveFormatFailure("Data", "operation.live_format_failed", "Failed.")
        self.assertIsNone(legacy_failure.mutation_started)
        self.assertEqual(legacy_failure.completed_stages, ())
        self.assertIsNone(legacy_failure.stage)

    def test_live_format_rejects_malformed_or_contradictory_autosave_metadata(self) -> None:
        for metadata in (
            None, [], {}, {"opt_in_requested": True},
            {"enabled_at_execution": False},
            {"enabled_at_execution": 1, "opt_in_requested": True},
            {"enabled_at_execution": "unknown", "opt_in_requested": True},
            {"enabled_at_execution": False, "opt_in_requested": 1},
            {"enabled_at_execution": True, "opt_in_requested": False},
        ):
            with self.subTest(metadata=metadata):
                document = _live_format_result()
                document["autosave"] = metadata
                call = parse_automation_response(
                    phase="apply", request_id="format-bad-autosave", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-bad-autosave", document),
                )
                self.assertEqual(call.classification, "apply_unknown")
                self.assertIsNone(call.result)

    def test_live_format_accepts_partial_only_sheet_and_its_filter_effect(self) -> None:
        document = _live_format_result(state="partial_failure")
        document.update(
            formatted_sheets=[], partially_modified_sheets=["Résumé"],
            filter_added_sheets=["Résumé"],
            autosave={"enabled_at_execution": True, "opt_in_requested": True},
        )
        document["failures"][0].update(
            stage="freeze_panes", exception_type="com_error", com_hresult=-2147352567,
            mutation_started=True, completed_stages=["body_font", "header", "filter", "activate"],
        )
        for filter_field in ("filter_added_sheets", "existing_filter_sheets"):
            with self.subTest(filter_field=filter_field):
                candidate = deepcopy(document)
                candidate["filter_added_sheets"] = []
                candidate[filter_field] = ["Résumé"]
                call = parse_automation_response(
                    phase="apply", request_id="format-partial-only", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-partial-only", candidate),
                )
                self.assertEqual(call.classification, "apply_partial_failure", call.reason)
                self.assertEqual(call.result.formatted_sheets, ())
                self.assertEqual(call.result.partially_modified_sheets, ("Résumé",))
                self.assertEqual(getattr(call.result, filter_field), ("Résumé",))
                failure = call.result.failures[0]
                self.assertTrue(failure.mutation_started)
                self.assertEqual(failure.completed_stages, ("body_font", "header", "filter", "activate"))
                self.assertEqual(failure.stage, "freeze_panes")

    def test_live_format_accepts_clean_failure_and_failure_before_first_stage_completes(self) -> None:
        for mutated, expected in ((False, "apply_failed"), (True, "apply_partial_failure")):
            with self.subTest(mutated=mutated):
                document = _live_format_result(state="failed")
                document.update(
                    state="partial_failure" if mutated else "failed",
                    partially_modified_sheets=["Résumé"] if mutated else [],
                )
                document["failures"][0].update(
                    mutation_started=mutated, completed_stages=[], stage="body_font",
                )
                call = parse_automation_response(
                    phase="apply", request_id="format-first-stage", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-first-stage", document),
                )
                self.assertEqual(call.classification, expected, call.reason)
                self.assertIs(call.result.failures[0].mutation_started, mutated)
                self.assertEqual(call.result.failures[0].completed_stages, ())

    def test_live_format_rejects_failure_mutation_metadata_contradictions(self) -> None:
        for partial, failure_metadata in (
            ([], {"mutation_started": True, "completed_stages": []}),
            (None, {"mutation_started": True, "completed_stages": []}),
            (["Résumé"], {"mutation_started": False, "completed_stages": []}),
            ([], {"mutation_started": False, "completed_stages": ["body_font"]}),
            ([], {"completed_stages": ["body_font"]}),
        ):
            with self.subTest(partial=partial, failure_metadata=failure_metadata):
                document = _live_format_result(state="failed")
                if partial is not None:
                    document["partially_modified_sheets"] = partial
                if partial:
                    document["state"] = "partial_failure"
                document["failures"][0].update(failure_metadata)
                call = parse_automation_response(
                    phase="apply", request_id="format-mutation-contradiction", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-mutation-contradiction", document),
                )
                self.assertEqual(call.classification, "apply_unknown")
                self.assertIsNone(call.result)
                self.assertIn("mutation metadata", call.reason)

    def test_live_format_rejects_malformed_failure_mutation_flags_and_stages(self) -> None:
        malformed_fields = (
            *(dict(mutation_started=value) for value in (None, 0, 1, "true", [], {})),
            *(dict(completed_stages=value) for value in (None, "body_font", [1], [False], ["unknown"], {})),
            *(dict(stage=value) for value in (1, False, "", "unknown")),
        )
        for failure_metadata in malformed_fields:
            with self.subTest(failure_metadata=failure_metadata):
                document = _live_format_result(state="failed")
                document["failures"][0].update(failure_metadata)
                call = parse_automation_response(
                    phase="apply", request_id="format-malformed-failure", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-malformed-failure", document),
                )
                self.assertEqual(call.classification, "apply_unknown")
                self.assertIsNone(call.result)

    def test_live_format_rejects_contradictory_partial_sheet_metadata(self) -> None:
        for partial, state in (
            (["Données"], "partial_failure"), (["Caché"], "partial_failure"),
            (["Other"], "partial_failure"), (["Résumé", "Résumé"], "partial_failure"),
            (["Résumé"], "failed"), (["Résumé"], "succeeded"),
        ):
            with self.subTest(partial=partial, state=state):
                document = _live_format_result(state="partial_failure")
                document.update(state=state, partially_modified_sheets=partial)
                call = parse_automation_response(
                    phase="apply", request_id="format-bad-partial", return_code=0,
                    stdout=_envelope("apply_live_format_profile", "format-bad-partial", document),
                )
                self.assertEqual(call.classification, "apply_unknown")
                self.assertIsNone(call.result)

    def test_live_inventory_is_immutable_bounded_and_preserves_unicode(self) -> None:
        result = parse_automation_response(
            phase="inventory",
            request_id="inventory-é",
            return_code=0,
            stdout=_envelope(
                "inventory_live_excel",
                "inventory-é",
                _live_inventory_result(),
                warnings=[
                    {
                        "code": "warning.live_inventory_truncated",
                        "message": "Bounded.",
                        "details": {"maximum": 1},
                    }
                ],
            ),
        )

        self.assertEqual(result.classification, "inventory_succeeded", result.reason)
        self.assertIsInstance(result.result, LiveExcelInventoryResult)
        assert isinstance(result.result, LiveExcelInventoryResult)
        workbook = result.result.applications[0].workbooks[0]
        self.assertEqual(workbook.token, "live-workbook-v1.classeur-é")
        self.assertEqual(workbook.sheets[0].name, "Données")
        self.assertEqual(result.result.warnings[0].details["maximum"], 1)
        with self.assertRaises(TypeError):
            result.result.warnings[0].details["maximum"] = 2  # type: ignore[index]

    def test_live_inventory_accepts_disappearing_items_and_unknown_sheet_state(
        self,
    ) -> None:
        document = _live_inventory_result()
        document["applications_total"] = 2
        applications = document["applications"]
        assert isinstance(applications, list)
        application = applications[0]
        assert isinstance(application, dict)
        application["workbooks_total"] = 2
        workbooks = application["workbooks"]
        assert isinstance(workbooks, list)
        workbook = workbooks[0]
        assert isinstance(workbook, dict)
        sheets = workbook["sheets"]
        assert isinstance(sheets, list)
        sheets[1]["state"] = "unknown"

        result = parse_automation_response(
            phase="inventory",
            request_id="inventory-race",
            return_code=0,
            stdout=_envelope(
                "inventory_live_excel",
                "inventory-race",
                document,
            ),
        )

        self.assertEqual(result.classification, "inventory_succeeded", result.reason)
        assert isinstance(result.result, LiveExcelInventoryResult)
        self.assertFalse(result.result.applications_truncated)
        application_result = result.result.applications[0]
        self.assertEqual(application_result.workbooks_total, 2)
        self.assertFalse(application_result.workbooks_truncated)
        self.assertEqual(
            application_result.workbooks[0].sheets[1].state,
            "unknown",
        )

    def test_live_success_rejects_any_file_path_claim(self) -> None:
        for phase, operation, result_document, classification in (
            (
                "inventory",
                "inventory_live_excel",
                _live_inventory_result(),
                "inventory_failed",
            ),
            (
                "apply",
                "apply_live_format_profile",
                _live_format_result(),
                "apply_unknown",
            ),
        ):
            with self.subTest(phase=phase):
                envelope = json.loads(
                    _envelope(operation, "live-path", result_document)
                )
                envelope["paths"]["input"] = "C:/unexpected.xlsx"
                parsed = parse_automation_response(
                    phase=phase,  # type: ignore[arg-type]
                    request_id="live-path",
                    return_code=0,
                    stdout=json.dumps(envelope).encode("utf-8"),
                )

                self.assertEqual(parsed.classification, classification)
                self.assertIn("file path", parsed.reason)

    def test_live_format_states_and_stable_outer_errors_are_distinct(self) -> None:
        succeeded = parse_automation_response(
            phase="apply",
            request_id="apply-1",
            return_code=0,
            stdout=_envelope(
                "apply_live_format_profile", "apply-1", _live_format_result()
            ),
        )
        partial = parse_automation_response(
            phase="apply",
            request_id="apply-2",
            return_code=0,
            stdout=_envelope(
                "apply_live_format_profile",
                "apply-2",
                _live_format_result(state="partial_failure"),
            ),
        )
        autosave = parse_automation_response(
            phase="apply",
            request_id="apply-3",
            return_code=2,
            stdout=_envelope(
                "apply_live_format_profile",
                "apply-3",
                None,
                status="error",
                error={
                    "code": "conflict.live_autosave_enabled",
                    "category": "conflict",
                    "message": "AutoSave is enabled.",
                    "retryable": False,
                    "details": {},
                },
            ),
        )
        stale = parse_automation_response(
            phase="apply",
            request_id="apply-4",
            return_code=2,
            stdout=_envelope(
                "apply_live_format_profile",
                "apply-4",
                None,
                status="error",
                error={
                    "code": "conflict.live_workbook_stale",
                    "category": "conflict",
                    "message": "Workbook changed.",
                    "retryable": True,
                    "details": {},
                },
            ),
        )

        self.assertEqual(succeeded.classification, "apply_succeeded")
        self.assertIsInstance(succeeded.result, LiveFormatProfileResult)
        self.assertEqual(partial.classification, "apply_partial_failure")
        assert isinstance(partial.result, LiveFormatProfileResult)
        self.assertEqual(partial.result.failures[0].worksheet, "Résumé")
        self.assertEqual(autosave.classification, "outer_error")
        self.assertEqual(autosave.error.code, "conflict.live_autosave_enabled")  # type: ignore[union-attr]
        self.assertEqual(stale.error.code, "conflict.live_workbook_stale")  # type: ignore[union-attr]

    def test_live_format_protocol_loss_and_lifecycle_contradiction_are_unknown(self) -> None:
        malformed = parse_automation_response(
            phase="apply",
            request_id="apply-loss",
            return_code=70,
            stdout=b"not json",
        )
        contradiction = _live_format_result()
        contradiction["workbook_saved"] = True
        lifecycle = parse_automation_response(
            phase="apply",
            request_id="apply-life",
            return_code=0,
            stdout=_envelope(
                "apply_live_format_profile", "apply-life", contradiction
            ),
        )

        self.assertEqual(malformed.classification, "apply_unknown")
        self.assertTrue(malformed.unknown_outcome)
        self.assertEqual(lifecycle.classification, "apply_unknown")
        self.assertIn("lifecycle", lifecycle.reason)

    def test_describe_plan_and_execution_states_are_typed(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        describe = parse_automation_response(
            phase="describe",
            request_id="describe-1",
            return_code=0,
            stdout=_envelope(
                "describe_automations", "describe-1", _describe_result()
            ),
        )
        plan = parse_automation_response(
            phase="plan",
            request_id="plan-1",
            return_code=0,
            stdout=_envelope(
                "plan_automation", "plan-1", _ready_plan_result(source, output)
            ),
        )
        execution = parse_automation_response(
            phase="execute",
            request_id="execute-1",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-1",
                _execution_result(source, output),
            ),
        )

        self.assertEqual(describe.classification, "describe_succeeded")
        self.assertIsInstance(describe.result, DescribeAutomationsResult)
        assert isinstance(describe.result, DescribeAutomationsResult)
        self.assertTrue(describe.result.csv_automation.available)  # type: ignore[union-attr]
        self.assertEqual(plan.classification, "plan_ready", plan.reason)
        self.assertIsInstance(plan.result, PlanAutomationResult)
        assert isinstance(plan.result, PlanAutomationResult)
        self.assertEqual(plan.result.inputs[0].physical_columns, (1, 3))
        self.assertEqual(plan.result.inputs[0].output_disposition, "create")
        self.assertEqual(plan.result.effect.outputs_to_create, 1)  # type: ignore[union-attr]
        self.assertEqual(plan.result.effect.outputs_to_replace, 0)  # type: ignore[union-attr]
        self.assertEqual(execution.classification, "execute_succeeded")
        self.assertIsInstance(execution.result, ExecuteAutomationResult)

    def test_v2_replacement_plan_and_execution_receipts_are_typed(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")

        plan = parse_automation_response(
            phase="plan",
            request_id="plan-replace",
            return_code=0,
            stdout=_envelope(
                "plan_automation",
                "plan-replace",
                _ready_plan_result(
                    source,
                    output,
                    disposition="replace",
                    allow_overwrite=True,
                ),
            ),
        )
        execution = parse_automation_response(
            phase="execute",
            request_id="execute-replace",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-replace",
                _execution_result(source, output, replace=True),
            ),
        )

        self.assertEqual(plan.classification, "plan_ready", plan.reason)
        assert isinstance(plan.result, PlanAutomationResult)
        planned = plan.result.inputs[0]
        self.assertEqual(planned.output_disposition, "replace")
        self.assertTrue(planned.destination_state.exists)
        self.assertEqual(plan.result.effect.outputs_to_replace, 1)  # type: ignore[union-attr]
        self.assertEqual(execution.classification, "execute_succeeded")
        assert isinstance(execution.result, ExecuteAutomationResult)
        self.assertEqual(execution.result.outputs_created, ())
        self.assertEqual(execution.result.outputs_replaced, (str(output / "book.csv"),))
        self.assertEqual(execution.result.outputs_overwritten, 1)

    def test_execution_rejects_any_claimed_source_workbook_mutation(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        result = _execution_result(source, output)
        result["source_effect"] = {
            "mutates_inputs": True,
            "workbooks_saved": 1,
        }

        parsed = parse_automation_response(
            phase="execute",
            request_id="execute-mutated-source",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-mutated-source",
                result,
            ),
        )

        self.assertEqual(parsed.classification, "execute_unknown")
        self.assertIn("no-source-mutation", parsed.reason)

    def test_engine_shaped_before_effect_failure_accepts_unresolved_input_details(
        self,
    ) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        result = _execution_result(source, output, state="failed_before_effect")
        result["final_plan_fingerprint"] = None
        result["inputs"] = [
            {
                "input_id": "input-1",
                "outcome": "failed",
                "code": "conflict.output_exists",
                "message": "The destination appeared after review.",
                "source_path": str(source),
                "worksheet": None,
                "physical_columns": [],
                "output_path": None,
                "rows_written": 0,
                "columns_written": 0,
                "escaped_cells": 0,
            }
        ]

        parsed = parse_automation_response(
            phase="execute",
            request_id="execute-output-conflict",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-output-conflict",
                result,
            ),
        )

        self.assertEqual(parsed.classification, "execute_failed_before_effect")
        self.assertIsInstance(parsed.result, ExecuteAutomationResult)
        assert isinstance(parsed.result, ExecuteAutomationResult)
        failed = parsed.result.inputs[0]
        self.assertEqual(failed.outcome, "failed")
        self.assertIsNone(failed.worksheet)
        self.assertEqual(failed.physical_columns, ())
        self.assertIsNone(failed.output_path)

    def test_successful_execution_input_still_requires_complete_effect_details(
        self,
    ) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        for field, missing in (
            ("worksheet", None),
            ("physical_columns", []),
            ("output_path", None),
        ):
            with self.subTest(field=field):
                result = _execution_result(source, output)
                inputs = result["inputs"]
                assert isinstance(inputs, list)
                inputs[0][field] = missing

                parsed = parse_automation_response(
                    phase="execute",
                    request_id=f"execute-missing-{field}",
                    return_code=0,
                    stdout=_envelope(
                        "execute_automation",
                        f"execute-missing-{field}",
                        result,
                    ),
                )

                self.assertEqual(parsed.classification, "execute_unknown")
                self.assertIn("omitted", parsed.reason)

    def test_before_effect_failure_rejects_a_claimed_successful_input(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        result = _execution_result(source, output, state="failed_before_effect")
        succeeded = _execution_result(source, output)["inputs"]
        assert isinstance(succeeded, list)
        result["inputs"] = succeeded

        parsed = parse_automation_response(
            phase="execute",
            request_id="execute-contradictory-input",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-contradictory-input",
                result,
            ),
        )

        self.assertEqual(parsed.classification, "execute_unknown")
        self.assertIn("successful input", parsed.reason)

    def test_needs_parameters_and_blocked_are_success_envelope_states(self) -> None:
        base = {
            "automation": {
                "automation_id": EXCEL_AUTOMATION_ID,
                "automation_version": EXCEL_AUTOMATION_VERSION,
            },
            "inputs": [],
            "warnings": [],
            "effect": None,
            "predicted_artifacts": [],
            "plan_fingerprint": None,
            "writes_performed": 0,
        }
        requirement = {
            "code": "parameter.output_directory_required",
            "message": "Choose an output directory.",
            "parameter_id": "output_directory",
            "input_id": None,
            "choices": {
                "items": [],
                "total": 0,
                "returned": 0,
                "truncated": False,
            },
        }
        needs = dict(
            base,
            state="needs_parameters",
            requirements=[requirement],
            blockers=[],
        )
        blocked = dict(
            base,
            state="blocked",
            requirements=[],
            blockers=[
                {
                    "code": "conflict.output_exists",
                    "message": "Output exists.",
                    "input_id": "input-1",
                    "path": "C:/data/book.csv",
                    "retryable": False,
                }
            ],
        )

        needs_result = parse_automation_response(
            phase="plan",
            request_id="needs",
            return_code=0,
            stdout=_envelope("plan_automation", "needs", needs),
        )
        blocked_result = parse_automation_response(
            phase="plan",
            request_id="blocked",
            return_code=0,
            stdout=_envelope("plan_automation", "blocked", blocked),
        )

        self.assertEqual(needs_result.classification, "plan_needs_parameters")
        self.assertEqual(blocked_result.classification, "plan_blocked")

    def test_valid_outer_error_is_known_before_effect(self) -> None:
        error = {
            "code": "request.unsupported_automation_version",
            "category": "invalid_request",
            "message": "Unsupported automation version.",
            "retryable": False,
            "details": {"field": "automation_version"},
        }
        result = parse_automation_response(
            phase="execute",
            request_id="execute-1",
            return_code=2,
            stdout=_envelope(
                "execute_automation",
                "execute-1",
                None,
                status="error",
                error=error,
            ),
        )

        self.assertEqual(result.classification, "outer_error")
        self.assertFalse(result.unknown_outcome)
        self.assertEqual(result.error.code, error["code"])  # type: ignore[union-attr]

    def test_partial_effect_and_stale_plan_remain_distinct(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        stale = parse_automation_response(
            phase="execute",
            request_id="stale",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "stale",
                _execution_result(source, output, state="failed_before_effect"),
            ),
        )
        partial = parse_automation_response(
            phase="execute",
            request_id="partial",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "partial",
                _execution_result(
                    source, output, state="failed_after_partial_effect"
                ),
            ),
        )

        self.assertEqual(stale.classification, "execute_failed_before_effect")
        self.assertEqual(partial.classification, "execute_failed_after_partial_effect")
        assert isinstance(partial.result, ExecuteAutomationResult)
        self.assertEqual(partial.result.outputs_created, (str(output / "book.csv"),))

    def test_execution_protocol_loss_or_contradiction_is_unknown(self) -> None:
        for stdout, return_code in (
            (b"not json", 70),
            (
                _envelope("execute_automation", "wrong-request", {}),
                0,
            ),
            (
                _envelope(
                    "execute_automation",
                    "execute-1",
                    _execution_result(Path("C:/book.xlsx"), Path("C:/csv")),
                ),
                5,
            ),
        ):
            with self.subTest(return_code=return_code):
                result = parse_automation_response(
                    phase="execute",
                    request_id="execute-1",
                    return_code=return_code,
                    stdout=stdout,
                )
                self.assertTrue(result.unknown_outcome)

    def test_v2_plan_rejects_an_unknown_output_disposition(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        document = _ready_plan_result(source, output)
        inputs = document["inputs"]
        assert isinstance(inputs, list)
        inputs[0]["output_disposition"] = "rename"

        result = parse_automation_response(
            phase="plan",
            request_id="plan-invalid-disposition",
            return_code=0,
            stdout=_envelope(
                "plan_automation",
                "plan-invalid-disposition",
                document,
            ),
        )

        self.assertEqual(result.classification, "plan_failed")
        self.assertIn("output disposition", result.reason)

    def test_v2_plan_rejects_contradictory_destination_and_policy_semantics(
        self,
    ) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        for mutation in ("destination", "policy"):
            with self.subTest(mutation=mutation):
                document = _ready_plan_result(source, output)
                if mutation == "destination":
                    inputs = document["inputs"]
                    assert isinstance(inputs, list)
                    destination = inputs[0]["destination_state"]
                    assert isinstance(destination, dict)
                    destination.update(
                        {
                            "exists": True,
                            "size_bytes": 12,
                            "modified_ns": 20,
                            "created_ns": 10,
                            "device": 1,
                            "inode": 2,
                            "sha256": "c" * 64,
                        }
                    )
                else:
                    parameters = document["parameters"]
                    assert isinstance(parameters, dict)
                    parameters["allow_overwrite"] = True

                result = parse_automation_response(
                    phase="plan",
                    request_id=f"plan-{mutation}",
                    return_code=0,
                    stdout=_envelope(
                        "plan_automation",
                        f"plan-{mutation}",
                        document,
                    ),
                )

                self.assertEqual(result.classification, "plan_failed")
                self.assertIn("contradict", result.reason)

    def test_v2_execution_rejects_contradictory_create_replace_totals(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        document = _execution_result(source, output)
        document["outputs_replaced"] = [str(output / "book.csv")]
        document["outputs_overwritten"] = 1
        document["writes_performed"] = 2

        result = parse_automation_response(
            phase="execute",
            request_id="execute-overlapping-output",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-overlapping-output",
                document,
            ),
        )

        self.assertEqual(result.classification, "execute_unknown")
        self.assertIn("contradictory", result.reason)

    def test_v2_execution_rejects_a_receipt_with_the_wrong_disposition(self) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        document = _execution_result(source, output, replace=True)
        inputs = document["inputs"]
        assert isinstance(inputs, list)
        inputs[0]["code"] = "automation.output_created"

        result = parse_automation_response(
            phase="execute",
            request_id="execute-wrong-receipt",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-wrong-receipt",
                document,
            ),
        )

        self.assertEqual(result.classification, "execute_unknown")
        self.assertIn("receipts", result.reason)

    def test_v2_execution_rejects_a_receipt_in_the_wrong_effect_collection(
        self,
    ) -> None:
        source = Path("C:/data/book.xlsx")
        output = Path("C:/data/csv")
        document = _execution_result(source, output)
        inputs = document["inputs"]
        assert isinstance(inputs, list)
        inputs[0]["code"] = "automation.output_replaced"

        result = parse_automation_response(
            phase="execute",
            request_id="execute-wrong-receipt",
            return_code=0,
            stdout=_envelope(
                "execute_automation",
                "execute-wrong-receipt",
                document,
            ),
        )

        self.assertEqual(result.classification, "execute_unknown")
        self.assertIn("receipts", result.reason)


class LiveScientificConversionProtocolTests(unittest.TestCase):
    def test_capability_records_preserve_unavailable_and_version_mismatch_data(
        self,
    ) -> None:
        unavailable = parse_automation_response(
            phase="capabilities",
            request_id="capabilities-1",
            return_code=0,
            stdout=_envelope(
                "describe_capabilities",
                "capabilities-1",
                _capabilities_result(available=False),
            ),
        )
        self.assertEqual(unavailable.classification, "capabilities_succeeded")
        assert isinstance(unavailable.result, DescribeCapabilitiesResult)
        capability = unavailable.result.live_text_conversion
        self.assertIsNotNone(capability)
        assert capability is not None
        self.assertFalse(capability.availability.available)
        self.assertEqual(capability.availability.reason, "Install the Excel extras.")

        mismatched = parse_automation_response(
            phase="capabilities",
            request_id="capabilities-2",
            return_code=0,
            stdout=_envelope(
                "describe_capabilities",
                "capabilities-2",
                _capabilities_result(operation_version="2.0"),
            ),
        )
        assert isinstance(mismatched.result, DescribeCapabilitiesResult)
        self.assertIsNone(mismatched.result.live_text_conversion)
        self.assertIsNotNone(
            mismatched.result.find("convert_live_column_representation", "2.0")
        )

    def test_preflight_preserves_blank_duplicate_headers_truncation_and_warnings(
        self,
    ) -> None:
        warning = {
            "code": "live_excel.column_outside_used_range",
            "message": "A selected column is outside the used range.",
            "details": {"column_index": 5},
        }
        duplicate = parse_automation_response(
            phase="preflight",
            request_id="preflight-1",
            return_code=0,
            stdout=_envelope(
                "preflight_live_columns",
                "preflight-1",
                _live_preflight_result(truncated=True),
                warnings=[warning],
            ),
        )
        self.assertEqual(duplicate.classification, "preflight_succeeded")
        assert isinstance(duplicate.result, LiveColumnPreflightResult)
        self.assertEqual(
            tuple(item.header_value for item in duplicate.result.columns),
            ("Identifier", "Identifier"),
        )
        self.assertTrue(duplicate.result.data_rows.truncated)
        self.assertTrue(duplicate.result.columns_truncated)
        self.assertEqual(duplicate.result.next_column_offset, 2)
        self.assertEqual(duplicate.result.warnings[0].details["column_index"], 5)
        with self.assertRaises(FrozenInstanceError):
            duplicate.result.columns[0].column_index = 9  # type: ignore[misc]

        blank_document = _live_preflight_result()
        blank_document["columns"][1]["header_value"] = None  # type: ignore[index]
        blank = parse_automation_response(
            phase="preflight",
            request_id="preflight-blank",
            return_code=0,
            stdout=_envelope(
                "preflight_live_columns", "preflight-blank", blank_document
            ),
        )
        assert isinstance(blank.result, LiveColumnPreflightResult)
        self.assertIsNone(blank.result.columns[1].header_value)

    def test_preflight_reconciles_formula_cells_as_a_separate_class(self) -> None:
        document = _live_preflight_result()
        column = document["columns"][0]
        column["classifications"]["numeric"] = 1
        column["classifications"]["formula"] = 1
        column["formulas"] = {
            "count": 1,
            "samples": [{"row": 4, "formula": "=1+1"}],
            "samples_truncated": False,
        }
        call = parse_automation_response(
            phase="preflight", request_id="formula-class", return_code=0,
            stdout=_envelope("preflight_live_columns", "formula-class", document),
        )
        self.assertEqual(call.classification, "preflight_succeeded")
        self.assertIsInstance(call.result, LiveColumnPreflightResult)
        self.assertEqual(call.result.columns[0].classifications.formula, 1)
        self.assertEqual(call.result.columns[0].formulas.samples[0].formula, "=1+1")

        # Formulas are exclusive, so counting the formula's result as numeric
        # as well must still reject the contradictory receipt.
        column["classifications"]["numeric"] = 2
        duplicate = parse_automation_response(
            phase="preflight", request_id="double-count", return_code=0,
            stdout=_envelope("preflight_live_columns", "double-count", document),
        )
        self.assertEqual(duplicate.classification, "preflight_failed")
        self.assertIsNone(duplicate.result)

    def test_conversion_plan_ready_blocked_and_warnings_are_typed(self) -> None:
        warning = {
            "code": "live.numeric_precision_may_already_be_lost",
            "message": "Excel may already have lost digits.",
            "details": {"cells": 1},
        }
        ready = parse_automation_response(
            phase="conversion_plan",
            request_id="conversion-plan-ready",
            return_code=0,
            stdout=_envelope(
                "plan_live_column_conversion",
                "conversion-plan-ready",
                _live_conversion_plan_result(),
                warnings=[warning],
            ),
        )
        self.assertEqual(ready.classification, "conversion_plan_ready")
        assert isinstance(ready.result, LiveColumnConversionPlanResult)
        self.assertEqual(ready.result.effect.eligible, 2)
        self.assertEqual(
            ready.result.recovery.path,
            "C:/Users/Élodie/Classeur été.python-excel-recovery.xlsx",
        )
        self.assertEqual(ready.result.warnings[0].details["cells"], 1)
        self.assertEqual(ready.result.target.physical_columns, (2,))

        blocked = parse_automation_response(
            phase="conversion_plan",
            request_id="conversion-plan-blocked",
            return_code=0,
            stdout=_envelope(
                "plan_live_column_conversion",
                "conversion-plan-blocked",
                _live_conversion_plan_result(ready=False),
            ),
        )
        self.assertEqual(blocked.classification, "conversion_plan_blocked")
        assert isinstance(blocked.result, LiveColumnConversionPlanResult)
        self.assertEqual(blocked.result.blockers[0].code, "input.live_workbook_dirty")
        self.assertFalse(blocked.result.can_execute)

    def test_conversion_success_clean_failure_and_partial_failure_are_distinct(
        self,
    ) -> None:
        expected = {
            "succeeded": "conversion_execute_succeeded",
            "failed": "conversion_execute_failed",
            "partial_failure": "conversion_execute_partial_failure",
        }
        for state, classification in expected.items():
            with self.subTest(state=state):
                parsed = parse_automation_response(
                    phase="conversion_execute",
                    request_id=f"conversion-{state}",
                    return_code=0,
                    stdout=_envelope(
                        "convert_live_column_representation",
                        f"conversion-{state}",
                        _live_conversion_execution_result(state=state),
                    ),
                )
                self.assertEqual(parsed.classification, classification)
                assert isinstance(parsed.result, LiveColumnConversionResult)
                self.assertFalse(parsed.result.workbook_saved)
                self.assertFalse(parsed.result.workbook_closed)
                self.assertFalse(parsed.result.application_closed)
                if state == "failed":
                    failure = parsed.result.failure
                    assert failure is not None
                    self.assertEqual(failure.stage, "recovery")
                    self.assertEqual(failure.exception_type, "com_error")
                    self.assertEqual(failure.com_hresult, -2147352567)
                    self.assertFalse(parsed.result.recovery.verified)
                elif state == "partial_failure":
                    self.assertTrue(parsed.result.mutation_started)
                    self.assertEqual(parsed.result.columns_completed, (2,))
                    self.assertEqual(
                        parsed.result.failure.column_index,  # type: ignore[union-attr]
                        5,
                    )

    def test_partial_failure_before_observable_edit_retains_its_receipt(self) -> None:
        document = _live_conversion_execution_result(state="partial_failure")
        document.update(
            changed_cells=0, already_compliant_cells=0, blank_cells=0,
            columns_completed=[], workbook_dirty=False,
        )
        parsed = parse_automation_response(
            phase="conversion_execute", request_id="write-start-failure", return_code=0,
            stdout=_envelope(
                "convert_live_column_representation", "write-start-failure", document,
            ),
        )
        self.assertEqual(parsed.classification, "conversion_execute_partial_failure")
        assert isinstance(parsed.result, LiveColumnConversionResult)
        self.assertTrue(parsed.result.mutation_started)
        self.assertTrue(parsed.result.recovery.verified)
        self.assertFalse(parsed.result.workbook_dirty)
        self.assertEqual(parsed.result.columns_completed, ())

    def test_failed_receipt_cannot_claim_completed_cell_effects(self) -> None:
        document = _live_conversion_execution_result(state="failed")
        document["failure"].update(stage="write", column_index=2)
        document["recovery"]["verified"] = True
        document.update(changed_cells=2, already_compliant_cells=1, columns_completed=[2])
        parsed = parse_automation_response(
            phase="conversion_execute", request_id="failed-with-effects", return_code=0,
            stdout=_envelope(
                "convert_live_column_representation", "failed-with-effects", document,
            ),
        )
        self.assertEqual(parsed.classification, "conversion_execute_unknown")
        self.assertTrue(parsed.unknown_outcome)
        self.assertIsNone(parsed.result)

    def test_live_protocol_mismatch_and_lifecycle_contradictions_fail_closed(self) -> None:
        wrong_operation = parse_automation_response(
            phase="preflight",
            request_id="preflight-mismatch",
            return_code=0,
            stdout=_envelope(
                "inventory_live_excel",
                "preflight-mismatch",
                _live_preflight_result(),
            ),
        )
        self.assertEqual(wrong_operation.classification, "preflight_failed")

        document = _live_conversion_execution_result()
        document["workbook_saved"] = True
        contradiction = parse_automation_response(
            phase="conversion_execute",
            request_id="conversion-contradiction",
            return_code=0,
            stdout=_envelope(
                "convert_live_column_representation",
                "conversion-contradiction",
                document,
            ),
        )
        self.assertEqual(
            contradiction.classification, "conversion_execute_unknown"
        )
        self.assertTrue(contradiction.unknown_outcome)
        self.assertIn("lifecycle", contradiction.reason)

        not_dirty = _live_conversion_execution_result()
        not_dirty["workbook_dirty"] = False
        dirty_contradiction = parse_automation_response(
            phase="conversion_execute",
            request_id="conversion-not-dirty",
            return_code=0,
            stdout=_envelope(
                "convert_live_column_representation",
                "conversion-not-dirty",
                not_dirty,
            ),
        )
        self.assertEqual(
            dirty_contradiction.classification,
            "conversion_execute_unknown",
        )
        self.assertTrue(dirty_contradiction.unknown_outcome)

        bad_version = json.loads(
            _envelope(
                "describe_capabilities", "capabilities-version", _capabilities_result()
            )
        )
        bad_version["operation_version"] = "2.0"
        version_result = parse_automation_response(
            phase="capabilities",
            request_id="capabilities-version",
            return_code=0,
            stdout=json.dumps(bad_version).encode("utf-8"),
        )
        self.assertEqual(version_result.classification, "capabilities_failed")

    def test_conversion_outer_error_is_known_but_protocol_loss_is_unknown(self) -> None:
        error = {
            "code": "conflict.live_conversion_plan_stale",
            "category": "conflict",
            "message": "The reviewed plan is stale.",
            "retryable": True,
            "details": {"current_plan_fingerprint": "sha256:" + "e" * 64},
        }
        outer = parse_automation_response(
            phase="conversion_execute",
            request_id="conversion-outer",
            return_code=4,
            stdout=_envelope(
                "convert_live_column_representation",
                "conversion-outer",
                None,
                status="error",
                error=error,
            ),
        )
        self.assertEqual(outer.classification, "outer_error")
        self.assertFalse(outer.unknown_outcome)
        self.assertTrue(outer.error.retryable)  # type: ignore[union-attr]

        malformed = parse_automation_response(
            phase="conversion_execute",
            request_id="conversion-malformed",
            return_code=70,
            stdout=b"not json",
        )
        self.assertEqual(malformed.classification, "conversion_execute_unknown")
        self.assertTrue(malformed.unknown_outcome)


class ExcelAutomationProcessClientTests(unittest.TestCase):
    def test_format_client_requires_request_correlated_autosave_metadata(self) -> None:
        from io import BytesIO

        for requested, metadata, expected in (
            (False, None, "apply_succeeded"),
            (False, {"enabled_at_execution": False, "opt_in_requested": False}, "apply_succeeded"),
            (False, {"enabled_at_execution": False, "opt_in_requested": True}, "apply_unknown"),
            (True, None, "apply_unknown"),
            (True, {"enabled_at_execution": False, "opt_in_requested": False}, "apply_unknown"),
            (True, {"enabled_at_execution": False, "opt_in_requested": True}, "apply_succeeded"),
            (True, {"enabled_at_execution": True, "opt_in_requested": True}, "apply_succeeded"),
            (True, {"enabled_at_execution": None, "opt_in_requested": True}, "apply_succeeded"),
        ):
            with self.subTest(requested=requested, metadata=metadata), tempfile.TemporaryDirectory() as directory:
                document = _live_format_result()
                if metadata is not None:
                    document["autosave"] = metadata

                class FakeProcess:
                    stdin = BytesIO()
                    stdout = BytesIO(_envelope("apply_live_format_profile", "format-echo", document))
                    stderr = BytesIO()

                    def wait(self, timeout=None):
                        return 0

                starts = []

                def start(*args, **kwargs):
                    starts.append((args, kwargs))
                    return FakeProcess()

                launcher = Path(directory) / "python-excel.bat"
                launcher.write_text("@echo off\n", encoding="utf-8")
                call = PythonExcelProcessClient(popen_factory=start).call(
                    launcher,
                    build_apply_live_format_profile_request("format-echo", LiveFormatProfileInvocation(
                        "live-workbook-v1.classeur-é", worksheet="Données", allow_autosave_enabled=requested
                    )),
                    phase="apply", timeout_seconds=1,
                )
                self.assertEqual(call.classification, expected, call.reason)
                self.assertEqual(len(starts), 1)
                if expected == "apply_unknown":
                    self.assertTrue(call.unknown_outcome)
                    self.assertIsNone(call.result)

    def test_format_opt_in_client_keeps_correlation_and_result_null_errors_unknown(self) -> None:
        from io import BytesIO

        for mode in ("wrong_request_id", "wrong_operation", "wrong_version", "outer_conflict", "outer_internal"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                document = _live_format_result()
                document["autosave"] = {"enabled_at_execution": True, "opt_in_requested": True}
                envelope = json.loads(_envelope("apply_live_format_profile", "format-correlation", document))
                return_code = 0
                if mode == "wrong_request_id":
                    envelope["request_id"] = "other"
                elif mode == "wrong_operation":
                    envelope["operation"] = "inventory_live_excel"
                elif mode == "wrong_version":
                    envelope["operation_version"] = "2.0"
                else:
                    return_code = 2 if mode == "outer_conflict" else 70
                    envelope.update(status="error", result=None, error={
                        "code": "conflict.live_autosave_enabled" if mode == "outer_conflict" else "internal.unexpected_error",
                        "category": "conflict" if mode == "outer_conflict" else "internal",
                        "message": "The engine could not complete formatting.", "retryable": False, "details": {},
                    })

                class FakeProcess:
                    stdin = BytesIO()
                    stdout = BytesIO(json.dumps(envelope).encode("utf-8"))
                    stderr = BytesIO()

                    def wait(self, timeout=None):
                        return return_code

                launcher = Path(directory) / "python-excel.bat"
                launcher.write_text("@echo off\n", encoding="utf-8")
                call = PythonExcelProcessClient(popen_factory=lambda *_args, **_kwargs: FakeProcess()).call(
                    launcher,
                    build_apply_live_format_profile_request("format-correlation", LiveFormatProfileInvocation(
                        "live-workbook-v1.classeur-é", worksheet="Données", allow_autosave_enabled=True
                    )),
                    phase="apply", timeout_seconds=1,
                )
                self.assertEqual(call.classification, "apply_unknown", call.reason)
                self.assertIsNone(call.result)
                if mode.startswith("wrong_"):
                    self.assertIn("did not match", call.reason)

    def test_format_client_rejects_non_boolean_opt_in_before_starting(self) -> None:
        for invalid in (None, 0, 1, "true"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                launcher = Path(directory) / "python-excel.bat"
                launcher.write_text("@echo off\n", encoding="utf-8")
                request = build_apply_live_format_profile_request(
                    "format-invalid-opt-in", LiveFormatProfileInvocation("opaque", worksheet="Data")
                )
                request["arguments"]["allow_autosave_enabled"] = invalid

                def start(*args, **kwargs):
                    self.fail("Invalid opt-in must not launch the engine.")

                call = PythonExcelProcessClient(popen_factory=start).call(
                    launcher, request, phase="apply", timeout_seconds=1,
                )
                self.assertEqual(call.classification, "start_failed")
                self.assertFalse(call.process_started)

    def test_native_timeout_process_loss_and_malformed_output_never_retry(self) -> None:
        from io import BytesIO

        for mode in ("timeout", "process_loss", "malformed"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                class FakeProcess:
                    def __init__(self):
                        self.stdin = BytesIO()
                        self.stdout = BytesIO(b"invalid" if mode == "malformed" else b"")
                        self.stderr = BytesIO()
                        self.waits = 0

                    def wait(self, timeout=None):
                        self.waits += 1
                        if mode == "timeout" and self.waits == 1:
                            raise subprocess.TimeoutExpired("fake engine", timeout)
                        return 70

                    def kill(self):
                        raise AssertionError("A native mutation owner must not be killed.")

                process = FakeProcess()
                starts = []
                terminated = []

                def start(*args, **kwargs):
                    starts.append((args, kwargs))
                    return process

                launcher = Path(directory) / "python-excel.bat"
                launcher.write_text("@echo off\n", encoding="utf-8")
                client = PythonExcelProcessClient(
                    popen_factory=start, terminate_process=terminated.append,
                )
                call = client.call(
                    launcher,
                    build_apply_live_text_to_columns_as_text_request(
                        "native-loss", LiveTextToColumnsInvocation("opaque", "Data", (3, 5, 7))
                    ),
                    phase="native_text", timeout_seconds=0.01,
                )
                self.assertEqual(call.classification, "native_text_unknown")
                self.assertTrue(call.process_started)
                self.assertTrue(call.unknown_outcome)
                self.assertIsNone(call.result)
                self.assertEqual(len(starts), 1)
                self.assertEqual(len(terminated), 0)

    def test_native_client_correlates_opaque_target_sheet_columns_and_header(self) -> None:
        from io import BytesIO

        for token, sheet, columns, header, expected in (
            ("live-workbook-v1.classeur-é", "Données", (3, 5, 7), 1, "native_text_succeeded"),
            ("other opaque token", "Données", (3, 5, 7), 1, "native_text_unknown"),
            ("live-workbook-v1.classeur-é", "Other", (3, 5, 7), 1, "native_text_unknown"),
            ("live-workbook-v1.classeur-é", "Données", (7, 3, 5), 1, "native_text_unknown"),
            ("live-workbook-v1.classeur-é", "Données", (3, 5, 7), 2, "native_text_unknown"),
        ):
            with self.subTest(token=token, sheet=sheet, columns=columns, header=header), tempfile.TemporaryDirectory() as directory:
                class FakeProcess:
                    stdin = BytesIO()
                    stdout = BytesIO(_envelope(LIVE_NATIVE_TEXT_OPERATION, "correlation", _live_native_text_result()))
                    stderr = BytesIO()

                    def wait(self, timeout=None):
                        return 0

                launcher = Path(directory) / "python-excel.bat"
                launcher.write_text("@echo off\n", encoding="utf-8")
                client = PythonExcelProcessClient(popen_factory=lambda *_args, **_kwargs: FakeProcess())
                call = client.call(
                    launcher,
                    build_apply_live_text_to_columns_as_text_request("correlation", LiveTextToColumnsInvocation(token, sheet, columns, header)),
                    phase="native_text", timeout_seconds=1,
                )
                self.assertEqual(call.classification, expected)
                if expected == "native_text_unknown":
                    self.assertIsNone(call.result)
                    self.assertIn("target did not match", call.reason)

    def test_headers_only_client_requires_matching_echo(self) -> None:
        from io import BytesIO

        for requested, response, expected in (
            (True, _headers_only_preflight_result(), "preflight_succeeded"),
            (True, _live_preflight_result(), "preflight_failed"),
            (False, _headers_only_preflight_result(), "preflight_failed"),
            (False, _live_preflight_result(), "preflight_succeeded"),
        ):
            with self.subTest(requested=requested, response=response.get("headers_only")), tempfile.TemporaryDirectory() as directory:
                class FakeProcess:
                    stdin = BytesIO()
                    stdout = BytesIO(_envelope("preflight_live_columns", "header-echo", response))
                    stderr = BytesIO()

                    def wait(self, timeout=None):
                        return 0

                launcher = Path(directory) / "python-excel.bat"
                launcher.write_text("@echo off\n", encoding="utf-8")
                client = PythonExcelProcessClient(popen_factory=lambda *_args, **_kwargs: FakeProcess())
                call = client.call(
                    launcher,
                    build_preflight_live_columns_request("header-echo", LiveColumnPreflightInvocation("opaque", "Data", headers_only=requested)),
                    phase="preflight", timeout_seconds=1,
                )
                self.assertEqual(call.classification, expected)

    def test_missing_launcher_is_a_known_start_failure(self) -> None:
        client = PythonExcelProcessClient()
        inventory = client.call(
            Path("C:/missing/python-excel.bat"),
            build_inventory_live_excel_request("inventory-1"),
            phase="inventory",
            timeout_seconds=1,
        )

        self.assertEqual(inventory.classification, "start_failed")
        self.assertFalse(inventory.process_started)

        apply = client.call(
            Path("C:/missing/python-excel.bat"),
            build_apply_live_format_profile_request(
                "apply-1", LiveFormatProfileInvocation("opaque", worksheet="Data")
            ),
            phase="apply",
            timeout_seconds=1,
        )
        self.assertEqual(apply.classification, "start_failed")
        self.assertFalse(apply.unknown_outcome)

    def test_live_conversion_timeout_is_unknown_without_launching_excel(self) -> None:
        class TimedOutProcess:
            def __init__(self) -> None:
                from io import BytesIO

                self.stdin = BytesIO()
                self.stdout = BytesIO()
                self.stderr = BytesIO()
                self.pid = 123
                self.waits = 0

            def wait(self, timeout=None):
                self.waits += 1
                if self.waits == 1:
                    raise subprocess.TimeoutExpired("python-excel", timeout)
                return 1

            def poll(self):
                return None

            def kill(self):
                return None

        process = TimedOutProcess()

        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "python-excel.bat"
            launcher.write_text("@echo off\n", encoding="utf-8")
            client = PythonExcelProcessClient(
                popen_factory=lambda *_args, **_kwargs: process,  # type: ignore[arg-type]
                terminate_process=lambda _process: None,
            )
            result = client.call(
                launcher,
                build_convert_live_column_representation_request(
                    "conversion-timeout",
                    LiveColumnConversionInvocation(
                        "live-workbook-v1.opaque",
                        "Data",
                        (2,),
                        "sha256:" + "f" * 64,
                        "C:/work/book.python-excel-recovery.xlsx",
                    ),
                ),
                phase="conversion_execute",
                timeout_seconds=0.01,
            )

        self.assertEqual(result.classification, "conversion_execute_unknown")
        self.assertTrue(result.unknown_outcome)
        self.assertIn("timed out", result.reason)

    @unittest.skipUnless(os.name == "nt", "Real .bat child boundary requires Windows")
    def test_real_child_drains_stdout_and_stderr_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = _fake_launcher(Path(directory), mode="simultaneous")
            client = PythonExcelProcessClient(maximum_stderr_bytes=512 * 1024)

            result = client.call(
                launcher,
                build_describe_automations_request("child-1"),
                phase="describe",
                timeout_seconds=10,
            )

            self.assertEqual(result.classification, "describe_succeeded")
            self.assertTrue(result.diagnostic_present)

    @unittest.skipUnless(os.name == "nt", "Real .bat child boundary requires Windows")
    def test_real_child_output_limit_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = _fake_launcher(Path(directory), mode="extra-output")
            client = PythonExcelProcessClient(maximum_stdout_bytes=128)

            result = client.call(
                launcher,
                build_describe_automations_request("child-limit"),
                phase="describe",
                timeout_seconds=10,
            )

            self.assertEqual(result.classification, "describe_failed")
            self.assertIn("bounded output limit", result.reason)

    @unittest.skipUnless(os.name == "nt", "Real .bat child boundary requires Windows")
    def test_real_child_execution_timeout_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = _fake_launcher(Path(directory), mode="hang")
            client = PythonExcelProcessClient()

            result = client.call(
                launcher,
                {
                    "schema_version": "1.0",
                    "request_id": "child-hang",
                    "operation": "execute_automation",
                    "operation_version": "1.0",
                    "arguments": {},
                },
                phase="execute",
                timeout_seconds=0.1,
            )

            self.assertEqual(result.classification, "execute_unknown")
            self.assertTrue(result.process_started)
            self.assertIn("timed out", result.reason)

    @unittest.skipUnless(os.name == "nt", "Process-tree timeout requires Windows")
    def test_execution_timeout_kills_delayed_grandchild_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = _fake_launcher(root, mode="grandchild")
            spawned = root / "grandchild-spawned.txt"
            sentinel = root / "grandchild-survived.txt"
            client = PythonExcelProcessClient()

            result = client.call(
                launcher,
                {
                    "schema_version": "1.0",
                    "request_id": "child-tree-timeout",
                    "operation": "execute_automation",
                    "operation_version": "1.0",
                    "arguments": {},
                },
                phase="execute",
                timeout_seconds=0.4,
            )

            self.assertEqual(result.classification, "execute_unknown")
            self.assertTrue(spawned.is_file(), "The fixture did not spawn its child.")
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline and not sentinel.exists():
                time.sleep(0.02)
            self.assertFalse(
                sentinel.exists(),
                "The timed-out Python Excel descendant survived taskkill /T.",
            )


class ExcelAutomationCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        # Collect widgets left by earlier Tk tests on the main thread before
        # this class starts workers. Tk variables cannot be finalized safely
        # by a worker after their owning interpreter has been destroyed.
        gc.collect()

    def test_apply_completion_is_single_call_without_an_automatic_retry(self) -> None:
        expected = AutomationCallResult("apply", "apply_unknown", True, 70)

        class Client:
            calls = 0

            def call(self, *_args, **_kwargs):
                self.calls += 1
                return expected

        client = Client()
        coordinator = ExcelAutomationCoordinator(client)  # type: ignore[arg-type]
        completions: list[AutomationCallResult] = []
        self.assertTrue(
            coordinator.start(
                Path("C:/python-excel.bat"),
                build_apply_live_format_profile_request(
                    "apply-1", LiveFormatProfileInvocation("opaque", worksheet="Data")
                ),
                phase="apply",
                timeout_seconds=1,
                on_complete=completions.append,
            )
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not coordinator.drain():
            time.sleep(0.005)

        self.assertEqual(completions, [expected])
        self.assertEqual(client.calls, 1)

    def test_single_flight_delivers_completion_only_during_drain(self) -> None:
        expected = AutomationCallResult(
            "plan", "plan_blocked", True, 0, result=None
        )
        release = threading.Event()

        class Client:
            def call(self, *_args, **_kwargs):
                release.wait(2)
                return expected

        coordinator = ExcelAutomationCoordinator(Client())  # type: ignore[arg-type]
        completions: list[AutomationCallResult] = []
        request = build_plan_automation_request(
            "plan-1", csv_invocation((Path("C:/book.xlsx"),))
        )

        self.assertTrue(
            coordinator.start(
                Path("C:/python-excel.bat"),
                request,
                phase="plan",
                timeout_seconds=1,
                on_complete=completions.append,
            )
        )
        self.assertFalse(
            coordinator.start(
                Path("C:/python-excel.bat"),
                request,
                phase="plan",
                timeout_seconds=1,
                on_complete=completions.append,
            )
        )
        self.assertEqual(completions, [])
        release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not coordinator.drain():
            time.sleep(0.005)

        self.assertEqual(completions, [expected])
        self.assertFalse(coordinator.running)

    def test_completion_callback_can_immediately_start_next_phase(self) -> None:
        expected = AutomationCallResult(
            "plan", "plan_needs_parameters", True, 0, result=None
        )

        class Client:
            def call(self, *_args, **_kwargs):
                return expected

        coordinator = ExcelAutomationCoordinator(Client())  # type: ignore[arg-type]
        request = build_plan_automation_request(
            "plan-1", csv_invocation((Path("C:/book.xlsx"),))
        )
        restarted: list[bool] = []

        def continue_with_replan(_result: AutomationCallResult) -> None:
            restarted.append(
                coordinator.start(
                    Path("C:/python-excel.bat"),
                    request,
                    phase="plan",
                    timeout_seconds=1,
                    on_complete=lambda _next: None,
                )
            )

        coordinator.start(
            Path("C:/python-excel.bat"),
            request,
            phase="plan",
            timeout_seconds=1,
            on_complete=continue_with_replan,
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not coordinator.drain():
            time.sleep(0.005)

        self.assertEqual(restarted, [True])


def _fake_launcher(root: Path, *, mode: str) -> Path:
    helper = root / "fake_engine.py"
    helper.write_text(
        """
import json
import os
from pathlib import Path
import subprocess
import sys
import time

mode = sys.argv[1]
request = json.loads(sys.stdin.read())
if mode == "hang":
    time.sleep(30)
    raise SystemExit(1)
if mode == "grandchild":
    child_code = (
        "from pathlib import Path; import sys, time; "
        "time.sleep(1.0); "
        "Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, sys.argv[3]],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    Path(sys.argv[2]).write_text(str(child.pid), encoding="utf-8")
    time.sleep(30)
    raise SystemExit(1)
result = {
    "contract_schema_version": "1.0",
    "automations": [{
        "automation_id": "excel.export_workbooks_to_csv",
        "automation_version": "1.0",
        "availability": {
            "available": True,
            "supported_phases": ["describe", "plan", "execute"],
            "code": None,
            "reason": None,
        },
    }],
}
envelope = {
    "schema_version": "1.0",
    "request_id": request["request_id"],
    "operation": request["operation"],
    "operation_version": "1.0",
    "status": "success",
    "duration_ms": 1,
    "paths": {"input": None, "output": None, "backup": None},
    "result": result,
    "warnings": [],
    "error": None,
}
if mode == "simultaneous":
    os.write(2, b"diagnostic" * 20000)
payload = json.dumps(envelope).encode("utf-8") + b"\\n"
if mode == "extra-output":
    payload += b"x" * 2048
os.write(1, payload)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    launcher = root / "python-excel.bat"
    extra_arguments = ""
    if mode == "grandchild":
        extra_arguments = (
            f' "{root / "grandchild-spawned.txt"}"'
            f' "{root / "grandchild-survived.txt"}"'
        )
    launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "{helper}" {mode}{extra_arguments}\r\n',
        encoding="utf-8",
    )
    return launcher


if __name__ == "__main__":
    unittest.main()
