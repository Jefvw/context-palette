# Change guide

Use this guide to find the smallest safe change path. Current boundaries are
described in [Architecture](ARCHITECTURE.md); repository rules remain in
[AGENTS.md](../AGENTS.md).

## Before editing

The owner accepts the current Edge score stop at Save As for manual filename
and folder choice (2026-09-15). The subsequent owner request removes the error
popup for this handoff only: the exact `filename_missing` helper outcome closes
the progress window after cleanup; other errors remain visible. Do not resume
automatic-save repair without a new request. The generated Action catalogue
describes the supported score types and Save As fallback; Help and Testing detail this
accepted manual finish and its limitations.

For future requested Edge score PDF changes, use `action_types.py`, `actions.py`,
`action_preview.py`, and `launcher.py` for the constrained saved Action and its
manual runner; keep `edge_score_pdf.py` / `.ps1` and
`edge_score_pdf_window.py` as the site-specific Windows/file boundary. Check
configured Quick-action placement, Context slots, Drop/AI/sequence exclusions,
and ordinary bulk import/update. The allowed Ultimate Guitar URL type must agree
with the inspected document title: retain the existing Official shape and only
the `tabs.ultimate-guitar.com/tab/{artist}/{song}-guitar-pro-{digits}` Guitar
Pro shape. Do not broaden this into normal text tabs, chords, arbitrary webpages,
or a general browser workflow. Run the Edge score, Action type, Action preview,
launcher, configuration, bulk, and complete checks. Native control selection and
actual PDF content still require Windows UAT.

For webpage-to-PDF changes, start with `src/context_palette/webpage_pdf.py`
(browser and file boundary), `webpage_pdf_window.py` (worker/result window),
and `launcher.py` / `resource_operations.py` (Send-to routing). Run
`tests.test_webpage_pdf`, `tests.test_webpage_pdf_window` and
`tests.test_webpage_pdf_integration`, then the complete check. Keep the
Windows content-fidelity checks in [Testing](TESTING.md) separate from mocks.

1. Inspect `git status --short` and preserve existing work.
2. Confirm the behavior in code and its focused tests.
3. Keep personal files under `data/local_*`, `data/inbox.json`,
   `data/palette.json`, logs, and backups out of commits.
4. Run focused tests while editing and `.\develop-context-palette.bat` once
   after the final code change.

## Common change paths

