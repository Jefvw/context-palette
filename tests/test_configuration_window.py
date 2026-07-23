from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.configuration_window import (
    ActionDialog,
    ButtonDialog,
    ConfigurationWindow,
    ContextDialog,
    GroupDialog,
    LOCAL_DESTINATION,
    PROJECT_DESTINATION,
    action_matches_filter,
    select_first_tree_item,
    _focus_entry,
)
from context_palette.action_deletion import ActionDeletionReport
from context_palette.actions import Action, append_action, load_actions
from context_palette.command_surface import CommandGroup, CommandItem
from context_palette.contexts import ContextDefinition


class FakeVariable:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeText:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self, _start: str, _end: str) -> str:
        return self.value


class FakeWindow:
    def __init__(self) -> None:
        self.destroy_calls = 0
        self.clipboard_value = ""
        self.update_calls = 0

    def destroy(self) -> None:
        self.destroy_calls += 1

    def clipboard_clear(self) -> None:
        self.clipboard_value = ""

    def clipboard_append(self, value: str) -> None:
        self.clipboard_value += value

    def update(self) -> None:
        self.update_calls += 1


class FakeFocusWindow:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def after_idle(self, callback: object) -> None:
        self.callbacks.append(callback)


class FakeNotebook:
    def __init__(self, selected: int = 0) -> None:
        self.selected = selected

    def select(self, value: int | None = None) -> int:
        if value is not None:
            self.selected = value
        return self.selected

    def index(self, value: int) -> int:
        return value


class HarvestRefreshTests(unittest.TestCase):
    def test_harvest_refresh_reloads_actions_in_open_configuration_window(self):
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.shared_actions_path = Path("shared.json")
        configuration.local_actions_path = Path("local.json")
        configuration.actions = []
        configuration.local_action_ids = set()
        configuration._reload = Mock()
        configuration.on_change = Mock()
        harvested = Action(
            "harvested",
            "Harvested",
            "General",
            "open_url",
            "https://example.test",
            "Active",
        )

        with patch(
            "context_palette.configuration_window.load_combined_actions",
            return_value=([harvested], {harvested.id}),
        ):
            configuration._harvest_changed()

        self.assertEqual(configuration.actions, [harvested])
        self.assertEqual(configuration.local_action_ids, {harvested.id})
        configuration._reload.assert_called_once_with()
        configuration.on_change.assert_called_once_with()

class FakeEntry:
    def __init__(self) -> None:
        self.focus_calls = 0
        self.selection: tuple[object, object] | None = None

    def focus_set(self) -> None:
        self.focus_calls += 1

    def focus(self) -> None:
        self.focus_set()

    def selection_range(self, start: object, end: object) -> None:
        self.selection = (start, end)


class FakeEvent:
    def __init__(self, state: int = 0, keycode: int = 0, keysym: str = "") -> None:
        self.state = state
        self.keycode = keycode
        self.keysym = keysym


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


class FakeActionTree(FakeTree):
    def __init__(self) -> None:
        super().__init__(())
        self.inserted: list[str] = []
        self.seen: str | None = None

    def delete(self, *_items: str) -> None:
        self.inserted.clear()

    def insert(self, _parent: str, _position: str, *, iid: str, **_options: object) -> None:
        self.inserted.append(iid)

    def tag_configure(self, _tag: str, **_options: object) -> None:
        return

    def see(self, item: str) -> None:
        self.seen = item


class FakeSelectedActionTree:
    def __init__(self, item: str) -> None:
        self.selected_item = item

    def selection(self) -> tuple[str, ...]:
        return (self.selected_item,)


class FakeSelectedConfigTree(FakeSelectedActionTree):
    def __init__(self, item: str, scope: str) -> None:
        super().__init__(item)
        self.scope = scope

    def item(self, _item: str, _option: str) -> tuple[str, ...]:
        return (self.scope,)


