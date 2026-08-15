from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.action_preview import (
    build_action_preview,
    format_preview_summary,
)
from context_palette.action_types import ACTION_TYPES
from context_palette.actions import Action


class ActionPreviewTests(unittest.TestCase):
    def test_every_supported_type_has_structured_bounded_preview(self):
        actions = {
            "copy_text": self._action("copy_text", "Reusable text"),
            "workspace_template": self._action("workspace_template", "Template"),
            "ai_prompt": self._action("ai_prompt", "Review this prompt"),
            "open_url": self._action("open_url", "https://example.com"),
            "open_windows_target": self._action(
                "open_windows_target",
                "shell:AppsFolder",
            ),
            "open_file": self._action("open_file", "C:/work/report.txt"),
            "open_folder": self._action("open_folder", "C:/work"),
            "launch_app": self._action("launch_app", "C:/Tools/tool.exe"),
            "paste_credential": self._action(
                "paste_credential",
                "ContextPalette:Example",
            ),
            "build_url_open": self._action(
                "build_url_open",
                "https://example.com/{id_url}",
            ),
            "build_url_selection_open": self._action(
                "build_url_selection_open",
                "https://example.com/{id_url}",
            ),
            "transform_file_text": self._action(
                "transform_file_text",
                "C:/work/source.txt",
                arguments=("uppercase",),
            ),
            "transform_list_csv": self._action("transform_list_csv", "csv"),
            "transform_text": self._action("transform_text", "uppercase"),
            "transform_slashes": self._action(
                "transform_slashes",
                "forward_to_back",
            ),
        }

        self.assertEqual(set(actions), set(ACTION_TYPES))
        for action_type, action in actions.items():
            with self.subTest(action_type=action_type):
                preview = build_action_preview(
                    action,
                    workspace_has_text=True,
                    captured_selection_available=True,
                    destination_available=True,
                )
                self.assertTrue(preview.summary.startswith("Input: "))
                self.assertIn(" → Effect: ", preview.summary)
                self.assertLessEqual(len(preview.summary), 220)
                self.assertNotIn(action_type, preview.summary)
                detail = preview.full_text(action)
                self.assertIn("\n\nType\n", detail)
                self.assertIn("\n\nInput\n", detail)
                self.assertIn("\n\nEffect\n", detail)
                self.assertIn("\n\nRecovery / limitations\n", detail)
                self.assertIn(ACTION_TYPES[action_type].label, detail)

    def test_runtime_state_changes_input_and_failure_explanation(self):
        transform = self._action("transform_text", "uppercase")
        empty = build_action_preview(transform, workspace_has_text=False)
        available = build_action_preview(transform, workspace_has_text=True)

        self.assertEqual(
            empty.summary,
            "Input: needed: Input / Output is empty → Effect: Run will stop without changes",
        )
        self.assertEqual(available.input_text, "Input / Output")
        self.assertIn("replace the field", available.effect_text)

    def test_saved_content_names_its_source_and_clipboard_variables(self):
        template = build_action_preview(
            self._action("workspace_template", "Static template")
        )
        prompt = build_action_preview(
            self._action("ai_prompt", "Review %CLIPBOARD%")
        )

        self.assertEqual(template.input_text, "saved template")
        self.assertEqual(
            prompt.input_text,
            "saved prompt + text clipboard variables",
        )

    def test_url_builder_reports_existing_input_precedence_without_content(self):
        action = self._action(
            "build_url_selection_open",
            "https://example.com/{id_url}",
        )

        workspace = build_action_preview(
            action,
            workspace_has_text=True,
            captured_selection_available=True,
        )
        capture = build_action_preview(
            action,
            captured_selection_available=True,
        )
        fallback = build_action_preview(action)

        self.assertEqual(workspace.input_text, "Input / Output")
        self.assertEqual(capture.input_text, "captured selection")
        self.assertIn("clipboard fallback", fallback.input_text)
        self.assertNotIn("secret identifier", fallback.summary)

    def test_destination_sensitive_actions_explain_safe_stop_or_fallback(self):
        credential = self._action("paste_credential", "ContextPalette:Example")
        saved_text = self._action("copy_text", "private saved text")

        missing = build_action_preview(credential)
        available = build_action_preview(credential, destination_available=True)
        copied = build_action_preview(saved_text)

        self.assertIn("fresh hotkey destination is missing", missing.input_text)
        self.assertEqual(missing.effect_text, "Run will stop without changes")
        self.assertIn("clear the protected clipboard", available.effect_text)
        self.assertNotIn(saved_text.value, copied.summary)
        self.assertIn("manual paste", copied.effect_text)

    def test_safety_and_non_submission_promises_remain_visible(self):
        windows_target = build_action_preview(
            self._action("open_windows_target", "shell:AppsFolder")
        )
        ai_prompt = build_action_preview(
            self._action("ai_prompt", "Draft a response")
        )
        file_transform = build_action_preview(
            self._action(
                "transform_file_text",
                "C:/work/source.txt",
                arguments=("uppercase",),
            )
        )

        self.assertIn("may execute code", windows_target.summary)
        self.assertIn("not sandboxed", windows_target.summary)
        self.assertIn("nothing is submitted", ai_prompt.summary)
        self.assertIn("source unchanged", file_transform.summary)

    def test_full_detail_uses_readable_operation_and_structured_arguments(self):
        action = self._action(
            "launch_app",
            "C:/Tools/tool.exe",
            arguments=("--safe", "report.txt"),
            working_directory="C:/work",
        )

        detail = build_action_preview(action).full_text(action)

        self.assertIn("Configured application\nC:/Tools/tool.exe", detail)
        self.assertIn("Arguments\n--safe\nreport.txt", detail)
        self.assertIn("Working folder\nC:/work", detail)

    def test_summary_formatter_preserves_one_row_bound(self):
        summary = format_preview_summary("x" * 180, "y" * 180)

        self.assertEqual(len(summary), 220)
        self.assertTrue(summary.endswith("…"))

    @staticmethod
    def _action(
        action_type: str,
        value: str,
        *,
        arguments: tuple[str, ...] = (),
        working_directory: str | None = None,
    ) -> Action:
        return Action(
            id=f"preview-{action_type}",
            title="Preview action",
            context="General",
            type=action_type,
            value=value,
            arguments=arguments,
            working_directory=working_directory,
            description="Readable description",
        )


if __name__ == "__main__":
    unittest.main()
