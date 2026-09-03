from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import context_palette.action_quick_menu_organization as organization_module
from context_palette.action_quick_menu_organization import (
    QuickMenuOrganizationError,
    commit_quick_menu_organization,
    plan_quick_menu_assignment,
    plan_quick_menu_branch_move,
)
from context_palette.actions import (
    Action,
    append_actions,
    load_stored_actions,
    update_action,
    update_actions as real_update_actions,
)


def action(
    action_id: str,
    *,
    action_type: str = "open_folder",
    state: str = "Active",
    quick_path: tuple[str, ...] = (),
    value: str | None = None,
) -> Action:
    return Action(
        action_id,
        action_id.replace("-", " ").title(),
        "General",
        action_type,
        value or rf"D:\targets\{action_id}",
        state=state,
        quick_action_path=quick_path,
    )


class QuickMenuOrganizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.shared = self.root / "actions.json"
        self.local = self.root / "local_actions.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write(
        self,
        shared: tuple[Action, ...],
        local: tuple[Action, ...] = (),
    ) -> None:
        append_actions(self.shared, shared)
        if local:
            append_actions(self.local, local)

    def _stored(self, path: Path) -> dict[str, Action]:
        return {
            item.id: item
            for item in load_stored_actions(path, inspect_external_paths=False)
        }

    def test_assignment_canonicalizes_collision_and_reports_exact_storage(self) -> None:
        marker = self.root / "external target marker.txt"
        marker.write_bytes(b"do not touch")
        self._write(
            (
                action(
                    "existing",
                    quick_path=("Work", "Reports"),
                    value=str(marker),
                ),
                action("shared-selected", quick_path=("Old",)),
                action(
                    "unrelated-prompt",
                    action_type="ai_prompt",
                    quick_path=("Work",),
                ),
            ),
            (
                action(
                    "local-selected",
                    quick_path=("Other",),
                ),
            ),
        )

        plan = plan_quick_menu_assignment(
            ("LOCAL-SELECTED", "shared-selected"),
            (" work ", " reports "),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        self.assertEqual(plan.action_type, "open_folder")
        self.assertEqual(plan.destination_path, ("Work", "Reports"))
        self.assertTrue(plan.destination_merged)
        self.assertTrue(plan.canonicalization_applied)
        self.assertEqual(
            plan.affected_action_ids,
            ("shared-selected", "local-selected"),
        )
        self.assertEqual(plan.shared_action_count, 1)
        self.assertEqual(plan.local_action_count, 1)
        self.assertEqual(plan.active_action_count, 2)
        self.assertEqual(plan.files_to_write, 2)

        result = commit_quick_menu_organization(plan)

        self.assertEqual(result.affected_action_ids, plan.affected_action_ids)
        self.assertEqual(result.files_written, 2)
        shared = self._stored(self.shared)
        local = self._stored(self.local)
        self.assertEqual(
            shared["shared-selected"].quick_action_path,
            ("Work", "Reports"),
        )
        self.assertEqual(
            local["local-selected"].quick_action_path,
            ("Work", "Reports"),
        )
        self.assertEqual(shared["existing"].value, str(marker))
        self.assertEqual(marker.read_bytes(), b"do not touch")
        self.assertEqual(
            set(shared),
            {"existing", "shared-selected", "unrelated-prompt"},
        )
        self.assertEqual(set(local), {"local-selected"})

    def test_branch_move_changes_active_actions_but_not_legacy_inactive_records(self) -> None:
        self._write(
            (
                action("shared-root", quick_path=("Work",)),
                action(
                    "shared-report",
                    state="Archived",
                    quick_path=("Work", "reports"),
                ),
                action(
                    "existing-destination",
                    quick_path=("Archive", "Reports", "Existing"),
                ),
            ),
            (
                action(
                    "local-monthly",
                    quick_path=("work", "REPORTS", "Monthly"),
                ),
            ),
        )

        plan = plan_quick_menu_branch_move(
            "open_folder",
            (" work ",),
            (" archive ",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        self.assertEqual(plan.source_prefix, ("Work",))
        self.assertEqual(plan.destination_path, ("Archive",))
        self.assertEqual(
            plan.matched_action_ids,
            ("shared-root", "local-monthly"),
        )
        self.assertEqual(plan.affected_action_ids, plan.matched_action_ids)
        self.assertEqual(plan.shared_action_count, 1)
        self.assertEqual(plan.local_action_count, 1)
        self.assertEqual(plan.active_action_count, 2)
        self.assertTrue(plan.destination_merged)
        self.assertTrue(plan.canonicalization_applied)
        paths = {change.action_id: change.after_path for change in plan.changes}
        self.assertEqual(paths["shared-root"], ("Archive",))
        self.assertEqual(
            paths["local-monthly"],
            ("Archive", "Reports", "Monthly"),
        )

        commit_quick_menu_organization(plan)

        shared = self._stored(self.shared)
        local = self._stored(self.local)
        self.assertEqual(shared["shared-root"].quick_action_path, ("Archive",))
        self.assertEqual(
            shared["shared-report"].quick_action_path,
            ("Work", "reports"),
        )
        self.assertEqual(
            local["local-monthly"].quick_action_path,
            ("Archive", "Reports", "Monthly"),
        )
        self.assertEqual(
            shared["existing-destination"].quick_action_path,
            ("Archive", "Reports", "Existing"),
        )

    def test_case_only_branch_rename_uses_requested_spelling(self) -> None:
        self._write((action("folder", quick_path=("work", "Reports")),))

        plan = plan_quick_menu_branch_move(
            "open_folder",
            ("WORK",),
            ("Work",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        self.assertEqual(plan.source_prefix, ("work",))
        self.assertEqual(plan.destination_path, ("Work",))
        self.assertEqual(plan.affected_action_ids, ("folder",))
        self.assertEqual(plan.changes[0].after_path, ("Work", "Reports"))

    def test_remove_nested_branch_promotes_contents_without_deleting_actions(self) -> None:
        direct = action(
            "direct",
            quick_path=("Work", "Reports"),
        )
        nested = action(
            "nested",
            state="Archived",
            quick_path=("Work", "Reports", "Monthly"),
        )
        unrelated = action(
            "unrelated",
            quick_path=("Work", "Other"),
        )
        local_nested = action(
            "local-nested",
            quick_path=("Work", "Reports", "Weekly"),
        )
        self._write((direct, nested, unrelated), (local_nested,))

        plan = plan_quick_menu_branch_move(
            "open_folder",
            ("Work", "Reports"),
            ("Work",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        self.assertEqual(
            plan.matched_action_ids,
            ("direct", "local-nested"),
        )
        self.assertEqual(plan.active_action_count, 2)
        paths = {change.action_id: change.after_path for change in plan.changes}
        self.assertEqual(paths["direct"], ("Work",))
        self.assertEqual(paths["local-nested"], ("Work", "Weekly"))

        result = commit_quick_menu_organization(plan)

        self.assertEqual(set(result.affected_action_ids), set(plan.matched_action_ids))
        shared = self._stored(self.shared)
        local = self._stored(self.local)
        self.assertEqual(shared["unrelated"], unrelated)
        self.assertEqual(shared["direct"].title, direct.title)
        self.assertEqual(shared["nested"].state, "Archived")
        self.assertEqual(
            shared["nested"].quick_action_path,
            ("Work", "Reports", "Monthly"),
        )
        self.assertEqual(local["local-nested"].value, local_nested.value)

    def test_assignment_rejects_legacy_inactive_action(self) -> None:
        self._write((action("legacy", state="Archived", quick_path=("Old",)),))

        with self.assertRaisesRegex(
            QuickMenuOrganizationError,
            "Legacy inactive Actions can only be deleted",
        ):
            plan_quick_menu_assignment(
                ("legacy",),
                ("New",),
                shared_actions_path=self.shared,
                local_actions_path=self.local,
            )

    def test_promoting_child_branch_to_root_reports_existing_branch_merge(self) -> None:
        promoted = action(
            "promoted",
            quick_path=("Work", "Reports", "Monthly"),
        )
        existing = action(
            "existing",
            quick_path=("Reports", "Existing"),
        )
        self._write((promoted, existing))

        plan = plan_quick_menu_branch_move(
            "open_folder",
            ("Work",),
            (),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        self.assertTrue(plan.destination_merged)
        self.assertEqual(plan.changes[0].after_path, ("Reports", "Monthly"))

    def test_validation_rejects_mixed_types_bad_paths_and_recursive_moves(self) -> None:
        self._write(
            (
                action("folder", quick_path=("Work",)),
                action("prompt", action_type="ai_prompt", quick_path=("Work",)),
                action(
                    "deep",
                    quick_path=("Work", "Reports", "Monthly"),
                ),
            )
        )

        cases = (
            (
                lambda: plan_quick_menu_assignment(
                    ("folder", "prompt"),
                    ("New",),
                    shared_actions_path=self.shared,
                    local_actions_path=self.local,
                ),
                "same automatic menu type",
            ),
            (
                lambda: plan_quick_menu_assignment(
                    ("folder",),
                    ("One", "Two", "Three", "Four"),
                    shared_actions_path=self.shared,
                    local_actions_path=self.local,
                ),
                "at most 3 levels",
            ),
            (
                lambda: plan_quick_menu_branch_move(
                    "open_folder",
                    ("Work",),
                    ("Work", "Nested"),
                    shared_actions_path=self.shared,
                    local_actions_path=self.local,
                ),
                "inside itself",
            ),
            (
                lambda: plan_quick_menu_branch_move(
                    "open_folder",
                    ("Work",),
                    ("Archive", "2026"),
                    shared_actions_path=self.shared,
                    local_actions_path=self.local,
                ),
                "three-level",
            ),
        )
        for operation, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                QuickMenuOrganizationError,
                message,
            ):
                operation()

    def test_stale_plan_is_rejected_before_any_commit_write(self) -> None:
        self._write(
            (
                action("selected", quick_path=("Before",)),
                action("other", quick_path=("Other",)),
            )
        )
        plan = plan_quick_menu_assignment(
            ("selected",),
            ("After",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )
        other = self._stored(self.shared)["other"]
        update_action(self.shared, replace(other, title="Changed elsewhere"))

        with (
            patch(
                "context_palette.action_quick_menu_organization.update_actions"
            ) as update_many,
            self.assertRaisesRegex(
                QuickMenuOrganizationError,
                "changed after review",
            ) as captured,
        ):
            commit_quick_menu_organization(plan)

        self.assertIsNone(captured.exception.rollback_completed)
        update_many.assert_not_called()

    def test_change_during_final_file_snapshot_is_rejected_before_write(self) -> None:
        self._write(
            (
                action("selected", quick_path=("Before",)),
                action("other", quick_path=("Other",)),
            )
        )
        plan = plan_quick_menu_assignment(
            ("selected",),
            ("After",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )
        real_fingerprint = organization_module._plan_fingerprint
        calls = 0

        def mutate_during_snapshot(**kwargs: object) -> str:
            nonlocal calls
            calls += 1
            fingerprint = real_fingerprint(**kwargs)  # type: ignore[arg-type]
            if calls == 2:
                other = self._stored(self.shared)["other"]
                update_action(self.shared, replace(other, title="Changed during commit"))
            return fingerprint

        with (
            patch(
                "context_palette.action_quick_menu_organization._plan_fingerprint",
                side_effect=mutate_during_snapshot,
            ),
            patch(
                "context_palette.action_quick_menu_organization.update_actions"
            ) as update_many,
            self.assertRaisesRegex(
                QuickMenuOrganizationError,
                "changed after review",
            ) as captured,
        ):
            commit_quick_menu_organization(plan)

        self.assertIsNone(captured.exception.rollback_completed)
        update_many.assert_not_called()
        stored = self._stored(self.shared)
        self.assertEqual(stored["selected"].quick_action_path, ("Before",))
        self.assertEqual(stored["other"].title, "Changed during commit")

    def test_each_changed_action_file_is_written_once(self) -> None:
        self._write(
            (action("shared", quick_path=("Before",)),),
            (action("local", quick_path=("Before",)),),
        )
        plan = plan_quick_menu_assignment(
            ("shared", "local"),
            ("After",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )
        calls: list[Path] = []

        def tracking_write(path: Path, actions: tuple[Action, ...]) -> None:
            calls.append(Path(path))
            real_update_actions(path, actions)

        with patch(
            "context_palette.action_quick_menu_organization.update_actions",
            side_effect=tracking_write,
        ):
            result = commit_quick_menu_organization(plan)

        self.assertEqual(calls, [self.shared, self.local])
        self.assertEqual(result.files_written, 2)

    def test_second_write_failure_restores_exact_action_and_backup_bytes(self) -> None:
        self._write(
            (action("shared", quick_path=("Before",)),),
            (action("local", quick_path=("Before",)),),
        )
        shared_backup = self.shared.with_name(self.shared.name + ".bak")
        local_backup = self.local.with_name(self.local.name + ".bak")
        shared_backup.write_bytes(b"original shared backup\x00")
        local_backup.write_bytes(b"original local backup\x00")
        originals = {
            path: path.read_bytes()
            for path in (self.shared, self.local, shared_backup, local_backup)
        }
        plan = plan_quick_menu_assignment(
            ("shared", "local"),
            ("After",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )
        calls: list[Path] = []

        def fail_second(path: Path, actions: tuple[Action, ...]) -> None:
            path = Path(path)
            calls.append(path)
            if len(calls) == 1:
                real_update_actions(path, actions)
                return
            path.write_bytes(b"partial second write")
            path.with_name(path.name + ".bak").write_bytes(b"partial backup")
            raise OSError("second write failed")

        with (
            patch(
                "context_palette.action_quick_menu_organization.update_actions",
                side_effect=fail_second,
            ),
            self.assertRaises(QuickMenuOrganizationError) as captured,
        ):
            commit_quick_menu_organization(plan)

        self.assertTrue(captured.exception.rollback_completed)
        self.assertEqual(calls, [self.shared, self.local])
        for path, payload in originals.items():
            self.assertEqual(path.read_bytes(), payload, path.name)

    def test_rollback_failure_is_reported_as_unknown_effects(self) -> None:
        self._write(
            (action("shared", quick_path=("Before",)),),
            (action("local", quick_path=("Before",)),),
        )
        plan = plan_quick_menu_assignment(
            ("shared", "local"),
            ("After",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        def fail_second(path: Path, actions: tuple[Action, ...]) -> None:
            if Path(path) == self.shared:
                real_update_actions(path, actions)
                return
            raise OSError("second write failed")

        with (
            patch(
                "context_palette.action_quick_menu_organization.update_actions",
                side_effect=fail_second,
            ),
            patch(
                "context_palette.action_quick_menu_organization.atomic_replace_bytes",
                side_effect=OSError("restore denied"),
            ),
            self.assertRaises(QuickMenuOrganizationError) as captured,
        ):
            commit_quick_menu_organization(plan)

        self.assertFalse(captured.exception.rollback_completed)
        self.assertIn("rollback was incomplete", str(captured.exception))

    def test_no_change_plan_performs_no_write(self) -> None:
        self._write((action("folder", quick_path=("Work",)),))
        plan = plan_quick_menu_assignment(
            ("folder",),
            ("Work",),
            shared_actions_path=self.shared,
            local_actions_path=self.local,
        )

        self.assertEqual(plan.affected_action_ids, ())
        self.assertEqual(plan.files_to_write, 0)
        with patch(
            "context_palette.action_quick_menu_organization.update_actions"
        ) as update_many:
            result = commit_quick_menu_organization(plan)

        update_many.assert_not_called()
        self.assertEqual(result.files_written, 0)
        self.assertEqual(result.affected_action_ids, ())


if __name__ == "__main__":
    unittest.main()
