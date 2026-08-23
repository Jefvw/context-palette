from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
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
    DescribeAutomationsResult,
    ExcelAutomationCoordinator,
    ExcelAutomationInputError,
    ExcelAutomationSettings,
    ExcelAutomationSettingsError,
    ExecuteAutomationResult,
    PlanAutomationResult,
    PythonExcelProcessClient,
    build_describe_automations_request,
    build_execute_automation_request,
    build_plan_automation_request,
    csv_invocation,
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
                "warnings": [],
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


def _ready_plan_result(source: Path, output: Path) -> dict[str, object]:
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
            }
        ],
        "parameters": {
            "output_directory": str(output),
            "delimiter": ",",
            "encoding": "utf-8-sig",
            "formula_mode": "formulas",
            "excel_safe": True,
            "worksheet_selector_policy": (
                "single_sheet_automatic_otherwise_exact_required"
            ),
            "physical_column_selector_policy": "all_used_physical_columns",
            "output_policy": "create_only",
        },
        "warnings": [],
        "effect": {
            "effect_class": "creates_output",
            "mutates_inputs": False,
            "output_policy": "create_only",
            "input_files": 1,
            "output_files": 1,
            "rows_to_write": 20,
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
) -> dict[str, object]:
    created = [str(output / "book.csv")] if state != "failed_before_effect" else []
    effects_started = state != "failed_before_effect"
    inputs = (
        [
            {
                "input_id": "input-1",
                "outcome": "succeeded",
                "code": "automation.output_created",
                "message": "The reviewed CSV output was created.",
                "source_path": str(source),
                "worksheet": "Données",
                "physical_columns": [1, 3],
                "output_path": str(output / "book.csv"),
                "rows_written": 20,
                "columns_written": 2,
                "escaped_cells": 0,
            }
        ]
        if created
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
        "writes_performed": len(created),
        "inputs": inputs,
        "source_effect": {"mutates_inputs": False, "workbooks_saved": 0},
        "outputs_created": created,
        "outputs_overwritten": 0,
        "artifacts": (
            [
                {
                    "artifact_id": "csv_files",
                    "kind": "file",
                    "path": created[0],
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
            if created
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

    def test_execute_builder_rejects_unreviewed_fingerprint(self) -> None:
        invocation = CsvAutomationInvocation(
            csv_invocation((Path("C:/data/one.xlsx"),)).inputs
        )
        with self.assertRaises(ExcelAutomationInputError):
            build_execute_automation_request("execute-1", invocation, "not-a-hash")


class ExcelAutomationResponseTests(unittest.TestCase):
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
        self.assertEqual(plan.classification, "plan_ready")
        self.assertIsInstance(plan.result, PlanAutomationResult)
        assert isinstance(plan.result, PlanAutomationResult)
        self.assertEqual(plan.result.inputs[0].physical_columns, (1, 3))
        self.assertEqual(execution.classification, "execute_succeeded")
        self.assertIsInstance(execution.result, ExecuteAutomationResult)

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


class ExcelAutomationProcessClientTests(unittest.TestCase):
    def test_missing_launcher_is_a_known_start_failure(self) -> None:
        client = PythonExcelProcessClient()
        result = client.call(
            Path("C:/missing/python-excel.bat"),
            build_describe_automations_request("describe-1"),
            phase="describe",
            timeout_seconds=1,
        )

        self.assertEqual(result.classification, "start_failed")
        self.assertFalse(result.process_started)

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
