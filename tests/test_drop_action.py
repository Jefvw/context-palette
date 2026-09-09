from dataclasses import replace
import unittest

from context_palette.actions import Action, ActionError
from context_palette.drop_action import (
    DropActionSettings,
    approve_drop_action,
    drop_action_eligibility,
    drop_action_settings_data,
    parse_drop_action_settings,
    resolve_drop_action,
)


class DropActionTests(unittest.TestCase):
    def setUp(self):
        self.action = Action("upper", "Uppercase", "General", "transform_text", "uppercase")

    def test_default_does_not_resolve_or_authorize_an_action(self):
        result = resolve_drop_action(DropActionSettings(), [self.action])
        self.assertIsNone(result.action)
        self.assertEqual(result.reason, "")

    def test_approval_resolves_only_exact_executable_record(self):
        settings = approve_drop_action(self.action)
        self.assertIs(resolve_drop_action(settings, [self.action]).action, self.action)
        changes = ({"id": "UPPER"}, {"title": "Changed"}, {"value": "lowercase"}, {"arguments": ("new",)}, {"working_directory": "C:/Other"}, {"type": "copy_text"})
        for change in changes:
            with self.subTest(change=change):
                result = resolve_drop_action(settings, [replace(self.action, **change)])
                self.assertIsNone(result.action)
                self.assertTrue(result.reason)

    def test_organization_edits_do_not_change_execution_authority(self):
        settings = approve_drop_action(self.action)
        action = replace(self.action, context="Work", contexts=("Work",), tags=("tag",), description="More detail", quick_action_path=("Organized",))
        self.assertEqual(resolve_drop_action(settings, [action]).action, action)

    def test_missing_duplicate_and_inactive_actions_degrade_to_show(self):
        settings = approve_drop_action(self.action)
        for actions in ([], [self.action, self.action], [replace(self.action, state="Archived")], [replace(self.action, state="Draft")]):
            with self.subTest(actions=actions):
                result = resolve_drop_action(settings, actions)
                self.assertIsNone(result.action)
                self.assertTrue(result.reason)

    def test_eligibility_allows_only_explicitly_supported_input_types(self):
        for action_type, value in (
            ("transform_list_csv", "csv"),
            ("transform_slashes", "forward_to_back"),
            ("build_url_selection_open", "https://example.test/{id}"),
            ("excel_automation", "excel.export_workbooks_to_csv"),
            ("send_files_to_folder", "C:/Exports"),
            ("workspace_template", "Text: %CLIPBOARD%"),
            ("ai_prompt", "Explain %pptxt%"),
            ("open_url", "https://example.test/?q=%CLIPBOARD_URL%"),
            ("open_folder", "%CLIPBOARD%"),
        ):
            with self.subTest(action_type=action_type):
                self.assertTrue(drop_action_eligibility(replace(self.action, type=action_type, value=value)).eligible)

    def test_unsafe_or_unrelated_actions_have_explanations_and_cannot_be_approved(self):
        for action_type, value in (
            ("paste_credential", "credential"), ("copy_text", "%CLIPBOARD%"),
            ("launch_app", "C:/tool.exe"), ("open_windows_target", "%CLIPBOARD%"),
            ("open_file", "%CLIPBOARD%"), ("sequence", ""),
            ("transform_file_text", "C:/fixed.txt"),
            ("build_url_open", "https://example.test/{id}"),
            ("excel_automation", "excel.apply_live_format_profile"),
            ("workspace_template", "Fixed text"), ("open_url", "https://example.test/"),
        ):
            with self.subTest(action_type=action_type):
                action = replace(self.action, type=action_type, value=value)
                eligibility = drop_action_eligibility(action)
                self.assertFalse(eligibility.eligible)
                self.assertTrue(eligibility.reason)
                with self.assertRaises(ActionError):
                    approve_drop_action(action)

    def test_ignored_argument_placeholder_does_not_make_fixed_folder_input_aware(self):
        action = replace(self.action, type="open_folder", value="C:/Fixed", arguments=("%CLIPBOARD%",))
        self.assertFalse(drop_action_eligibility(action).eligible)

    def test_copy_destination_edit_revokes_drop_approval(self):
        action = replace(self.action, type="send_files_to_folder", value="C:/Exports")
        settings = approve_drop_action(action)
        self.assertIs(resolve_drop_action(settings, [action]).action, action)
        self.assertIn("Conflict-free copies start automatically", drop_action_eligibility(action).effect)
        changed = replace(action, value="C:/Other")
        self.assertIsNone(resolve_drop_action(settings, [changed]).action)
        for field in ({"arguments": ("%CLIPBOARD%",)}, {"working_directory": "C:/Work"}, {"value": "%CLIPBOARD%"}):
            with self.subTest(field=field):
                self.assertFalse(drop_action_eligibility(replace(action, **field)).eligible)

    def test_settings_validate_and_round_trip_without_serializing_action_content(self):
        settings = approve_drop_action(self.action)
        data = drop_action_settings_data(settings)
        self.assertEqual(parse_drop_action_settings(data), settings)
        self.assertEqual(set(data), {"mode", "action_id", "action_fingerprint"})
        self.assertEqual(parse_drop_action_settings({}), DropActionSettings())
        for raw in (None, [], {"mode": "automatic"}, {"mode": "action", "action_id": "upper"}, {"mode": "show", "action_id": "upper"}, {"unexpected": True}):
            with self.subTest(raw=raw), self.assertRaises(ActionError):
                parse_drop_action_settings(raw)


if __name__ == "__main__":
    unittest.main()
