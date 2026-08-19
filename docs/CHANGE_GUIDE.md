# Change guide

Use this guide to find the smallest safe change path. Current boundaries are
described in [Architecture](ARCHITECTURE.md); repository rules remain in
[AGENTS.md](../AGENTS.md).

## Before editing

1. Inspect `git status --short` and preserve existing work.
2. Confirm the behavior in code and its focused tests.
3. Keep personal files under `data/local_*`, `data/inbox.json`,
   `data/palette.json`, logs, and backups out of commits.
4. Run focused tests while editing and `.\develop-context-palette.bat` once
   after the final code change.

## Common change paths

| Goal | Primary owner | Usually update | Focused verification |
| --- | --- | --- | --- |
| Add or change an Input / Output transformation | `src/context_palette/actions.py` for the pure algorithm; `src/context_palette/workspace_transforms.py` for its label, group, operation key, and success message | `tests/test_actions.py`, `tests/test_workspace_transforms.py`, `docs/HELP.md`, `CHANGELOG.md` | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_workspace_transforms tests.test_launcher_smoke` |
| Change text-file transformation, preview provenance, or save-back behavior | `src/context_palette/actions.py` for bounded decoding, transformation, stale-source checks, and atomic writes; `src/context_palette/workspace_panel.py` for review controls | `tests/test_actions.py`, `tests/test_launcher_smoke.py`, Architecture, Help, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_launcher_smoke` |
| Change Input / Output widgets, menus, selection, undo, or clipboard behavior | `src/context_palette/workspace_panel.py` | `tests/test_launcher_smoke.py`, `docs/ARCHITECTURE.md`; Help and Changelog when visible behavior changes | `.\python-context-palette.bat -m unittest tests.test_launcher_smoke tests.test_actions` |
| Change OCR sources, limits, provider, setup, or result handling | `src/context_palette/ocr.py` for bounded decoding/provider behavior; `workspace_panel.py` and `launcher.py` for the UI flow; `requirements-ocr.txt` and OCR/offline setup scripts for deployment | `tests/test_ocr.py`, launcher interaction/smoke tests, `tests/test_windows_scripts.py`, `docs/OCR_SETUP.md`, Help, Architecture, Decisions, Testing, and Changelog | `.\python-context-palette.bat -m unittest tests.test_ocr tests.test_launcher_interactions tests.test_launcher_smoke tests.test_windows_scripts` |
| Change Find, result-list, Focus-list, or filter widgets | `src/context_palette/action_discovery_panel.py`, `src/context_palette/searchable_selection.py` | `tests/test_launcher_smoke.py`, `tests/test_searchable_selection.py`, `docs/ARCHITECTURE.md` | `.\python-context-palette.bat -m unittest tests.test_launcher_smoke tests.test_launcher_interactions tests.test_searchable_selection` |
| Change the inert real-Tk visual baseline | `src/context_palette/ui_mockups.py`; do not import production state or effects | `tests/test_ui_mockups.py`, `docs/UI_MOCKUPS.md`, the UI/UX audit, and Decisions when the proposed product model changes | `.\python-context-palette.bat -m unittest tests.test_ui_mockups tests.test_windows_scripts` |
| Change pre-Run Action input/effect explanations | `src/context_palette/action_preview.py`; `action_types.py` remains the semantic catalogue | `launcher.py`, `tests/test_action_preview.py`, launcher smoke tests, Help, Architecture, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_preview tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change search, ranking, Focus membership, or slot policy | `src/context_palette/actions.py`, `src/context_palette/focus_model.py`, or `src/context_palette/palette_state.py` | Matching domain tests plus launcher interaction tests; Product Vision, MVP, or a decision when product policy changes | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_focus_model tests.test_palette_state tests.test_launcher_interactions` |
| Change guided context/tag pickers | `src/context_palette/context_membership_field.py`, `src/context_palette/searchable_selection.py` | `tests/test_context_membership_field.py`, `tests/test_searchable_selection.py`, `tests/test_configuration_window.py`, Help and Architecture for visible behavior | `.\python-context-palette.bat -m unittest tests.test_context_membership_field tests.test_searchable_selection tests.test_configuration_window` |
| Change existing-action selection in Configure | `src/context_palette/action_picker.py`; `configuration_window.py` supplies action metadata and owning callbacks | `tests/test_action_picker.py`, `tests/test_configuration_window.py`, launcher smoke tests, Help and Architecture | `.\python-context-palette.bat -m unittest tests.test_action_picker tests.test_configuration_window tests.test_launcher_smoke` |
| Add or change a built-in action type | `src/context_palette/action_types.py` and execution/validation in `src/context_palette/actions.py` | `tests/test_action_types.py`, `tests/test_actions.py`, generated `docs/ACTION_TYPES.md`, Help and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_types tests.test_actions tests.test_configuration_window` |
| Change guided configuration | `src/context_palette/configuration_window.py` and `src/context_palette/configuration_data.py`; `context_deletion.py` for context removal | Configuration tests and relevant configuration guide; Help and Changelog for visible behavior | `.\python-context-palette.bat -m unittest tests.test_configuration_window tests.test_configuration_data tests.test_context_deletion tests.test_configuration_check` |
| Change Action archive, restore, or permanent deletion | `src/context_palette/action_deletion.py` for lifecycle/reference integrity; `src/context_palette/actions.py` for stored versus Active projections; `configuration_window.py` for guided controls | `tests/test_action_deletion.py`, `tests/test_actions.py`, `tests/test_configuration_window.py`, Help, Architecture, Decisions, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_deletion tests.test_actions tests.test_configuration_window tests.test_configuration_snapshot` |
| Change quick Action creation | `src/context_palette/action_type_picker.py`, `configuration_window.py`, and `launcher.py` | Picker, configuration-window, and launcher interaction tests; Help, Architecture, Testing, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_type_picker tests.test_configuration_window tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change Action suggestions from Input / Output | `src/context_palette/action_suggestions.py` for pure conservative inference; `workspace_panel.py` for source selection; `launcher.py` and `configuration_window.py` for the reviewed form route | `tests/test_action_suggestions.py`, launcher interaction/smoke and configuration-window tests; Help, Architecture, Decisions, Testing, and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_suggestions tests.test_configuration_window tests.test_launcher_interactions tests.test_launcher_smoke` |
| Change captured-item Inbox or Inbox action creation | `src/context_palette/inbox_window.py`; `inbox.py` for stored-item behavior and `actions.py` for action validation | `tests/test_inbox.py`, `tests/test_inbox_window.py`, `tests/test_launcher_help.py`, launcher smoke tests; Help and Architecture when behavior changes | `.\python-context-palette.bat -m unittest tests.test_inbox tests.test_inbox_window tests.test_launcher_help tests.test_launcher_smoke` |
| Change Work Item discovery or configuration | `src/context_palette/work_items.py` for discovery; `src/context_palette/work_item_configuration.py` for guided setup | Work Item storage/refresh tests, launcher smoke tests, Help, Architecture, and Work Items plan | `.\python-context-palette.bat -m unittest tests.test_work_items tests.test_work_item_storage tests.test_work_item_refresh tests.test_work_item_configuration tests.test_launcher_smoke` |
| Change Work Item creation or naming | `src/context_palette/work_item_creation.py` for file safety; `src/context_palette/work_item_configuration.py` for the form | Creation, storage, configuration, and launcher smoke tests; Help and Changelog | `.\python-context-palette.bat -m unittest tests.test_work_item_creation tests.test_work_item_storage tests.test_work_item_configuration tests.test_launcher_smoke` |
| Change Quick actions | `src/context_palette/action_bound_quick_actions.py` for automatic menus; `command_surface.py` for loaded structure; `configuration_data.py` and `configuration_window.py` for guided writes; `launcher.py` for rendering/orchestration; `action_deletion.py` for reference cleanup | Command-surface, configuration, deletion, and launcher tests plus the configuration guide | `.\python-context-palette.bat -m unittest tests.test_action_deletion tests.test_command_surface tests.test_configuration_data tests.test_configuration_window tests.test_launcher_command_surface tests.test_launcher_smoke` |
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
