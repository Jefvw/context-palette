from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.configuration_window import (
    ActionDialog,
    ActionBoundQuickSelection,
    ButtonDialog,
    CONFIGURATION_TAB_INDEXES,
    ConfigurationWindow,
    ContextDialog,
    GroupDialog,
    LOCAL_DESTINATION,
    PROJECT_DESTINATION,
    EMPTY_PIN_LABEL,
    action_reference_labels,
    action_matches_filter,
    compact_selection_summary,
    compact_selection_title,
    context_action_summary,
    context_membership_count,
    context_matches_filter,
    quick_action_matches_filter,
    select_first_tree_item,
    _focus_entry,
)
from context_palette.action_deletion import ActionDeletionError, ActionDeletionReport
from context_palette.action_suggestions import ActionCreationSuggestion
from context_palette.action_bound_quick_actions import action_bound_quick_groups
from context_palette.action_picker import ActionPickerField
from context_palette.actions import Action, ActionError, append_action, load_actions
from context_palette.command_surface import (
    CommandGroup,
    CommandItem,
    CommandTarget,
    GROUP_PRESENTATION_NESTED_MENU,
)
from context_palette.contexts import ContextDefinition
from context_palette.palette_state import PaletteState, load_palette_state
from context_palette.work_items import DiscoveredWorkItem, WorkItemReference


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
        self.bindings: list[object] = []
        self.cancelled: list[str] = []

    def after_idle(self, callback: object) -> str:
        self.callbacks.append(callback)
        return "after#focus"

    def after_cancel(self, callback_id: str) -> None:
        self.cancelled.append(callback_id)

    def bind(self, _sequence: str, callback: object, *, add: str) -> None:
        self.bindings.append(callback)


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


class ContextMembershipCountTests(unittest.TestCase):
    def test_selection_summary_is_bounded(self) -> None:
        value = compact_selection_summary("word " * 100)

        self.assertLessEqual(len(value), 180)
        self.assertTrue(value.endswith("…"))

    def test_explicit_context_membership_is_authoritative(self):
        context = ContextDefinition(
            "My work",
            preferred_action_ids=("one",),
            action_ids=("one", "two", "two"),
        )
        actions = [
            Action("one", "One", "General", "copy_text", "1"),
            Action("legacy", "Legacy", "My work", "copy_text", "2"),
        ]

        self.assertEqual(context_membership_count(context, actions), 2)

    def test_legacy_context_membership_includes_preferred_actions_once(self):
        context = ContextDefinition(
            "My work",
            preferred_action_ids=("one", "preferred-only"),
        )
        actions = [
            Action("one", "One", "My work", "copy_text", "1"),
            Action("two", "Two", "My work", "copy_text", "2"),
        ]

        self.assertEqual(context_membership_count(context, actions), 3)


class ActionReferenceLabelTests(unittest.TestCase):
    def test_action_references_use_names_and_identify_missing_actions(self):
        actions = [
            Action("open-project", "Open project folder", "General", "open_folder", "."),
            Action("copy-greeting", "Friendly greeting", "General", "copy_text", "Hi"),
        ]

        labels = action_reference_labels(
            ("open-project", "missing-id", "copy-greeting"),
            actions,
        )

        self.assertEqual(
            labels,
            (
                "Open project folder",
                "Missing action: missing-id",
                "Friendly greeting",
            ),
        )

    def test_context_summary_uses_action_names_instead_of_ids(self):
        actions = [
            Action("open-project", "Open project folder", "General", "open_folder", "."),
            Action("open-code", "Open code editor", "General", "launch_app", "code.exe"),
        ]
        context = ContextDefinition(
            "Developing",
            preferred_action_ids=("open-project", "open-code"),
            action_ids=("open-project", "open-code"),
        )

        summary = context_action_summary(context, actions)

        self.assertEqual(
            summary,
            "2 member(s) · Context shortcuts: Open project folder, Open code editor",
        )
        self.assertNotIn("open-project", summary)


