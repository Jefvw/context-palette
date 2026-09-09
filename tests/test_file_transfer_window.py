from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock

from context_palette.file_transfer import (
    FileTransferError,
    FileTransferUnexpectedError,
)
from context_palette.file_transfer_window import FileTransferWindow


class FakeCoordinator:
    def __init__(self) -> None:
        self.running = False
        self.phase: str | None = None
        self.calls: list[dict[str, object]] = []
        self.stop_requests = 0
        self._callback = None
        self._completion = None

    def start_plan(
        self,
        workspace_text,
        destination_folder,
        allow_overwrite,
        on_complete,
    ) -> bool:
        if self.running:
            return False
        self.running = True
        self.phase = "plan"
        self.calls.append(
            {
                "phase": "plan",
                "workspace_text": workspace_text,
                "destination_folder": destination_folder,
                "allow_overwrite": allow_overwrite,
            }
        )
        self._callback = on_complete
        return True

    def start_execute(self, plan, on_complete) -> bool:
        if self.running:
            return False
        self.running = True
        self.phase = "execute"
        self.calls.append({"phase": "execute", "plan": plan})
        self._callback = on_complete
        return True

    def request_stop(self) -> None:
        self.stop_requests += 1

    def complete(self, result=None, error=None) -> None:
        self._completion = (result, error)

    def drain(self) -> bool:
        if self._completion is None:
            return False
        result, error = self._completion
        callback = self._callback
        self._completion = None
        self._callback = None
        self.running = False
        self.phase = None
        callback(result, error)
        return True


def transfer_item(
    source: Path,
    destination: Path,
    disposition: str = "create",
    *,
    renamed: bool = False,
    original_conflict: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        source_path=source,
        destination_path=destination,
        disposition=disposition,
        renamed=renamed,
        original_conflict=original_conflict,
    )


def transfer_plan(
    destination: Path,
    *items: SimpleNamespace,
    allow_overwrite: bool = False,
    requires_review: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        destination_folder=destination,
        allow_overwrite=allow_overwrite,
        items=items,
        fingerprint="reviewed-plan",
        create_count=sum(item.disposition == "create" for item in items),
        replace_count=sum(item.disposition == "replace" for item in items),
        renamed_count=sum(item.renamed for item in items),
        skipped_count=sum(item.disposition == "skip_same" for item in items),
        bytes_total=123,
        requires_review=requires_review,
    )


def transfer_result(
    destination: Path,
    *,
    created: tuple[Path, ...] = (),
    replaced: tuple[Path, ...] = (),
    skipped: tuple[Path, ...] = (),
    failures: tuple[SimpleNamespace, ...] = (),
    stopped: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        destination_folder=destination,
        created=created,
        replaced=replaced,
        skipped=skipped,
        failures=failures,
        bytes_copied=123,
        stopped=stopped,
    )


class FileTransferWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("1x1+0+0")
        self.root.update_idletasks()
        self.addCleanup(self.root.destroy)
        self.original_scaling = float(self.root.tk.call("tk", "scaling"))
        self.addCleanup(
            lambda: self.root.tk.call("tk", "scaling", self.original_scaling)
        )

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.destination = self.base / "destination"
        self.destination.mkdir()
        self.source = self.base / "report.txt"
        self.source.write_bytes(b"source-content")
        self.coordinator = FakeCoordinator()
        self.status_setter = Mock()
        self.folder_opener = Mock()
        self.on_success = Mock()
        self.windows: list[FileTransferWindow] = []

    def _window(self, *, workspace_text: str | None = None) -> FileTransferWindow:
        window = FileTransferWindow(
            self.root,
            workspace_text=workspace_text or str(self.source),
            destination_folder=self.destination,
            destination_label="Reports",
            status_setter=self.status_setter,
            coordinator=self.coordinator,  # type: ignore[arg-type]
            folder_opener=self.folder_opener,
            on_success=self.on_success,
        )
        self.windows.append(window)
        self.addCleanup(self._close, window)
        self.root.update()
        return window

    def _close(self, window: FileTransferWindow) -> None:
        self.coordinator.running = False
        self.coordinator.phase = None
        self.coordinator._callback = None
        self.coordinator._completion = None
        if not window._closed and window.window.winfo_exists():
            window.close()

    def _complete(self, window: FileTransferWindow, result=None, error=None) -> None:
        self.coordinator.complete(result, error)
        if window._poll_after_id is not None:
            window.window.after_cancel(window._poll_after_id)
            window._poll_after_id = None
        window._poll()
        self.root.update()

    def test_review_is_visible_with_hidden_palette_and_can_be_shown_after_owner_hides(self) -> None:
        self.root.withdraw()
        window = self._window()
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertTrue(window.window.winfo_viewable())
        self.assertEqual(str(window.window.transient()), "")
        self.assertEqual(self.coordinator.calls[-1]["phase"], "plan")
        self.root.deiconify()
        self.root.update()
        window.show()
        self.assertEqual(str(window.window.transient()), str(self.root))
        self.root.withdraw()
        self.root.update()
        window.show()
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertTrue(window.window.winfo_viewable())

    def test_conflict_free_destination_is_the_only_confirmation_and_sources_stay_unchanged(self) -> None:
        original = self.source.read_bytes()
        window = self._window()
        self.assertEqual(self.coordinator.calls[-1]["phase"], "plan")
        self.assertFalse(self.coordinator.calls[-1]["allow_overwrite"])

        plan = transfer_plan(
            self.destination,
            transfer_item(self.source, self.destination / self.source.name),
        )
        self._complete(window, plan)

        self.assertEqual(self.coordinator.calls[-1], {"phase": "execute", "plan": plan})
        self.assertEqual(window.view_state, "executing")
        self.assertFalse(window.primary_button.winfo_ismapped())
        self.assertTrue(window.close_button.instate(["disabled"]))

        result = transfer_result(
            self.destination,
            created=(self.destination / self.source.name,),
        )
        self._complete(window, result)

        self.assertEqual(window.view_state, "result")
        self.assertEqual(self.source.read_bytes(), original)
        self.on_success.assert_called_once_with(self.destination)
        self.assertIn("Source files were not changed", window.status_var.get())
        self.assertFalse(window.primary_button.winfo_ismapped())

    def test_conflict_review_replans_overwrite_and_has_one_effect_labelled_button(self) -> None:
        sources = tuple(self.base / f"source-{number}.txt" for number in range(3))
        for source in sources:
            source.write_text(source.name, encoding="utf-8")
        window = self._window(workspace_text="\n".join(str(path) for path in sources))
        suffix_plan = transfer_plan(
            self.destination,
            transfer_item(
                sources[0],
                self.destination / "source-0(1).txt",
                renamed=True,
                original_conflict=True,
            ),
            transfer_item(sources[1], self.destination / sources[1].name),
            transfer_item(sources[2], self.destination / sources[2].name),
            requires_review=True,
        )
        self._complete(window, suffix_plan)

        self.assertEqual(window.view_state, "review")
        assert window.overwrite_checkbutton is not None
        self.assertFalse(window.overwrite_checkbutton.instate(["selected"]))
        self.assertEqual(window.primary_button.cget("text"), "Copy 3 files")
        self.assertEqual(
            [call["phase"] for call in self.coordinator.calls],
            ["plan"],
        )
        assert window.review_text is not None
        self.assertIn("source-0(1).txt", window.review_text.get("1.0", "end-1c"))

        window.overwrite_checkbutton.invoke()
        self.assertTrue(window.allow_overwrite)
        self.assertEqual(self.coordinator.calls[-1]["phase"], "plan")
        self.assertTrue(self.coordinator.calls[-1]["allow_overwrite"])

        overwrite_plan = transfer_plan(
            self.destination,
            transfer_item(
                sources[0],
                self.destination / sources[0].name,
                "replace",
                original_conflict=True,
            ),
            transfer_item(sources[1], self.destination / sources[1].name),
            transfer_item(sources[2], self.destination / sources[2].name),
            allow_overwrite=True,
            requires_review=True,
        )
        self._complete(window, overwrite_plan)
        self.assertEqual(
            window.primary_button.cget("text"),
            "Replace 1 and copy 2 files",
        )

        window.primary_button.invoke()
        self.assertEqual(self.coordinator.calls[-1], {"phase": "execute", "plan": overwrite_plan})
        self.assertEqual(
            [call["phase"] for call in self.coordinator.calls],
            ["plan", "plan", "execute"],
        )

    def test_same_file_destination_is_a_clear_no_effect_state(self) -> None:
        window = self._window()
        plan = transfer_plan(
            self.destination,
            transfer_item(
                self.source,
                self.source,
                "skip_same",
                original_conflict=True,
            ),
            requires_review=True,
        )

        self._complete(window, plan)

        self.assertEqual(window.view_state, "no_effect")
        self.assertIsNone(window.overwrite_checkbutton)
        self.assertFalse(window.primary_button.winfo_ismapped())
        self.assertTrue(window.open_folder_button.winfo_ismapped())
        self.assertEqual(
            [call["phase"] for call in self.coordinator.calls],
            ["plan"],
        )
        content = " ".join(_widget_texts(window.content)).casefold()
        self.assertIn("nothing to copy", content)
        self.assertIn("will not overwrite a file with itself", content)
        self.assertIn("already in the destination", window.status_var.get().casefold())

    def test_stop_and_partial_result_report_exact_effects_without_retry(self) -> None:
        original = self.source.read_bytes()
        window = self._window()
        plan = transfer_plan(
            self.destination,
            transfer_item(self.source, self.destination / self.source.name),
        )
        self._complete(window, plan)

        self.assertTrue(window.stop_button.winfo_ismapped())
        window.stop_button.invoke()
        self.assertEqual(self.coordinator.stop_requests, 1)
        self.assertTrue(window.stop_button.instate(["disabled"]))
        self.assertFalse(window.close())
        self.assertTrue(window.window.winfo_exists())

        created = self.destination / "report.txt"
        pending = self.destination / "pending.txt"
        failure = SimpleNamespace(
            source_path=self.source,
            destination_path=pending,
            message="The destination became unavailable.",
        )
        result = transfer_result(
            self.destination,
            created=(created,),
            failures=(failure,),
            stopped=True,
        )
        self._complete(window, result)

        self.assertEqual(window.view_state, "result")
        assert window.result_text is not None
        details = window.result_text.get("1.0", "end-1c")
        self.assertIn(str(created), details)
        self.assertIn(str(pending), details)
        self.assertIn("The destination became unavailable.", details)
        self.assertFalse(window.primary_button.winfo_ismapped())
        self.assertNotIn("retry", " ".join(_widget_texts(window.content)).casefold())
        self.assertIn("no automatic rollback or retry", window.status_var.get().casefold())
        self.assertEqual(self.source.read_bytes(), original)

    def test_known_execution_error_reports_no_effect_instead_of_unknown(self) -> None:
        window = self._window()
        plan = transfer_plan(
            self.destination,
            transfer_item(self.source, self.destination / self.source.name),
        )
        self._complete(window, plan)

        self._complete(window, None, FileTransferError("Destination unavailable."))

        self.assertEqual(window.view_state, "pre_effect_error")
        self.assertIn("No files were copied", window.status_var.get())
        self.assertNotIn(
            "outcome unknown",
            " ".join(_widget_texts(window.content)).casefold(),
        )

    def test_unexpected_execution_error_requires_destination_inspection(self) -> None:
        window = self._window()
        plan = transfer_plan(
            self.destination,
            transfer_item(self.source, self.destination / self.source.name),
        )
        self._complete(window, plan)

        self._complete(
            window,
            None,
            FileTransferUnexpectedError("Unexpected local error."),
        )

        self.assertEqual(window.view_state, "unknown")
        content = " ".join(_widget_texts(window.content)).casefold()
        self.assertIn("outcome unknown", content)
        self.assertIn("inspect the destination", content)
        self.assertIn("no rollback or automatic retry", window.status_var.get().casefold())

    def test_fixed_footer_remains_visible_at_100_125_and_150_percent_scaling(self) -> None:
        for scaling in (1.0, 1.25, 1.5):
            with self.subTest(scaling=scaling):
                self.root.tk.call("tk", "scaling", scaling)
                self.coordinator = FakeCoordinator()
                window = self._window()
                many_items = tuple(
                    transfer_item(
                        self.source,
                        self.destination / f"report({number}).txt",
                        renamed=True,
                        original_conflict=True,
                    )
                    for number in range(30)
                )
                self._complete(
                    window,
                    transfer_plan(
                        self.destination,
                        *many_items,
                        requires_review=True,
                    ),
                )
                window.window.geometry("780x600+20+20")
                self.root.update()

                bottom = window.window.winfo_rooty() + window.window.winfo_height()
                self.assertTrue(window.footer.winfo_ismapped())
                self.assertTrue(window.primary_button.winfo_ismapped())
                self.assertTrue(window.close_button.winfo_ismapped())
                self.assertLessEqual(
                    window.footer.winfo_rooty() + window.footer.winfo_height(),
                    bottom,
                )
                self.assertLessEqual(
                    window.status_label.winfo_rooty() + window.status_label.winfo_height(),
                    bottom,
                )
                window.close()


def _widget_texts(widget: tk.Misc) -> list[str]:
    values: list[str] = []
    for child in widget.winfo_children():
        try:
            value = child.cget("text")
        except tk.TclError:
            value = ""
        if value:
            values.append(str(value))
        values.extend(_widget_texts(child))
    return values


if __name__ == "__main__":
    unittest.main()
