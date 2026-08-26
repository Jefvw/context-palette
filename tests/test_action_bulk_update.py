from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from context_palette.action_bulk_update import (
    BulkActionUpdateError,
    commit_bulk_action_update,
    eligible_personal_actions_for_update,
    plan_bulk_action_update,
)
from context_palette.action_sequences import SequenceStep
from context_palette.action_update_workbook import (
    ActionUpdateWorkbook,
    ActionUpdateWorkbookRow,
    action_record_fingerprint,
    read_action_update_workbook,
    write_action_update_workbook,
)
from context_palette.actions import (
    Action,
    append_action,
    load_combined_stored_actions,
    load_stored_actions,
    open_action_target,
    update_action,
)
from context_palette.configuration_data import save_contexts
from context_palette.context_membership import (
    ContextMembershipUpdateError,
    actions_with_canonical_contexts,
)
from context_palette.contexts import ContextDefinition, ContextError, load_contexts


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _action(
    action_id: str,
    *,
    title: str = "Example",
    action_type: str = "copy_text",
    value: str = "Text",
    state: str = "Active",
    contexts: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    description: str = "",
    quick_action_path: tuple[str, ...] = (),
    arguments: tuple[str, ...] = (),
    working_directory: str | None = None,
    sequence_steps: tuple[SequenceStep, ...] = (),
) -> Action:
    return Action(
        action_id,
        title,
        contexts[0] if contexts else "General",
        action_type,
        value,
        state=state,
        contexts=contexts,
        tags=tags,
        description=description,
        quick_action_path=quick_action_path,
        arguments=arguments,
        working_directory=working_directory,
        sequence_steps=sequence_steps,
    )


def _row(
    row_number: int,
    original: Action,
    **changes: object,
) -> ActionUpdateWorkbookRow:
    values: dict[str, object] = {
        "row_number": row_number,
        "action_id": original.id,
        "state": original.state,
        "action_type": original.type,
        "original_fingerprint": action_record_fingerprint(original),
        "name": original.title,
        "value": original.value,
        "contexts": original.effective_contexts,
        "tags": original.effective_tags,
        "description": original.description,
        "quick_menu": original.quick_action_path,
        "arguments": original.arguments,
        "working_folder": original.working_directory or "",
    }
    values.update(changes)
    return ActionUpdateWorkbookRow(**values)  # type: ignore[arg-type]


def _workbook(path: Path, *rows: ActionUpdateWorkbookRow) -> ActionUpdateWorkbook:
    payload = path.read_bytes()
    return ActionUpdateWorkbook(
        path.resolve(),
        sha256(payload).hexdigest(),
        "sha256:" + "0" * 64,
        tuple(rows),
    )


def _replace_zip_part(path: Path, name: str, payload: bytes) -> None:
    with zipfile.ZipFile(path) as source:
        parts = {item.filename: source.read(item.filename) for item in source.infolist()}
    parts[name] = payload
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for part_name, part_payload in parts.items():
            target.writestr(part_name, part_payload)


