import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_palette.actions import (
    Action,
    ActionError,
    append_action,
    build_url,
    draft_build_url_action,
    draft_copy_text_action,
    edited_copy_text_action,
    execute_action,
    expand_template,
    load_actions,
    list_to_comma_separated,
    load_combined_actions,
    search_actions,
    transform_text,
    trusted_action,
    update_action,
)


class ActionTests(unittest.TestCase):
    def test_workspace_case_transformations(self):
        self.assertEqual(transform_text("AbC É", "lowercase"), "abc é")
        self.assertEqual(transform_text("AbC é", "uppercase"), "ABC É")

    def test_workspace_normalize_spaces_preserves_line_breaks(self):
        value = "one   two\nthree\t\tfour"

        self.assertEqual(transform_text(value, "normalize_spaces"), "one two\nthree four")

    def test_workspace_prefix_suffix_applies_to_every_line(self):
        value = "one\n\ntwo\n"

        self.assertEqual(
            transform_text(value, "prefix_suffix_lines", prefix="[", suffix="]"),
            "[one]\n[]\n[two]\n",
        )

    def test_workspace_remove_duplicate_lines_preserves_order_and_final_newline(self):
        value = "one\r\ntwo\r\none\r\n"

        self.assertEqual(transform_text(value, "remove_duplicate_lines"), "one\r\ntwo\r\n")

    def test_workspace_transform_rejects_unknown_operation(self):
        with self.assertRaises(ActionError):
            transform_text("text", "unknown")

    def test_shared_product_lookup_actions_build_valid_urls(self):
        actions = {action.id: action for action in load_actions(ROOT / "data" / "actions.json")}
        expected = {
            "colruyt-open-product": "https://www.colruyt.be/nl/producten/5331",
            "product-lookup-bioplanet": "https://www.bioplanet.be/nl/producten/5331",
            "product-lookup-productinfoscreen": (
                "https://productinfoscreen.colruyt.int/productinfoscreen/consultArticle.xhtml"
                "?technicalArticleNumber=5331"
            ),
            "product-lookup-fic": "https://fic.colruytgroup.com/productinfo/nl/algc/5331",
            "product-lookup-rti": "https://rti.colruytgroup.com/nl/product-info/5331",
            "product-lookup-solucious": "https://www.solucious.be/5331",
            "product-lookup-myproduct-retail-article": (
                "https://myproduct.colruyt.int/#/product-entities/RETAILARTICLE/5331"
            ),
            "product-lookup-myproduct-base-product": (
                "https://myproduct.colruyt.int/#/product-entities/RETAILBASEPRODUCT/5331"
            ),
            "product-lookup-myproduct-gtin": (
                "https://myproduct.colruyt.int/#/product-entities/RETAILTRADEITEM/5331"
            ),
            "product-lookup-myproduct-pss": (
                "https://myproduct.colruyt.int/#/product-entities/PRODUCTSPECIFICATIONSHEET/5331"
            ),
            "product-lookup-myproduct-any-id": (
                "https://myproduct.colruyt.int/#/product-entities?productId=5331"
            ),
        }

        self.assertTrue(expected.keys() <= actions.keys())
        for action_id, expected_url in expected.items():
            action = actions[action_id]
            self.assertEqual(action.type, "build_url_selection_open")
            self.assertEqual(build_url(action.value, "5331"), expected_url)

    def test_draft_build_url_action_validates_and_preserves_metadata(self):
        action = draft_build_url_action(
            title="Open archive",
            technology="Browser",
            task="Archive lookup",
            context="Archives",
            template="http://linkto/archives/{id_url}",
        )

        self.assertEqual(action.type, "build_url_selection_open")
        self.assertEqual(action.value, "http://linkto/archives/{id_url}")
        self.assertEqual(action.technology, "Browser")
        self.assertEqual(action.state, "Draft")

    def test_draft_build_url_action_rejects_template_without_input_placeholder(self):
        with self.assertRaises(ActionError):
            draft_build_url_action(
                title="Open archive",
                context="Archives",
                template="http://linkto/archives/",
            )

    def test_load_actions_filters_archived_items(self):
        path = self._write_actions(
            [
                {
                    "id": "draft",
                    "title": "Draft action",
                    "context": "General",
                    "type": "copy_text",
                    "value": "hello",
                    "state": "Draft",
                },
                {
                    "id": "archived",
                    "title": "Archived action",
                    "context": "General",
                    "type": "copy_text",
                    "value": "old",
                    "state": "Archived",
                },
            ]
        )

        actions = load_actions(path)

        self.assertEqual([action.id for action in actions], ["draft"])

    def test_combined_actions_allow_missing_local_file(self):
        shared = self._write_actions(
            [{"id": "shared", "title": "Shared", "context": "General", "type": "copy_text", "value": "x"}]
        )
        actions, local_ids = load_combined_actions(shared, shared.parent / "missing.json")

        self.assertEqual([action.id for action in actions], ["shared"])
        self.assertEqual(local_ids, set())

    def test_combined_actions_reject_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "shared.json"
            local = Path(directory) / "local.json"
            payload = {
                "actions": [
                    {"id": "same", "title": "Same", "context": "General", "type": "copy_text", "value": "x"}
                ]
            }
            shared.write_text(json.dumps(payload), encoding="utf-8")
            local.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ActionError):
                load_combined_actions(shared, local)

    def test_load_actions_rejects_case_insensitive_duplicate_ids(self):
        path = self._write_actions(
            [
                {"id": "Lookup", "title": "One", "context": "General", "type": "copy_text", "value": "x"},
                {"id": "lookup", "title": "Two", "context": "General", "type": "copy_text", "value": "y"},
            ]
        )

        with self.assertRaises(ActionError):
            load_actions(path)

    def test_combined_actions_reject_case_insensitive_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / "shared.json"
            local = Path(directory) / "local.json"
            shared.write_text(
                json.dumps({"actions": [{"id": "Lookup", "title": "One", "context": "General", "type": "copy_text", "value": "x"}]}),
                encoding="utf-8",
            )
            local.write_text(
                json.dumps({"actions": [{"id": "lookup", "title": "Two", "context": "General", "type": "copy_text", "value": "y"}]}),
                encoding="utf-8",
            )

            with self.assertRaises(ActionError):
                load_combined_actions(shared, local)

    def test_search_matches_context_and_title(self):
        actions = [
            Action("email", "Copy greeting", "Email", "copy_text", "Hello"),
            Action("database", "Copy SELECT", "Database", "copy_text", "SELECT"),
        ]

        self.assertEqual([action.id for action in search_actions(actions, "email greeting")], ["email"])
        self.assertEqual([action.id for action in search_actions(actions, "select")], ["database"])

    def test_compact_display_separates_command_and_hides_context(self):
        action = Action(
            "item",
            "Open selected product",
            "Colruyt",
            "open_url",
            "https://example.com",
            technology="Browser",
            task="Product lookup",
        )

        self.assertEqual(action.compact_display_text, "Open → selected product")
        self.assertIn("Browser", action.display_text)
        self.assertEqual(search_actions([action], "browser product lookup"), [action])

    def test_compact_display_infers_command_when_title_has_no_verb(self):
        action = Action("settings", "Quick Settings", "Windows", "copy_text", "Win + A")

        self.assertEqual(action.compact_display_text, "Copy → Quick Settings")

    def test_execute_copy_text_uses_clipboard_callback(self):
        copied = []
        action = Action("copy", "Copy greeting", "Email", "copy_text", "Hello")

        message = execute_action(action, clipboard_setter=copied.append)

        self.assertEqual(copied, ["Hello"])
        self.assertIn("Copied", message)

    def test_copy_text_expands_clipboard_and_date_variables(self):
        action = Action("dynamic", "Dynamic", "General", "copy_text", "%pptxt% - %YYYY%")
        copied = []

        execute_action(
            action,
            clipboard_setter=copied.append,
            clipboard_getter=lambda: "Selected text",
        )

        self.assertEqual(copied, [f"Selected text - {datetime.now():%Y}"])

    def test_expand_template_supports_qtp_date_url_and_newline_aliases(self):
        moment = datetime(2026, 7, 11, 9, 5, 3)

        result = expand_template(
            "%YYYY%-%MM%-%DD% %hh%:%mm%\\n%cpy_txt_urlencode%",
            clipboard="a value & more",
            now=moment,
        )

        self.assertEqual(result, "2026-07-11 09:05\na%20value%20%26%20more")

    def test_expand_template_supports_portable_environment_paths(self):
        with patch.dict("os.environ", {"PROJECT_ROOT": "C:\\Portable\\Project"}):
            result = expand_template("%PROJECT_ROOT%\\docs")

        self.assertEqual(result, "C:\\Portable\\Project\\docs")

    def test_execute_open_url_uses_opener_callback(self):
        opened = []
        action = Action("docs", "Open docs", "General", "open_url", "https://example.com")

        message = execute_action(action, opener=opened.append)

        self.assertEqual(opened, [action])
        self.assertIn("Opened", message)

    def test_open_target_without_clipboard_tokens_does_not_read_clipboard(self):
        opened = []
        action = Action("config", "Edit config", "Configuration", "open_file", "C:\\config.json")

        execute_action(
            action,
            clipboard_getter=lambda: (_ for _ in ()).throw(RuntimeError("not text")),
            opener=opened.append,
        )

        self.assertEqual(opened[0].value, "C:\\config.json")

    def test_build_url_inserts_and_url_encodes_identifier(self):
        result = build_url(
            "https://example.com/items/{id}?search={id_url}",
            " ABC 12 ",
        )

        self.assertEqual(result, "https://example.com/items/ABC 12?search=ABC%2012")

    def test_build_url_rejects_empty_identifier_and_missing_placeholder(self):
        with self.assertRaises(ActionError):
            build_url("https://example.com/{id}", "  ")
        with self.assertRaises(ActionError):
            build_url("https://example.com/items", "123")

    def test_execute_build_url_can_copy_or_open(self):
        copied = []
        opened = []
        copy_action = Action(
            "copy-url", "Copy item URL", "Work", "build_url_copy", "https://example.com/{id_url}"
        )
        open_action = Action(
            "open-url", "Open item URL", "Work", "build_url_open", "https://example.com/{id_url}"
        )

        execute_action(copy_action, input_provider=lambda _prompt: "ABC 12", clipboard_setter=copied.append)
        execute_action(open_action, input_provider=lambda _prompt: "ABC 12", opener=opened.append)

        self.assertEqual(copied, ["https://example.com/ABC%2012"])
        self.assertEqual(opened[0].type, "open_url")
        self.assertEqual(opened[0].value, "https://example.com/ABC%2012")

    def test_execute_build_url_from_selection_copies_and_opens(self):
        copied = []
        opened = []
        action = Action(
            "product",
            "Open product",
            "Colruyt",
            "build_url_selection_open",
            "https://www.colruyt.be/nl/producten/{id_url}",
        )

        message = execute_action(
            action,
            selected_text=" 5331 ",
            clipboard_setter=copied.append,
            opener=opened.append,
        )

        self.assertEqual(copied, ["https://www.colruyt.be/nl/producten/5331"])
        self.assertEqual(opened[0].value, "https://www.colruyt.be/nl/producten/5331")
        self.assertIn("Copied", message)

    def test_execute_build_url_uses_clipboard_when_selection_is_unavailable(self):
        copied = []
        opened = []
        action = Action(
            "archive",
            "Open archive",
            "Archives",
            "build_url_selection_open",
            "http://linkto/archives/{id_url}",
        )

        execute_action(
            action,
            clipboard_getter=lambda: "ABC 123",
            clipboard_setter=copied.append,
            opener=opened.append,
        )

        self.assertEqual(copied, ["http://linkto/archives/ABC%20123"])
        self.assertEqual(opened[0].value, "http://linkto/archives/ABC%20123")

    def test_list_to_comma_separated_supports_plain_and_sql_strings(self):
        self.assertEqual(list_to_comma_separated("one\ntwo\nthree"), "one, two, three")
        self.assertEqual(
            list_to_comma_separated("one\nO'Brien", sql_strings=True),
            "'one', 'O''Brien'",
        )

    def test_execute_list_transform_updates_output_and_clipboard(self):
        copied = []
        output = []
        action = Action("csv", "To SQL list", "Database", "transform_list_csv", "sql_strings")

        execute_action(
            action,
            input_text="alpha\nbeta",
            clipboard_setter=copied.append,
            output_setter=output.append,
        )

        self.assertEqual(output, ["'alpha', 'beta'"])
        self.assertEqual(copied, output)

    def test_workspace_template_updates_output_and_clipboard(self):
        copied = []
        output = []
        action = Action("template", "Template", "Time", "workspace_template", "Date: %YYYY%")

        execute_action(action, clipboard_setter=copied.append, output_setter=output.append)

        self.assertEqual(copied, output)
        self.assertRegex(output[0], r"Date: \d{4}")

    def test_window_layout_action_uses_constrained_runner(self):
        received = []
        action = Action("layout", "Arrange", "Developing", "window_layout", "layout.json")

        message = execute_action(action, window_layout_runner=lambda value: received.append(value) or "Done")

        self.assertEqual(received, ["layout.json"])
        self.assertEqual(message, "Done")

    def test_window_snapshot_action_uses_constrained_runner(self):
        received = []
        action = Action("snapshot", "Restore", "Work", "restore_window_snapshot", "snapshot.json")

        message = execute_action(
            action,
            window_snapshot_runner=lambda value: received.append(value) or "Restored",
        )

        self.assertEqual(received, ["snapshot.json"])
        self.assertEqual(message, "Restored")

    def test_append_draft_copy_text_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            action = draft_copy_text_action(title=" Greeting ", context=" Email ", value=" Hello ")

            append_action(path, action)
            loaded = load_actions(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "Greeting")
        self.assertEqual(loaded[0].context, "Email")
        self.assertEqual(loaded[0].value, "Hello")
        self.assertEqual(loaded[0].state, "Draft")

    def test_append_action_rejects_duplicate_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            action = Action("same", "One", "General", "copy_text", "one")
            append_action(path, action)

            with self.assertRaises(ActionError):
                append_action(path, Action("SAME", "Two", "General", "copy_text", "two"))

    def test_draft_copy_text_action_accepts_technology_and_task(self):
        action = draft_copy_text_action(
            title="Open item",
            technology="Browser",
            task="Product lookup",
            context="Colruyt",
            value="5331",
        )

        self.assertEqual(
            action.display_text,
            "Browser > Product lookup > Colruyt > Open item",
        )

    def test_update_draft_copy_text_action(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "actions.json"
            action = draft_copy_text_action(title="Old", context="General", value="Old text")
            append_action(path, action)

            updated = edited_copy_text_action(
                action,
                title=" New ",
                context=" Email ",
                value=" New text ",
            )
            update_action(path, updated)
            loaded = load_actions(path)

        self.assertEqual(loaded[0].id, action.id)
        self.assertEqual(loaded[0].title, "New")
        self.assertEqual(loaded[0].context, "Email")
        self.assertEqual(loaded[0].value, "New text")

    def test_only_draft_copy_text_actions_can_be_edited(self):
        action = Action("trusted", "Trusted", "General", "copy_text", "Text", state="Trusted")

        with self.assertRaises(ActionError):
            edited_copy_text_action(action, title="New", context="General", value="Text")

    def test_draft_action_can_be_marked_trusted(self):
        action = Action("draft", "Draft", "General", "copy_text", "Text", state="Draft")

        trusted = trusted_action(action)

        self.assertEqual(trusted.id, action.id)
        self.assertEqual(trusted.state, "Trusted")

    def test_only_draft_actions_can_be_marked_trusted(self):
        action = Action("trusted", "Trusted", "General", "copy_text", "Text", state="Trusted")

        with self.assertRaises(ActionError):
            trusted_action(action)

    def test_load_action_supports_fixed_launch_arguments(self):
        path = self._write_actions(
            [
                {
                    "id": "vscode",
                    "title": "Open in VS Code",
                    "context": "Developing",
                    "type": "launch_app",
                    "value": "C:\\Program Files\\App\\App.exe",
                    "arguments": ["C:\\Project"],
                    "working_directory": "C:\\Project",
                    "state": "Draft",
                }
            ]
        )

        action = load_actions(path)[0]

        self.assertEqual(action.arguments, ("C:\\Project",))
        self.assertEqual(action.working_directory, "C:\\Project")

    def test_load_action_supports_url_builder_types(self):
        path = self._write_actions(
            [
                {
                    "id": "item-url",
                    "title": "Open item",
                    "context": "Work",
                    "type": "build_url_open",
                    "value": "https://example.com/items/{id_url}",
                    "state": "Draft",
                }
            ]
        )

        self.assertEqual(load_actions(path)[0].type, "build_url_open")

    def test_unsupported_action_type_is_rejected_when_loading(self):
        path = self._write_actions(
            [
                {
                    "id": "bad",
                    "title": "Bad action",
                    "context": "General",
                    "type": "shell",
                    "value": "dir",
                    "state": "Draft",
                }
            ]
        )

        with self.assertRaises(ActionError):
            load_actions(path)

    def _write_actions(self, actions):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "actions.json"
        path.write_text(json.dumps({"actions": actions}), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
