from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from context_palette.action_configured_placement import (
    LOCAL_STORAGE,
    SHARED_STORAGE,
    ConfiguredPlacementError,
    ConfiguredPlacementKey,
    commit_configured_action_placements,
    configured_action_placement_inventory,
    configured_action_placement_paths,
    draft_configured_action_placement_inventory,
    plan_configured_action_placements,
    save_action_with_configured_placements,
)
from context_palette.actions import Action
from context_palette.command_surface import (
    CommandGroup,
    CommandItem,
    CommandTarget,
    GROUP_PRESENTATION_NESTED_MENU,
    command_group_action_ids,
    command_item_targets,
    load_command_groups,
)
from context_palette.configuration_data import (
    save_command_groups as real_save_command_groups,
)
from context_palette.work_items import WorkItemReference


class ConfiguredActionPlacementTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path, Path, Path]:
        return (
            root / "actions.json",
            root / "local_actions.json",
            root / "command_surface.json",
            root / "local_command_surface.json",
        )

    def _write(self, path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def _action(
        self,
        action_id: str,
        *,
        title: str | None = None,
        state: str = "Active",
    ) -> dict[str, object]:
        return {
            "id": action_id,
            "title": title or action_id.title(),
            "context": "General",
            "type": "copy_text",
            "value": action_id,
            "state": state,
        }

    def _seed(
        self,
        root: Path,
        *,
        shared_surface: dict[str, object] | None = None,
        local_surface: dict[str, object] | None = None,
        shared_actions: list[dict[str, object]] | None = None,
        local_actions: list[dict[str, object]] | None = None,
    ) -> tuple[Path, Path, Path, Path]:
        paths = self._paths(root)
        self._write(
            paths[0],
            {"actions": shared_actions or [self._action("built-in")]},
        )
        self._write(
            paths[1],
            {"actions": local_actions or [self._action("personal")]},
        )
        self._write(
            paths[2],
            shared_surface
            or {
                "groups": [
                    {
                        "id": "standard",
                        "label": "Standard",
                        "presentation": "nested_menu",
                        "action_ids": ["built-in"],
                        "items": [
                            {
                                "id": "work",
                                "label": "Work",
                                "items": [],
                            }
                        ],
                    }
                ]
            },
        )
        self._write(
            paths[3],
            local_surface
            or {
                "groups": [
                    {
                        "id": "apps",
                        "label": "Apps",
                        "items": [
                            {
                                "id": "projects",
                                "label": "Projects",
                                "action_ids": ["personal"],
                            }
                        ],
                    }
                ]
            },
        )
        return paths

    def _inventory(self, action_id: str, paths: tuple[Path, Path, Path, Path]):
        return configured_action_placement_inventory(
            action_id,
            shared_actions_path=paths[0],
            local_actions_path=paths[1],
            shared_command_surface_path=paths[2],
            local_command_surface_path=paths[3],
        )

    def _plan(
        self,
        action_id: str,
        desired: tuple[ConfiguredPlacementKey, ...],
        paths: tuple[Path, Path, Path, Path],
    ):
        return plan_configured_action_placements(
            action_id,
            desired,
            shared_actions_path=paths[0],
            local_actions_path=paths[1],
            shared_command_surface_path=paths[2],
            local_command_surface_path=paths[3],
        )

    def _composite_kwargs(
        self,
        root: Path,
        paths: tuple[Path, Path, Path, Path],
    ) -> dict[str, Path]:
        shared_contexts = root / "contexts.json"
        local_contexts = root / "local_contexts.json"
        self._write(shared_contexts, {"contexts": []})
        self._write(local_contexts, {"contexts": []})
        return {
            "shared_actions_path": paths[0],
            "local_actions_path": paths[1],
            "shared_contexts_path": shared_contexts,
            "local_contexts_path": local_contexts,
            "shared_command_surface_path": paths[2],
            "local_command_surface_path": paths[3],
        }

    def test_pure_paths_include_group_root_and_nested_references(self) -> None:
        groups = (
            CommandGroup(
                "apps",
                "Apps",
                (
                    CommandItem(
                        "development",
                        "Development",
                        items=(
                            CommandItem(
                                "projects",
                                "Projects",
                                action_ids=("target",),
                            ),
                        ),
                    ),
                ),
                presentation=GROUP_PRESENTATION_NESTED_MENU,
                action_ids=("target",),
            ),
        )

        self.assertEqual(
            configured_action_placement_paths("target", groups),
            (("Apps",), ("Apps", "Development", "Projects")),
        )

    def test_inventory_lists_personal_first_and_enforces_ownership(self) -> None:
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary))

            inventory = self._inventory("personal", paths)

        self.assertEqual(inventory.action_storage, LOCAL_STORAGE)
        self.assertEqual(
            [location.menu_path for location in inventory.locations],
            [
                ("Apps",),
                ("Apps", "Projects"),
                ("Standard",),
                ("Standard", "Work"),
            ],
        )
        self.assertEqual(
            inventory.current_locations,
            (ConfiguredPlacementKey(LOCAL_STORAGE, "apps", ("projects",)),),
        )
        self.assertTrue(inventory.locations[0].assignable)
        self.assertFalse(inventory.locations[2].assignable)
        self.assertIn("cannot be placed", inventory.locations[2].unavailable_reason)

    def test_draft_inventory_needs_no_saved_id_and_applies_storage_ownership(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary))

            personal = draft_configured_action_placement_inventory(
                action_storage=LOCAL_STORAGE,
                shared_command_surface_path=paths[2],
                local_command_surface_path=paths[3],
            )
            built_in = draft_configured_action_placement_inventory(
                action_storage=SHARED_STORAGE,
                shared_command_surface_path=paths[2],
                local_command_surface_path=paths[3],
            )

        self.assertEqual(personal.action_id, "")
        self.assertEqual(personal.current_locations, ())
        self.assertEqual(
            [location.menu_path for location in personal.locations],
            [
                ("Apps",),
                ("Apps", "Projects"),
                ("Standard",),
                ("Standard", "Work"),
            ],
        )
        self.assertTrue(all(location.assignable for location in personal.locations[:2]))
        self.assertTrue(
            all(not location.assignable for location in personal.locations[2:])
        )
        self.assertTrue(all(location.assignable for location in built_in.locations))

    def test_composite_create_saves_action_context_and_selected_placement(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._seed(root)
            kwargs = self._composite_kwargs(root, paths)
            action = Action(
                "new-personal",
                "New personal",
                "General",
                "copy_text",
                "hello",
            )
            destination = ConfiguredPlacementKey(LOCAL_STORAGE, "apps")

            result = save_action_with_configured_placements(
                action,
                (destination,),
                action_is_local=True,
                **kwargs,
            )

            saved_actions = json.loads(paths[1].read_text(encoding="utf-8"))["actions"]
            saved_group = load_command_groups(paths[3])[0]

        self.assertIn("new-personal", [item["id"] for item in saved_actions])
        self.assertEqual(result.additions, (destination,))
        self.assertIn("new-personal", command_group_action_ids(saved_group))

    def test_composite_update_preserves_id_and_replaces_configured_locations(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._seed(root)
            kwargs = self._composite_kwargs(root, paths)
            previous = Action(
                "personal",
                "Personal",
                "General",
                "copy_text",
                "personal",
            )
            updated = Action(
                "personal",
                "Renamed personal",
                "General",
                "copy_text",
                "updated",
            )
            root_key = ConfiguredPlacementKey(LOCAL_STORAGE, "apps")

            result = save_action_with_configured_placements(
                updated,
                (root_key,),
                previous_action=previous,
                action_is_local=True,
                **kwargs,
            )

            saved_actions = json.loads(paths[1].read_text(encoding="utf-8"))["actions"]
            saved_group = load_command_groups(paths[3])[0]

        saved = next(item for item in saved_actions if item["id"] == "personal")
        self.assertEqual(saved["title"], "Renamed personal")
        self.assertEqual(result.current_locations, (root_key,))
        self.assertIn("personal", command_group_action_ids(saved_group))
        self.assertEqual(saved_group.items, ())

    def test_composite_update_rejects_action_changed_after_editor_opened(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._seed(root)
            kwargs = self._composite_kwargs(root, paths)
            previous = Action(
                "personal",
                "Personal",
                "General",
                "copy_text",
                "personal",
            )
            updated = Action(
                "personal",
                "Reviewed edit",
                "General",
                "copy_text",
                "updated",
            )
            changed = json.loads(paths[1].read_text(encoding="utf-8"))
            changed["actions"][0]["title"] = "Concurrent edit"
            self._write(paths[1], changed)
            before = tuple(path.read_bytes() for path in paths)

            with self.assertRaisesRegex(
                ConfiguredPlacementError,
                "changed after this editor opened",
            ):
                save_action_with_configured_placements(
                    updated,
                    (ConfiguredPlacementKey(LOCAL_STORAGE, "apps"),),
                    previous_action=previous,
                    action_is_local=True,
                    **kwargs,
                )

            after = tuple(path.read_bytes() for path in paths)

        self.assertEqual(after, before)

    def test_composite_failure_restores_all_primary_and_backup_bytes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._seed(root)
            kwargs = self._composite_kwargs(root, paths)
            self._write(
                kwargs["shared_contexts_path"],
                {"contexts": [{"name": "Work", "action_ids": []}]},
            )
            action = Action(
                "new-built-in",
                "New built-in",
                "General",
                "copy_text",
                "hello",
                contexts=("Work",),
            )
            desired = (
                ConfiguredPlacementKey(SHARED_STORAGE, "standard", ("work",)),
                ConfiguredPlacementKey(LOCAL_STORAGE, "apps"),
            )
            primaries = (
                paths[0],
                kwargs["shared_contexts_path"],
                kwargs["local_contexts_path"],
                paths[2],
                paths[3],
            )
            for index, primary in enumerate(primaries):
                primary.with_name(primary.name + ".bak").write_bytes(
                    f"backup-{index}".encode()
                )
            participants = tuple(
                path
                for primary in primaries
                for path in (primary, primary.with_name(primary.name + ".bak"))
            )
            originals = {path: path.read_bytes() for path in participants}

            def fail_after_context_membership(
                _path: Path,
                _groups: list[CommandGroup],
            ) -> None:
                contexts = json.loads(
                    kwargs["shared_contexts_path"].read_text(encoding="utf-8")
                )["contexts"]
                self.assertIn("new-built-in", contexts[0]["action_ids"])
                raise OSError("surface write failed")

            with patch(
                "context_palette.action_configured_placement.save_command_groups",
                side_effect=fail_after_context_membership,
            ):
                with self.assertRaises(ConfiguredPlacementError) as caught:
                    save_action_with_configured_placements(
                        action,
                        desired,
                        action_is_local=False,
                        **kwargs,
                    )

            restored = {path: path.read_bytes() for path in participants}

        self.assertTrue(caught.exception.rollback_completed)
        self.assertEqual(restored, originals)

    def test_built_in_action_can_move_between_both_surface_files(self) -> None:
        local_surface = {
            "groups": [
                {
                    "id": "apps",
                    "label": "Apps",
                    "items": [
                        {
                            "id": "mixed",
                            "label": "Mixed",
                            "targets": [
                                {
                                    "type": "work_item",
                                    "source_id": "source",
                                    "relative_folder": "ISS-ABC-one",
                                },
                                {"type": "action", "action_id": "personal"},
                            ],
                        }
                    ],
                }
            ]
        }
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary), local_surface=local_surface)
            action_bytes = (paths[0].read_bytes(), paths[1].read_bytes())
            desired = (
                ConfiguredPlacementKey(LOCAL_STORAGE, "apps"),
                ConfiguredPlacementKey(LOCAL_STORAGE, "apps", ("mixed",)),
            )

            plan = self._plan("built-in", desired, paths)

            self.assertEqual(len(plan.additions), 2)
            self.assertEqual(len(plan.removals), 1)
            self.assertEqual(plan.shared_reference_changes, 1)
            self.assertEqual(plan.local_reference_changes, 2)
            self.assertEqual(plan.files_to_write, 2)
            result = commit_configured_action_placements(plan)

            shared_group = load_command_groups(paths[2])[0]
            local_group = load_command_groups(paths[3])[0]
            mixed_targets = command_item_targets(local_group.items[0])
            action_bytes_after = (paths[0].read_bytes(), paths[1].read_bytes())

        self.assertEqual(result.files_written, 2)
        self.assertEqual(command_group_action_ids(shared_group), ())
        self.assertEqual(command_group_action_ids(local_group), ("built-in",))
        self.assertEqual(
            mixed_targets,
            (
                CommandTarget(
                    work_item_ref=WorkItemReference("source", "ISS-ABC-one")
                ),
                CommandTarget(action_id="personal"),
                CommandTarget(action_id="built-in"),
            ),
        )
        self.assertEqual(action_bytes_after, action_bytes)

    def test_removal_preserves_mixed_targets_children_and_order(self) -> None:
        local_surface = {
            "groups": [
                {
                    "id": "apps",
                    "label": "Apps",
                    "items": [
                        {
                            "id": "mixed",
                            "label": "Mixed",
                            "targets": [
                                {"type": "action", "action_id": "personal"},
                                {
                                    "type": "work_item",
                                    "source_id": "source",
                                    "relative_folder": "ISS-ABC-one",
                                },
                                {"type": "action", "action_id": "built-in"},
                            ],
                            "items": [
                                {
                                    "id": "child",
                                    "label": "Child",
                                    "action_ids": ["built-in"],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary), local_surface=local_surface)
            plan = self._plan("personal", (), paths)

            result = commit_configured_action_placements(plan)
            mixed = load_command_groups(paths[3])[0].items[0]

        self.assertEqual(result.items_pruned, 0)
        self.assertEqual(
            command_item_targets(mixed),
            (
                CommandTarget(
                    work_item_ref=WorkItemReference("source", "ISS-ABC-one")
                ),
                CommandTarget(action_id="built-in"),
            ),
        )
        self.assertEqual([item.id for item in mixed.items], ["child"])

    def test_removing_sole_reference_prunes_newly_empty_ancestors_only(self) -> None:
        local_surface = {
            "groups": [
                {
                    "id": "apps",
                    "label": "Apps",
                    "items": [
                        {"id": "already-empty", "label": "Already empty"},
                        {
                            "id": "parent",
                            "label": "Parent",
                            "items": [
                                {
                                    "id": "leaf",
                                    "label": "Leaf",
                                    "action_ids": ["personal"],
                                }
                            ],
                        },
                    ],
                }
            ]
        }
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary), local_surface=local_surface)

            plan = self._plan("personal", (), paths)

            self.assertEqual(plan.items_pruned, 2)
            result = commit_configured_action_placements(plan)
            items = load_command_groups(paths[3])[0].items

        self.assertEqual(result.items_pruned, 2)
        self.assertEqual([item.id for item in items], ["already-empty"])

    def test_personal_action_cannot_be_added_to_built_in_menu(self) -> None:
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary))
            shared_root = ConfiguredPlacementKey(SHARED_STORAGE, "standard")

            with self.assertRaisesRegex(
                ConfiguredPlacementError,
                "cannot be placed in Built-in",
            ):
                self._plan("personal", (shared_root,), paths)

    def test_existing_invalid_shared_reference_can_be_retained_or_removed(self) -> None:
        shared_surface = {
            "groups": [
                {
                    "id": "standard",
                    "label": "Standard",
                    "presentation": "nested_menu",
                    "action_ids": ["personal"],
                    "items": [],
                }
            ]
        }
        local_surface = {
            "groups": [{"id": "apps", "label": "Apps", "items": []}]
        }
        with TemporaryDirectory() as temporary:
            paths = self._seed(
                Path(temporary),
                shared_surface=shared_surface,
                local_surface=local_surface,
            )
            shared_root = ConfiguredPlacementKey(SHARED_STORAGE, "standard")

            inventory = self._inventory("personal", paths)
            retained = self._plan("personal", (shared_root,), paths)
            removal = self._plan("personal", (), paths)
            result = commit_configured_action_placements(removal)
            saved = load_command_groups(paths[2])[0]

        self.assertEqual(inventory.current_locations, (shared_root,))
        self.assertFalse(inventory.locations[-1].assignable)
        self.assertEqual(retained.files_to_write, 0)
        self.assertEqual(removal.removals, (shared_root,))
        self.assertEqual(result.removals, (shared_root,))
        self.assertEqual(command_group_action_ids(saved), ())

    def test_legacy_inactive_action_cannot_own_configured_placements(self) -> None:
        with TemporaryDirectory() as temporary:
            paths = self._seed(
                Path(temporary),
                local_actions=[self._action("personal", state="Archived")],
            )

            with self.assertRaisesRegex(ConfiguredPlacementError, "Legacy inactive"):
                self._inventory("personal", paths)

    def test_no_change_plan_writes_nothing(self) -> None:
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary))
            before = (paths[2].read_bytes(), paths[3].read_bytes())
            current = self._inventory("personal", paths).current_locations

            plan = self._plan("personal", current, paths)
            result = commit_configured_action_placements(plan)

            self.assertEqual(plan.additions, ())
            self.assertEqual(plan.removals, ())
            self.assertEqual(plan.files_to_write, 0)
            self.assertEqual(result.files_written, 0)
            self.assertEqual((paths[2].read_bytes(), paths[3].read_bytes()), before)

    def test_stale_action_or_surface_change_rejects_before_write(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._seed(root)
            desired = (
                ConfiguredPlacementKey(LOCAL_STORAGE, "apps"),
            )
            plan = self._plan("built-in", desired, paths)
            before_surfaces = (paths[2].read_bytes(), paths[3].read_bytes())
            actions = json.loads(paths[0].read_text(encoding="utf-8"))
            actions["actions"][0]["title"] = "Changed after review"
            self._write(paths[0], actions)

            with self.assertRaisesRegex(ConfiguredPlacementError, "changed after review"):
                commit_configured_action_placements(plan)

            self.assertEqual(
                (paths[2].read_bytes(), paths[3].read_bytes()),
                before_surfaces,
            )

    def test_two_file_failure_restores_exact_primaries_and_backups(self) -> None:
        local_surface = {
            "groups": [
                {"id": "apps", "label": "Apps", "items": []},
            ]
        }
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary), local_surface=local_surface)
            paths[2].with_name(paths[2].name + ".bak").write_bytes(b"shared backup")
            paths[3].with_name(paths[3].name + ".bak").write_bytes(b"local backup")
            participants = (
                paths[2],
                paths[2].with_name(paths[2].name + ".bak"),
                paths[3],
                paths[3].with_name(paths[3].name + ".bak"),
            )
            originals = {path: path.read_bytes() for path in participants}
            desired = (ConfiguredPlacementKey(LOCAL_STORAGE, "apps"),)
            plan = self._plan("built-in", desired, paths)
            calls = 0

            def fail_second(path: Path, groups: list[CommandGroup]) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("second write failed")
                real_save_command_groups(path, groups)

            with patch(
                "context_palette.action_configured_placement.save_command_groups",
                side_effect=fail_second,
            ):
                with self.assertRaises(ConfiguredPlacementError) as caught:
                    commit_configured_action_placements(plan)

            self.assertTrue(caught.exception.rollback_completed)
            self.assertEqual(
                {path: path.read_bytes() for path in participants},
                originals,
            )

    def test_unknown_and_duplicate_location_keys_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            paths = self._seed(Path(temporary))
            missing = ConfiguredPlacementKey(LOCAL_STORAGE, "missing")
            existing = ConfiguredPlacementKey(LOCAL_STORAGE, "apps")

            with self.assertRaisesRegex(ConfiguredPlacementError, "no longer exists"):
                self._plan("built-in", (missing,), paths)
            with self.assertRaisesRegex(ConfiguredPlacementError, "more than once"):
                self._plan("built-in", (existing, existing), paths)


if __name__ == "__main__":
    unittest.main()
