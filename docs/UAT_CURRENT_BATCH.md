# Current batch: owner acceptance

## Acceptance record — 2026-09-09

**Status: owner UAT accepted for now; coverage partial.** The owner stated:
"Not checked everything but consider UAT done for now."

This closes owner acceptance for the current Input / Output, Preview, Drop,
Send-files and cosmetic batch. Individual checks, display scales and monitor
coverage were not reported, so no unreported check is marked Pass. Remaining
checks below are optional follow-up, not blockers to this batch's acceptance.
There is no request to repeat the checklist now.

This decision does not change the separate live Excel conversion execution
gate or authorize a commit, push or release. Earlier engineering logs retain
their status at the time they were produced; this record is the later owner
decision.

## Checklist retained for optional follow-up

UAT means user acceptance testing: check that the application behaves as you
expect during real Windows use. Engineering owns automated tests, diagnosis,
and fixes. Your part is to try the short flows below and report Pass, Fail,
or Not tested. A confusing result is useful feedback even when nothing crashes.

Allow about 20 minutes for checks 1–5 at your normal display scale. Check 6 is
a separate display/optional-integration follow-up. These checks accept the
existing compact interface; they do not reopen the product design or require
completion of the older [manual testing backlog](../BACKLOG.md).

## Prepare once

1. Save any Input / Output text you want to keep. Record your current Drop
   setting so you can restore it afterward.
2. Close Context Palette with **Quit**, then run `run-context-palette.bat`
   from this checkout. F9 alone only reveals an existing process; it does not
   load changed Python code. This restart clears session histories.
3. Open `data\uat-current-batch` in Explorer. The September 9 acceptance pass
   prepares a harmless `source\sample.txt` and empty `destination` and
   `alternate-destination` folders. This directory is local and Git-ignored.
   On another checkout, create the same folders and a plain text sample first.
   Do not empty these folders if they already contain results; extra suffixed
   copies from a previous pass are expected.
4. Use **Create Action** (document-plus) to create two Actions in
   **My configuration**, leaving Context as General:

| Name | Type | Configured value |
| --- | --- | --- |
| UAT text | Place a template in Input / Output | `UAT: %CLIPBOARD%` |
| UAT copy | Send files to folder | `%PROJECT_ROOT%\data\uat-current-batch\destination` |

The text Action uses a supported template so no legacy transformation type or
JSON editing is needed. Dropping a file supplies its path, not its contents.
Use only these disposable Actions and folders for the checks below.

## Checks at your normal Windows scale

### 1. Input / Output and the compact controls

Type `KEEP THIS INPUT`, select part of it, and use the **Input / Output**
checkbox to hide and show the pane twice. Expect the same text and selection,
a visible hidden-input dot, and working Undo/Redo and Back/Forward history.
Resize the window smaller and larger; Create Action, Edit, Preview, Run/Open,
Filter, and the three item scopes must remain usable without overlap.
The document-plus must open the normal type chooser; cancel it afterward.

### 2. Preview has no effects

In Explorer, copy the path of `source\sample.txt`, then put that path in
Input / Output. Select **UAT copy** and choose **Preview**. Expect the input
path and destination explanation, with no file copy and no copy-review window.
Preview **UAT text**: expect the clipboard-based template result without
replacing Input / Output or the clipboard. Close Preview. Optionally preview
an existing text transformation or external target; neither should execute.
Preview should never be required before ordinary Run.

### 3. Default Drop and text output

Open **More → Show drop target** if needed. In its **Settings…**, select
**Show in Context Palette** and save. With unrelated text in Input / Output,
drop `sample.txt` from Explorer. Try Cancel, then drop again for Append, then
again for Replace. Expect the selected placement, no file copy, and no
clipboard change. Hide the Input / Output pane and repeat: it must reappear.

