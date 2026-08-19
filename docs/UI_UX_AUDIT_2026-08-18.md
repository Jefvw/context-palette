# Context Palette UI/UX audit

Date: 2026-08-18

Implementation status: the accepted first Configure batch is now in
production. It includes grouped Set up/Support navigation, the revised Actions
page with collapsed pins, and the revised Work Items source/table layout.
Action types remains a direct destination for compatibility; the remaining
screen recommendations below are still an audit and roadmap, not completed UI.

## Product goal used for the review

Context Palette is a resident Windows work assistant for non-developers. Its
daily job is to make finding, understanding, and deliberately running a saved
Action or opening a Work Item faster than locating the target manually. Its
configuration and advanced tools must remain safe, previewable, portable
without administrator rights, and understandable without learning internal
IDs or implementation terms.

The interface should therefore optimize for:

1. Fast daily retrieval and one clear primary action.
2. A visible Input → Effect trust boundary before execution.
3. Stable terms and control locations across scopes and screens.
4. Progressive disclosure for configuration and expert workflows.
5. Native Tkinter layouts that remain readable on real Windows themes and at
   100%, 125%, and 150% display scaling.

## Executive findings

### P0 — fix before further styling

- Configure exposed two navigation systems for the same destinations. The
  native notebook has been replaced by an internal frame stack; the vertical
  navigator is now the only Configure navigation.
- The main palette still asks several icon-only or abbreviated controls to
  carry primary meaning. Tooltips are useful support, but cannot be the only
  explanation of a frequent or consequential command.
- Focus and Context filtering are related but different: Focus changes the
  prioritized working set and slots; a Context filter narrows results. The
  interface needs to teach that difference visibly.
- Discovery results, Quick actions, and Input / Output compete for a fixed
  height. Search results must remain the dominant daily-use area.

### P1 — next product-wide consistency work

- Action creation has many valid entry points but no clearly stated canonical
  model. Routes should resolve to three intentional outcomes: create manually,
  create from current content, or use an advanced import/AI workflow.
- Configure list pages independently arrange search, tables, selection
  details, and commands. A shared page shell would improve visual consistency
  without changing persistence or domain behavior.
- The application has primary and ordinary buttons, but lacks consistent
  quiet-navigation, destructive, selected-navigation, table-toolbar, and
  dialog-footer roles.
- Child windows use a mostly generic size even though small pickers, forms,
  tables, and review workspaces need different monitor-fitted presets.

### P2 — polish after structure is stable

- Harmonize confirmation verbs and button order.
- Give Help and advanced creation tools clearer task stages.
- Add real Windows screenshot/UAT coverage for representative empty, full,
  error, disconnected, and in-progress states.

## Screen-by-screen evaluation

