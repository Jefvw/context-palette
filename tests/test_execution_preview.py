from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_preview import build_execution_preview
from context_palette.actions import Action, transform_text
from context_palette.action_sequences import SequenceStep
from context_palette.action_types import ACTION_TYPES


class ExecutionPreviewTests(unittest.TestCase):
    def action(self, kind, value, **kwargs):
        return Action("preview-" + kind, "Preview " + kind, "General", kind, value, **kwargs)

    def test_transform_uses_complete_workspace_and_existing_algorithm(self):
        action = self.action("transform_text", "literal_replace", arguments=("two", "THREE"))
        preview = build_execution_preview(
            action, workspace_text="one\ntwo", captured_selection="ignored", clipboard_text="ignored too"
        )
        self.assertEqual(preview.input_source, "Input / Output (complete field)")
        self.assertEqual(preview.input_value, "one\ntwo")
        self.assertEqual(preview.output_text, transform_text("one\ntwo", "literal_replace", arguments=action.arguments))
        self.assertIn("Undo", preview.recovery_text)
        self.assertNotIn("ignored", preview.full_text())

    def test_url_builder_matches_workspace_selection_clipboard_priority(self):
        action = self.action("build_url_selection_open", "https://example.com/{id_url}")
        cases = (
            ({"workspace_text": "a b", "captured_selection": "c", "clipboard_text": "d"}, "a%20b", "Input / Output"),
            ({"workspace_text": "", "captured_selection": "c d", "clipboard_text": "e"}, "c%20d", "Captured selection"),
            ({"workspace_text": "", "captured_selection": "", "clipboard_text": "e f"}, "e%20f", "Text clipboard"),
        )
        for snapshots, expected, source in cases:
            with self.subTest(snapshots=snapshots):
                preview = build_execution_preview(action, **snapshots)
                self.assertTrue(preview.input_source.startswith(source))
                self.assertEqual(preview.resolved_target, "https://example.com/" + expected)
                self.assertEqual(preview.output_text, preview.resolved_target)

    def test_whitespace_workspace_does_not_fall_back_to_selection(self):
        preview = build_execution_preview(
            self.action("build_url_selection_open", "https://example.com/{id}"),
            workspace_text="   ", captured_selection="valid", clipboard_text="valid too",
        )
        self.assertEqual(preview.input_value, "   ")
        self.assertIsNone(preview.output_text)
        self.assertIn("ID cannot be empty", preview.full_text())

    def test_prompted_url_does_not_use_any_snapshot_or_prompt(self):
        preview = build_execution_preview(
            self.action("build_url_open", "https://example.com/{id}"),
            workspace_text="workspace-private", captured_selection="selection-private", clipboard_text="clipboard-private",
        )
        self.assertIsNone(preview.input_value)
        self.assertIsNone(preview.output_text)
        self.assertIn("ID is required", preview.resolved_target)
        self.assertNotIn("-private", preview.full_text())

    def test_templates_use_clipboard_snapshot_not_workspace_and_expand_once(self):
        preview = build_execution_preview(
            self.action("launch_app", "C:/Apps/%YYYY%/tool.exe", arguments=("%CLIPBOARD%",), working_directory="C:/%MM%"),
            workspace_text="not this", clipboard_text="an argument", now=datetime(2026, 9, 3),
        )
        self.assertEqual(preview.resolved_target, "C:/Apps/2026/tool.exe")
        self.assertIn(("Arguments", "an argument"), preview.details)
        self.assertIn(("Working folder", "C:/09"), preview.details)
        self.assertNotIn("not this", preview.full_text())

    def test_credential_preview_never_exposes_unrelated_content(self):
        preview = build_execution_preview(
            self.action("paste_credential", "ContextPalette:Example"),
            workspace_text="secret-workspace", captured_selection="secret-selection", clipboard_text="secret-password",
            destination_available=True,
        )
        self.assertIsNone(preview.input_value)
        self.assertIsNone(preview.output_text)
        self.assertIn("ContextPalette:Example", preview.full_text())
        for secret in ("secret-workspace", "secret-selection", "secret-password"):
            self.assertNotIn(secret, preview.full_text())

    def test_unavailable_clipboard_is_not_substituted_with_empty_text(self):
        action = self.action("copy_text", "prefix %CLIPBOARD%")
        missing = build_execution_preview(action)
        empty = build_execution_preview(action, clipboard_text="")
        self.assertIsNone(missing.output_text)
        self.assertIn("unavailable", missing.full_text())
        self.assertEqual(empty.output_text, "prefix ")

    def test_unneeded_clipboard_snapshot_cannot_block_saved_content(self):
        preview = build_execution_preview(
            self.action("copy_text", "Saved text"), clipboard_text="x" * 100_001,
        )
        self.assertEqual(preview.output_text, "Saved text")
        self.assertIsNone(preview.input_value)

    def test_missing_and_invalid_transform_inputs_return_notices(self):
        for value, text, expected in (
            ("uppercase", "", "Add text to see your result"),
            ("json_pretty", "{", "JSON is invalid"),
        ):
            with self.subTest(value=value):
                preview = build_execution_preview(self.action("transform_text", value), workspace_text=text)
                self.assertIsNone(preview.output_text)
                self.assertIn(expected, preview.full_text())

    def test_invalid_built_url_is_not_presented_as_runnable(self):
        preview = build_execution_preview(
            self.action("build_url_selection_open", "https://{id}/"), workspace_text="user:pass@example.com"
        )
        self.assertIsNone(preview.output_text)
        self.assertIn("must not include", preview.full_text())

    def test_file_preview_does_not_claim_to_have_read_file(self):
        preview = build_execution_preview(
            self.action("transform_file_text", "Z:/unavailable/data.txt", arguments=("uppercase",))
        )
        self.assertIsNone(preview.output_text)
        self.assertIn("not read", preview.full_text())
        self.assertEqual(preview.resolved_target, "Z:/unavailable/data.txt")

    def test_large_computations_refuse_without_truncating_input(self):
        text = "x" * 100_001
        preview = build_execution_preview(self.action("transform_text", "uppercase"), workspace_text=text)
        self.assertEqual(preview.input_value, text)
        self.assertIsNone(preview.output_text)
        self.assertIn("Preview limit", preview.full_text())

    def test_full_report_is_bounded_and_marks_display_truncation(self):
        text = "x" * 30_000
        preview = build_execution_preview(self.action("transform_text", "uppercase"), workspace_text=text)
        self.assertEqual(preview.output_text, text.upper())
        report = preview.full_text()
        self.assertLessEqual(len(report), 32_768)
        self.assertIn("truncated", report)

    def test_prompt_is_literal_and_shown_once_after_the_run_explanation(self):
        prompt = "  When you run this Action\n\n1. Explain the code.\n2. Do not run it.  "
        preview = build_execution_preview(self.action("ai_prompt", prompt))
        blocks = preview.display_blocks()
        content = [block.text for block in blocks if block.role == "content"]
        self.assertEqual(content, [prompt])
        headings = [block.text for block in blocks if block.role == "heading"]
        self.assertIn("Prompt text", headings)
        self.assertNotIn("Saved prompt", headings)
        self.assertLess(headings.index("When you run this Action"), headings.index("Prompt text"))
        self.assertEqual(preview.input_source, "saved prompt")
        self.assertNotIn("pasted into another app", preview.recovery_text)

    def test_notice_and_recovery_remain_visible_before_large_input(self):
        preview = build_execution_preview(self.action("transform_text", "uppercase"), workspace_text="x" * 100_001)
        report = preview.full_text()
        self.assertLess(report.index("Preview limit"), report.index("Before · your text"))
        self.assertLess(report.index("Undo and clipboard"), report.index("Before · your text"))
        self.assertIn("Close this window to add or correct your text", report)
        self.assertLessEqual(len(report), 32_768)

    def test_empty_slash_preview_explains_both_directions_with_labelled_examples(self):
        for kind in ("transform_slashes", "transform_text"):
            for operation, before, after, description in (
                ("forward_to_back", "C:/Work/report.txt", "C:\\Work\\report.txt", "forward slash (/)"),
                ("back_to_forward", "C:\\Work\\report.txt", "C:/Work/report.txt", "backslash (\\)"),
            ):
                with self.subTest(kind=kind, operation=operation):
                    preview = build_execution_preview(self.action(kind, operation), clipboard_text="Do not use this")
                    blocks = preview.display_blocks()
                    report = "\n".join(block.text for block in blocks)
                    self.assertIn(description, report)
                    self.assertIn("Add text to see your result", report)
                    self.assertIn("Example only — not your text", report)
                    self.assertIn(f"Before: {before}\nAfter:  {after}", report)
                    self.assertIsNone(preview.output_text)
                    self.assertEqual(preview.input_value, "")
                    for clutter in ("could not compute", "Run will stop", "(empty)", "Where it goes", "Operation", "Do not use this", "choose Run when ready"):
                        self.assertNotIn(clutter, report)

    def test_transform_before_after_uses_actual_whole_input_and_no_example(self):
        original = "  C:/One/file.txt\nD:/Two/file.txt  "
        preview = build_execution_preview(self.action("transform_slashes", "forward_to_back"), workspace_text=original)
        blocks = preview.display_blocks()
        self.assertEqual([block.text for block in blocks if block.role == "content"], [original, original.replace("/", "\\")])
        self.assertFalse(any(block.role == "example" for block in blocks))
        self.assertIn("Replaces all text", preview.full_text())
        self.assertIn("does not restore the previous clipboard", preview.full_text())

    def test_unchanged_text_is_explicit_without_inventing_a_change(self):
        original = "C:\\Work\\report.txt"
        preview = build_execution_preview(self.action("transform_slashes", "forward_to_back"), workspace_text=original)
        self.assertEqual(preview.output_text, original)
        self.assertIn("would leave your text unchanged", preview.full_text())
        self.assertNotIn("Example only", preview.full_text())

    def test_invalid_input_shows_problem_and_no_example_or_run_invitation(self):
        preview = build_execution_preview(self.action("transform_text", "json_pretty"), workspace_text="{")
        report = preview.full_text()
        self.assertIn("Cannot show a result", report)
        self.assertIn("JSON is invalid", report)
        self.assertIn("Check the text", report)
        for misleading in ("Example only", "After · result", "choose Run when ready", "could not compute"):
            self.assertNotIn(misleading, report)

    def test_empty_comma_list_asks_for_input_without_showing_an_empty_result(self):
        preview = build_execution_preview(self.action("transform_list_csv", "csv"))
        self.assertIsNone(preview.output_text)
        self.assertIn("Add text to see your result", preview.full_text())
        self.assertNotIn("After · result", preview.full_text())
        self.assertNotIn("Run will stop", preview.full_text())

    def test_resolved_target_is_not_repeated_but_arguments_are_retained(self):
        preview = build_execution_preview(self.action("launch_app", "C:/tool.exe", arguments=("C:/tool.exe",)))
        headings = [block.text for block in preview.display_blocks() if block.role == "heading"]
        self.assertNotIn("Configured application", headings)
        self.assertIn("Arguments", headings)

    def test_missing_sequence_member_shows_existing_validation_without_running(self):
        preview = build_execution_preview(self.action(
            "sequence", "sequence-v1", sequence_steps=(
                SequenceStep("action", action_id="missing"),
                SequenceStep("action", action_id="also-missing"),
            ),
        ))
        self.assertIn("missing Action", preview.full_text())
        self.assertIn("Run will stop", preview.effect_text)

    def test_saved_copy_preview_resolves_destination_without_inspecting_or_copying(self):
        with mock.patch("context_palette.launcher.FileTransferWindow") as window, \
                mock.patch("context_palette.file_transfer.plan_file_transfer") as plan, \
                mock.patch("context_palette.file_transfer.execute_file_transfer_plan") as execute, \
                mock.patch.object(Path, "is_dir", side_effect=AssertionError("filesystem access")), \
                mock.patch.object(Path, "is_file", side_effect=AssertionError("filesystem access")):
            preview = build_execution_preview(
                self.action("send_files_to_folder", "C:/Exports/%YYYY%"),
                workspace_text="C:/Input/report.xlsx", clipboard_text="unrelated clipboard",
                captured_selection="unrelated selection", now=datetime(2026, 9, 3),
            )
        self.assertEqual(preview.resolved_target, "C:/Exports/2026")
        self.assertEqual(preview.input_value, "C:/Input/report.xlsx")
        self.assertNotIn("unrelated", preview.full_text())
        self.assertIn("no automatic rollback", preview.recovery_text)
        self.assertIsNone(preview.output_text)
        self.assertFalse(preview.notices[0].startswith("Preview could not"))
        for effect in (window, plan, execute):
            effect.assert_not_called()

    def test_every_type_previews_without_execution_file_or_process_effects(self):
        actions = {
            "copy_text": self.action("copy_text", "Saved text"),
            "workspace_template": self.action("workspace_template", "Saved template"),
            "ai_prompt": self.action("ai_prompt", "Saved prompt"),
            "open_url": self.action("open_url", "https://example.com"),
            "open_windows_target": self.action("open_windows_target", "shell:AppsFolder"),
            "open_file": self.action("open_file", "C:/work/file.txt"),
            "open_folder": self.action("open_folder", "C:/work"),
            "send_files_to_folder": self.action("send_files_to_folder", "C:/work"),
            "save_edge_score_pdf": self.action("save_edge_score_pdf", "C:/Music/Scores"),
            "launch_app": self.action("launch_app", "C:/tool.exe"),
            "excel_automation": self.action("excel_automation", "excel.export_workbooks_to_csv"),
            "paste_credential": self.action("paste_credential", "ContextPalette:Example"),
            "build_url_open": self.action("build_url_open", "https://example.com/{id}"),
            "build_url_selection_open": self.action("build_url_selection_open", "https://example.com/{id_url}"),
            "transform_file_text": self.action("transform_file_text", "C:/work/file.txt", arguments=("uppercase",)),
            "transform_text": self.action("transform_text", "uppercase"),
            "transform_list_csv": self.action("transform_list_csv", "csv"),
            "transform_slashes": self.action("transform_slashes", "forward_to_back"),
            "sequence": self.action("sequence", "sequence-v1", sequence_steps=(
                SequenceStep("action", action_id="preview-open_url"),
                SequenceStep("action", action_id="preview-open_folder"),
            )),
        }
        self.assertEqual(set(actions), set(ACTION_TYPES))
        forbidden = (
            "context_palette.actions.execute_action",
            "context_palette.actions.open_action_target",
            "context_palette.actions.transform_text_file",
            "context_palette.actions._open_url",
            "context_palette.actions.subprocess.Popen",
            "pathlib.Path.stat", "pathlib.Path.read_bytes", "pathlib.Path.write_bytes",
            "pathlib.Path.write_text", "builtins.open",
        )
        with ExitStack() as stack:
            mocks = [stack.enter_context(mock.patch(name, side_effect=AssertionError(name))) for name in forbidden]
            for action in actions.values():
                with self.subTest(kind=action.type):
                    preview = build_execution_preview(
                        action, workspace_text="a\nb", clipboard_text="text", available_actions=list(actions.values())
                    )
                    self.assertIn("nothing has been run or changed", preview.full_text())
                    self.assertTrue(preview.input_source)
                    self.assertTrue(preview.resolved_target)
                    self.assertTrue(preview.recovery_text)
            for effect in mocks:
                effect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