| Goal | Primary owner | Usually update | Focused verification |
| --- | --- | --- | --- |
| Connect a resource automation to Run, Send to or Drop | `resource_operations.py` for immutable requests and dispatch; `launcher.py` for adapters; `actions.py`/`action_types.py` for saved Action definitions; `drop_action.py` for explicit Drop eligibility | `tests/test_resource_operations.py`, `tests/test_resource_operation_integration.py`, execution-preview and drop tests; Architecture, Data model, Decisions, Help, and Changelog. Preserve domain reviews and never dispatch from Preview. | `.\python-context-palette.bat -m unittest tests.test_resource_operations tests.test_resource_operation_integration tests.test_execution_preview tests.test_drop_action tests.test_launcher_enhancements` |
| Add or change an Input / Output transformation | `src/context_palette/actions.py` for the pure algorithm; `src/context_palette/workspace_transforms.py` for its label, group, operation key, and success message | `tests/test_actions.py`, `tests/test_workspace_transforms.py`, `docs/HELP.md`, `CHANGELOG.md` | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_workspace_transforms tests.test_launcher_smoke` |
| Change text-file transformation, preview provenance, or save-back behavior | `src/context_palette/actions.py` for bounded decoding, transformation, stale-source checks, and atomic writes; `src/context_palette/workspace_panel.py` for review controls | `tests/test_actions.py`, `tests/test_launcher_smoke.py`, Architecture, Help, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_launcher_smoke` |
| Change Input / Output widgets, menus, selection, undo, or clipboard behavior | `src/context_palette/workspace_panel.py` | `tests/test_launcher_smoke.py`, `docs/ARCHITECTURE.md`; Help and Changelog when visible behavior changes | `.\python-context-palette.bat -m unittest tests.test_launcher_smoke tests.test_actions` |
| Change outbound Send to file parsing, collision policy, copying, or destination routing | `src/context_palette/file_transfer.py` for pure planning/publication and coordinator behavior; `file_transfer_window.py` for attended review/result UI; `workspace_panel.py` and `launcher.py` for destination menus and orchestration | `tests/test_file_transfer.py`, `tests/test_file_transfer_window.py`, launcher interaction/smoke tests; Help, Architecture, Decisions, Testing, MVP, and Changelog | `.\python-context-palette.bat -m unittest tests.test_file_transfer tests.test_file_transfer_window tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change the constrained Input / Output VS Code opener | `src/context_palette/vscode_integration.py` for exact-path validation and registered-protocol handoff; `launcher.py` for the separate **Open with** menu route | `tests/test_vscode_integration.py`, launcher interaction/smoke and UI-mockup tests; Help, Architecture, Decisions, Testing, MVP, and Changelog | `.\python-context-palette.bat -m unittest tests.test_vscode_integration tests.test_launcher_interactions tests.test_launcher_smoke tests.test_ui_mockups` |
| Change drag-and-drop intake | `drop_extraction.py` for pure normalization; `drop_adapter.py` for Tcl decoding and bounded shortcut resolution; `drop_target_window.py` for the isolated Toplevel; `launcher.py` and `workspace_panel.py` for safe placement | Drop extraction/adapter/window tests, launcher interaction/smoke tests, Help, Architecture, Decisions, Testing, requirements/setup documentation, and Changelog | `.\python-context-palette.bat -m unittest tests.test_drop_extraction tests.test_drop_adapter tests.test_drop_target_window tests.test_launcher_interactions tests.test_launcher_smoke tests.test_windows_scripts` |
| Change OCR sources, limits, provider, setup, or result handling | `src/context_palette/ocr.py` for bounded decoding/provider behavior; `workspace_panel.py` and `launcher.py` for the UI flow; `requirements-ocr.txt` and OCR/offline setup scripts for deployment | `tests/test_ocr.py`, launcher interaction/smoke tests, `tests/test_windows_scripts.py`, `docs/OCR_SETUP.md`, Help, Architecture, Decisions, Testing, and Changelog | `.\python-context-palette.bat -m unittest tests.test_ocr tests.test_launcher_interactions tests.test_launcher_smoke tests.test_windows_scripts` |
| Change Find, result-list, Context scope, or filter widgets | `src/context_palette/action_discovery_panel.py`, `src/context_palette/searchable_selection.py` | `tests/test_launcher_smoke.py`, `tests/test_searchable_selection.py`, `docs/ARCHITECTURE.md` | `.\python-context-palette.bat -m unittest tests.test_launcher_smoke tests.test_launcher_interactions tests.test_searchable_selection` |
| Change the inert real-Tk visual baseline | `src/context_palette/ui_mockups.py`; do not import production state or effects | `tests/test_ui_mockups.py`, `docs/UI_MOCKUPS.md`, the UI/UX audit, and Decisions when the proposed product model changes | `.\python-context-palette.bat -m unittest tests.test_ui_mockups tests.test_windows_scripts` |
| Change pre-Run Action input/effect explanations | `src/context_palette/action_preview.py`; `action_types.py` remains the semantic catalogue | `launcher.py`, `tests/test_action_preview.py`, launcher smoke tests, Help, Architecture, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_preview tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change search, ranking, Context membership, or context-shortcut policy | `src/context_palette/actions.py`, `src/context_palette/focus_model.py`, or `src/context_palette/palette_state.py` | Matching domain tests plus launcher interaction tests; Product Vision, MVP, or a decision when product policy changes | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_focus_model tests.test_palette_state tests.test_launcher_interactions` |
| Change guided context/tag pickers | `src/context_palette/context_membership_field.py`, `src/context_palette/searchable_selection.py` | `tests/test_context_membership_field.py`, `tests/test_searchable_selection.py`, `tests/test_configuration_window.py`, Help and Architecture for visible behavior | `.\python-context-palette.bat -m unittest tests.test_context_membership_field tests.test_searchable_selection tests.test_configuration_window` |
| Change existing-action selection in Configure | `src/context_palette/action_picker.py`; `configuration_window.py` supplies action metadata and owning callbacks | `tests/test_action_picker.py`, `tests/test_configuration_window.py`, launcher smoke tests, Help and Architecture | `.\python-context-palette.bat -m unittest tests.test_action_picker tests.test_configuration_window tests.test_launcher_smoke` |
| Add or change a built-in action type | `src/context_palette/action_types.py` and execution/validation in `src/context_palette/actions.py` | `tests/test_action_types.py`, `tests/test_actions.py`, generated `docs/ACTION_TYPES.md`, Help and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_types tests.test_actions tests.test_configuration_window` |
| Change bulk Action workbook creation/import | `src/context_palette/action_workbook.py` for bounded `.xlsx`; `action_bulk.py` for planning/commit; `action_bulk_window.py` and `configuration_window.py` for review/routes | `tests/test_action_workbook.py`, `tests/test_action_bulk.py`, `tests/test_action_bulk_window.py`, configuration and launcher smoke tests; Help, Architecture, Decisions, Testing, Changelog | `.\python-context-palette.bat -m unittest tests.test_action_workbook tests.test_action_bulk tests.test_action_bulk_window tests.test_configuration_window tests.test_launcher_smoke` |
| Change bulk Action workbook update | `src/context_palette/action_update_workbook.py` for the identity-bound `.xlsx`; `action_bulk_update.py` for planning/guarded commit; `action_bulk_update_window.py` and `configuration_window.py` for export/review routes | `tests/test_action_update_workbook.py`, `tests/test_action_bulk_update.py`, `tests/test_action_bulk_update_window.py`, context-membership, configuration, and launcher smoke tests; Help, Architecture, Decisions, Testing, Changelog | `.\python-context-palette.bat -m unittest tests.test_action_update_workbook tests.test_action_bulk_update tests.test_action_bulk_update_window tests.test_context_membership tests.test_configuration_window tests.test_launcher_smoke` |
| Change bulk Action deletion | `src/context_palette/action_bulk_lifecycle.py` for reviewed plans/stale checks; `action_deletion.py` for set-aware transaction/reference cleanup; `action_bulk_lifecycle_window.py` and `configuration_window.py` for the attended one-effect route | `tests/test_action_bulk_lifecycle.py`, `tests/test_action_deletion.py`, `tests/test_action_bulk_lifecycle_window.py`, configuration and launcher smoke tests; Help, Architecture, Decisions, Testing, Changelog | `.\python-context-palette.bat -m unittest tests.test_action_deletion tests.test_action_bulk_lifecycle tests.test_action_bulk_lifecycle_window tests.test_configuration_window tests.test_launcher_smoke` |
| Change Python Excel automation | `src/context_palette/excel_automation.py` for bounded engine protocol/result classification; `excel_automation_window.py` for attended CSV review; `excel_live_target_selector.py` for shared already-open workbook/worksheet selection; `excel_live_format_window.py` for direct live formatting; `excel_live_text_conversion_window.py` for reviewed recovery-backed column conversion; `launcher.py` for Action routing; `action_types.py` and `actions.py` for constrained Actions | Excel automation/target-selector/window tests, action catalogue/preview, launcher interaction/smoke, data-catalog, Help, Architecture, Decisions, Testing, Changelog | `.\python-context-palette.bat -m unittest tests.test_excel_automation tests.test_excel_automation_window tests.test_excel_live_target_selector tests.test_excel_live_format_window tests.test_excel_live_text_conversion_window tests.test_action_types tests.test_action_preview tests.test_launcher_interactions tests.test_launcher_smoke tests.test_data_catalog` |
| Change guided configuration | `src/context_palette/configuration_window.py` and `src/context_palette/configuration_data.py`; `context_deletion.py` for context removal | Configuration tests and relevant configuration guide; Help and Changelog for visible behavior | `.\python-context-palette.bat -m unittest tests.test_configuration_window tests.test_configuration_data tests.test_context_deletion tests.test_configuration_check` |
| Change direct Action deletion or legacy-inactive compatibility | `src/context_palette/action_deletion.py` for reference integrity; `src/context_palette/actions.py` for stored versus Active projections; `configuration_window.py` for guided controls | `tests/test_action_deletion.py`, `tests/test_actions.py`, `tests/test_configuration_window.py`, Help, Architecture, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_deletion tests.test_actions tests.test_configuration_window tests.test_configuration_snapshot` |
| Change quick Action creation | `src/context_palette/action_type_picker.py`, `configuration_window.py`, and `launcher.py` | Picker, configuration-window, and launcher interaction tests; Help, Architecture, Testing, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_type_picker tests.test_configuration_window tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change Action suggestions from Input / Output | `src/context_palette/action_suggestions.py` for pure conservative inference; `workspace_panel.py` for source selection; `launcher.py` and `configuration_window.py` for the reviewed form route | `tests/test_action_suggestions.py`, launcher interaction/smoke and configuration-window tests; Help, Architecture, Decisions, Testing, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_suggestions tests.test_configuration_window tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change captured-item Inbox or Inbox action creation | `src/context_palette/inbox_window.py`; `inbox.py` for stored-item behavior and `actions.py` for action validation | `tests/test_inbox.py`, `tests/test_inbox_window.py`, `tests/test_launcher_help.py`, launcher smoke tests; Help and Architecture when behavior changes | `.\python-context-palette.bat -m unittest tests.test_inbox tests.test_inbox_window tests.test_launcher_help tests.test_launcher_smoke` |
| Change Work Item discovery or configuration | `src/context_palette/work_items.py` for discovery; `src/context_palette/work_item_configuration.py` for guided setup | Work Item storage/refresh tests, launcher smoke tests, Help, Architecture, and Work Items plan | `.\python-context-palette.bat -m unittest tests.test_work_items tests.test_work_item_storage tests.test_work_item_refresh tests.test_work_item_configuration tests.test_launcher_smoke` |
| Change Work Item organization cleanup | `src/context_palette/work_item_organization.py` for transactional personal-reference inspection/removal; `src/context_palette/work_item_configuration.py` for confirmation and refresh | `tests/test_work_item_organization.py`, Work Item configuration and launcher smoke tests; Help, Architecture, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_work_item_organization tests.test_work_item_configuration tests.test_launcher_smoke` |
| Change Work Item creation or naming | `src/context_palette/work_item_creation.py` for file safety; `src/context_palette/work_item_configuration.py` for the form | Creation, storage, configuration, and launcher smoke tests; Help and Changelog | `.\python-context-palette.bat -m unittest tests.test_work_item_creation tests.test_work_item_storage tests.test_work_item_configuration tests.test_launcher_smoke` |
| Change Quick actions | `src/context_palette/action_bound_quick_actions.py` for automatic menus; `quick_menu_path_dialog.py` for the combined create/edit chooser; `action_quick_menu_organization*.py` for submenu CRUD and one-or-many automatic Action placement/removal; `action_configured_placement*.py` for draft inventories, composite Action saves, and saved-Action configured references; `command_surface.py` for loaded configured structure; `configuration_data.py`, `context_membership.py`, and `configuration_window.py` for guided writes; `launcher.py` for rendering/orchestration; `action_deletion.py` for deletion reference cleanup | Combined chooser/save, automatic-menu organization, configured-placement, Context-membership, command-surface, configuration, deletion, and launcher tests plus the configuration guide | `.\python-context-palette.bat -m unittest tests.test_quick_menu_path_dialog tests.test_action_quick_menu_organization tests.test_action_quick_menu_organization_window tests.test_action_configured_placement tests.test_action_configured_placement_window tests.test_context_membership tests.test_action_deletion tests.test_command_surface tests.test_configuration_data tests.test_configuration_window tests.test_launcher_command_surface tests.test_launcher_smoke` |
| Change shared Action/Work Item grouping | `src/context_palette/palette_items.py`, `contexts.py`, `palette_state.py`, and `focus_model.py`; `configuration_window.py` and `launcher.py` for UI | Data model and Context configuration guide | `.\python-context-palette.bat -m unittest tests.test_contexts tests.test_palette_state tests.test_focus_model tests.test_configuration_window tests.test_launcher_interactions` |
| Change persistence or runtime JSON formats | `src/context_palette/persistence.py` and the owning domain loader | Persistence/configuration tests, format documentation, migration or cleanup when required | `.\python-context-palette.bat -m unittest tests.test_persistence tests.test_configuration_check` |
| Change Windows hotkeys, credentials, window placement, or single-instance behavior | The matching focused module under `src/context_palette/` | Matching unit tests and the relevant manual checks in [Testing](TESTING.md) | Run the matching test module, then perform the documented Windows check |
| Change setup or multi-computer development | Root `.bat` scripts and `.python-version` | `tests/test_windows_scripts.py`, README, Multi-PC guide, Contributing | `.\python-context-palette.bat -m unittest tests.test_windows_scripts` |
| Correct current documentation facts or executable reference tables | The owning implementation/catalogue and its current guide; keep Decisions and Changelog as history | `tests/test_documentation_semantics.py`, navigation/link tests, and the owning domain test | `.\python-context-palette.bat -m unittest tests.test_documentation_semantics tests.test_documentation_navigation tests.test_documentation_links` |

## Adding a workspace transformation

This frequent change has a deliberate two-part boundary:

1. Add the pure operation to `transform_text()` or a focused helper in
   `actions.py`.
2. Add one `WorkspaceTransform` entry to `workspace_transforms.py`.
3. Add algorithm examples and edge cases to `tests/test_actions.py`.
4. Run `tests.test_workspace_transforms`; it rejects duplicate catalogue
   metadata and any non-prompting operation missing from the algorithm layer.
5. Update Help and Changelog because the command is user-visible.

Do not hand-build another Transform menu in the launcher. `WorkspacePanel`
renders the catalogue automatically.

## Verification levels

| Change stage | Command |
| --- | --- |
| Fast feedback | Run the focused command from the table |
| Documentation moved or renamed | `.\python-context-palette.bat -m unittest tests.test_documentation_links` |
| Complete automated check | `.\develop-context-palette.bat` |
| Final repository check | `git diff --check` and `git status --short` |
| Windows behavior changed | Complete the relevant section of [Testing](TESTING.md) |

Do not repeat the complete check after documentation-only edits unless those
edits are themselves validated by tests or changed executable scripts.
