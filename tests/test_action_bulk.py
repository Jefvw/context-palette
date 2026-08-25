from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from context_palette.action_bulk import (
    BulkActionError,
    commit_bulk_action_create,
    plan_bulk_action_create,
)
from context_palette.action_workbook import (
    ActionWorkbook,
    ActionWorkbookRow,
    workbook_digest,
)
from context_palette.actions import Action, append_action, load_stored_actions
from context_palette.configuration_data import save_contexts
from context_palette.context_membership import actions_with_canonical_contexts
from context_palette.contexts import ContextDefinition, load_contexts


def workbook_row(
    row_number: int,
    *,
    include: bool = True,
    title: str = "Example",
    action_type: str = "copy_text",
    value: str = "Hello",
    contexts: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    description: str = "",
    quick_action_path: tuple[str, ...] = (),
    arguments: tuple[str, ...] = (),
    working_directory: str = "",
) -> ActionWorkbookRow:
    return ActionWorkbookRow(
        row_number=row_number,
        include=include,
        name=title,
        action_type=action_type,
        value=value,
        contexts=contexts,
        tags=tags,
        description=description,
        quick_menu=quick_action_path,
        arguments=arguments,
        working_folder=working_directory,
    )


def workbook(path: Path, *rows: ActionWorkbookRow) -> ActionWorkbook:
    return ActionWorkbook(path=path, digest=workbook_digest(path), rows=tuple(rows))