class ActionSurfaceRefreshTests(unittest.TestCase):
    def test_action_view_refresh_updates_every_dependent_configuration_surface(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration._render_actions = Mock()
        configuration._render_contexts = Mock()
        configuration._render_buttons = Mock()
        configuration._refresh_diagnostics = Mock()

        configuration._refresh_action_views()

        configuration._render_actions.assert_called_once_with()
        configuration._render_contexts.assert_called_once_with()
        configuration._render_buttons.assert_called_once_with()
        configuration._refresh_diagnostics.assert_called_once_with()


class ConfigurationFilterTests(unittest.TestCase):
    def test_context_filter_searches_names_descriptions_actions_and_storage(self):
        actions = [
            Action("open-code", "Open code editor", "General", "launch_app", "code.exe")
        ]
        context = ContextDefinition(
            "Development",
            description="Application maintenance",
            action_ids=("open-code",),
        )

        for query in (
            "development",
            "maintenance",
            "open code",
            "my configuration",
        ):
            self.assertTrue(
                context_matches_filter(
                    context,
                    query,
                    actions=actions,
                    personal=True,
                )
            )
        self.assertFalse(
            context_matches_filter(
                context,
                "database",
                actions=actions,
                personal=True,
            )
        )

    def test_quick_action_filter_searches_group_item_action_and_storage(self):
        actions = [
            Action("open-code", "Open code editor", "General", "launch_app", "code.exe")
        ]
        item = CommandItem("code", "Editor", action_ids=("open-code",))
        group = CommandGroup("navigation", "Navigation", (item,))

        for query in ("navigation", "editor", "open code", "built-in"):
            self.assertTrue(
                quick_action_matches_filter(
                    group,
                    item,
                    query,
                    actions=actions,
                    personal=False,
                )
            )
        self.assertFalse(
            quick_action_matches_filter(
                group,
                item,
                "personal",
                actions=actions,
                personal=False,
            )
        )

    def test_quick_action_filter_searches_work_item_identity(self):
        work_item = DiscoveredWorkItem(
            "product-work",
            "Product work",
            "ISS-ABC-example",
            ROOT / "ISS-ABC-example",
            "ISS-ABC-example",
            "ISS",
            "Issue",
            "ABC",
            "example",
            ("AB9C",),
            None,
        )
        item = CommandItem(
            "current",
            "Current item",
            work_item_ref=WorkItemReference(
                work_item.source_id,
                work_item.relative_folder,
            ),
        )
        group = CommandGroup("work", "Work", (item,))

        for query in ("current item", "product work", "ISS-ABC", "AB9C"):
            self.assertTrue(
                quick_action_matches_filter(
                    group,
                    item,
                    query,
                    actions=[],
                    personal=True,
                    work_items=(work_item,),
                )
            )


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
        self.rows: dict[str, tuple[str, dict[str, object]]] = {}
        self.seen: str | None = None
        self.configuration: dict[str, object] = {}

    def delete(self, *_items: str) -> None:
        self.inserted.clear()
        self.rows.clear()

    def insert(self, parent: str, _position: str, *, iid: str, **options: object) -> None:
        self.inserted.append(iid)
        self.rows[iid] = (parent, options)

    def tag_configure(self, _tag: str, **_options: object) -> None:
        return

    def configure(self, **options: object) -> None:
        self.configuration.update(options)

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
    def test_selection_title_is_single_line_and_bounded(self) -> None:
        title = "  A long\nAction title  " * 20

        compact = compact_selection_title(title)

        self.assertNotIn("\n", compact)
        self.assertLessEqual(len(compact), 88)
        self.assertTrue(compact.endswith("…"))

    def test_context_selection_card_reflects_selected_context(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts = [
            ContextDefinition(
                "Developing",
                description="Application maintenance",
                action_ids=("one",),
                preferred_action_ids=("one",),
            )
        ]
        configuration.actions = [
            Action("one", "One", "General", "copy_text", "Text")
        ]
        configuration.context_tree = FakeSelectedConfigTree(
            "context-0",
            LOCAL_DESTINATION,
        )
        configuration.context_detail_title_var = FakeVariable()
        configuration.context_detail_summary_var = FakeVariable()
        configuration.context_edit_button = Mock()
        configuration.context_delete_button = Mock()

        configuration._update_context_controls()

        self.assertEqual(
            configuration.context_detail_title_var.value,
            "Developing",
        )
        self.assertIn(
            "1 member(s) · 1 context shortcut(s)",
            configuration.context_detail_summary_var.value,
        )
        self.assertIn(
            "Application maintenance",
            configuration.context_detail_summary_var.value,
        )
        configuration.context_edit_button.configure.assert_called_once_with(
            state="normal"
        )
        configuration.context_delete_button.configure.assert_called_once_with(
            state="normal"
        )

    def test_empty_context_selection_disables_selection_commands(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts = []
        configuration.context_tree = Mock()
        configuration.context_tree.selection.return_value = ()
        configuration.context_detail_title_var = FakeVariable()
        configuration.context_detail_summary_var = FakeVariable()
        configuration.context_edit_button = Mock()
        configuration.context_delete_button = Mock()

        configuration._update_context_controls()

        self.assertEqual(
            configuration.context_detail_title_var.value,
            "Select a Context",
        )
        configuration.context_edit_button.configure.assert_called_once_with(
            state="disabled"
        )
        configuration.context_delete_button.configure.assert_called_once_with(
            state="disabled"
        )

    def test_custom_quick_menu_selection_enables_valid_commands(self) -> None:
        local_path = Path("local-commands.json")
        selected_group = CommandGroup(
            "selected",
            "Selected menu",
            source_path=local_path,
        )
        next_group = CommandGroup(
            "next",
            "Next menu",
            source_path=local_path,
        )
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [selected_group, next_group]
        configuration.actions = []
        configuration.command_surface_path = Path("shared-commands.json")
        configuration.local_command_surface_path = local_path
        configuration.button_tree = FakeSelectedActionTree("group-0")
        configuration.action_bound_button_records = {}
        configuration.button_preview_var = FakeVariable()
        configuration.button_detail_title_var = FakeVariable()
        configuration.quick_item_edit_button = Mock()
        configuration.new_quick_item_button = Mock()
        configuration.quick_item_move_menu = Mock()
        configuration.quick_item_move_button = Mock()
        configuration.quick_item_delete_button = Mock()

        configuration._update_button_preview()

        configuration.quick_item_edit_button.configure.assert_called_once_with(
            text="Edit…",
            state="normal",
        )
        configuration.new_quick_item_button.configure.assert_called_once_with(
            text="New Quick action…",
            state="normal",
        )
        self.assertEqual(
            configuration.quick_item_move_menu.entryconfigure.call_args_list,
            [
                call(0, state="disabled"),
                call(1, state="normal"),
            ],
        )
        configuration.quick_item_delete_button.configure.assert_called_once_with(
            state="normal"
        )
        configuration.new_quick_item_button.pack.assert_called_once()
        configuration.quick_item_edit_button.pack.assert_called_once()
        configuration.quick_item_move_button.pack.assert_called_once()
        configuration.quick_item_delete_button.pack.assert_called_once()

    def test_standard_quick_menu_root_is_fixed_but_its_contents_remain_editable(self) -> None:
        local_path = Path("local-commands.json")
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [
            CommandGroup("standard", "Standard"),
            CommandGroup("next", "Next", source_path=local_path),
        ]
        configuration.actions = []
        configuration.command_surface_path = Path("shared-commands.json")
        configuration.local_command_surface_path = local_path
        configuration.button_tree = FakeSelectedActionTree("group-0")
        configuration.action_bound_button_records = {}
        configuration.button_preview_var = FakeVariable()
        configuration.button_detail_title_var = FakeVariable()
        configuration.quick_item_edit_button = Mock()
        configuration.new_quick_item_button = Mock()
        configuration.quick_item_move_menu = Mock()
        configuration.quick_item_move_button = Mock()
        configuration.quick_item_delete_button = Mock()

        configuration._update_button_preview()

        configuration.quick_item_edit_button.configure.assert_called_once_with(
            text="Edit…",
            state="normal",
        )
        configuration.new_quick_item_button.configure.assert_called_once_with(
            text="New Quick action…",
            state="normal",
        )
        self.assertEqual(
            configuration.quick_item_move_menu.entryconfigure.call_args_list,
            [call(0, state="disabled"), call(1, state="disabled")],
        )
        configuration.quick_item_delete_button.configure.assert_called_once_with(
            state="disabled"
        )
        self.assertIn("Fixed first menu", configuration.button_preview_var.value)
        configuration.new_quick_item_button.pack.assert_called_once()
        configuration.quick_item_edit_button.pack.assert_called_once()
        configuration.quick_item_move_button.pack.assert_not_called()
        configuration.quick_item_delete_button.pack.assert_not_called()

    def test_configured_quick_manager_selects_exact_stable_submenu(self) -> None:
        child = CommandItem("child", "Child")
        parent = CommandItem("parent", "Parent", items=(child,))
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [CommandGroup("tools", "Tools", (parent,))]
        configuration.notebook = Mock()
        configuration.button_filter_var = FakeVariable()
        configuration.button_tree = Mock()
        configuration.button_tree.exists.return_value = True
        configuration._update_button_preview = Mock()

        selected = configuration.select_configured_quick_action(
            "TOOLS",
            ("PARENT", "CHILD"),
        )

        self.assertTrue(selected)
        configuration.notebook.select.assert_called_once_with(
            CONFIGURATION_TAB_INDEXES["buttons"]
        )
        configuration.button_tree.selection_set.assert_called_once_with(
            "button-0-0.0"
        )
        configuration.button_tree.see.assert_called_once_with("button-0-0.0")

    def test_automatic_quick_manager_selects_exact_branch(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = Mock()
        configuration.button_filter_var = FakeVariable()
        configuration.button_tree = Mock()
        configuration.action_bound_button_records = {
            "automatic-work": ActionBoundQuickSelection(
                "Folders",
                "open_folder",
                ("Work", "Reports"),
            ),
            "automatic-other": ActionBoundQuickSelection(
                "Folders",
                "open_folder",
                ("Other",),
            ),
        }
        configuration._update_button_preview = Mock()

        selected = configuration.select_automatic_quick_action(
            "open_folder",
            ("work", "REPORTS"),
        )

        self.assertTrue(selected)
        configuration.button_tree.selection_set.assert_called_once_with(
            "automatic-work"
        )
        configuration.button_tree.see.assert_called_once_with("automatic-work")

    def test_automatic_quick_action_disables_structure_commands(self) -> None:
        action = Action(
            "folder",
            "Reports folder",
            "General",
            "open_folder",
            ".",
        )
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [action]
        configuration.button_tree = FakeSelectedActionTree("automatic-folder")
        configuration.action_bound_button_records = {
            "automatic-folder": ActionBoundQuickSelection(
                "Folders",
                "open_folder",
                ("Reports",),
                action.id,
            )
        }
        configuration.button_preview_var = FakeVariable()
        configuration.button_detail_title_var = FakeVariable()
        configuration.quick_item_edit_button = Mock()
        configuration.new_quick_item_button = Mock()
        configuration.quick_item_move_menu = Mock()
        configuration.quick_item_move_button = Mock()
        configuration.quick_item_delete_button = Mock()

        configuration._update_button_preview()

        configuration.quick_item_edit_button.configure.assert_called_once_with(
            text="Edit Action…",
            state="normal",
        )
        configuration.new_quick_item_button.configure.assert_called_once_with(
            text="New submenu…",
            state="disabled",
        )
        configuration.quick_item_move_button.configure.assert_called_once_with(
            state="disabled"
        )
        configuration.quick_item_delete_button.configure.assert_called_once_with(
            state="disabled"
        )
        configuration.quick_item_edit_button.pack.assert_called_once()
        configuration.new_quick_item_button.pack.assert_not_called()
        configuration.quick_item_move_button.pack.assert_not_called()
        configuration.quick_item_delete_button.pack.assert_not_called()

    def test_automatic_branch_offers_typed_add_and_matching_actions(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = []
        configuration.button_tree = FakeSelectedActionTree("automatic-work")
        configuration.action_bound_button_records = {
            "automatic-work": ActionBoundQuickSelection(
                "Folders",
                "open_folder",
                ("Work",),
            )
        }
        configuration.button_preview_var = FakeVariable()
        configuration.button_detail_title_var = FakeVariable()
        configuration.quick_item_edit_button = Mock()
        configuration.new_quick_item_button = Mock()
        configuration.quick_item_move_menu = Mock()
        configuration.quick_item_move_button = Mock()
        configuration.quick_item_delete_button = Mock()

        configuration._update_button_preview()

        configuration.new_quick_item_button.configure.assert_called_once_with(
            text="Add folder here…",
            state="normal",
        )
        configuration.quick_item_edit_button.configure.assert_called_once_with(
            text="Find matching Actions…",
            state="normal",
        )
        configuration.new_quick_item_button.pack.assert_called_once()
        configuration.quick_item_edit_button.pack.assert_called_once()

    def test_reused_configuration_opens_requested_active_action_editor_directly(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action("edit-me", "Edit me", "General", "copy_text", "one")
        configuration.actions = [action]
        configuration.stored_actions = [action]
        configuration.initial_action_id = None
        configuration.action_filter_var = FakeVariable("hidden query")
        configuration.action_state_filter_var = FakeVariable("Archived")
        configuration.notebook = Mock()
        configuration.work_items_panel = Mock()
        configuration.window = Mock()
        configuration._reload = Mock()
        configuration._focus_current_tab = Mock()
        configuration._edit_action_record = Mock()
        configuration._pending_action_edit_id = None
        configuration._pending_action_edit_after_id = None
        callbacks: list[object] = []
        configuration.window.after_idle.side_effect = (
            lambda callback: callbacks.append(callback) or f"after#{len(callbacks)}"
        )

        configuration.show(
            initial_tab="actions",
            initial_action_id="EDIT-ME",
            start_action_edit=True,
        )
        for callback in callbacks:
            callback()

        self.assertEqual(configuration.action_filter_var.value, "")
        self.assertEqual(configuration.action_state_filter_var.value, "Active")
        configuration._reload.assert_called_once_with()
        configuration.notebook.select.assert_called_once_with(1)
        configuration._edit_action_record.assert_called_once_with(action)
        configuration.window.deiconify.assert_called_once_with()
        configuration.window.lift.assert_called_once_with()

    def test_automatic_menu_creation_forwards_type_and_exact_path(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration._raise_existing_action_creation_dialog = Mock(return_value=False)
        configuration._create_action_for_type = Mock()

        configuration.create_action_for_automatic_menu(
            "open_folder",
            ("Work", "Reports"),
        )

        configuration._create_action_for_type.assert_called_once_with(
            "open_folder",
            initial_quick_action_path=("Work", "Reports"),
        )

    def test_direct_action_edit_fails_safely_when_active_action_disappeared(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = []
        configuration.stored_actions = [
            Action(
                "archived",
                "Archived",
                "General",
                "copy_text",
                "one",
                state="Archived",
            )
        ]
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        configuration._edit_action_record = Mock()

        configuration._edit_action_by_id("archived")

        configuration._edit_action_record.assert_not_called()
        self.assertIn("no longer available", configuration.feedback_var.value)
        configuration.feedback_label.configure.assert_called_once_with(
            style="Error.TLabel"
        )

    def test_repeated_direct_edit_requests_coalesce_to_the_latest_action(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = Mock()
        configuration._pending_action_edit_id = None
        configuration._pending_action_edit_after_id = None
        configuration._edit_action_by_id = Mock()
        callbacks: list[object] = []
        configuration.window.after_idle.side_effect = (
            lambda callback: callbacks.append(callback) or "after#edit"
        )

        configuration._schedule_action_edit("first")
        configuration._schedule_action_edit("second")

        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        configuration._edit_action_by_id.assert_called_once_with("second")
        self.assertIsNone(configuration._pending_action_edit_after_id)

    def test_closing_configuration_cancels_pending_direct_edit(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = Mock()
        configuration.backup_restore_panel = None
        configuration._pending_action_edit_id = "edit-me"
        configuration._pending_action_edit_after_id = "after#edit"

        configuration._request_close()

        configuration.window.after_cancel.assert_called_once_with("after#edit")
        configuration.window.destroy.assert_called_once_with()
        self.assertIsNone(configuration._pending_action_edit_id)
        self.assertIsNone(configuration._pending_action_edit_after_id)

    def test_existing_action_editor_is_raised_instead_of_duplicated(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        existing_dialog = Mock()
        existing_dialog.window.winfo_exists.return_value = True
        configuration.action_edit_dialog = existing_dialog
        action = Action("edit-me", "Edit me", "General", "copy_text", "one")

        with patch("context_palette.configuration_window.ActionDialog") as dialog:
            configuration._edit_action_record(action)

        dialog.assert_not_called()
        existing_dialog.window.lift.assert_called_once_with()
        existing_dialog.window.focus_force.assert_called_once_with()

    def test_reload_keeps_stored_actions_separate_from_active_picker_projection(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        active = Action("active", "Active", "General", "copy_text", "one")
        archived = Action(
            "archived",
            "Archived",
            "General",
            "copy_text",
            "two",
            state="Archived",
        )
        configuration.window = Mock()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.palette_path = Path("palette.json")
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("missing-local-contexts.json")
        configuration.command_surface_path = Path("commands.json")
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration._refresh_action_views = Mock()

        with (
            patch(
                "context_palette.configuration_window.load_combined_actions",
                return_value=([active], {"active"}),
            ),
            patch(
                "context_palette.configuration_window.load_combined_stored_actions",
                return_value=([active, archived], {"active", "archived"}),
            ),
            patch(
                "context_palette.configuration_window.load_palette_state",
                return_value=PaletteState(),
            ),
            patch(
                "context_palette.configuration_window.load_combined_contexts",
                return_value=[],
            ),
            patch(
                "context_palette.configuration_window.load_combined_command_groups",
                return_value=[],
            ),
        ):
            configuration._reload()

        self.assertEqual(configuration.actions, [active])
        self.assertEqual(configuration.stored_actions, [active, archived])
        self.assertEqual(configuration.local_action_ids, {"active", "archived"})
        configuration._refresh_action_views.assert_called_once_with()

    def test_requested_work_item_creation_uses_work_items_panel(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.work_items_panel = Mock()

        configuration._start_work_item_creation()

        configuration.work_items_panel.create_work_item.assert_called_once_with()

    def test_ctrl_n_starts_quick_action_creation(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration._start_action_creation = Mock()

        self.assertEqual(
            configuration._handle_configure_keypress(FakeEvent(state=0x0004, keysym="n")),
            "break",
        )

        configuration._start_action_creation.assert_called_once_with()

    def test_quick_creation_prefills_the_active_non_general_focus(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.focus_context = "Customer"
        configuration.local_actions_path = Path("local_actions.json")
        configuration.window = Mock()
        configuration.actions = []
        configuration.contexts = [ContextDefinition("Customer")]
        configuration._save_action = Mock()
        configuration.action_creation_dialog = None

        with patch("context_palette.configuration_window.ActionDialog") as dialog:
            configuration._create_action_for_type("copy_text")

        self.assertEqual(dialog.call_args.kwargs["initial_contexts"], ("Customer",))

    def test_workspace_suggestion_prefills_the_existing_creation_dialog(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.focus_context = "Customer"
        configuration.local_actions_path = Path("local_actions.json")
        configuration.window = Mock()
        configuration.actions = []
        configuration.contexts = [ContextDefinition("Customer")]
        configuration._save_action = Mock()
        configuration.action_creation_dialog = None
        suggestion = ActionCreationSuggestion(
            "open_file",
            "Open report.pdf",
            r"W:\Reports\report.pdf",
        )

        with patch("context_palette.configuration_window.ActionDialog") as dialog:
            configuration._create_action_for_type(
                "open_file",
                suggestion=suggestion,
            )

        self.assertEqual(dialog.call_args.kwargs["initial_title"], "Open report.pdf")
        self.assertEqual(
            dialog.call_args.kwargs["initial_value"],
            r"W:\Reports\report.pdf",
        )
        self.assertTrue(dialog.call_args.kwargs["suggested_from_workspace"])
        self.assertEqual(dialog.call_args.kwargs["initial_contexts"], ("Customer",))

    def test_repeated_workspace_suggestions_coalesce_and_close_cancels_pending(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = Mock()
        configuration.backup_restore_panel = None
        configuration._pending_action_edit_id = None
        configuration._pending_action_edit_after_id = None
        configuration._pending_action_suggestion = None
        configuration._pending_action_suggestion_after_id = None
        configuration._start_action_suggestion = Mock()
        callbacks: list[object] = []
        configuration.window.after_idle.side_effect = (
            lambda callback: callbacks.append(callback) or "after#suggestion"
        )
        first = ActionCreationSuggestion("open_url", "First", "https://first.example")
        second = ActionCreationSuggestion("open_url", "Second", "https://second.example")

        configuration._schedule_action_suggestion(first)
        configuration._schedule_action_suggestion(second)

        self.assertEqual(len(callbacks), 1)
        configuration._request_close()
        configuration.window.after_cancel.assert_called_once_with("after#suggestion")
        self.assertIsNone(configuration._pending_action_suggestion)
        self.assertIsNone(configuration._pending_action_suggestion_after_id)

    def test_quick_creation_refuses_while_backup_or_restore_is_busy(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.backup_restore_panel = Mock(busy=True)
        configuration._set_feedback = Mock()

        configuration._start_action_creation()

        configuration._set_feedback.assert_called_once()

    def test_quick_creation_does_not_open_overlapping_type_choosers(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.backup_restore_panel = Mock(busy=False)
        configuration.action_creation_dialog = None
        configuration.action_type_picker = None
        configuration.window = Mock()

        with patch("context_palette.configuration_window.ActionTypePickerDialog") as picker:
            created = picker.return_value
            created.window.winfo_exists.return_value = True
            configuration._start_action_creation()
            configuration._start_action_creation()

        picker.assert_called_once()
        created.window.lift.assert_called_once_with()

    def test_alt_mnemonics_select_configure_tabs(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook()

        for keysym, expected_tab in (
            ("a", 1),
            ("t", 2),
            ("c", 3),
            ("q", 4),
            ("w", 5),
            ("b", 6),
            ("d", 7),
        ):
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
        configuration.backup_restore_panel = FakeEntry()

        result = configuration._show_diagnostics_tab()
        callback = configuration.window.callbacks.pop()
        callback()

        self.assertEqual(result, "break")
        self.assertEqual(
            configuration.notebook.selected,
            CONFIGURATION_TAB_INDEXES["diagnostics"],
        )
        self.assertEqual(configuration.diagnostics_text.focus_calls, 1)

    def test_diagnostics_tab_change_moves_focus_into_read_only_summary(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook(
            selected=CONFIGURATION_TAB_INDEXES["diagnostics"]
        )
        configuration.action_tree = FakeEntry()
        configuration.type_list = FakeEntry()
        configuration.context_tree = FakeEntry()
        configuration.button_tree = FakeEntry()
        configuration.work_items_panel = FakeEntry()
        configuration.diagnostics_text = FakeEntry()
        configuration.backup_restore_panel = FakeEntry()

        configuration._focus_current_tab()

        self.assertEqual(configuration.diagnostics_text.focus_calls, 1)
        self.assertEqual(configuration.action_tree.focus_calls, 0)

    def test_backup_restore_tab_focuses_primary_action(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook(
            selected=CONFIGURATION_TAB_INDEXES["backup_restore"]
        )
        configuration.action_tree = FakeEntry()
        configuration.type_list = FakeEntry()
        configuration.context_tree = FakeEntry()
        configuration.button_tree = FakeEntry()
        configuration.work_items_panel = FakeEntry()
        configuration.diagnostics_text = FakeEntry()
        configuration.backup_restore_panel = Mock()

        configuration._focus_current_tab()

        configuration.backup_restore_panel.focus_primary.assert_called_once_with()

    def test_configure_waits_for_active_backup_before_closing(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = FakeWindow()
        configuration.backup_restore_panel = Mock(busy=True)
        configuration._set_feedback = Mock()

        configuration._request_close()

        self.assertEqual(configuration.window.destroy_calls, 0)
        configuration._set_feedback.assert_called_once()
        configuration.backup_restore_panel.close.assert_not_called()

    def test_restore_completion_closes_then_calls_launcher_adapter(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.window = FakeWindow()
        configuration.backup_restore_panel = Mock()
        configuration._launcher_restore_complete = Mock()

        configuration._restore_completed()

        configuration.backup_restore_panel.close.assert_called_once_with()
        self.assertEqual(configuration.window.destroy_calls, 1)
        configuration._launcher_restore_complete.assert_called_once_with()

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

    def test_find_shortcut_focuses_filter_for_current_tab(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook(selected=3)
        configuration.action_filter_entry = FakeEntry()
        configuration.context_filter_entry = FakeEntry()
        configuration.button_filter_entry = FakeEntry()

        result = configuration._focus_current_filter()

        self.assertEqual(result, "break")
        self.assertEqual(configuration.context_filter_entry.focus_calls, 1)
        self.assertEqual(configuration.context_filter_entry.selection, (0, "end"))
        self.assertEqual(configuration.action_filter_entry.focus_calls, 0)

    def test_find_shortcut_focuses_work_item_search(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.notebook = FakeNotebook(selected=5)
        configuration.action_filter_entry = FakeEntry()
        configuration.context_filter_entry = FakeEntry()
        configuration.button_filter_entry = FakeEntry()
        configuration.work_items_panel = Mock(search_entry=FakeEntry())

        result = configuration._focus_current_filter()

        self.assertEqual(result, "break")
        search = configuration.work_items_panel.search_entry
        self.assertEqual(search.focus_calls, 1)
        self.assertEqual(search.selection, (0, "end"))
        self.assertEqual(configuration.action_filter_entry.focus_calls, 0)

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
        self.assertTrue(action_matches_filter(action, "python-docs", personal=True))
        self.assertTrue(action_matches_filter(action, "docs.python.org", personal=True))
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
        self.assertEqual(
            configuration.action_tree.configuration["displaycolumns"],
            ("type", "contexts", "source"),
        )

    def test_action_state_filter_shows_archived_records_without_exposing_them_as_active(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        active = Action("active", "Active", "General", "copy_text", "one")
        archived = Action(
            "archived",
            "Archived",
            "General",
            "copy_text",
            "two",
            state="Archived",
        )
        configuration.actions = [active]
        configuration.stored_actions = [active, archived]
        configuration.local_action_ids = {"active", "archived"}
        configuration.initial_action_id = None
        configuration.action_filter_var = FakeVariable()
        configuration.action_state_filter_var = FakeVariable("Archived")
        configuration.action_filter_count_var = FakeVariable()
        configuration.action_tree = FakeActionTree()

        configuration._render_actions()

        self.assertEqual(configuration.action_tree.inserted, ["action-1"])
        self.assertEqual(configuration.action_filter_count_var.value, "1 archived")
        self.assertEqual(
            configuration.action_tree.configuration["displaycolumns"],
            ("type", "contexts", "source"),
        )
        self.assertEqual(configuration.actions, [active])

    def test_archive_confirmation_reports_impact_and_runs_lifecycle_service(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action("local", "Local action", "General", "copy_text", "one")
        configuration.actions = [action]
        configuration.stored_actions = [action]
        configuration.local_action_ids = {"local"}
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.command_surface_path = Path("commands.json")
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.palette_path = Path("palette.json")
        configuration.window = FakeWindow()
        configuration.initial_action_id = action.id
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        configuration.on_change = Mock()
        configuration._reload = Mock()

        with (
            patch(
                "context_palette.configuration_window.inspect_action_references",
                return_value=ActionDeletionReport(3, 1, 2),
            ),
            patch(
                "context_palette.configuration_window.messagebox.askyesno",
                return_value=True,
            ) as confirmation,
            patch(
                "context_palette.configuration_window.archive_action_and_references",
                return_value=ActionDeletionReport(3, 1, 3),
            ) as archive,
        ):
            configuration._change_action_state()

        self.assertIn("3 saved reference(s)", confirmation.call_args.args[1])
        self.assertIn("does not recreate", confirmation.call_args.args[1])
        archive.assert_called_once()
        configuration.on_change.assert_called_once_with()
        configuration._reload.assert_called_once_with()
        self.assertIn("Archived action", configuration.feedback_var.value)

    def test_restore_switches_to_active_and_does_not_claim_assignments_return(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action(
            "shared",
            "Shared action",
            "General",
            "copy_text",
            "one",
            state="Archived",
        )
        configuration.actions = []
        configuration.stored_actions = [action]
        configuration.local_action_ids = set()
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.window = FakeWindow()
        configuration.action_state_filter_var = FakeVariable("Archived")
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        configuration.on_change = Mock()
        configuration._reload = Mock()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askyesno",
                return_value=True,
            ) as confirmation,
            patch("context_palette.configuration_window.restore_action") as restore,
        ):
            configuration._change_action_state()

        self.assertIn("will not be recreated", confirmation.call_args.args[1])
        self.assertIn("tracked through Git", confirmation.call_args.args[1])
        restore.assert_called_once_with(Path("shared-actions.json"), "shared")
        self.assertEqual(configuration.action_state_filter_var.value, "Active")
        self.assertEqual(configuration.initial_action_id, "shared")
        self.assertIn("Reassign saved placements", configuration.feedback_var.value)

    def test_archive_failure_reloads_views_that_may_have_lost_placements(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action("local", "Local action", "General", "copy_text", "one")
        configuration.actions = [action]
        configuration.stored_actions = [action]
        configuration.local_action_ids = {"local"}
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.command_surface_path = Path("commands.json")
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.palette_path = Path("palette.json")
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()

        with (
            patch(
                "context_palette.configuration_window.inspect_action_references",
                return_value=ActionDeletionReport(1, 0, 1),
            ),
            patch(
                "context_palette.configuration_window.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "context_palette.configuration_window.archive_action_and_references",
                side_effect=ActionDeletionError(
                    "The Action remains Active; placements may have changed."
                ),
            ),
            patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error,
        ):
            configuration._change_action_state()

        configuration.on_change.assert_called_once_with()
        configuration._reload.assert_called_once_with()
        self.assertIn("remains Active", error.call_args.args[1])

    def test_editing_shared_action_warns_and_saves_to_shared_file(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action("shared", "Shared", "General", "copy_text", "one")
        configuration.actions = [action]
        configuration.local_action_ids = set()
        configuration.shared_actions_path = Path("shared-actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.contexts = []
        configuration.window = FakeWindow()
        configuration.action_filter_var = FakeVariable()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        configuration.on_change = Mock()
        configuration._reload = Mock()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askokcancel",
                return_value=True,
            ) as warning,
            patch("context_palette.configuration_window.ActionDialog") as dialog,
            patch(
                "context_palette.configuration_window.update_action_with_context_memberships"
            ) as update,
        ):
            configuration._edit_action()
            save_callback = dialog.call_args.args[3]
            self.assertTrue(save_callback(action))

        warning.assert_called_once()
        self.assertIn("tracked by Git", warning.call_args.args[1])
        update.assert_called_once_with(
            Path("shared-actions.json"),
            action,
            action,
            action_is_local=False,
            shared_contexts_path=Path("contexts.json"),
            local_contexts_path=Path("local-contexts.json"),
        )
        configuration._reload.assert_called_once_with()

    def test_action_edit_persists_atomically_and_preserves_previous_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            original = Action("shared", "Original", "General", "copy_text", "Before")
            updated = Action("shared", "Updated", "General", "copy_text", "After")
            append_action(path, original)
            contexts_path = Path(directory) / "contexts.json"
            contexts_path.write_text('{"contexts": []}\n', encoding="utf-8")
            configuration = ConfigurationWindow.__new__(ConfigurationWindow)
            configuration.actions = [original]
            configuration.shared_actions_path = path
            configuration.local_actions_path = Path(directory) / "local_actions.json"
            configuration.contexts_path = contexts_path
            configuration.local_contexts_path = Path(directory) / "local_contexts.json"
            configuration.window = FakeWindow()
            configuration.action_filter_var = FakeVariable()
            configuration.feedback_var = FakeVariable()
            configuration.feedback_label = Mock()
            configuration.on_change = Mock()
            configuration._reload = Mock()

            self.assertTrue(configuration._save_edited_action(updated, path))

            self.assertEqual(load_actions(path)[0], updated)
            self.assertEqual(
                load_actions(path.with_name("actions.json.bak"))[0],
                original,
            )
            configuration.on_change.assert_called_once_with()
            configuration._reload.assert_called_once_with()

    def test_archived_action_edit_requires_restore_before_context_assignment(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        archived = Action(
            "archived",
            "Archived",
            "General",
            "copy_text",
            "one",
            state="Archived",
        )
        edited = Action(
            "archived",
            "Archived",
            "Work",
            "copy_text",
            "one",
            state="Archived",
            contexts=("Work",),
        )
        configuration.actions = []
        configuration.stored_actions = [archived]
        configuration.window = FakeWindow()

        with (
            patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error,
            patch(
                "context_palette.configuration_window.update_action_with_context_memberships"
            ) as update,
        ):
            saved = configuration._save_edited_action(
                edited, Path("local-actions.json")
            )

        self.assertFalse(saved)
        self.assertIn("Restore it first", error.call_args.args[1])
        update.assert_not_called()

    def test_action_edit_write_failure_preserves_file_and_open_editor_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            original = Action("shared", "Original", "General", "copy_text", "Before")
            updated = Action("shared", "Updated", "General", "copy_text", "After")
            append_action(path, original)
            contexts_path = Path(directory) / "contexts.json"
            contexts_path.write_text('{"contexts": []}\n', encoding="utf-8")
            configuration = ConfigurationWindow.__new__(ConfigurationWindow)
            configuration.actions = [original]
            configuration.shared_actions_path = path
            configuration.local_actions_path = Path(directory) / "local_actions.json"
            configuration.contexts_path = contexts_path
            configuration.local_contexts_path = Path(directory) / "local_contexts.json"
            configuration.window = FakeWindow()
            configuration.action_filter_var = FakeVariable()
            configuration.feedback_var = FakeVariable("unchanged")
            configuration.feedback_label = Mock()
            configuration.on_change = Mock()
            configuration._render_actions = Mock()
            configuration._reload = Mock()

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

    def test_delete_context_reports_context_owned_action_count(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts = [
            ContextDefinition("My work", action_ids=("one", "two"))
        ]
        configuration.context_tree = FakeSelectedConfigTree(
            "context-0",
            LOCAL_DESTINATION,
        )
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.shared_actions_path = Path("actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.palette_path = Path("palette.json")
        configuration.actions = []
        configuration.local_action_ids = set()
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askyesno",
                return_value=True,
            ) as confirmation,
            patch(
                "context_palette.configuration_window.delete_context_and_memberships"
            ) as delete,
            patch(
                "context_palette.configuration_window.load_combined_actions",
                return_value=([], set()),
            ),
        ):
            configuration._delete_context()

        self.assertIn("2 action(s)", confirmation.call_args.args[1])
        delete.assert_called_once()
        self.assertIn("2 action(s)", configuration.feedback_var.value)

    def test_delete_built_in_context_explains_shared_git_impact(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.contexts = [ContextDefinition("Shared")]
        configuration.context_tree = FakeSelectedConfigTree(
            "context-0",
            PROJECT_DESTINATION,
        )
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.actions = []
        configuration.window = FakeWindow()

        with patch(
            "context_palette.configuration_window.messagebox.askyesno",
            return_value=False,
        ) as confirmation:
            configuration._delete_context()

        self.assertIn("tracked by Git", confirmation.call_args.args[1])
        self.assertIn("other computers", confirmation.call_args.args[1])

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

    def test_delete_built_in_quick_menu_explains_shared_git_impact(self) -> None:
        shared_path = Path("shared-commands.json")
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [
            CommandGroup("tools", "Tools", source_path=shared_path)
        ]
        configuration.button_tree = FakeSelectedActionTree("group-0")
        configuration.action_bound_button_records = {}
        configuration.command_surface_path = shared_path
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.window = FakeWindow()

        with patch(
            "context_palette.configuration_window.messagebox.askyesno",
            return_value=False,
        ) as confirmation:
            configuration._delete_button()

        self.assertIn("tracked by Git", confirmation.call_args.args[1])
        self.assertIn("other computers", confirmation.call_args.args[1])

    def test_fixed_standard_quick_menu_cannot_be_deleted(self) -> None:
        shared_path = Path("shared-commands.json")
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [
            CommandGroup("standard", "Standard", source_path=shared_path)
        ]
        configuration.button_tree = FakeSelectedActionTree("group-0")
        configuration.action_bound_button_records = {}
        configuration.command_surface_path = shared_path
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.feedback_var = FakeVariable()

        with (
            patch("context_palette.configuration_window.delete_command_group") as delete,
            patch("context_palette.configuration_window.messagebox.askyesno") as confirm,
        ):
            configuration._delete_button()

        delete.assert_not_called()
        confirm.assert_not_called()
        self.assertIn("fixed first menu", configuration.feedback_var.value)

    def test_move_built_in_quick_menu_requires_shared_change_confirmation(self) -> None:
        shared_path = Path("shared-commands.json")
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [
            CommandGroup("one", "One", source_path=shared_path),
            CommandGroup("two", "Two", source_path=shared_path),
        ]
        configuration.button_tree = FakeSelectedActionTree("group-0")
        configuration.action_bound_button_records = {}
        configuration.command_surface_path = shared_path
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.window = FakeWindow()

        with (
            patch(
                "context_palette.configuration_window.messagebox.askokcancel",
                return_value=False,
            ) as confirmation,
            patch(
                "context_palette.configuration_window.move_command_group"
            ) as move,
        ):
            configuration._move_button(1)

        self.assertIn("tracked by Git", confirmation.call_args.args[1])
        move.assert_not_called()

    def test_fixed_standard_quick_menu_cannot_be_moved(self) -> None:
        shared_path = Path("shared-commands.json")
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [
            CommandGroup("standard", "Standard", source_path=shared_path),
            CommandGroup("two", "Two", source_path=shared_path),
        ]
        configuration.button_tree = FakeSelectedActionTree("group-0")
        configuration.action_bound_button_records = {}
        configuration.command_surface_path = shared_path
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.feedback_var = FakeVariable()

        with (
            patch("context_palette.configuration_window.move_command_group") as move,
            patch("context_palette.configuration_window.messagebox.askokcancel") as confirm,
        ):
            configuration._move_button(1)

        move.assert_not_called()
        confirm.assert_not_called()
        self.assertIn("fixed first menu", configuration.feedback_var.value)

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

    def test_automatic_folder_menu_is_rendered_with_editable_action_leaf(self) -> None:
        folder = Action(
            "folder",
            "Reports folder",
            "General",
            "open_folder",
            ".",
            quick_action_path=("Work", "Reports"),
        )
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [folder]
        configuration.local_action_ids = {folder.id}
        configuration.button_tree = FakeActionTree()
        configuration.action_bound_button_records = {}

        matches = configuration._render_action_bound_button_groups(
            action_bound_quick_groups(configuration.actions),
            "folders",
        )

        rendered_labels = {
            options["text"]
            for _parent, options in configuration.button_tree.rows.values()
        }
        self.assertEqual(matches, 3)
        self.assertEqual(
            rendered_labels,
            {"Folders", "Work", "Reports", folder.compact_display_text},
        )
        action_records = [
            record
            for record in configuration.action_bound_button_records.values()
            if record.action_id
        ]
        self.assertEqual(
            action_records,
            [
                ActionBoundQuickSelection(
                    "Folders",
                    "open_folder",
                    ("Work", "Reports"),
                    "folder",
                )
            ],
        )

    def test_automatic_action_without_path_is_rendered_at_menu_root(self) -> None:
        folder = Action(
            "folder",
            "Project folder",
            "General",
            "open_folder",
            ".",
        )
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [folder]
        configuration.local_action_ids = {folder.id}
        configuration.button_tree = FakeActionTree()
        configuration.action_bound_button_records = {}

        matches = configuration._render_action_bound_button_groups(
            action_bound_quick_groups(configuration.actions),
            "folders",
        )

        folder_group_iid = "automatic-group-open_folder"
        root_action_rows = [
            (parent, options)
            for parent, options in configuration.button_tree.rows.values()
            if options["text"] == folder.compact_display_text
        ]
        self.assertEqual(matches, 1)
        self.assertEqual(len(root_action_rows), 1)
        self.assertEqual(root_action_rows[0][0], folder_group_iid)
        self.assertIn("menu root", root_action_rows[0][1]["values"][1])
        self.assertNotIn(
            "Unsorted",
            {
                options["text"]
                for _parent, options in configuration.button_tree.rows.values()
            },
        )

    def test_editing_automatic_folder_leaf_opens_its_action_editor(self) -> None:
        folder = Action("folder", "Reports", "General", "open_folder", ".")
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [folder]
        configuration.button_tree = FakeSelectedActionTree("automatic-folder")
        configuration.action_bound_button_records = {
            "automatic-folder": ActionBoundQuickSelection(
                "Folders",
                "open_folder",
                ("Work",),
                folder.id,
            )
        }
        configuration._edit_action_record = Mock()

        configuration._edit_button()

        configuration._edit_action_record.assert_called_once_with(folder)

    def test_editing_automatic_folder_group_opens_filtered_actions(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = []
        configuration.button_tree = FakeSelectedActionTree("automatic-folders")
        configuration.action_bound_button_records = {
            "automatic-folders": ActionBoundQuickSelection(
                "Folders",
                "open_folder",
            )
        }
        configuration.notebook = FakeNotebook(selected=4)
        configuration.action_filter_var = FakeVariable()
        configuration.action_state_filter_var = FakeVariable("Archived")
        configuration.action_filter_entry = FakeEntry()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()

        configuration._edit_button()

        self.assertEqual(configuration.notebook.selected, 1)
        self.assertEqual(configuration.action_state_filter_var.value, "Active")
        self.assertEqual(configuration.action_filter_var.value, "Open a folder")
        self.assertEqual(configuration.action_filter_entry.focus_calls, 1)
        self.assertIsNotNone(configuration.action_filter_entry.selection)
        self.assertIn("Folders action", configuration.feedback_var.value)

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

    def test_add_menu_level_under_selected_parent_passes_full_parent_path(self) -> None:
        local_path = Path("local-commands.json")
        group = CommandGroup(
            "nested",
            "Nested",
            (
                CommandItem(
                    "level-1",
                    "Level 1",
                    items=(CommandItem("level-2", "Level 2"),),
                ),
            ),
            source_path=local_path,
            presentation=GROUP_PRESENTATION_NESTED_MENU,
        )
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [group]
        configuration.button_tree = FakeSelectedActionTree("button-0-0.0")
        configuration.command_surface_path = Path("shared-commands.json")
        configuration.local_command_surface_path = local_path
        configuration.actions = []
        configuration.local_action_ids = set()
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()
        configuration.feedback_var = FakeVariable()
        configuration.feedback_label = Mock()
        child = CommandItem("level-3", "Level 3")

        with (
            patch("context_palette.configuration_window.ButtonDialog") as dialog,
            patch(
                "context_palette.configuration_window.save_command_item"
            ) as save,
        ):
            configuration._add_button()
            callback = dialog.call_args.args[4]
            self.assertTrue(
                callback(
                    "nested",
                    "Nested",
                    child,
                    "nested",
                    "",
                )
            )

        save.assert_called_once_with(
            local_path,
            group_id="nested",
            group_label="Nested",
            item=child,
            original_group_id="nested",
            original_item_id="",
            parent_item_ids=("level-1", "level-2"),
        )

    def test_add_menu_level_rejects_a_fourth_level(self) -> None:
        group = CommandGroup(
            "nested",
            "Nested",
            (
                CommandItem(
                    "one",
                    "One",
                    items=(
                        CommandItem(
                            "two",
                            "Two",
                            items=(CommandItem("three", "Three"),),
                        ),
                    ),
                ),
            ),
            presentation=GROUP_PRESENTATION_NESTED_MENU,
        )
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.groups = [group]
        configuration.button_tree = FakeSelectedActionTree(
            "button-0-0.0.0"
        )
        configuration.window = FakeWindow()

        with (
            patch(
                "context_palette.configuration_window.messagebox.showinfo"
            ) as info,
            patch(
                "context_palette.configuration_window.ButtonDialog"
            ) as dialog,
        ):
            configuration._add_button()

        self.assertIn("3 levels", info.call_args.args[1])
        dialog.assert_not_called()

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
        self.assertEqual(error.call_args.args[0], "Quick-action item was not saved")
        self.assertIn("left unchanged", error.call_args.args[1])

    def test_cancelling_shared_action_deletion_preserves_action(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        configuration.actions = [
            Action(
                "shared",
                "Shared",
                "General",
                "copy_text",
                "one",
                state="Archived",
            )
        ]
        configuration.stored_actions = list(configuration.actions)
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

    def test_failed_action_deletion_reloads_transaction_result(self) -> None:
        configuration = ConfigurationWindow.__new__(ConfigurationWindow)
        action = Action(
            "local",
            "Local archived Action",
            "General",
            "copy_text",
            "one",
            state="Archived",
        )
        configuration.actions = [action]
        configuration.stored_actions = [action]
        configuration.local_action_ids = {action.id}
        configuration.action_tree = FakeSelectedActionTree("action-0")
        configuration.contexts_path = Path("contexts.json")
        configuration.local_contexts_path = Path("local-contexts.json")
        configuration.command_surface_path = Path("commands.json")
        configuration.local_command_surface_path = Path("local-commands.json")
        configuration.palette_path = Path("palette.json")
        configuration.shared_actions_path = Path("actions.json")
        configuration.local_actions_path = Path("local-actions.json")
        configuration.window = FakeWindow()
        configuration.on_change = Mock()
        configuration._reload = Mock()

        with (
            patch(
                "context_palette.configuration_window.dependent_sequences",
                return_value=(),
            ),
            patch(
                "context_palette.configuration_window.inspect_action_references",
                return_value=ActionDeletionReport(1, 0, 0),
            ),
            patch(
                "context_palette.configuration_window.messagebox.askyesno",
                return_value=True,
            ),
            patch(
                "context_palette.configuration_window.delete_action_and_references",
                side_effect=ActionDeletionError("The Action file is locked."),
            ),
            patch(
                "context_palette.configuration_window.messagebox.showerror"
            ) as error,
        ):
            configuration._delete_action()

        configuration.on_change.assert_called_once_with()
        configuration._reload.assert_called_once_with()
        self.assertEqual(error.call_args.args[0], "Action was not deleted")
        self.assertIn("reloaded the current state", error.call_args.args[1])
        self.assertNotIn("fewer", error.call_args.args[1])
        self.assertEqual(configuration.stored_actions, [action])

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

    def test_focus_entry_cancels_pending_focus_when_window_is_destroyed(self) -> None:
        window = FakeFocusWindow()
        entry = FakeEntry()

        _focus_entry(window, entry)
        self.assertEqual(len(window.bindings), 1)

        window.bindings[0](Mock(widget=window))

        self.assertEqual(window.cancelled, ["after#focus"])
        self.assertEqual(entry.focus_calls, 0)

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
            configuration.contexts_path = root / "contexts.json"
            configuration.contexts_path.write_text(
                '{"contexts": []}\n',
                encoding="utf-8",
            )
            configuration.local_contexts_path = root / "local_contexts.json"
            configuration.actions = []
            configuration.local_action_ids = set()
            configuration.window = FakeWindow()
            configuration.action_filter_var = FakeVariable()
            configuration.feedback_var = FakeVariable()
            configuration.feedback_label = Mock()
            configuration.on_change = Mock()
            configuration._reload = Mock()
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
            configuration._reload.assert_called_once_with()

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
            dialog.tag_field.picker.invoke()
            root.update()
            sql_index = dialog.tag_field.tag_picker.visible_values.index("sql")
            dialog.tag_field.tag_picker.listbox.selection_set(sql_index)
            dialog.tag_field.tag_picker._selection_changed()
            dialog.tag_field.tag_picker.apply()
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

    def test_action_dialog_shows_reviewed_workspace_prefill(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = ActionDialog(
                root,
                "open_url",
                [],
                lambda _action: True,
                context_names=["General"],
                initial_title="Open example.com",
                initial_value="https://example.com/report",
                suggested_from_workspace=True,
            )
            root.update_idletasks()

            self.assertEqual(dialog.title_var.get(), "Open example.com")
            assert dialog.value is not None
            self.assertEqual(
                dialog.value.get("1.0", "end-1c"),
                "https://example.com/report",
            )
            self.assertIsNotNone(dialog.suggestion_notice)
            assert dialog.suggestion_notice is not None
            self.assertIn("review", dialog.suggestion_notice.cget("text"))
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_application_action_dialog_accepts_one_argument_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            application = Path(directory) / "control.exe"
            application.write_bytes(b"test")
            root = tk.Tk()
            root.withdraw()
            saved: list[Action] = []
            try:
                dialog = ActionDialog(
                    root,
                    "launch_app",
                    [],
                    lambda action: saved.append(action) or True,
                    context_names=["General"],
                )
                root.update_idletasks()
                self.assertIsInstance(dialog.arguments_text, tk.Text)
                dialog.title_var.set("Open Credential Manager")
                dialog.value.insert("1.0", str(application))
                dialog.arguments_text.insert(
                    "1.0",
                    "/name\nMicrosoft.CredentialManager",
                )

                dialog._save()

                self.assertEqual(len(saved), 1)
                self.assertEqual(
                    saved[0].arguments,
                    ("/name", "Microsoft.CredentialManager"),
                )
            finally:
                for child in root.winfo_children():
                    child.destroy()
                root.destroy()

    def test_action_bound_dialog_saves_nested_quick_menu_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            saved: list[Action] = []
            try:
                dialog = ActionDialog(
                    root,
                    "open_folder",
                    [],
                    lambda action: saved.append(action) or True,
                    context_names=["General"],
                )
                root.update_idletasks()
                dialog.title_var.set("Open reports")
                dialog.value.insert("1.0", directory)
                dialog.quick_action_path_var.set("Work > Reports > Monthly")

                dialog._save()

                self.assertEqual(len(saved), 1)
                self.assertEqual(
                    saved[0].quick_action_path,
                    ("Work", "Reports", "Monthly"),
                )
            finally:
                for child in root.winfo_children():
                    child.destroy()
                root.destroy()

    def test_action_dialog_uses_compact_inline_fields_and_tooltip_guidance(self) -> None:
        root = tk.Tk()
        root.geometry("780x600+0+0")
        try:
            dialog = ActionDialog(
                root,
                "copy_text",
                [],
                lambda _action: True,
                context_names=["General", "Mail"],
                choose_destination=True,
            )
            root.update()

            self.assertLessEqual(dialog.window.winfo_width(), 700)
            self.assertLessEqual(dialog.window.winfo_height(), 520)
            self.assertEqual(dialog.context_field.label.pack_info()["side"], "left")
            self.assertEqual(dialog.tag_field.label.pack_info()["side"], "left")
            tooltip_widgets = {tooltip.widget for tooltip in dialog.tooltips}
            self.assertIn(dialog.destination_field, tooltip_widgets)
            self.assertIn(dialog.context_field.entry, tooltip_widgets)
            self.assertIn(dialog.tag_field.entry, tooltip_widgets)
            self.assertIn(dialog.value, tooltip_widgets)
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_automatic_menu_creation_uses_full_action_form_and_prefills_branch(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = ActionDialog(
                root,
                "open_folder",
                [],
                lambda _action: True,
                context_names=["General", "Work"],
                choose_destination=True,
                initial_contexts=("Work",),
                initial_quick_action_path=("Projects", "Reports"),
            )
            root.update_idletasks()

            self.assertEqual(dialog.contexts_var.get(), "Work")
            self.assertEqual(dialog.tags_var.get(), "")
            self.assertEqual(
                dialog.quick_action_path_var.get(),
                "Projects > Reports",
            )
            self.assertTrue(dialog.context_field.entry.winfo_exists())
            self.assertTrue(dialog.tag_field.entry.winfo_exists())
            self.assertEqual(dialog.destination_var.get(), LOCAL_DESTINATION)
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_transform_action_dialog_uses_readable_operation_and_parameters(self) -> None:
        root = tk.Tk()
        root.withdraw()
        saved: list[Action] = []
        try:
            dialog = ActionDialog(
                root,
                "transform_text",
                [],
                lambda action: saved.append(action) or True,
                context_names=["General"],
            )
            root.update_idletasks()
            replace_label = next(
                label
                for label, operation in dialog.transform_operation_choices.items()
                if operation == "literal_replace"
            )
            dialog.title_var.set("Remove confidential marker")
            dialog.transform_operation_var.set(replace_label)
            dialog._render_transform_parameters()
            dialog.transform_parameter_vars[0].set("CONFIDENTIAL")
            dialog.transform_parameter_vars[1].set("")

            dialog._save()

            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].value, "literal_replace")
            self.assertEqual(saved[0].arguments, ("CONFIDENTIAL", ""))
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_file_transform_dialog_saves_source_operation_and_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("Alpha", encoding="utf-8")
            root = tk.Tk()
            root.withdraw()
            saved: list[Action] = []
            try:
                dialog = ActionDialog(
                    root,
                    "transform_file_text",
                    [],
                    lambda action: saved.append(action) or True,
                    context_names=["General"],
                    default_text_file_path=source,
                )
                root.update_idletasks()
                uppercase_label = next(
                    label
                    for label, operation in dialog.transform_operation_choices.items()
                    if operation == "uppercase"
                )
                dialog.title_var.set("Uppercase recurring export")
                dialog.transform_operation_var.set(uppercase_label)
                dialog._render_transform_parameters()

                dialog._save()

                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0].value, str(source))
                self.assertEqual(saved[0].arguments, ("uppercase",))
            finally:
                for child in root.winfo_children():
                    child.destroy()
                root.destroy()

    def test_action_dialog_scrolls_fields_and_keeps_footer_visible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.txt"
            source.write_text("Alpha", encoding="utf-8")
            root = tk.Tk()
            root.geometry("1x1+0+0")
            try:
                dialog = ActionDialog(
                    root,
                    "transform_file_text",
                    [],
                    lambda _action: True,
                    context_names=["General", "Mail"],
                    choose_destination=True,
                    default_text_file_path=source,
                )
                dialog.window.minsize(1, 1)
                dialog.window.geometry("700x300")
                root.update()
                dialog.form_canvas.yview_moveto(0.0)
                root.update_idletasks()

                self.assertEqual(dialog.form_scrollbar.winfo_manager(), "pack")
                self.assertTrue(dialog.window.bind("<FocusIn>"))
                self.assertTrue(dialog.window.bind("<MouseWheel>"))
                self.assertLess(
                    dialog.form_canvas.yview()[1],
                    1.0,
                    "The constrained form should have scrollable content.",
                )
                self.assertLessEqual(
                    dialog.controls_frame.winfo_y()
                    + dialog.controls_frame.winfo_height(),
                    dialog.controls_frame.master.winfo_height(),
                )

                dialog._scroll_form(
                    Mock(widget=dialog.form_canvas, delta=-120)
                )
                root.update()
                self.assertGreater(dialog.form_canvas.yview()[0], 0.0)

                parameter_entries = [
                    child
                    for row in dialog.transform_parameters_frame.winfo_children()
                    for child in row.winfo_children()
                    if isinstance(child, ttk.Entry)
                ]
                self.assertTrue(parameter_entries)
                parameter_entries[-1].focus_set()
                dialog._show_form_widget(parameter_entries[-1])
                root.update()
                self.assertLessEqual(
                    parameter_entries[-1].winfo_rooty()
                    + parameter_entries[-1].winfo_height(),
                    dialog.form_canvas.winfo_rooty()
                    + dialog.form_canvas.winfo_height(),
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
            self.assertIsInstance(dialog.member_choice, ActionPickerField)
            self.assertIsNone(dialog.member_choice.scope_note)
            self.assertTrue(
                all(
                    isinstance(picker, ActionPickerField)
                    for picker in dialog.slot_choices
                )
            )
            self.assertEqual(len(dialog.slot_choices), 5)
            dialog._save()

            self.assertEqual(saved[0].action_ids, ("built-in", "local"))
            self.assertEqual(saved[0].preferred_action_ids, ("built-in",))
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_personal_context_dialog_adds_work_item_and_prefers_it_in_slot(self) -> None:
        root = tk.Tk()
        root.withdraw()
        saved: list[ContextDefinition] = []
        work_item = DiscoveredWorkItem(
            "product-work",
            "Product work",
            "ISS-ABC-example",
            ROOT / "ISS-ABC-example",
            "ISS-ABC-example",
            "ISS",
            "Issue",
            "ABC",
            "example",
            (),
            ROOT / "ISS-ABC-example" / "ISS-ABC-example.xlsx",
        )
        try:
            dialog = ContextDialog(
                root,
                ContextDefinition("Product", action_ids=("open-docs",)),
                [Action("open-docs", "Open docs", "General", "copy_text", "x")],
                lambda context, _original: saved.append(context) or True,
                work_items=(work_item,),
            )
            work_item_label = next(iter(dialog.work_item_choices))
            dialog.member_work_item_var.set(work_item_label)
            dialog._add_member_work_item()
            dialog.slots[0].set(work_item_label)

            dialog._save()

            reference = WorkItemReference("product-work", "ISS-ABC-example")
            self.assertEqual(saved[0].work_item_refs, (reference,))
            self.assertEqual(
                saved[0].preferred_items,
                (CommandTarget(work_item_ref=reference),),
            )
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_builtin_context_picker_explains_its_action_scope(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = ContextDialog(
                root,
                ContextDefinition("Standard"),
                [Action("built-in", "Built in", "General", "copy_text", "one")],
                lambda _context, _original: True,
                shared=True,
            )
            root.update_idletasks()

            self.assertIn("Built-in actions only", dialog.member_choice.scope_note)
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
        dialog.direct_action_ids = ["direct"]
        dialog.destination_var = FakeVariable(PROJECT_DESTINATION)
        dialog.window = FakeWindow()
        captured: list[tuple[CommandGroup, str, str]] = []
        dialog.on_save = lambda *args: captured.append(args) or True

        dialog._save()

        self.assertEqual(captured[0][0].id, "project-tools")
        self.assertEqual(captured[0][0].label, "Project tools")
        self.assertEqual(
            captured[0][0].presentation,
            GROUP_PRESENTATION_NESTED_MENU,
        )
        self.assertEqual(captured[0][0].action_ids, ("direct",))
        self.assertEqual(captured[0][0].primary_action_id, "")
        self.assertEqual(captured[0][2], PROJECT_DESTINATION)
        self.assertEqual(dialog.window.destroy_calls, 1)

    def test_editing_legacy_row_menu_without_root_actions_preserves_presentation(self) -> None:
        dialog = GroupDialog.__new__(GroupDialog)
        dialog.group = CommandGroup("legacy", "Legacy")
        dialog.original_group_id = "legacy"
        dialog.label_var = FakeVariable("Renamed legacy")
        dialog.id_var = FakeVariable("legacy")
        dialog.direct_action_ids = []
        dialog.destination_var = FakeVariable(LOCAL_DESTINATION)
        dialog.window = FakeWindow()
        captured: list[tuple[CommandGroup, str, str]] = []
        dialog.on_save = lambda *args: captured.append(args) or True

        dialog._save()

        self.assertEqual(captured[0][0].presentation, "rows")
        self.assertEqual(captured[0][0].primary_action_id, "")

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
                "Edit built-in Quick-action item",
            )
            button_dialog.window.destroy()
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def _assert_scrollable_dialog_target_visible(
        self,
        root: tk.Tk,
        dialog: object,
        target: tk.Misc,
        *,
        expect_overflow: bool = False,
    ) -> None:
        root.update()
        view = dialog.form_view
        self.assertTrue(view.scrollbar.winfo_ismapped())
        overflow = view.canvas.yview()[1] < 1.0
        if expect_overflow:
            self.assertTrue(overflow)
        self.assertLessEqual(
            view.canvas.winfo_rooty() + view.canvas.winfo_height(),
            dialog.controls_frame.winfo_rooty(),
        )
        self.assertLessEqual(
            dialog.controls_frame.winfo_rooty()
            + dialog.controls_frame.winfo_height(),
            dialog.window.winfo_rooty() + dialog.window.winfo_height(),
        )
        if not overflow:
            self.assertGreaterEqual(
                target.winfo_rooty(),
                view.canvas.winfo_rooty() - 1,
            )
            self.assertLessEqual(
                target.winfo_rooty() + target.winfo_height(),
                view.canvas.winfo_rooty() + view.canvas.winfo_height() + 1,
            )
            return

        view.canvas.yview_moveto(0.0)
        root.update()
        with patch.object(
            view,
            "_pointer_is_over_canvas",
            return_value=True,
        ):
            self.assertEqual(
                view._on_mousewheel(Mock(widget=view.canvas, delta=-120)),
                "break",
            )
        root.update()
        self.assertGreater(view.canvas.yview()[0], 0.0)

        view.canvas.yview_moveto(0.0)
        root.update()
        view.ensure_visible(target)
        root.update()
        self.assertGreater(view.canvas.yview()[0], 0.0)
        self.assertGreaterEqual(
            target.winfo_rooty(),
            view.canvas.winfo_rooty() - 1,
        )
        self.assertLessEqual(
            target.winfo_rooty() + target.winfo_height(),
            view.canvas.winfo_rooty() + view.canvas.winfo_height() + 1,
        )

    def test_configuration_dialog_bodies_scroll_at_150_percent(self) -> None:
        root = tk.Tk()
        root.geometry("780x600+0+0")
        original_scaling = float(root.tk.call("tk", "scaling"))
        action = Action("one", "One", "General", "copy_text", "one")
        try:
            root.tk.call("tk", "scaling", 2.0)

            context_dialog = ContextDialog(
                root,
                None,
                [action],
                lambda *_args: True,
                choose_destination=True,
            )
            self.assertEqual(context_dialog.window.title(), "New context")
            self._assert_scrollable_dialog_target_visible(
                root,
                context_dialog,
                context_dialog.slot_choices[-1].entry,
                expect_overflow=True,
            )
            context_dialog.window.destroy()
            root.update()

            group_dialog = GroupDialog(
                root,
                None,
                lambda *_args: True,
                actions=[action],
                choose_destination=True,
            )
            self.assertEqual(
                group_dialog.window.title(),
                "New Quick-action menu",
            )
            self._assert_scrollable_dialog_target_visible(
                root,
                group_dialog,
                group_dialog.direct_move_down_button,
            )
            group_dialog.window.destroy()
            root.update()

            button_dialog = ButtonDialog(
                root,
                CommandGroup("tools", "Tools"),
                None,
                [action],
                lambda *_args: True,
            )
            self.assertEqual(
                button_dialog.window.title(),
                "New Quick action",
            )
            self._assert_scrollable_dialog_target_visible(
                root,
                button_dialog,
                button_dialog.assignment_preview_label,
            )
            button_dialog.window.destroy()
            root.update()
        finally:
            root.tk.call("tk", "scaling", original_scaling)
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
                items=(CommandItem("child", "Child"),),
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
            self.assertIsInstance(dialog.action_choice, ActionPickerField)
            dialog._save()

            self.assertEqual(captured[0].action_ids, ())
            self.assertEqual(captured[0].primary_action_id, "")
            self.assertEqual(
                captured[0].targets,
                tuple(CommandTarget(action_id=action.id) for action in actions),
            )
            self.assertEqual(
                [child.id for child in captured[0].items],
                ["child"],
            )
        finally:
            for child in root.winfo_children():
                child.destroy()
            root.destroy()

    def test_personal_quick_action_dialog_mixes_ordered_action_and_work_item(self) -> None:
        root = tk.Tk()
        root.withdraw()
        captured: list[CommandItem] = []
        work_item = DiscoveredWorkItem(
            "product-work",
            "Product work",
            "ISS-ABC-example",
            ROOT / "ISS-ABC-example",
            "ISS-ABC-example",
            "ISS",
            "Issue",
            "ABC",
            "example",
            (),
            ROOT / "ISS-ABC-example" / "ISS-ABC-example.xlsx",
        )
        action = Action("open-docs", "Open docs", "General", "open_folder", str(ROOT))
        try:
            dialog = ButtonDialog(
                root,
                CommandGroup("work", "Work"),
                None,
                [action],
                lambda _group_id, _group_label, saved, *_args: (
                    captured.append(saved) or True
                ),
                work_items=(work_item,),
            )
            action_label = next(iter(dialog.action_choices))
            dialog.action_choice_var.set(action_label)
            dialog._add_assigned_action()
            selected_label = next(iter(dialog.work_item_choices))
            dialog.work_item_choice_var.set(selected_label)

            dialog._use_work_item()
            dialog._save()

            self.assertEqual(
                captured[0].targets,
                (
                    CommandTarget(action_id="open-docs"),
                    CommandTarget(
                        work_item_ref=WorkItemReference(
                            "product-work",
                            "ISS-ABC-example",
                        )
                    ),
                ),
            )
            self.assertEqual(captured[0].action_ids, ())
            self.assertEqual(captured[0].primary_action_id, "")
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

            self.assertIn("Built-in actions only", dialog.action_choice.scope_note)
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
