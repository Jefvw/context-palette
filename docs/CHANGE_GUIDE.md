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
| Change Input / Output widgets, menus, selection, undo, or clipboard behavior | `src/context_palette/workspace_panel.py` | `tests/test_launcher_smoke.py`, `docs/ARCHITECTURE.md`; Help and Changelog when visible behavior changes | `.\python-context-palette.bat -m unittest tests.test_launcher_smoke tests.test_actions` |
| Change Find, result-list, Focus-list, or filter widgets | `src/context_palette/action_discovery_panel.py` | `tests/test_launcher_smoke.py`, `docs/ARCHITECTURE.md` | `.\python-context-palette.bat -m unittest tests.test_launcher_smoke tests.test_launcher_interactions` |
| Change search, ranking, Focus membership, or slot policy | `src/context_palette/actions.py`, `src/context_palette/focus_model.py`, or `src/context_palette/palette_state.py` | Matching domain tests plus launcher interaction tests; Product Vision, MVP, or a decision when product policy changes | `.\python-context-palette.bat -m unittest tests.test_actions tests.test_focus_model tests.test_palette_state tests.test_launcher_interactions` |
| Change guided context/tag pickers | `src/context_palette/context_membership_field.py` | `tests/test_context_membership_field.py`, `tests/test_configuration_window.py`, Help and Architecture for visible behavior | `.\python-context-palette.bat -m unittest tests.test_context_membership_field tests.test_configuration_window` |
| Add or change a built-in action type | `src/context_palette/action_types.py` and execution/validation in `src/context_palette/actions.py` | `tests/test_action_types.py`, `tests/test_actions.py`, generated `docs/ACTION_TYPES.md`, Help and Changelog | `.\python-context-palette.bat -m unittest tests.test_action_types tests.test_actions tests.test_configuration_window` |
| Change guided personal configuration | `src/context_palette/configuration_window.py` and `src/context_palette/configuration_data.py` | Configuration tests and relevant configuration guide; Help and Changelog for visible behavior | `.\python-context-palette.bat -m unittest tests.test_configuration_window tests.test_configuration_data tests.test_configuration_check` |
| Change right-side Quick actions | `src/context_palette/command_surface.py` for data policy; `src/context_palette/launcher.py` for rendering and orchestration | Command-surface tests and configuration guide | `.\python-context-palette.bat -m unittest tests.test_command_surface tests.test_launcher_command_surface tests.test_launcher_smoke` |
| Change persistence or runtime JSON formats | `src/context_palette/persistence.py` and the owning domain loader | Persistence/configuration tests, format documentation, migration or cleanup when required | `.\python-context-palette.bat -m unittest tests.test_persistence tests.test_configuration_check` |
| Change Windows hotkeys, credentials, window placement, or single-instance behavior | The matching focused module under `src/context_palette/` | Matching unit tests and the relevant manual checks in [Testing](TESTING.md) | Run the matching test module, then perform the documented Windows check |
| Change setup or multi-computer development | Root `.bat` scripts and `.python-version` | `tests/test_windows_scripts.py`, README, Multi-PC guide, Contributing | `.\python-context-palette.bat -m unittest tests.test_windows_scripts` |

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
