from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from context_palette.persistence import atomic_write_json as real_atomic_write_json
from context_palette.work_item_organization import (
    WorkItemOrganizationError,
    forget_work_item_organization,
    inspect_work_item_organization,
)
from context_palette.work_items import WorkItemReference


class WorkItemOrganizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = WorkItemReference("source", "ISS-CAP40-target")
        self.other_reference = WorkItemReference("source", "ISS-CAP40-other")

    def _write(self, path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def _read(self, path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    def _paths(self, root: Path) -> tuple[Path, Path, Path, Path]:
        return (
            root / "local_work_item_metadata.json",
            root / "local_contexts.json",
            root / "palette.json",
            root / "local_command_surface.json",
        )

    def _call(self, function, root: Path):
        metadata, contexts, palette, commands = self._paths(root)
        return function(
            self.reference,
            metadata_path=metadata,
            context_paths=(contexts,),
            palette_path=palette,
            command_surface_path=commands,
        )

    def _seed_complete_configuration(self, root: Path) -> None:
        metadata, contexts, palette, commands = self._paths(root)
        self._write(
            metadata,
            {
                "work_items": {
                    "source/ISS-CAP40-target": {"tags": ["age"]},
                    "source/ISS-CAP40-other": {"tags": ["keep"]},
                }
            },
        )
        self._write(
            contexts,
            {
                "contexts": [
                    {
                        "name": "Delivery",
                        "action_ids": ["keep-action"],
                        "work_item_refs": [
                            {
                                "source_id": "source",
                                "relative_folder": "ISS-CAP40-target",
                            },
                            {
                                "source_id": "source",
                                "relative_folder": "ISS-CAP40-other",
                            },
                        ],
                        "preferred_items": [
                            {
                                "type": "work_item",
                                "source_id": "source",
                                "relative_folder": "ISS-CAP40-target",
                            },
                            {"type": "action", "action_id": "keep-action"},
                        ],
                    }
                ]
            },
        )
        self._write(
            palette,
            {
                "pinned_action_ids": [],
                "focus_context": "Delivery",
                "context_slots": {},
                "context_item_slots": {
                    "Delivery": [
                        {
                            "type": "work_item",
                            "source_id": "source",
                            "relative_folder": "ISS-CAP40-target",
                        },
                        {"type": "action", "action_id": "keep-action"},
                    ]
                },
            },
        )
        self._write(
            commands,
            {
                "groups": [
                    {
                        "id": "personal",
                        "label": "Personal",
                        "items": [
                            {
                                "id": "already-empty",
                                "label": "Already empty",
                                "action_ids": [],
                            },
                            {
                                "id": "newly-empty-parent",
                                "label": "Newly empty parent",
                                "items": [
                                    {
                                        "id": "target-child",
                                        "label": "Target child",
                                        "work_item_ref": {
                                            "source_id": "source",
                                            "relative_folder": "ISS-CAP40-target",
                                        },
                                    }
                                ],
                            },
                            {
                                "id": "mixed",
                                "label": "Mixed",
                                "targets": [
                                    {
                                        "type": "work_item",
                                        "source_id": "source",
                                        "relative_folder": "ISS-CAP40-target",
                                    },
                                    {"type": "action", "action_id": "keep-action"},
                                    {
                                        "type": "work_item",
                                        "source_id": "source",
                                        "relative_folder": "ISS-CAP40-other",
                                    },
                                ],
                            },
                            {
                                "id": "legacy-target",
                                "label": "Legacy target",
                                "work_item_ref": {
                                    "source_id": "source",
                                    "relative_folder": "ISS-CAP40-target",
                                },
                            },
                        ],
                    },
                    {
                        "id": "unchanged-root",
                        "label": "Unchanged root",
                        "items": [],
                    },
                ]
            },
        )

    def test_inspection_reports_every_personal_placement_without_writing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._seed_complete_configuration(root)
            before = {
                path: path.read_bytes()
                for path in self._paths(root)
            }

            report = self._call(inspect_work_item_organization, root)

            self.assertEqual(report.metadata_entries_removed, 1)
            self.assertEqual(report.context_memberships_removed, 1)
            self.assertEqual(report.preferred_references_removed, 1)
            self.assertEqual(report.palette_references_removed, 1)
            self.assertEqual(report.quick_action_references_removed, 3)
            self.assertEqual(report.quick_action_items_removed, 3)
            self.assertEqual(report.references_removed, 6)
            self.assertEqual(report.files_changed, 4)
            self.assertEqual(
                {path: path.read_bytes() for path in before},
                before,
            )

    def test_forget_removes_organization_and_keeps_external_content_and_roots(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._seed_complete_configuration(root)
            external_folder = root / "external-source" / self.reference.relative_folder
            external_folder.mkdir(parents=True)
            workbook = external_folder / f"{self.reference.relative_folder}.xlsx"
            workbook.write_bytes(b"external workbook")
            inbox = root / "inbox.json"
            inbox.write_bytes(b'{"items":["unchanged"]}\n')

            report = self._call(forget_work_item_organization, root)

            self.assertEqual(report.files_changed, 4)
            metadata, contexts, palette, commands = self._paths(root)
            self.assertEqual(
                set(self._read(metadata)["work_items"]),
                {"source/ISS-CAP40-other"},
            )
            context = self._read(contexts)["contexts"][0]
            self.assertEqual(
                context["work_item_refs"],
                [
                    {
                        "source_id": "source",
                        "relative_folder": "ISS-CAP40-other",
                    }
                ],
            )
            self.assertEqual(
                context["preferred_items"],
                [{"type": "action", "action_id": "keep-action"}],
            )
            self.assertEqual(
                self._read(palette)["context_item_slots"]["Delivery"],
                [{"type": "action", "action_id": "keep-action"}],
            )
            groups = self._read(commands)["groups"]
            self.assertEqual(
                [group["id"] for group in groups],
                ["personal", "unchanged-root"],
            )
            personal_items = groups[0]["items"]
            self.assertEqual(
                [item["id"] for item in personal_items],
                ["already-empty", "mixed"],
            )
            self.assertEqual(
                personal_items[1]["targets"],
                [
                    {"type": "action", "action_id": "keep-action"},
                    {
                        "type": "work_item",
                        "source_id": "source",
                        "relative_folder": "ISS-CAP40-other",
                    },
                ],
            )
            self.assertTrue(external_folder.is_dir())
            self.assertEqual(workbook.read_bytes(), b"external workbook")
            self.assertEqual(inbox.read_bytes(), b'{"items":["unchanged"]}\n')

    def test_forget_is_idempotent_and_missing_files_are_an_empty_state(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._seed_complete_configuration(root)
            self._call(forget_work_item_organization, root)
            after_first = {
                path: path.read_bytes()
                for path in self._paths(root)
            }

            second = self._call(forget_work_item_organization, root)

            self.assertEqual(second.files_changed, 0)
            self.assertEqual(second.references_removed, 0)
            self.assertEqual(second.metadata_entries_removed, 0)
            self.assertEqual(
                {path: path.read_bytes() for path in after_first},
                after_first,
            )

            empty_root = root / "missing"
            empty = self._call(forget_work_item_organization, empty_root)
            self.assertEqual(empty, type(empty)())
            self.assertFalse(empty_root.exists())

    def test_invalid_late_file_blocks_every_write_during_preflight(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._seed_complete_configuration(root)
            metadata, contexts, palette, commands = self._paths(root)
            before = {
                path: path.read_bytes()
                for path in (metadata, contexts, palette)
            }
            commands.write_text("not-json", encoding="utf-8")

            with self.assertRaises(WorkItemOrganizationError):
                self._call(forget_work_item_organization, root)

            self.assertEqual(
                {path: path.read_bytes() for path in before},
                before,
            )
            self.assertEqual(commands.read_text(encoding="utf-8"), "not-json")

    def test_invalid_palette_schema_is_wrapped_and_blocks_every_write(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._seed_complete_configuration(root)
            metadata, contexts, palette, commands = self._paths(root)
            before = {
                path: path.read_bytes()
                for path in (metadata, contexts, commands)
            }
            self._write(palette, {"pinned_action_ids": "not-a-list"})

            with self.assertRaises(WorkItemOrganizationError):
                self._call(forget_work_item_organization, root)

            self.assertEqual(
                {path: path.read_bytes() for path in before},
                before,
            )

    def test_failed_write_restores_all_attempted_files_as_exact_bytes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._seed_complete_configuration(root)
            paths = self._paths(root)
            # Use deliberately noncanonical bytes to prove rollback is not a
            # semantic JSON rewrite.
            contexts = paths[1]
            contexts.write_bytes(
                contexts.read_text(encoding="utf-8").replace("  ", "    ").encode("utf-8")
            )
            before = {path: path.read_bytes() for path in paths}
            calls = 0

            def fail_after_replacement(
                path: Path,
                payload: object,
                *,
                preserve_previous: bool = True,
            ) -> None:
                nonlocal calls
                calls += 1
                real_atomic_write_json(
                    path,
                    payload,
                    preserve_previous=preserve_previous,
                )
                if calls == 2:
                    raise OSError("injected write failure")

            with patch(
                "context_palette.work_item_organization.atomic_write_json",
                side_effect=fail_after_replacement,
            ):
                with self.assertRaises(WorkItemOrganizationError) as captured:
                    self._call(forget_work_item_organization, root)

            self.assertTrue(captured.exception.rollback_completed)
            self.assertEqual(
                {path: path.read_bytes() for path in paths},
                before,
            )


if __name__ == "__main__":
    unittest.main()
