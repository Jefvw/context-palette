import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.window_layouts import (
    _match_snapshot_window,
    browser_windows_without_launch_url,
    load_window_layout,
    selected_placements,
    set_snapshot_launch_target,
)


class WindowLayoutTests(unittest.TestCase):
    def test_selects_single_or_multi_monitor_variant(self):
        layout = {
            "windows": [],
            "placements": {
                "one": {"a": {"monitor": 0}},
                "two_or_more": {"a": {"monitor": 1}},
            },
        }

        self.assertEqual(selected_placements(layout, 1)["a"]["monitor"], 0)
        self.assertEqual(selected_placements(layout, 2)["a"]["monitor"], 1)

    def test_loads_example_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layout.json"
            path.write_text(
                json.dumps({"windows": [], "placements": {"one": {}, "two_or_more": {}}}),
                encoding="utf-8",
            )
            loaded = load_window_layout(path)

        self.assertIn("placements", loaded)

    def test_snapshot_matching_falls_back_when_window_title_changed(self):
        saved = {"executable": "browser.exe", "class_name": "Browser", "title": "Old page"}
        current = [
            {
                "handle": 10,
                "executable": "browser.exe",
                "class_name": "Browser",
                "title": "New page",
            }
        ]

        self.assertEqual(_match_snapshot_window(saved, current, set())["handle"], 10)

    def test_browser_snapshot_can_receive_launch_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text(
                json.dumps(
                    {
                        "windows": [
                            {
                                "title": "Example",
                                "executable": "C:/Browser/msedge.exe",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(browser_windows_without_launch_url(path), [(0, "Example")])
            set_snapshot_launch_target(path, 0, "https://example.com")
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(saved["windows"][0]["launch_target"], "https://example.com")


if __name__ == "__main__":
    unittest.main()