Now set Drop to **Run an Action… → UAT text**, review the effect and save.
Put unrelated text back in Input / Output and drop the same file. Expect
`UAT: ` followed by the dropped file's full path, copied to the clipboard and
delivered to Input / Output, without a Replace/Append question. Undo must
recover the previous editor text. **Show details** must show the original
dropped path as prepared content. **Send again** must only offer placement
of that original path; it must not run the template again.

### 4. Run, Drop and copy review

Put the source file's full path in Input / Output and Run **UAT copy**.
Expect a copy in `destination`, with the source unchanged. If a name already
exists, expect the copy review; leave overwrite off and confirm a suffixed
copy. The editor and clipboard must remain unchanged.

Set Drop to **UAT copy** and save. Keep the Palette visible and replace its
editor text with `KEEP THIS INPUT`. Drop the source file. Expect the copy
review for the existing name, no editor-placement question, and unchanged
editor text. While this review is open, drop again: it must preserve the
existing review rather than replace it or start another copy. Finish the
review with overwrite off; source and original destination file must survive.

Close the review and use **More → Hide** to hide the Palette. Drop again:
the copy-review window must remain visible and usable on its own. Close it
when finished. Reopening through F9 can refresh Input / Output from the
clipboard; assess editor preservation in the visible-Palette check above.

### 5. Changed approval and normal retrieval

Edit only **UAT copy** and change its destination to
`%PROJECT_ROOT%\data\uat-current-batch\alternate-destination`. Save, then drop
the source again without reapproving Drop. Expect **Action blocked — review
Settings**, no copy in the new destination, and retained original input in
Drop history. Reselect **UAT copy** in Drop settings, review and save: a new
drop may now copy there. This is intentional approval of the changed effect.

Try your usual Context, tag and Find choices across All items, Actions and
Work Items. Context must choose membership and shortcuts 6–0; tags only narrow
results; All contexts uses General's bank. Try an ordinary Action from a
Quick menu and an available Work Item. If you already know how to add a
personal Quick-menu reference, add **UAT copy** and verify its Run behavior
there too; otherwise report that part as Not tested and we can do it together.

## 6. Separate follow-up when the environment is available

- At physical Windows 100%, 125%, and 150% scaling, check normal and minimum
  sizes, readable symbols, alternating rows, selected text, keyboard focus,
  and reachable Preview/Run buttons. Move between monitors if available.
  Record the scales actually tried; simulated Tk scaling is engineering
  evidence, not a substitute for this check.
- If Python Excel CSV export is configured, use a disposable closed workbook.
  An approved Drop must open the normal CSV review without writing before
  confirmation; another drop must not replace that open review. Otherwise
  report this as Not tested. Keep live Excel conversion's UAT gate unchanged.
- Broader Excel, backup/restore, menu-maintenance and second-PC matrices remain
  in the backlog. They are not all expected from this short owner pass.

## Finish and report

Restore **Show in Context Palette**, or your previous explicitly reviewed
Drop setting. Remove temporary Quick-menu references and review deletion of
the two UAT Actions if you no longer want them. Keep the disposable files
until any failure has been diagnosed; no personal Actions need changing.

Send this short report in the task; you do not need to edit a repository file:

```text
Date / Windows display scale / monitor count:
Restarted this checkout before testing: Yes / No
1. Input / Output and compact controls: Pass / Fail / Not tested
2. Effect-free Preview: Pass / Fail / Not tested
3. Default Drop, text output and resend: Pass / Fail / Not tested
4. Run, copying, conflict and hidden-window review: Pass / Fail / Not tested
5. Changed approval and normal retrieval: Pass / Fail / Not tested
6. Physical scales / monitors / Excel actually checked:
Failure: step, expected result, actual result (screenshot if helpful)
Anything confusing or slower than before:
Drop setting restored:
```

Owner acceptance is recorded above; automated tests do not establish manual
coverage. Engineering verification output is kept separately in the local
`acceptance-check-2026-09-09.log`, with source/test hashes and skip reasons.