| Screen or surface | What is working | Main improvement |
| --- | --- | --- |
| Main palette — discovery | All items, Actions, and Work Items are legitimate mutually exclusive scopes. The selected result and Run/Open route share one executor. | Reduce visible controls to Focus, scope, Find/Filter, results, and selection actions. Keep uncommon tools in a labelled menu. |
| Main palette — Focus | Focus-first ranking and slots are a valuable core capability. Truthful empty Focus behavior now passes UAT. | Show `Focus: <name>` and a short labelled Focus-only control. Explain once that Focus prioritizes while Context filters narrow. |
| Main palette — filters | One Filter menu and removable active criteria are the correct direction. | Do not reintroduce separate `C`, `#`, type, or project buttons. Use readable menu labels and chips. |
| Main palette — selection toolbar | New/Edit/Pin/Run are correctly associated with the selected result. Sequence Stop now remains visible. | Keep only valid commands enabled. Use text for primary commands; use icons only for stable, familiar micro-actions. |
| Main palette — Quick actions | Compact navigation menus are distinct from search and worth retaining. | Keep their region height-bounded so it cannot displace discovery results. Use one interaction model for configured and automatic menus: left browses, right manages, and only a selected Action executes. |
| Input / Output | Text tools, OCR, and Create from Input belong with the content they consume. OCR placement is an excellent explicit Replace/Append/Cancel model. | Preserve the compact header, but ensure each icon has an accessible name and clear status. Use `Extract image text` consistently. Enable suggested Action creation only for a defensible suggestion. |
| Main status / preview | Input → Effect summaries support the product's safety promise. | Make selected-item preview visibly primary; do not rely on users discovering that status text opens more information. |
| Result and text context menus | Secondary right-click access is a useful accelerator and can share callbacks with visible commands. | Keep names and ordering consistent with the visible route. Do not place a capability only in a context menu. |
| OCR placement dialog | Literal Replace, Append, and Cancel buttons make the result and non-action clear. | Reuse this explicit-verb pattern elsewhere. |
| Transform parameters dialog | A bounded native modal is appropriate. | Show the chosen operation and a one-line effect description above its parameters. |
| Configure shell | A stable vertical navigator matches heterogeneous setup and support areas. Direct routes and singleton reuse are good. | Keep the internal frame stack; never reintroduce native tabs. Separate frequent setup pages from Backup/Diagnostics support pages visually. |
| Configure — Start | Task-oriented entry choices help occasional users. | Phrase each choice as an outcome. Keep advanced catalogue and diagnostics links visually secondary; Start must not become a second full navigation system. |
| Configure — Actions | Search, lifecycle, ownership, and the Action table are valuable. | Collapse optional pins; keep New/Edit primary, Archive secondary, and permanent Delete visually destructive. Consolidate all manual creation through the same type chooser and form. |
| Configure — Action types | Descriptions and examples help users select a safe type. | Name this `Action types`, not `Create action`. Treat it as a catalogue reached from the canonical creation flow rather than an equal daily destination. |
| Configure — Contexts | Correctly owns membership and Focus shortcuts. | Add the permanent explanation: `A Context organizes items; Focus is the Context currently highlighted in the palette.` Present Members before optional Focus shortcuts 6–0. |
| Configure — Quick actions | Uses one consistent bounded menu model while preserving old `rows`/`nested_menu` files as readable compatibility data. | Use `New menu` and `New submenu` language. Mark automatic menus as derived and route their organization to Actions. |
| Configure — Work Items | The source-focused full-width table and compact selected-item strip are materially clearer. Context membership editing now passes UAT. | Use one source selector plus `Manage sources…` or clearly labelled source controls. `Source options` is clearer than `More`. Keep only Work Item, Type, and Project in the table; show Contexts/tags in the inspector. Shorten any command that clips at the supported minimum. |
| Configure — Diagnostics | Safe summary, Refresh, and Copy are appropriate. | Treat it as Support information, not a peer daily setup task. Remove references to visible Configure tabs. |
| Configure — Backup & restore | Inspect-before-apply and recovery behavior are strong. | Label the guarded stages literally: `Choose backup to inspect…` then `Apply inspected changes…`. Give restore/destructive actions a distinct role. |
| Action type picker | Search plus description and explicit selection make this a good canonical primitive. | Reuse it for all manual creation routes. |
| Action editor | Validation, immediate persistence, type-specific help, and fixed footer are sound. | Apply progressive disclosure to advanced fields. Sequence editing should emphasize the ordered step list and plain Add action/Add wait/Move/Remove controls. |
| Context editor | One source of truth for members and preferred slots is correct. | Separate membership from optional Focus placement visually and explain their relationship. |
| Quick-action group/menu editors | Bounded hierarchy and stable references are safe. | Use menu/submenu language and a shared dialog footer. Clearly distinguish configured versus generated structures. |
| Work Item source dialog | Friendly name, stable ID, and exact folder are valid fields. | Explain their relationship in one sentence and place removal in a visibly destructive secondary route. |
| Work Item tags/contexts dialog | Direct editing solves a high-priority UAT gap. | Title it `Tags and contexts` rather than generic `Edit Work Item`. |
| Create Work Item dialog | Attended template copy and exact destination confirmation are strong. | Summarize source + template + final folder/workbook as one readable preview before Create. |
| Searchable selection and Action pickers | Shared searchable primitives reduce inconsistent bespoke selectors. | Titles must state whether the user is filtering, choosing one item, or assigning several. |
| Inbox | Capture review and manual Action conversion are useful. | Keep Create Action primary; group Ask AI and Harvest under `Other ways to create` or an advanced menu. Make processed state or archiving explicit. |
| Inbox Action creator | A small manual conversion path is appropriate. | Keep it intentionally simpler than the full Action editor and converge on the same validation vocabulary. |
| Ask AI guidance | Manual copy/paste boundaries preserve privacy and control. | Present numbered stages: Prepare request, paste response, review proposals, create selected Actions. It is an advanced workflow, not a daily peer. |
| Harvest | Preview-before-create is a strong safety checkpoint. | Convert the dense expert screen into three attended stages: scan sources, review candidates/provenance, organize and create. Collapse filters and bulk editing. |
| Harvest preview | Exact review before permanent creation is valuable. | Preserve it as the model for advanced import safety. |
| Help | Searchable local documentation is valuable. | Lead with task guides: Use the palette, Set up Work Items/OCR, Documents, Troubleshooting. Keep browser-like navigation secondary. |
| Cheat Sheets | Reusable reference content and promotion are useful optional features. | Treat it as a reference library, not another primary Action-creation hub. Use a responsive master/detail layout. |
| Progress/recovery windows | Modal exclusion protects backup/restore integrity. | Use operation-specific titles and a stage/progress message rather than a generic Context Palette title. |
| Tooltips and message boxes | They provide useful detail and safety confirmation. | Tooltips must supplement visible affordances. Standardize confirmation language and button order by operation type. |

