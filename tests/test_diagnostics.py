from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.diagnostics import render_safe_diagnostics, summarize_diagnostics


class DiagnosticSummaryTests(unittest.TestCase):
    def test_summary_accepts_only_safe_structured_paste_events(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "context-palette.log"
            path.write_text(
                "\n".join(
                    (
                        "2026-07-20 10:00:00,000 INFO context_palette.launcher: Automatic paste: category=saved_text outcome=success reason=dispatched",
                        "2026-07-20 10:01:00,000 WARNING context_palette.launcher: Automatic paste: category=protected_credential outcome=failed reason=destination_unavailable",
                        "2026-07-20 10:02:00,000 ERROR context_palette.launcher: unrelated failure secret-value",
                        "2026-07-20 10:03:00,000 INFO context_palette.launcher: Automatic paste: category=saved_text outcome=success reason=secret-value",
                    )
                ),
                encoding="utf-8",
            )

            summary = summarize_diagnostics(path)
            rendered = render_safe_diagnostics(
                summary,
                action_count=12,
                personal_action_count=3,
                context_count=4,
                button_group_count=2,
            )

        self.assertEqual(summary.error_count, 1)
        self.assertEqual(summary.paste_outcome_counts, (("failed", 1), ("success", 1)))
        self.assertEqual(len(summary.recent_paste_events), 2)
        self.assertIn("Actions: 12 (3 personal)", rendered)
        self.assertIn("Successful: 1", rendered)
        self.assertIn("Failed: 1", rendered)
        self.assertNotIn("secret-value", rendered)

    def test_missing_log_produces_useful_empty_summary(self) -> None:
        summary = summarize_diagnostics(Path("missing-diagnostic-log.txt"))

        rendered = render_safe_diagnostics(
            summary,
            action_count=0,
            personal_action_count=0,
            context_count=0,
            button_group_count=0,
        )

        self.assertFalse(summary.log_available)
        self.assertIn("No local diagnostic log is available yet.", rendered)


if __name__ == "__main__":
    unittest.main()