class BulkActionPlanningTests(unittest.TestCase):
    def test_maps_ids_labels_and_display_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.xlsx"
            path.write_bytes(b"workbook")
            existing_folder = str(Path(directory))
            plan = plan_bulk_action_create(
                workbook(
                    path,
                    workbook_row(2, action_type="copy_text"),
                    workbook_row(
                        3,
                        title="Folder",
                        action_type="OPEN A FOLDER",
                        value=existing_folder,
                    ),
                    workbook_row(
                        4,
                        title="Website",
                        action_type="↗ Open a website",
                        value="https://example.com",
                    ),
                ),
                (),
                (),
            )

        self.assertEqual([item.status for item in plan.candidates], ["Ready"] * 3)
        self.assertEqual(
            [item.action.type for item in plan.candidates if item.action],
            ["copy_text", "open_folder", "open_url"],
        )
        self.assertTrue(
            all(item.action.state == "Active" for item in plan.candidates if item.action)
        )

    def test_excluded_and_invalid_rows_remain_visible_without_importing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.xlsx"
            path.write_bytes(b"workbook")
            plan = plan_bulk_action_create(
                workbook(
                    path,
                    workbook_row(2, include=False, action_type="not-real"),
                    workbook_row(3, title="", action_type="copy_text"),
                    workbook_row(4, action_type="sequence"),
                    workbook_row(5, action_type="excel_automation"),
                ),
                (),
                (),
            )

        self.assertEqual(
            [item.status for item in plan.candidates],
            ["Not selected", "Error", "Error", "Error"],
        )
        self.assertTrue(all(not item.selected_by_default for item in plan.candidates))
        self.assertIsNone(plan.candidates[0].action)
        self.assertIn("cannot be created in bulk", plan.candidates[2].messages[0])

    def test_only_canonical_personal_contexts_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.xlsx"
            path.write_bytes(b"workbook")
            plan = plan_bulk_action_create(
                workbook(
                    path,
                    workbook_row(2, contexts=("personal",)),
                    workbook_row(3, title="Built-in", contexts=("Shared",)),
                    workbook_row(4, title="General", contexts=("General",)),
                ),
                (),
                ("Personal",),
            )

        self.assertEqual(plan.candidates[0].action.effective_contexts, ("Personal",))
        self.assertEqual(plan.candidates[1].status, "Error")
        self.assertIn("Unknown specific context", plan.candidates[1].messages[0])
        self.assertEqual(plan.candidates[2].action.effective_contexts, ())

    def test_existing_and_batch_duplicates_are_conservative(self) -> None:
        existing_exact = Action(
            "old-one",
            "Exact",
            "General",
            "copy_text",
            "same",
            tags=("tag",),
        )
        existing_effect = Action(
            "old-two",
            "Different name",
            "General",
            "open_url",
            "https://example.com",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.xlsx"
            path.write_bytes(b"workbook")
            plan = plan_bulk_action_create(
                workbook(
                    path,
                    workbook_row(2, title="Exact", value="same", tags=("tag",)),
                    workbook_row(
                        3,
                        title="New URL",
                        action_type="open_url",
                        value="https://example.com",
                    ),
                    workbook_row(4, title="First batch", value="batch"),
                    workbook_row(5, title="First batch", value="batch"),
                    workbook_row(6, title="Second name", value="batch"),
                ),
                (existing_exact, existing_effect),
                (),
            )

        self.assertEqual(
            [item.status for item in plan.candidates],
            ["Already exists", "Possible duplicate", "Ready", "Warning", "Warning"],
        )
        self.assertEqual(
            [item.selected_by_default for item in plan.candidates],
            [False, False, True, False, False],
        )


class BulkActionCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "actions.xlsx"
        self.source.write_bytes(b"reviewed workbook")
        self.shared_actions = self.root / "actions.json"
        self.local_actions = self.root / "local_actions.json"
        self.shared_contexts = self.root / "contexts.json"
        self.local_contexts = self.root / "local_contexts.json"
        self.shared_actions.write_text('{"actions": []}\n', encoding="utf-8")
        save_contexts(self.shared_contexts, [])
        save_contexts(
            self.local_contexts,
            [ContextDefinition("Personal", action_ids=())],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _plan(self, *rows: ActionWorkbookRow, existing: tuple[Action, ...] = ()):
        return plan_bulk_action_create(
            workbook(self.source, *rows),
            existing,
            ("Personal",),
        )

    def test_commits_selected_rows_once_and_persists_memberships(self) -> None:
        plan = self._plan(
            workbook_row(2, title="One", value="one", contexts=("Personal",)),
            workbook_row(3, title="Two", value="two"),
        )

        created = commit_bulk_action_create(
            plan,
            (2, 3),
            self.local_actions,
            self.shared_actions,
            self.shared_contexts,
            self.local_contexts,
        )

        self.assertEqual([item.title for item in created], ["One", "Two"])
        stored = load_stored_actions(self.local_actions, inspect_external_paths=False)
        self.assertEqual([item.title for item in stored], ["One", "Two"])
        projected = actions_with_canonical_contexts(
            stored,
            load_contexts(self.local_contexts),
        )
        self.assertEqual(projected[0].effective_contexts, ("Personal",))
        self.assertEqual(projected[1].effective_contexts, ())

    def test_calls_the_atomic_append_boundary_once(self) -> None:
        plan = self._plan(
            workbook_row(2, title="One", value="one"),
            workbook_row(3, title="Two", value="two"),
        )
        with patch(
            "context_palette.action_bulk.append_actions_with_context_memberships"
        ) as append:
            created = commit_bulk_action_create(
                plan,
                (2, 3),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

        self.assertEqual(len(created), 2)
        append.assert_called_once()
        self.assertEqual([item.title for item in append.call_args.args[1]], ["One", "Two"])
        self.assertTrue(append.call_args.kwargs["actions_are_local"])
        self.assertFalse(append.call_args.kwargs["create_missing_local_contexts"])

    def test_changed_workbook_blocks_before_write(self) -> None:
        plan = self._plan(workbook_row(2))
        self.source.write_bytes(b"changed")

        with patch(
            "context_palette.action_bulk.append_actions_with_context_memberships"
        ) as append, self.assertRaisesRegex(BulkActionError, "workbook changed"):
            commit_bulk_action_create(
                plan,
                (2,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )
        append.assert_not_called()

    def test_changed_action_collection_blocks_before_write(self) -> None:
        plan = self._plan(workbook_row(2))
        append_action(
            self.shared_actions,
            Action("other", "Other", "General", "copy_text", "other"),
        )

        with self.assertRaisesRegex(BulkActionError, "saved Actions changed"):
            commit_bulk_action_create(
                plan,
                (2,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

    def test_action_that_now_exists_gets_specific_stale_error(self) -> None:
        plan = self._plan(workbook_row(2, title="Same", value="same"))
        append_action(
            self.shared_actions,
            Action("same", "Same", "General", "copy_text", "same"),
        )

        with self.assertRaisesRegex(BulkActionError, "now already exist"):
            commit_bulk_action_create(
                plan,
                (2,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

    def test_invalid_selection_and_duplicate_selected_rows_are_rejected(self) -> None:
        plan = self._plan(
            workbook_row(2, title="Same", value="same"),
            workbook_row(3, title="Same", value="same"),
            workbook_row(4, include=False),
        )
        with self.assertRaisesRegex(BulkActionError, "identical Action"):
            commit_bulk_action_create(
                plan,
                (2, 3),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )
        with self.assertRaisesRegex(BulkActionError, "cannot be created"):
            commit_bulk_action_create(
                plan,
                (4,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )
        with self.assertRaisesRegex(BulkActionError, "not part"):
            commit_bulk_action_create(
                plan,
                (99,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

    def test_possible_existing_effect_can_be_explicitly_selected(self) -> None:
        existing = Action(
            "existing",
            "Existing",
            "General",
            "copy_text",
            "same effect",
        )
        append_action(self.shared_actions, existing)
        plan = self._plan(
            workbook_row(2, title="Intentional alias", value="same effect"),
            existing=(existing,),
        )
        self.assertEqual(plan.candidates[0].status, "Possible duplicate")

        created = commit_bulk_action_create(
            plan,
            (2,),
            self.local_actions,
            self.shared_actions,
            self.shared_contexts,
            self.local_contexts,
        )

        self.assertEqual(created[0].title, "Intentional alias")


if __name__ == "__main__":
    unittest.main()