## Redundancy decisions

Keep these duplicate routes because they are useful accelerators that call the
same underlying behavior:

- Visible Run/Open plus Enter and double-click.
- A labelled Text tools menu plus the text editor's context menu.
- A visible command plus an equivalent selected-result context-menu command.
- Start task cards plus persistent Configure navigation.
- F1/help links plus contextual help.

Consolidate or remove these because they create competing mental models:

- Vertical Configure navigation plus horizontal tabs.
- Several apparently different manual Action creation workflows.
- Separate permanent controls for source selection, source management, and
  template setup when one clear source-management route is sufficient.
- Cryptic dynamic rails whose meanings change by scope.
- Always-visible expert controls in Harvest, AI, or Diagnostics.

## Tk-native visual system

No new UI dependency is required.

### Spacing and hierarchy

- Base spacing: 4 px; control gaps: 4/8 px; section gaps: 12/16 px.
- Page padding: 12 px; modal form padding: 14 px.
- One page title and at most one muted purpose line. Do not repeat the same
  title in the window, tab/navigation, and page body.
- Search and result count share one row. Selection details use one compact
  strip, not a second permanent form.

### Controls

- Primary: one teal button per page or dialog task.
- Secondary: ordinary labelled button.
- Quiet navigation: low-emphasis, left-aligned, with a clear selected state.
- Destructive: distinct style and literal verb such as `Delete permanently…`
  or `Apply restore…`.
- Icon-only: reserved for familiar, repeated micro-actions; always expose an
  accessible name and tooltip.
- Labels use verb + object. Avoid generic `More`, `Options`, or symbols when the
  control performs a consequential action.

### Tables and selected items

- Name is the stretchy, highest-priority column.
- Hide or move low-value columns into the inspector at constrained widths.
- Use consistent search, count, empty state, scrollbars, row selection, and a
  compact selected-item action strip.
- Never require horizontal scrolling for the final primary column at the
  supported minimum size.

### Windows and dialogs

- Small picker: approximately 420 × 260, monitor-fitted.
- Form: approximately 620 × 480.
- Table workspace: approximately 900 × 640.
- Review workspace: approximately 960 × 700.
- Dialog footers consistently place status/help left and Cancel + primary
  action right. Do not use one generic size for every child window.

## Recommended implementation batches

### Batch A — navigation correctness

Status: implemented; automated verification pending final complete-suite run.

- Keep vertical Configure navigation only.
- Use an internal frame stack, not styled hidden native tabs.
- Preserve direct routes, Alt keys, Ctrl+Tab, singleton reuse, and focus.
- Rename ambiguous Work Item `More` to `Source options`.

### Batch B — validated visual baseline

Status: real-Tk mockup gallery and simulated scaling tests implemented;
manual Windows 100%/125%/150% review remains pending. See
[Real-Tk UI mockups](UI_MOCKUPS.md).

- Create real Tkinter mockups for the main palette, Configure shell, and one
  representative list page at normal and minimum sizes.
- Agree on button roles, spacing, selection strip, source management, and
  setup/support grouping before further production changes.
- Validate at 100%, 125%, and 150% Windows scaling.

### Batch C — shared Configure page structure

Status: the approved page hierarchy is implemented for Actions, Contexts,
Quick actions, and Work Items without changing their domain callbacks. A broad
dialog-footer abstraction was deliberately deferred until more dialogs are
migrated; production pages currently reuse styles and explicit local frames.

- Keep the established page title/purpose, primary creation command, table,
  and selection-card hierarchy.
- Preserve ownership-aware Quick-action controls and literal destructive labels.
- Extract shared helpers only when another migration demonstrates stable
  duplication; do not introduce them solely for visual consistency.

### Batch D — daily palette clarity

- Preserve scope semantics and the Input → Effect trust boundary.
- Simplify Focus versus Context presentation.
- Keep results dominant over Quick actions.
- Replace unclear high-frequency glyphs with short text or stable bitmap icons.

### Batch E — advanced and secondary screens

- Capture Inbox now has an explicit confirmed **Delete capture…** route; broader
  Inbox and Action-creation redesign remains pending.
- Harvest and AI stages.
- Backup/restore guarded-stage wording and Diagnostics hierarchy are complete.
- Help and Cheat Sheet information architecture.

## Verification standard

Every visual batch should include:

1. Focused unit tests for routing, labels, and enabled states.
2. Real Tk smoke tests asserting one mapped page, no clipping, stable size, and
   preserved callbacks.
3. Complete automated test suite and `git diff --check`.
4. Manual Windows screenshots at 100%, 125%, and 150% for normal and minimum
   sizes.
5. Empty, populated, selected, error/unavailable, and in-progress states where
   applicable.

Automated widget metadata alone is insufficient: the duplicate native tab row
proved that Windows pixel rendering must be part of acceptance.