def _change_cell(path: Path, reference: str, value: str) -> None:
    part = "xl/worksheets/sheet2.xml"
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(part))
    cell = next(
        node
        for node in root.iter()
        if node.tag.endswith("}c") and node.attrib.get("r") == reference
    )
    text = next(node for node in cell.iter() if node.tag.endswith("}t"))
    text.text = value
    _replace_zip_part(
        path,
        part,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


class BulkActionUpdatePlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "updates.xlsx"
        self.path.write_bytes(b"reviewed")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_eligibility_is_personal_active_and_supported_only(self) -> None:
        personal = _action("personal")
        shared = _action("shared")
        archived = _action("archived", state="Archived")
        sequence = _action(
            "sequence",
            action_type="sequence",
            value="sequence-v1",
            sequence_steps=(
                SequenceStep("action", action_id="personal"),
                SequenceStep("action", action_id="personal"),
            ),
        )
        excel = _action(
            "excel",
            action_type="excel_automation",
            value="excel.export_workbooks_to_csv",
        )

        eligible = eligible_personal_actions_for_update(
            (shared, archived, sequence, excel, personal),
            ("personal", "archived", "sequence", "excel"),
        )

        self.assertEqual(eligible, (personal,))

    def test_plans_exact_changed_fields_and_no_changes(self) -> None:
        original = _action(
            "one",
            title="Before",
            value="old",
            contexts=("Personal",),
            tags=("old",),
            description="Old description",
        )
        plan = plan_bulk_action_update(
            _workbook(
                self.path,
                _row(2, original),
                _row(
                    3,
                    replace(original, id="two"),
                    name="After",
                    value="new",
                    contexts=(),
                    tags=("new",),
                    description="New description",
                ),
            ),
            (original, replace(original, id="two")),
            ("one", "two"),
            ("Personal",),
        )

        unchanged, changed = plan.candidates
        self.assertEqual(unchanged.status, "No changes")
        self.assertFalse(unchanged.selected_by_default)
        self.assertEqual(changed.status, "Ready")
        self.assertTrue(changed.selected_by_default)
        self.assertEqual(
            changed.changed_fields,
            ("Name", "Value", "Contexts", "Tags", "Description"),
        )
        self.assertEqual(changed.action.id, "two")
        self.assertEqual(changed.action.type, original.type)
        self.assertEqual(changed.action.state, original.state)

    def test_planning_preserves_lossless_json_arguments(self) -> None:
        exact_arguments = ("", "  padded  ", "line\nvalue", "\t")
        original = _action(
            "command",
            title="  Command  ",
            action_type="launch_app",
            value=r"  C:\Tools\command.exe  ",
            arguments=exact_arguments,
            working_directory=r"  C:\Work folder  ",
            description="  Keep this description spacing.  ",
        )

        plan = plan_bulk_action_update(
            _workbook(self.path, _row(2, original)),
            (original,),
            (original.id,),
            (),
        )

        self.assertEqual(plan.candidates[0].status, "No changes")
        self.assertEqual(plan.candidates[0].action, original)

    def test_planning_reviews_the_canonical_executable_url(self) -> None:
        original = _action(
            "url",
            action_type="open_url",
            value="https://example.com/before",
        )
        plan = plan_bulk_action_update(
            _workbook(
                self.path,
                _row(
                    2,
                    original,
                    value="\u2003https://example.com/after\u2003",
                ),
            ),
            (original,),
            (original.id,),
            (),
        )

        candidate = plan.candidates[0]
        self.assertEqual(candidate.status, "Ready")
        self.assertEqual(candidate.changed_fields, ("Value",))
        self.assertEqual(candidate.action.value, "https://example.com/after")

    def test_validation_errors_remain_visible_and_unselected(self) -> None:
        originals = tuple(
            _action(action_id) for action_id in ("args", "folder", "context", "quick")
        )
        plan = plan_bulk_action_update(
            _workbook(
                self.path,
                _row(2, originals[0], arguments=("--hidden",)),
                _row(3, originals[1], working_folder=r"C:\Hidden"),
                _row(4, originals[2], contexts=("Missing",)),
                _row(5, originals[3], quick_menu=("Not allowed",)),
            ),
            originals,
            (action.id for action in originals),
            ("Personal",),
        )

        self.assertEqual([item.status for item in plan.candidates], ["Error"] * 4)
        self.assertTrue(all(not item.selected_by_default for item in plan.candidates))
        self.assertIn("Arguments are not supported", plan.candidates[0].messages[0])
        self.assertIn("Working folder is supported", plan.candidates[1].messages[0])
        self.assertIn("Unknown specific context", plan.candidates[2].messages[0])
        self.assertIn("Quick menu paths", plan.candidates[3].messages[0])

    def test_shared_archived_changed_identity_and_duplicate_rows_are_errors(self) -> None:
        personal = _action("personal")
        shared = _action("shared")
        archived = _action("archived", state="Archived")
        plan = plan_bulk_action_update(
            _workbook(
                self.path,
                _row(2, shared, name="Changed"),
                _row(3, archived, name="Changed"),
                _row(4, personal, state="Archived"),
                _row(5, personal, name="First"),
                _row(6, personal, name="Second"),
            ),
            (shared, archived, personal),
            ("archived", "personal"),
            (),
        )

        self.assertEqual([item.status for item in plan.candidates], ["Error"] * 5)
        self.assertIn("eligible personal Active", plan.candidates[0].messages[0])
        self.assertIn("eligible personal Active", plan.candidates[1].messages[0])
        self.assertIn("State is not editable", plan.candidates[2].messages[0])
        self.assertIn("also appears", plan.candidates[4].messages[0])


class BulkActionUpdateCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "updates.xlsx"
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

    def _current(self) -> tuple[tuple[Action, ...], set[str]]:
        actions, local_ids = load_combined_stored_actions(
            self.shared_actions,
            self.local_actions,
            inspect_external_paths=False,
        )
        definitions = [
            *load_contexts(self.shared_contexts),
            *load_contexts(self.local_contexts),
        ]
        return tuple(actions_with_canonical_contexts(actions, definitions)), local_ids

    def _review(self, changes: dict[str, str]) -> object:
        current, local_ids = self._current()
        eligible = eligible_personal_actions_for_update(current, local_ids)
        write_action_update_workbook(self.source, eligible)
        rows_by_id = {
            action.id: row_number
            for row_number, action in enumerate(
                sorted(eligible, key=lambda item: (item.title.casefold(), item.id.casefold(), item.id)),
                2,
            )
        }
        for action_id, value in changes.items():
            _change_cell(self.source, f"E{rows_by_id[action_id]}", value)
        workbook = read_action_update_workbook(self.source, eligible)
        return plan_bulk_action_update(
            workbook,
            current,
            local_ids,
            ("Personal",),
        )

    def test_commits_selected_rows_once_preserves_order_and_unselected_action(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        append_action(self.local_actions, _action("two", title="Beta"))
        plan = self._review({"one": "Alpha updated", "two": "Beta updated"})
        rows = {candidate.action_id: candidate.row_number for candidate in plan.candidates}

        updated = commit_bulk_action_update(
            plan,
            (rows["one"],),
            self.local_actions,
            self.shared_actions,
            self.shared_contexts,
            self.local_contexts,
        )

        self.assertEqual([(action.id, action.title) for action in updated], [("one", "Alpha updated")])
        stored = load_stored_actions(self.local_actions, inspect_external_paths=False)
        self.assertEqual(
            [(action.id, action.title) for action in stored],
            [("one", "Alpha updated"), ("two", "Beta")],
        )

    def test_calls_batch_boundary_once_in_workbook_row_order(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        append_action(self.local_actions, _action("two", title="Beta"))
        plan = self._review({"one": "Alpha updated", "two": "Beta updated"})
        rows = {candidate.action_id: candidate.row_number for candidate in plan.candidates}

        with patch(
            "context_palette.action_bulk_update.update_actions_with_context_memberships"
        ) as update_many:
            result = commit_bulk_action_update(
                plan,
                (rows["two"], rows["one"]),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

        self.assertEqual([action.id for action in result], ["one", "two"])
        update_many.assert_called_once()
        self.assertEqual(
            [action.id for action in update_many.call_args.args[1]],
            ["one", "two"],
        )
        self.assertEqual(
            [action.id for action in update_many.call_args.args[2]],
            ["one", "two"],
        )
        self.assertTrue(update_many.call_args.kwargs["actions_are_local"])

    def test_changed_workbook_and_changed_actions_block_before_write(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        plan = self._review({"one": "Updated"})
        row_number = plan.candidates[0].row_number
        _change_cell(self.source, f"E{row_number}", "Changed again")
        with patch(
            "context_palette.action_bulk_update.update_actions_with_context_memberships"
        ) as update_many, self.assertRaisesRegex(BulkActionUpdateError, "workbook changed"):
            commit_bulk_action_update(
                plan,
                (row_number,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )
        update_many.assert_not_called()

        plan = self._review({"one": "Updated"})
        stored = load_stored_actions(self.local_actions, inspect_external_paths=False)[0]
        update_action(self.local_actions, replace(stored, value="changed elsewhere"))
        with self.assertRaisesRegex(BulkActionUpdateError, "saved Actions changed"):
            commit_bulk_action_update(
                plan,
                (plan.candidates[0].row_number,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

    def test_commit_rejects_the_validated_reread_when_its_digest_changed(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        plan = self._review({"one": "Updated"})
        current, local_ids = self._current()
        eligible = eligible_personal_actions_for_update(current, local_ids)
        reread = read_action_update_workbook(self.source, eligible)
        changed_reread = replace(reread, digest="0" * 64)

        with (
            patch(
                "context_palette.action_bulk_update.read_action_update_workbook",
                return_value=changed_reread,
            ),
            patch(
                "context_palette.action_bulk_update.update_actions_with_context_memberships"
            ) as update_many,
            self.assertRaisesRegex(BulkActionUpdateError, "workbook changed"),
        ):
            commit_bulk_action_update(
                plan,
                (plan.candidates[0].row_number,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

        update_many.assert_not_called()

    def test_rejects_unknown_no_change_and_invalid_selections(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        unchanged = self._review({})
        row_number = unchanged.candidates[0].row_number
        cases = (
            ((), "Select at least"),
            ((99,), "not part"),
            ((row_number,), "do not contain a reviewed change"),
            ((True,), "whole numbers"),
        )
        for selected, expected in cases:
            with self.subTest(selected=selected), self.assertRaisesRegex(
                BulkActionUpdateError,
                expected,
            ):
                commit_bulk_action_update(
                    unchanged,
                    selected,
                    self.local_actions,
                    self.shared_actions,
                    self.shared_contexts,
                    self.local_contexts,
                )

    def test_row_reviewed_as_error_cannot_be_promoted_during_commit(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        current, local_ids = self._current()
        eligible = eligible_personal_actions_for_update(current, local_ids)
        write_action_update_workbook(self.source, eligible)
        _change_cell(self.source, "E2", "Updated")
        _change_cell(self.source, "G2", "Future")
        workbook = read_action_update_workbook(self.source, eligible)
        plan = plan_bulk_action_update(
            workbook,
            current,
            local_ids,
            ("Personal",),
        )
        self.assertEqual(plan.candidates[0].status, "Error")

        save_contexts(
            self.local_contexts,
            [
                ContextDefinition("Personal", action_ids=()),
                ContextDefinition("Future", action_ids=()),
            ],
        )
        with patch(
            "context_palette.action_bulk_update.update_actions_with_context_memberships"
        ) as update_many, self.assertRaisesRegex(
            BulkActionUpdateError,
            "do not contain a reviewed change",
        ):
            commit_bulk_action_update(
                plan,
                (2,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )
        update_many.assert_not_called()

    def test_stable_id_preserves_sequence_and_context_references(self) -> None:
        target = _action(
            "target",
            title="Target",
            action_type="open_url",
            value="https://example.com/old",
        )
        sequence = _action(
            "sequence",
            title="Sequence",
            action_type="sequence",
            value="sequence-v1",
            sequence_steps=(
                SequenceStep("action", action_id="target"),
                SequenceStep("action", action_id="target"),
            ),
        )
        append_action(self.local_actions, target)
        append_action(self.local_actions, sequence)
        save_contexts(
            self.local_contexts,
            [
                ContextDefinition(
                    "Personal",
                    preferred_action_ids=("target",),
                    action_ids=("target",),
                )
            ],
        )
        plan = self._review({"target": "Renamed target"})

        updated = commit_bulk_action_update(
            plan,
            (plan.candidates[0].row_number,),
            self.local_actions,
            self.shared_actions,
            self.shared_contexts,
            self.local_contexts,
        )

        self.assertEqual(updated[0].id, "target")
        stored = load_stored_actions(self.local_actions, inspect_external_paths=False)
        saved_sequence = next(action for action in stored if action.id == "sequence")
        self.assertEqual(
            tuple(step.action_id for step in saved_sequence.sequence_steps),
            ("target", "target"),
        )
        context = load_contexts(self.local_contexts)[0]
        self.assertEqual(context.preferred_action_ids, ("target",))
        self.assertEqual(context.action_ids, ("target",))

    def test_context_failure_is_wrapped_without_claiming_success(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        plan = self._review({"one": "Updated"})
        before = self.local_actions.read_bytes()

        with patch(
            "context_palette.action_bulk_update.update_actions_with_context_memberships",
            side_effect=ContextError("memberships failed and originals were restored"),
        ), self.assertRaisesRegex(BulkActionUpdateError, "could not be updated"):
            commit_bulk_action_update(
                plan,
                (plan.candidates[0].row_number,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

        self.assertEqual(self.local_actions.read_bytes(), before)

    def test_incomplete_rollback_is_propagated_as_unknown_effects(self) -> None:
        append_action(self.local_actions, _action("one", title="Alpha"))
        plan = self._review({"one": "Updated"})
        failure = ContextMembershipUpdateError(
            "original files could not be restored completely",
            rollback_completed=False,
        )

        with (
            patch(
                "context_palette.action_bulk_update.update_actions_with_context_memberships",
                side_effect=failure,
            ),
            self.assertRaises(BulkActionUpdateError) as captured,
        ):
            commit_bulk_action_update(
                plan,
                (plan.candidates[0].row_number,),
                self.local_actions,
                self.shared_actions,
                self.shared_contexts,
                self.local_contexts,
            )

        self.assertFalse(captured.exception.rollback_completed)
        self.assertIs(captured.exception.__cause__, failure)
        self.assertIn("may have changed", str(captured.exception))
        self.assertIn("Diagnostics", str(captured.exception))

    def test_commit_persists_the_exact_reviewed_canonical_url(self) -> None:
        append_action(
            self.local_actions,
            _action(
                "url",
                action_type="open_url",
                value="https://example.com/before",
            ),
        )
        current, local_ids = self._current()
        eligible = eligible_personal_actions_for_update(current, local_ids)
        write_action_update_workbook(self.source, eligible)
        _change_cell(
            self.source,
            "F2",
            "\u2003https://example.com/after\u2003",
        )
        workbook = read_action_update_workbook(self.source, eligible)
        plan = plan_bulk_action_update(
            workbook,
            current,
            local_ids,
            ("Personal",),
        )
        reviewed = plan.candidates[0].action
        assert reviewed is not None

        updated = commit_bulk_action_update(
            plan,
            (plan.candidates[0].row_number,),
            self.local_actions,
            self.shared_actions,
            self.shared_contexts,
            self.local_contexts,
        )
        reloaded = load_stored_actions(
            self.local_actions,
            inspect_external_paths=False,
        )[0]

        self.assertEqual(reviewed.value, "https://example.com/after")
        self.assertEqual(updated[0], reviewed)
        self.assertEqual(reloaded, reviewed)
        with patch("context_palette.actions.webbrowser.open") as opened:
            open_action_target(reloaded)
        opened.assert_called_once_with("https://example.com/after")


if __name__ == "__main__":
    unittest.main()
