# Real-Tk UI mockups

The UI mockup gallery is the review baseline for the next broad visual batch.
It uses the application's real Tkinter theme, fonts, controls, tables, bitmap
icons, and window sizes. It is not an HTML approximation and it does not
replace the production interface.

## Safety boundary

Every example is fictional and held only in memory. The mockups do not:

- load or save Context Palette configuration;
- inspect, open, create, archive, or delete files or folders;
- read or replace the clipboard;
- start OCR, networking, applications, scripts, or Actions;
- write personal or runtime data.

Run/Open/Edit/Create controls only change the mockup's status text. Every
mockup window title says that it is inert.

## Open the gallery

After the normal Context Palette setup, double-click:

```text
run-ui-mockups.bat
```

No OCR setup or administrator access is required. On another computer, run
`setup-context-palette.bat` once if the local `.venv` has not been prepared,
then open the gallery.

Choose a screen, a representative state, a window size, and either the real
system text scaling or a 100%, 125%, or 150% simulated stress level. Each
choice opens in a separate window so two proposals can be compared side by
side.

The direct developer command is:

```powershell
.\python-context-palette.bat -m context_palette.ui_mockups
```

## Included baselines

### Main palette

The main mockup deliberately has no repeated pane title, count, Find label, or
Quick-actions heading. Its order is:

1. One `Context: <name>` Working-context selector and the adjacent
   `Everywhere` / `This context` retrieval selector.
2. Compact `All items / Actions / Work Items` scope choices.
3. Find and Filter on one line.
4. An explicit removable tag/type/project filter chip when a non-context
   filter is active.
5. The dominant result list.
6. Selection commands and Run/Open or Stop remaining.
7. A bounded, scrollable Quick-action region with no heading.
8. Configure, Help, and More controls that never scroll off screen.

Input / Output keeps only the five content-dependent icon controls above the
editor and a permanently readable Input -> Effect strip below it.

The Working context and retrieval boundary are deliberately one coherent
model:

- the Working context supplies its genuine slots 6-0 only while Find is empty;
- **Everywhere** keeps Find global, while **This context** limits results to
  the selected specific Context; General disables the latter because it would
  be equivalent to Everywhere;
- a non-empty Find ranks useful matches by relevance and never promotes a
  context-slot row above a better ordinary match;
- Context membership is not repeated as a separate filter control.

Quick-action launchers remain menu-only and are ordered as **Standard**, then
personal configured menus, shared configured menus, and automatic
Action-bound menus.

At the minimum-size 150% simulation, Quick actions show one scrollable row so
the result list retains at least five rows. This is an intentional resolution
of the user's request that discovery space take priority over secondary
shortcuts.

### Configure shell

The Configure mockup has one vertical navigation system. It groups:

- **Set up:** Start, Actions, Contexts, Quick actions, Work Items.
- **Support:** Backup & restore, Diagnostics.

`Action types` is intentionally not a permanent peer destination in the
mockup. The first production batch retained that direct destination and
`Alt+T` for compatibility while adopting the grouped navigator, Actions page,
and Work Items page. Removing the direct destination remains a separate
navigation decision rather than a hidden consequence of this visual batch.

### Work Items

The representative page uses:

- one `New Work Item...` primary action;
- one current-source selector;
- `Manage sources...` for Add/Edit/Remove/template setup;
- a visible Refresh command and full wrapping path/status;
- one Work Item / Type / Project table without horizontal scrolling;
- a compact selected-item strip with an `Organize` menu for Contexts, tags,
  precise personal-organization cleanup, and a separate folder
  opening.

### Actions

The representative page uses:

- one `New Action...` primary action;
- an `Other ways to create` menu for the type catalogue and Harvest;
- one Action table with readable type and ownership;
- Edit, Archive/Restore, and visibly destructive permanent deletion in the
  selected-item strip.

## Reconciled sizing decision

One design review proposed larger Configure windows to gain table height. A
separate Tk validation review warned that doing so could hide the crowding
problem. The mockups therefore retain today's supported boundaries:

| Surface | Normal | Minimum |
| --- | ---: | ---: |
| Main palette | 780 x 600 | 700 x 480 |
| Configure | 960 x 680 | 900 x 520 |

The mockups must prove the hierarchy at those sizes before production adopts
larger defaults or minimums.

## Verification status

Automated real-Tk tests construct every screen at Normal and Minimum under
simulated 100%, 125%, and 150% text scaling. They currently protect:

- client-bound containment and readable consequential button labels;
- the current supported window dimensions;
- five visible main results at the harshest minimum-size stress case;
- bounded Quick actions and a permanently visible application footer;
- Find and Filter sharing one visual row;
- explicit Working-context and Everywhere/This-context behavior, context
  slots 6-0, and relevance-ranked Find results;
- fixed Standard, personal, shared, then automatic Quick-action ordering;
- one mapped Configure page with no `ttk.Notebook`;
- useful table rows at the current minimum under normal scaling;
- no horizontal table scrollbar.

Simulation is not proof of actual Windows DPI rendering. Manual approval still
requires the Normal and Minimum variants on real Windows at 100%, 125%, and
150%, especially for fixed 16-pixel icons, title-bar metrics, and per-monitor
behavior.

## Review checklist

For each screen and size, check:

1. No command text is clipped and no control overlaps another.
2. Results or the main table receive the largest useful area.
3. Quick actions and application controls remain reachable.
4. Only the page's intended primary command is visually dominant.
5. Working context, Everywhere, and This context answer distinct questions
   without an overlapping membership filter.
6. The selected item's details and next safe command remain visible.
7. Empty, unavailable, and in-progress states explain what changed.
8. Tab focus is visible; Enter and Space operate only inert mockup controls.

Record feedback against the mockup before copying any structure into the
production launcher or Configure pages.