class ConfigurationDialogTests(unittest.TestCase):
    def test_requested_work_item_creation_uses_work_items_panel(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.work_items_panel = Mock()

        configuration._start_work_item_creation()

        configuration.work_items_panel.create_work_item.assert_called_once_with()

    def test_alt_mnemonics_select_configure_tabs(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook()

        for keysym, expected_tab in (("a", 0), ("t", 1), ("c", 2), ("q", 3), ("w", 4), ("d", 5)):
            with self.subTest(keysym=keysym):
                self.assertEqual(
                    configuration._handle_configure_keypress(
                        FakeEvent(state=0x20000, keysym=keysym),
                    ),
                    "break",
                )
                self.assertEqual(configuration.notebook.selected, expected_tab)

    def test_configure_closes_only_for_plain_escape(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = FakeWindow()

        self.assertEqual(
            configuration._close_on_plain_escape(FakeEvent(state=0x0004)),
            "break",
        )
        self.assertEqual(configuration.window.destroy_calls, 0)

        self.assertEqual(
            configuration._close_on_plain_escape(FakeEvent()),
            "break",
        )
        self.assertEqual(configuration.window.destroy_calls, 1)

    def test_diagnostics_shortcut_selects_tab_and_focuses_summary(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook()
        configuration.window = FakeFocusWindow()
        configuration.action_tree = FakeEntry()
        configuration.type_list = FakeEntry()
        configuration.context_tree = FakeEntry()
        configuration.button_tree = FakeEntry()
        configuration.work_items_panel = FakeEntry()
        configuration.diagnostics_text = FakeEntry()

        result = configuration._show_diagnostics_tab()
        callback = configuration.window.callbacks.pop()
        callback()

        self.assertEqual(result, "break")
        self.assertEqual(configuration.notebook.selected, 5)
        self.assertEqual(configuration.diagnostics_text.focus_calls, 1)

    def test_diagnostics_tab_change_moves_focus_into_read_only_summary(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook(selected=5)
        configuration.action_tree = FakeEntry()
        configuration.type_list = FakeEntry()
        configuration.context_tree = FakeEntry()
        configuration.button_tree = FakeEntry()
        configuration.work_items_panel = FakeEntry()
        configuration.diagnostics_text = FakeEntry()

        configuration._focus_current_tab()

        self.assertEqual(configuration.diagnostics_text.focus_calls, 1)
        self.assertEqual(configuration.action_tree.focus_calls, 0)

    def test_copy_diagnostics_copies_only_rendered_safe_summary(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = FakeWindow()
        configuration.diagnostics_summary = (
            "Context Palette diagnostics\nSuccessful: 2\nPrivacy: content excluded"
        )
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()

        configuration._copy_diagnostics()

        self.assertEqual(
            configuration.window.clipboard_value,
            configuration.diagnostics_summary,
        )
        self.assertEqual(configuration.window.update_calls, 1)
        self.assertEqual(
            configuration.feedback_var.value,
            "Copied the safe diagnostics summary.",
        )

    def test_copy_diagnostics_reports_clipboard_failure_without_success(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = FakeWindow()
        configuration.window.clipboard_clear = Mock(
            side_effect=tk.TclError("clipboard busy")
        )
        configuration.diagnostics_summary = "Safe summary"
        configuration.feedback_var = FakeVariable("unchanged")
        configuration.feedback_label = Mock()

        with patch("context_palette.configuration_window.messagebox.showerror") as error:
            configuration._copy_diagnostics()

        self.assertIn("could not be copied", error.call_args.args[1])
        self.assertEqual(configuration.feedback_var.value, "unchanged")
        configuration.feedback_label.configure.assert_not_called()

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
            state="Active",
            technology="Python",
            task="Reference",
            description="Official language documentation",
        )

        self.assertTrue(action_matches_filter(action, "python developing", personal=True))
        self.assertTrue(action_matches_filter(action, "website active", personal=True))
        self.assertTrue(action_matches_filter(action, "personal reference", personal=True))
        self.assertTrue(action_matches_filter(action, "official language", personal=True))
        self.assertFalse(action_matches_filter(action, "shared", personal=True))
        self.assertFalse(action_matches_filter(action, "project", personal=True))

    def test_initial_action_is_selected_when_actions_are_rendered(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [
            Action("first", "First", "General", "copy_text", "one"),
            Action("requested", "Requested", "General", "copy_text", "two"),
        ]
        configuration.local_action_ids = {"first", "requested"}
        configuration.initial_action_id = "REQUESTED"
        configuration.action_filter_var = FakeVariable()
        configuration.action_filter_count_var = FakeVariable()
        configuration.action_tree = FakeActionTree()

        configuration._render_actions()

        self.assertEqual(configuration.action_tree.selected, "action-1")
        self.assertEqual(configuration.action_tree.focused, "action-1")
        self.assertEqual(configuration.action_tree.seen, "action-1")

    def test_editing_shared_action_warns_and_saves_to_shared_file(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action("shared", "Shared", "General", "copy_text", "one")
        configuration.actions = [action]
        configuration.local_action_ids = set()
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.contexts = []
        configuration.window = FakeWindow()
        configuration.action_filter_var = FakeVariable()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        configuration.on_change = Mock()
        configuration._render_actions = Mock()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askokcancel",
                return_value=True,
            ) as warning,
            patch("context_palette.configuration_window.ActionDialog") as dialog,
            patch("context_palette.configuration_window.update_action") as update,
        ):
            configuration._edit_action()
            save_callback = dialog.call_args.args[3]
            self.assertTrue(save_callback(action))

        warning.assert_called_once()
        self.assertIn("tracked by Git", warning.call_args.args[1])
        update.assert_called_once_with(Path("shared-actions.json"), action)

    def test_action_edit_persists_atomically_and_preserves_previous_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            original = Action("shared", "Original", "General", "copy_text", "Before")
            updated = Action("shared", "Updated", "General", "copy_text", "After")
            append_action(path, original)
            configuration = ConfigurationWindow.__new__(ConfigurationWindow)
            configuration.actions = [original]
            configuration.window = FakeWindow()
            configuration.action_filter_var = FakeVariable()
            configuration.feedback_var = FakeVariable()
            configuration.feedback_label = Mock()
            configuration.on_change = Mock()
            configuration._render_actions = Mock()

            self.assertTrue(configuration._save_edited_action(updated, path))

            self.assertEqual(load_actions(path)[0], updated)
            self.assertEqual(
                load_actions(path.with_name("actions.json.bak"))[0],
                original,
            )
            self.assertEqual(configuration.actions, [updated])
            configuration.on_change.assert_called_once_with()

    def test_action_edit_write_failure_preserves_file_and_open_editor_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            original = Action("shared", "Original", "General", "copy_text", "Before")
            updated = Action("shared", "Updated", "General", "copy_text", "After")
            append_action(path, original)
            configuration = ConfigurationWindow.__new__(ConfigurationWindow)
            configuration.actions = [original]
            configuration.window = FakeWindow()
            configuration.action_filter_var = FakeVariable()
            configuration.feedback_var = FakeVariable("unchanged")
            configuration.feedback_label = Mock()
            configuration.on_change = Mock()
            configuration._render_actions = Mock()

            with (
                patch(
                    "context_palette.persistence.os.replace",
                    side_effect=OSError("The file is locked."),
                ),
                patch(
                    "context_palette.configuration_window.messagebox.showerror"
                ) as error,
            ):
                saved = configuration._save_edited_action(updated, path)

            self.assertFalse(saved)
            self.assertEqual(load_actions(path)[0], original)
            self.assertEqual(configuration.actions, [original])
            self.assertEqual(configuration.feedback_var.value, "unchanged")
            configuration.on_change.assert_not_called()
            configuration.feedback_label.configure.assert_not_called()
            self.assertEqual(error.call_args.args[0], "Action was not saved")
            self.assertIn("left unchanged", error.call_args.args[1])
            self.assertFalse(list(path.parent.glob(".actions.json.*.tmp")))

    def test_cancelling_shared_action_warning_does_not_open_editor(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [
            Action("shared", "Shared", "General", "copy_text", "one")
        ]
        configuration.local_action_ids = set()
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.contexts = []
        configuration.window = FakeWindow()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askokcancel",
                return_value=False,
            ),
            patch("context_palette.configuration_window.ActionDialog") as dialog,
        ):
            configuration._edit_action()

        dialog.assert_not_called()

    def test_editing_shared_context_warns_and_saves_to_shared_file(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts = [ContextDefinition("Shared")]
        configuration.context_tree = FakeSelectedConfigTree("context-0", "Shared")
        configuration.contexts_path = Path("shared-contexts.json")
        configuration.local_contexts_path = Path("missing-local-contexts.json")
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.palette_path = Path("palette.json")
        configuration.actions = []
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askokcancel",
                return_value=True,
            ) as warning,
            patch("context_palette.configuration_window.ContextDialog") as dialog,
            patch(
                "context_palette.configuration_window.rename_context_and_references"
            ) as rename,
        ):
            configuration._edit_context()
            callback = dialog.call_args.args[3]
            self.assertTrue(callback(ContextDefinition("Updated"), "Shared"))

        self.assertIn("tracked by Git", warning.call_args.args[1])
        self.assertTrue(dialog.call_args.kwargs["shared"])
        rename.assert_called_once_with(
            Path("shared-contexts.json"),
            "Shared",
            ContextDefinition("Updated"),
            action_paths=(
                Path("shared-actions.json"),
                Path("local-actions.json"),
            ),
            palette_path=Path("palette.json"),
        )

    def test_context_write_failure_reports_error_without_refreshing(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts_path = Path("shared-contexts.json")
        configuration.local_contexts_path = Path("missing-local-contexts.json")
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()
        configuration.feedback_var = FakeVariable("unchanged")
        configuration.feedback_label = Mock()

        with (
            patch(
                "context_palette.configuration_window.save_context",
                side_effect=OSError("The file is locked."),
            ),
            patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error,
        ):
            saved = configuration._save_context(
                ContextDefinition("Updated"),
                "Updated",
                target_path=configuration.contexts_path,
            )

        self.assertFalse(saved)
        configuration.on_change.assert_not_called()
        configuration._reload.assert_not_called()
        self.assertEqual(configuration.feedback_var.value, "unchanged")
        self.assertEqual(error.call_args.args[0], "Context was not saved")
        self.assertIn("left unchanged", error.call_args.args[1])

    def test_built_in_context_rejects_my_configuration_action_reference(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.local_action_ids = {"local"}
        configuration.window = FakeWindow()
        context = ContextDefinition("Built in", action_ids=("project", "local"))

        with (
            patch("context_palette.configuration_window.messagebox.showerror") as error,
            patch("context_palette.configuration_window.save_context") as save,
        ):
            result = configuration._save_context(
                context,
                "",
                target_path=configuration.contexts_path,
            )

        self.assertFalse(result)
        self.assertIn("only built-in actions", error.call_args.args[1])
        save.assert_not_called()

    def test_editing_shared_quick_action_warns_and_saves_to_shared_file(self) -> None:
        shared_path = Path("shared-commands.json")
        item = CommandItem("docs", "Docs", action_ids=("one",))
        group = CommandGroup("tools", "Tools", (item,), source_path=shared_path)
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [group]
        configuration.button_tree = FakeSelectedActionTree("button-0-0")
        configuration.command_surface_path = shared_path
        configuration.local_command_surface_path = Path("missing-local-commands.json")
        project_action = Action("one", "Project", "General", "copy_text", "one")
        local_action = Action("local", "Local", "General", "copy_text", "local")
        configuration.actions = [project_action, local_action]
        configuration.local_action_ids = {"local"}
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askokcancel",
                return_value=True,
            ) as warning,
            patch("context_palette.configuration_window.ButtonDialog") as dialog,
            patch("context_palette.configuration_window.save_command_item") as save,
        ):
            configuration._edit_button()
            callback = dialog.call_args.args[4]
            self.assertTrue(callback("tools", "Tools", item, "tools", "docs"))

        self.assertIn("tracked by Git", warning.call_args.args[1])
        self.assertTrue(dialog.call_args.kwargs["shared"])
        self.assertEqual(dialog.call_args.args[3], [project_action])
        save.assert_called_once_with(
            shared_path,
            group_id="tools",
            group_label="Tools",
            item=item,
            original_group_id="tools",
            original_item_id="docs",
        )

    def test_local_quick_action_can_assign_project_and_local_actions(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        project_action = Action("project", "Project", "General", "copy_text", "one")
        local_action = Action("local", "Local", "General", "copy_text", "two")
        configuration.actions = [project_action, local_action]
        configuration.local_action_ids = {"local"}

        self.assertEqual(
            configuration._actions_for_quick_action_storage(project=False),
            [project_action, local_action],
        )
        self.assertEqual(
            configuration._actions_for_quick_action_storage(project=True),
            [project_action],
        )

    def test_project_quick_action_save_rejects_local_action_reference(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.command_surface_path = Path("shared-commands.json")
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.local_action_ids = {"local"}
        configuration.window = FakeWindow()
        item = CommandItem(
            "mixed",
            "Mixed",
            primary_action_id="project",
            action_ids=("project", "local"),
        )

        with (
            patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error,
            patch(
                "context_palette.configuration_window.save_command_item"
            ) as save,
        ):
            result = configuration._save_button(
                "tools",
                "Tools",
                item,
                "tools",
                "mixed",
                target_path=configuration.command_surface_path,
            )

        self.assertFalse(result)
        self.assertIn("only built-in actions", error.call_args.args[1])
        save.assert_not_called()

    def test_quick_action_write_failure_reports_error_without_refreshing(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.command_surface_path = Path("shared-commands.json")
        configuration.local_command_surface_path = Path("missing-local-commands.json")
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()
        configuration.feedback_var = FakeVariable("unchanged")
        configuration.feedback_label = Mock()
        item = CommandItem("docs", "Docs", action_ids=("one",))

        with (
            patch(
                "context_palette.configuration_window.save_command_item",
                side_effect=OSError("The file is locked."),
            ),
            patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error,
        ):
            saved = configuration._save_button(
                "tools",
                "Tools",
                item,
                "tools",
                "docs",
                target_path=configuration.command_surface_path,
            )

        self.assertFalse(saved)
        configuration.on_change.assert_not_called()
        configuration._reload.assert_not_called()
        self.assertEqual(configuration.feedback_var.value, "unchanged")
        self.assertEqual(error.call_args.args[0], "Quick action was not saved")
        self.assertIn("left unchanged", error.call_args.args[1])

    def test_cancelling_shared_action_deletion_preserves_action(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [
            Action("shared", "Shared", "General", "copy_text", "one")
        ]
        configuration.local_action_ids = set()
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.command_surface_path = Path("commands.json")
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.palette_path = Path("palette.json")
        configuration.window = FakeWindow()

        with (
            patch(
                "context_palette.configuration_window.inspect_action_references",
                return_value=ActionDeletionReport(3, 1, 2),
            ),
            patch(
                "context_palette.configuration_window.messagebox.askyesno",
                return_value=False,
            ) as confirmation,
            patch(
                "context_palette.configuration_window.delete_action_and_references"
            ) as delete,
        ):
            configuration._delete_action()

        self.assertIn("3 saved reference(s)", confirmation.call_args.args[1])
        self.assertIn("built-in action", confirmation.call_args.args[1])
        delete.assert_not_called()
        self.assertEqual([action.id for action in configuration.actions], ["shared"])

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
        dialog = ActionDialog.__new__(ActionDialog)
        dialog.action_type = "copy_text"
        dialog.action = None
        dialog.context_names = ()
        dialog.title_var = FakeVariable("Greeting")
        dialog.description_var = FakeVariable("Professional opening")
        dialog.contexts_var = FakeVariable()
        dialog.tags_var = FakeVariable()
        dialog.arguments_var = FakeVariable()
        dialog.working_directory_var = FakeVariable()
        dialog.value = FakeText("Hello")
        dialog.window = FakeWindow()
        dialog.on_save = lambda _action: False

        dialog._save()

        self.assertEqual(dialog.window.destroy_calls, 0)

    def test_action_dialog_closes_when_save_callback_succeeds(self) -> None:
        dialog = ActionDialog.__new__(ActionDialog)
        dialog.action_type = "copy_text"
        dialog.action = None
        dialog.context_names = ()
        dialog.title_var = FakeVariable("Greeting")
        dialog.description_var = FakeVariable("Professional opening")
        dialog.contexts_var = FakeVariable()
        dialog.tags_var = FakeVariable()
        dialog.arguments_var = FakeVariable()
        dialog.working_directory_var = FakeVariable()
        dialog.value = FakeText("Hello")
        dialog.window = FakeWindow()
        dialog.on_save = lambda _action: True

        dialog._save()

        self.assertEqual(dialog.window.destroy_calls, 1)

    def test_new_action_passes_explicit_project_destination(self) -> None:
        dialog = ActionDialog.__new__(ActionDialog)
        dialog.action_type = "copy_text"
        dialog.action = None
        dialog.context_names = ()
        dialog.choose_destination = True
        dialog.destination_var = FakeVariable(PROJECT_DESTINATION)
        dialog.title_var = FakeVariable("Greeting")
        dialog.description_var = FakeVariable()
        dialog.contexts_var = FakeVariable()
        dialog.tags_var = FakeVariable()
        dialog.arguments_var = FakeVariable()
        dialog.working_directory_var = FakeVariable()
        dialog.value = FakeText("Hello")
        dialog.window = FakeWindow()
        destinations: list[str] = []
        dialog.on_save = (
            lambda _action, destination: destinations.append(destination) or True
        )

        dialog._save()

        self.assertEqual(destinations, [PROJECT_DESTINATION])
        self.assertEqual(dialog.window.destroy_calls, 1)

    def test_configuration_saves_new_project_action_to_tracked_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "actions.json"
            local_path = root / "local_actions.json"
            configuration = ConfigurationWindow.__new__(ConfigurationWindow)
            configuration.shared_actions_path = project_path
            configuration.local_actions_path = local_path
            configuration.actions = []
            configuration.local_action_ids = set()
            configuration.window = FakeWindow()
            configuration.action_filter_var = FakeVariable()
            configuration.feedback_var = FakeVariable()
            configuration.feedback_label = Mock()
            configuration.on_change = Mock()
            configuration._render_actions = Mock()
            action = Action(
                "project-action",
                "Project action",
                "General",
                "copy_text",
                "Hello",
            )

            self.assertTrue(
                configuration._save_action(action, PROJECT_DESTINATION)
            )

            self.assertEqual(load_actions(project_path), [action])
            self.assertFalse(local_path.exists())
            self.assertEqual(configuration.local_action_ids, set())

    def test_action_dialog_rejects_an_unknown_specific_context(self) -> None:
        dialog = ActionDialog.__new__(ActionDialog)
        dialog.action_type = "copy_text"
        dialog.action = None
        dialog.context_names = ("General", "Mail")
        dialog.title_var = FakeVariable("Greeting")
        dialog.description_var = FakeVariable("Professional opening")
        dialog.contexts_var = FakeVariable("Typo")
        dialog.tags_var = FakeVariable()
        dialog.arguments_var = FakeVariable()
        dialog.working_directory_var = FakeVariable()
        dialog.value = FakeText("Hello")
        dialog.window = FakeWindow()
        saved: list[Action] = []
        dialog.on_save = lambda action: saved.append(action) or True

        with patch("context_palette.configuration_window.messagebox.showerror") as error:
            dialog._save()

        self.assertEqual(saved, [])
        self.assertEqual(dialog.window.destroy_calls, 0)
        self.assertIn("Unknown specific context: Typo", error.call_args.args[1])

    def test_action_dialog_picker_selections_reach_created_action(self) -> None:
        root = tk.Tk()
        root.withdraw()
        saved: list[Action] = []
        try:
            existing = Action(
                "existing",
                "Existing",
                "General",
                "copy_text",
                "text",
                tags=("sql",),
            )
            dialog = ActionDialog(
                root,
                "copy_text",
                [existing],
                lambda action: saved.append(action) or True,
                context_names=["General", "Mail"],
            )
            root.update_idletasks()
            dialog.title_var.set("Reusable response")
            dialog.description_var.set("Professional opening for a customer reply")
            dialog.tags_var.set("new tag")
            dialog.value.insert("1.0", "Hello")

            dialog.context_field.menu.invoke(
                dialog.context_field.context_names.index("Mail")
            )
            dialog.tag_field.menu.invoke(
                dialog.tag_field.tag_names.index("sql")
            )
            dialog._save()

            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].effective_contexts, ("Mail",))
            self.assertEqual(saved[0].effective_tags, ("new tag", "sql"))
            self.assertEqual(saved[0].value, "Hello")
            self.assertEqual(
                saved[0].description,
                "Professional opening for a customer reply",
            )
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

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

    def test_new_context_passes_explicit_local_destination(self) -> None:
        dialog = ContextDialog.__new__(ContextDialog)
        dialog.name = FakeVariable("Research")
        dialog.description = FakeVariable()
        dialog.action_choices = {}
        dialog.slots = []
        dialog.original_name = ""
        dialog.choose_destination = True
        dialog.destination_var = FakeVariable(LOCAL_DESTINATION)
        dialog.window = FakeWindow()
        destinations: list[str] = []
        dialog.on_save = (
            lambda _context, _original, destination: (
                destinations.append(destination) or True
            )
        )

        dialog._save()

        self.assertEqual(destinations, [LOCAL_DESTINATION])
        self.assertEqual(dialog.window.destroy_calls, 1)

    def test_context_dialog_saves_member_actions_independently_of_action_records(self) -> None:
        root = tk.Tk()
        root.withdraw()
        saved: list[ContextDefinition] = []
        try:
            actions = [
                Action("built-in", "Built in", "General", "copy_text", "one"),
                Action("local", "Local", "General", "copy_text", "two"),
            ]
            dialog = ContextDialog(
                root,
                ContextDefinition(
                    "My work",
                    preferred_action_ids=("built-in",),
                    action_ids=("built-in", "local"),
                ),
                actions,
                lambda context, _original: saved.append(context) or True,
            )
            root.update_idletasks()

            self.assertEqual(dialog.member_action_ids, ["built-in", "local"])
            self.assertEqual(dialog.member_list.size(), 2)
            dialog._save()

            self.assertEqual(saved[0].action_ids, ("built-in", "local"))
            self.assertEqual(saved[0].preferred_action_ids, ("built-in",))
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_new_quick_action_group_passes_project_destination(self) -> None:
        dialog = GroupDialog.__new__(GroupDialog)
        dialog.group = None
        dialog.original_group_id = ""
        dialog.label_var = FakeVariable("Project tools")
        dialog.id_var = FakeVariable()
        dialog.destination_var = FakeVariable(PROJECT_DESTINATION)
        dialog.window = FakeWindow()
        captured: list[tuple[CommandGroup, str, str]] = []
        dialog.on_save = lambda *args: captured.append(args) or True

        dialog._save()

        self.assertEqual(captured[0][0].id, "project-tools")
        self.assertEqual(captured[0][0].label, "Project tools")
        self.assertEqual(captured[0][2], PROJECT_DESTINATION)
        self.assertEqual(dialog.window.destroy_calls, 1)

    def test_shared_edit_dialog_titles_identify_permanent_destination(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            context_dialog = ContextDialog(
                root,
                ContextDefinition("Shared"),
                [],
                lambda _context, _original_name: True,
                shared=True,
            )
            self.assertEqual(context_dialog.window.title(), "Edit built-in context")
            context_dialog.window.destroy()

            item = CommandItem("docs", "Docs")
            button_dialog = ButtonDialog(
                root,
                CommandGroup("tools", "Tools", (item,)),
                item,
                [],
                lambda *_args: True,
                shared=True,
            )
            self.assertEqual(
                button_dialog.window.title(),
                "Edit built-in Quick action",
            )
            button_dialog.window.destroy()
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_quick_action_dialog_preserves_more_than_four_menu_actions(self) -> None:
        root = tk.Tk()
        root.withdraw()
        captured: list[CommandItem] = []
        try:
            actions = [
                Action(
                    f"action-{index}",
                    f"Action {index}",
                    "General",
                    "copy_text",
                    str(index),
                )
                for index in range(6)
            ]
            item = CommandItem(
                "many",
                "Many",
                primary_action_id="action-0",
                action_ids=tuple(action.id for action in actions),
            )
            dialog = ButtonDialog(
                root,
                CommandGroup("tools", "Tools", (item,)),
                item,
                actions,
                lambda _group_id, _group_label, saved, *_args: (
                    captured.append(saved) or True
                ),
            )

            self.assertEqual(dialog.assigned_action_ids, [action.id for action in actions])
            self.assertEqual(dialog.assignment_list.size(), 6)
            dialog._save()

            self.assertEqual(captured[0].action_ids, tuple(action.id for action in actions))
            self.assertEqual(captured[0].primary_action_id, "action-0")
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_project_quick_action_rejects_existing_local_action_reference(self) -> None:
        root = tk.Tk()
        root.withdraw()
        saved: list[CommandItem] = []
        try:
            project_action = Action(
                "project",
                "Project",
                "General",
                "copy_text",
                "project",
            )
            item = CommandItem(
                "mixed",
                "Mixed",
                primary_action_id="project",
                action_ids=("project", "local-only"),
            )
            dialog = ButtonDialog(
                root,
                CommandGroup("tools", "Tools", (item,)),
                item,
                [project_action],
                lambda _group_id, _group_label, value, *_args: (
                    saved.append(value) or True
                ),
                shared=True,
            )
            root.update_idletasks()

            with patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error:
                dialog._save()

            self.assertEqual(saved, [])
            self.assertIn("only built-in actions", error.call_args.args[1])
            self.assertTrue(dialog.window.winfo_exists())
            dialog.window.destroy()
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

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
