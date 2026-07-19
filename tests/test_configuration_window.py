from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.configuration_window import (
    ActionDraftDialog,
    ButtonDialog,
    ConfigurationWindow,
    ContextDialog,
    action_matches_filter,
    select_first_tree_item,
    _focus_entry,
)
from context_palette.actions import Action


class FakeVariable:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeText:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self, _start: str, _end: str) -> str:
        return self.value


class FakeWindow:
    def __init__(self) -> None:
        self.destroy_calls = 0

    def destroy(self) -> None:
        self.destroy_calls += 1


class FakeFocusWindow:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def after_idle(self, callback: object) -> None:
        self.callbacks.append(callback)


class FakeEntry:
    def __init__(self) -> None:
        self.focus_calls = 0
        self.selection: tuple[object, object] | None = None

    def focus_set(self) -> None:
        self.focus_calls += 1

    def selection_range(self, start: object, end: object) -> None:
        self.selection = (start, end)


class FakeTree:
    def __init__(
        self,
        roots: tuple[str, ...],
        children: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.roots = roots
        self.children = children or {}
        self.selected: str | None = None
        self.focused: str | None = None

    def get_children(self, item: str = "") -> tuple[str, ...]:
        return self.roots if not item else self.children.get(item, ())

    def selection_set(self, item: str) -> None:
        self.selected = item

    def focus(self, item: str) -> None:
        self.focused = item


class ConfigurationDialogTests(unittest.TestCase):
    def test_first_nested_button_is_selected_for_keyboard_navigation(self) -> None:
        tree = FakeTree(("group-0",), {"group-0": ("button-0-0", "button-0-1")})

        select_first_tree_item(tree, descend=True)

        self.assertEqual(tree.selected, "button-0-0")
        self.assertEqual(tree.focused, "button-0-0")

    def test_first_context_is_selected_for_keyboard_navigation(self) -> None:
        tree = FakeTree(("context-0", "context-1"))

        select_first_tree_item(tree)

        self.assertEqual(tree.selected, "context-0")
        self.assertEqual(tree.focused, "context-0")

    def test_configure_filter_shortcut_focuses_and_selects_query(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.action_filter_entry = FakeEntry()

        result = configuration._focus_action_filter()

        self.assertEqual(result, "break")
        self.assertEqual(configuration.action_filter_entry.focus_calls, 1)
        self.assertEqual(configuration.action_filter_entry.selection, (0, "end"))

    def test_action_filter_matches_multiple_visible_facets(self) -> None:
        action = Action(
            id="python-docs",
            title="Open documentation",
            context="Developing",
            type="open_url",
            value="https://docs.python.org/",
            state="Draft",
            technology="Python",
            task="Reference",
        )

        self.assertTrue(action_matches_filter(action, "python developing", personal=True))
        self.assertTrue(action_matches_filter(action, "website draft", personal=True))
        self.assertTrue(action_matches_filter(action, "personal reference", personal=True))
        self.assertFalse(action_matches_filter(action, "shared", personal=True))

    def test_focus_entry_schedules_focus_and_selects_existing_text(self) -> None:
        window = FakeFocusWindow()
        entry = FakeEntry()

        _focus_entry(window, entry)

        self.assertEqual(len(window.callbacks), 1)
        callback = window.callbacks[0]
        self.assertTrue(callable(callback))
        callback()
        self.assertEqual(entry.focus_calls, 1)
        self.assertEqual(entry.selection, (0, "end"))

    def test_action_dialog_stays_open_when_save_callback_fails(self) -> None:
        dialog = ActionDraftDialog.__new__(ActionDraftDialog)
        dialog.action_type = "copy_text"
        dialog.action = None
        dialog.title_var = FakeVariable("Greeting")
        dialog.context_var = FakeVariable("General")
        dialog.technology_var = FakeVariable()
        dialog.task_var = FakeVariable()
        dialog.arguments_var = FakeVariable()
        dialog.working_directory_var = FakeVariable()
        dialog.value = FakeText("Hello")
        dialog.window = FakeWindow()
        dialog.on_save = lambda _action: False

        dialog._save()

        self.assertEqual(dialog.window.destroy_calls, 0)

    def test_action_dialog_closes_when_save_callback_succeeds(self) -> None:
        dialog = ActionDraftDialog.__new__(ActionDraftDialog)
        dialog.action_type = "copy_text"
        dialog.action = None
        dialog.title_var = FakeVariable("Greeting")
        dialog.context_var = FakeVariable("General")
        dialog.technology_var = FakeVariable()
        dialog.task_var = FakeVariable()
        dialog.arguments_var = FakeVariable()
        dialog.working_directory_var = FakeVariable()
        dialog.value = FakeText("Hello")
        dialog.window = FakeWindow()
        dialog.on_save = lambda _action: True

        dialog._save()

        self.assertEqual(dialog.window.destroy_calls, 1)

    def test_context_dialog_stays_open_when_save_callback_fails(self) -> None:
        dialog = ContextDialog.__new__(ContextDialog)
        dialog.name = FakeVariable("General")
        dialog.description = FakeVariable()
        dialog.technology = FakeVariable()
        dialog.task = FakeVariable()
        dialog.action_choices = {}
        dialog.slots = []
        dialog.original_name = ""
        dialog.window = FakeWindow()
        dialog.on_save = lambda _context, _original_name: False

        dialog._save()

        self.assertEqual(dialog.window.destroy_calls, 0)

    def test_button_dialog_stays_open_when_save_callback_fails(self) -> None:
        dialog = ButtonDialog.__new__(ButtonDialog)
        dialog.group_id = FakeVariable()
        dialog.group_label = FakeVariable("Tools")
        dialog.item_id = FakeVariable()
        dialog.item_label = FakeVariable("Python")
        dialog.action_choices = {"Python docs": "general-open-python-docs"}
        dialog.action_ids = [FakeVariable("Python docs")]
        dialog.original_group_id = ""
        dialog.original_item_id = ""
        dialog.window = FakeWindow()
        dialog.on_save = lambda *_args: False

        dialog._save()

        self.assertEqual(dialog.window.destroy_calls, 0)


if __name__ == "__main__":
    unittest.main()
