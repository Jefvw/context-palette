"""Static capability/offering tests with fake processes; never access desktop Excel."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from context_palette.actions import Action, LIVE_NATIVE_TEXT_AUTOMATION_ID, LIVE_TEXT_CONVERSION_AUTOMATION_ID
from context_palette.action_preview import build_action_preview
from context_palette.configuration_window import ActionDialog
from context_palette.excel_automation import AutomationCallResult, DescribeCapabilitiesResult
from context_palette.excel_native_availability import NativeExcelAvailability
from context_palette.launcher import LauncherApp
from context_palette.resource_operations import ExcelWorkflowRequest
from tests.test_excel_live_text_conversion_window import FakeCoordinator, capability


OPERATIONS = ("inventory_live_excel", "preflight_live_columns", "apply_live_text_to_columns_as_text")


def metadata(*, version="1.0", available=True, missing=False):
    entries = tuple(capability(operation, version=version, available=available)
                    for operation in OPERATIONS if not missing or operation != OPERATIONS[-1])
    return AutomationCallResult("capabilities", "capabilities_succeeded", True, 0,
                                result=DescribeCapabilitiesResult(entries))


class NativeAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="palette native catalogue ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.installation = self.base / "Context Palette ü"
        self.installation.mkdir()
        self.settings = self.installation / "data/local_excel_automation_settings.json"
        self.launcher = self.base / "python-excel/python-excel.bat"
        self.launcher.parent.mkdir()
        self.launcher.write_text("Fake launcher; never executed", encoding="utf-8")
        self.coordinator = FakeCoordinator()
        self.changed = Mock()
        self.probe = NativeExcelAvailability(self.settings, self.installation,
            coordinator=self.coordinator, on_changed=self.changed)

    def complete(self, call):
        self.coordinator.complete(call)
        self.probe.drain()

    def test_constructor_and_cached_offering_make_no_request(self):
        self.assertFalse(self.probe.available)
        self.assertEqual(self.coordinator.calls, [])
        app = LauncherApp.__new__(LauncherApp)
        app.native_excel_availability = self.probe
        self.assertFalse(app._native_text_available())
        self.assertFalse(app._native_text_available())
        self.assertEqual(self.coordinator.calls, [])

    def test_refresh_only_describes_metadata_and_never_inventories_excel(self):
        self.probe.refresh()
        call = self.coordinator.calls[0]
        self.assertEqual(call["launcher_path"], self.launcher)
        self.assertEqual(call["phase"], "capabilities")
        self.assertEqual(call["request"]["operation"], "describe_capabilities")
        self.assertEqual(call["request"]["arguments"], {})
        self.assertFalse(self.probe.available)
        self.complete(metadata())
        self.assertTrue(self.probe.available)
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_exact_version_availability_and_operation_are_required(self):
        for call in (metadata(version="2.0"), metadata(available=False), metadata(missing=True),
                     AutomationCallResult("capabilities", "capabilities_failed", True, 70)):
            with self.subTest(call=call.classification):
                self.probe.refresh()
                self.complete(call)
                self.assertFalse(self.probe.available)

    def test_missing_explicit_launcher_never_substitutes_valid_sibling(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"launcher_path": str(self.base / "missing.bat")}), encoding="utf-8")
        self.probe.refresh()
        self.assertFalse(self.probe.available)
        self.assertEqual(self.coordinator.calls, [])

    def test_absent_sibling_stays_unavailable_without_install_or_probe(self):
        self.launcher.unlink()
        self.probe.refresh()
        self.assertEqual(self.coordinator.calls, [])
        self.assertFalse(self.probe.available)

    def test_stale_metadata_cannot_reenable_reconfigured_engine(self):
        self.probe.refresh()
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text(json.dumps({"launcher_path": str(self.base / "missing.bat")}), encoding="utf-8")
        self.probe.refresh()
        self.complete(metadata())
        self.assertFalse(self.probe.available)
        self.assertEqual(len(self.coordinator.calls), 1)

    def test_other_capability_versions_do_not_hide_matching_supported_version(self):
        self.probe.refresh()
        call = metadata()
        entries = call.result.capabilities + (capability(OPERATIONS[-1], version="2.0", available=False),)
        self.complete(replace(call, result=DescribeCapabilitiesResult(entries)))
        self.assertTrue(self.probe.available)


class NativeActionIntegrationTests(unittest.TestCase):
    def action(self):
        return Action("native", "Text to Columns → Text (fast)", "Excel", "excel_automation", LIVE_NATIVE_TEXT_AUTOMATION_ID)

    def test_configuration_restore_invalidates_the_old_engine_catalogue(self):
        app = LauncherApp.__new__(LauncherApp)
        app._reload = Mock()
        app._refresh_native_catalogue = Mock()
        app._configuration_restored()
        app._reload.assert_called_once()
        app._refresh_native_catalogue.assert_called_once()

    def test_offering_filters_only_native_action_and_keeps_checked_converter(self):
        app = LauncherApp.__new__(LauncherApp)
        checked = Action("checked", "Convert Excel values to text", "Excel", "excel_automation", LIVE_TEXT_CONVERSION_AUTOMATION_ID)
        app.actions = [self.action(), checked]
        app.native_excel_availability = SimpleNamespace(available=False)
        self.assertEqual(app._offered_actions(), [checked])
        app.native_excel_availability.available = True
        self.assertEqual(app._offered_actions(), app.actions)

    def test_native_cannot_dispatch_without_capability_metadata(self):
        app = LauncherApp.__new__(LauncherApp)
        app.status_var = Mock()
        app.native_excel_availability = SimpleNamespace(available=False)
        with patch("context_palette.launcher.execute_action") as execute:
            self.assertFalse(app._execute_action(self.action()))
            execute.assert_not_called()

    def test_run_routes_to_separate_shared_native_window(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = Mock()
        app.excel_automation_settings_path = Path("D:/synthetic/data/excel.json")
        app.native_excel_availability = SimpleNamespace(available=True)
        app.excel_automation_window = None
        request = ExcelWorkflowRequest(self.action(), invocation="manual")
        with patch("context_palette.launcher.ExcelLiveTextToColumnsWindow") as native, \
             patch("context_palette.launcher.ExcelLiveTextConversionWindow") as checked:
            app._start_excel_workflow(request)
            native.assert_called_once()
            checked.assert_not_called()
            self.assertIs(app.excel_automation_window, native.return_value)

    def test_shared_action_description_and_preview_explain_scientific_distinction(self):
        root = Path(__file__).resolve().parents[1]
        actions = json.loads((root / "data/actions.json").read_text(encoding="utf-8"))["actions"]
        record = next(item for item in actions if item["value"] == LIVE_NATIVE_TEXT_AUTOMATION_ID)
        self.assertIn("scientific notation may remain unchanged", record["description"])
        preview = build_action_preview(self.action())
        self.assertIn("scientific notation may remain unchanged", preview.effect_text)
        self.assertIn("No backup", preview.limitations)

    def test_closing_a_finished_workflow_does_not_revoke_the_new_gesture(self):
        app = LauncherApp.__new__(LauncherApp)
        app.root = Mock()
        app.status_var = Mock()
        app.excel_automation_settings_path = Path("D:/synthetic/data/excel.json")
        app.native_excel_availability = SimpleNamespace(available=True)
        existing = Mock(busy=False)
        existing.close.side_effect = lambda: setattr(app.native_excel_availability, "available", False)
        app.excel_automation_window = existing
        request = ExcelWorkflowRequest(self.action(), invocation="manual")
        with patch("context_palette.launcher.ExcelLiveTextToColumnsWindow") as native:
            app._start_excel_workflow(request)
            native.assert_called_once()

    def test_new_configuration_choice_requires_available_capability(self):
        root = tk.Tk()
        root.withdraw()
        try:
            for available in (False, True):
                with self.subTest(available=available):
                    dialog = ActionDialog(root, "excel_automation", [], Mock(), native_excel_available=available)
                    self.assertEqual(LIVE_NATIVE_TEXT_AUTOMATION_ID in dialog.excel_automation_choices.values(), available)
                    dialog.window.destroy()
        finally:
            root.destroy()

    def test_existing_native_record_stays_editable_when_engine_is_unavailable(self):
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = ActionDialog(root, "excel_automation", [self.action()], Mock(),
                                  action=self.action(), native_excel_available=False)
            self.assertIn(LIVE_NATIVE_TEXT_AUTOMATION_ID, dialog.excel_automation_choices.values())
            self.assertEqual(dialog.excel_automation_var.get(), "Text to Columns → Text (fast)")
            dialog.window.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
