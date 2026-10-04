# Send text to OneNote — proposed attended host UAT

Prepared 2026-10-03. **Not yet authorized or performed.** This supersedes the
earlier Review-then-Send proposal; it remains a proposal, not permission. Previous engine-only
creation and Search UAT do not authorize this test. Complete the host automated
gate first. The owner must agree to the scope below before any live read/write.

## Exact proposed scope

- Existing disposable notebook: `PYTHON_ONENOTE_DISPOSABLE_UAT`.
- Existing section: `READ_ONLY_PROBE`. Resolve its current exact identity through
  explicit selection; do not reuse an old ID or select by matching title alone.
- Metadata: list open notebook names, then list section/group names and identities
  only under the explicitly chosen disposable notebook. The owner confirms only
  that disposable notebook is open. No existing page text needs to be read.
- Exactly one new page, title: `Context Palette host Send UAT 2026-10-03 B2`.
- Exact body (there is one empty line; the last line has a tab between its words):

```text
Synthetic Context Palette host Send check B2.
Café 日本語

Tab	kept
```

The test does not delete or edit that page afterward. Cleanup, if wanted, belongs
to the owner. No navigation, automatic retry, settings repair or OneNote restart.

## Attended steps after approval

1. Preserve existing Input / Output and open the agreed notebook. Put the exact
   synthetic body in Input / Output and open **Send to → OneNote — new text page…**.
   Confirm the source stays visible/intact; opening and editing cause no reads.
2. Explicitly select the agreed notebook/section. Check the breadcrumb, close and
   reopen Send, and confirm it is remembered independently of search scope.
   If an application restart is needed to check persistence, preserve Input /
   Output first and obtain the owner's agreement to restart; no automatic restart.
3. Set the exact title. Check the visible final normalized title and complete body,
   including Unicode, tab and blank line, and confirm that there is no Review
   control. Cancel/close before Send and confirm no page creation. Reopen and
   confirm that opening and editing still cause no reads.
4. Choose **Send to OneNote** once. Expect `content_verified`, the same original
   Input / Output, no automatic navigation, and no unexpected prompt or change.
   Use one initiation gesture only: a button click, a double-click, or one held
   Ctrl+Enter press. Confirm it creates just one page. Do not press Send again
   after completion or test cancellation after dispatch in this live scope.
   Fresh gestures after completion can intentionally create another page; those
   and repeated-gesture fault cases are covered synthetically here.
5. The owner opens the new page manually and checks title/body, one-page count,
   and unchanged existing notes. Record owner observations separately from the
   adapter's read-back receipt. Do not enumerate or read unrelated page content.

Unknown or partial result: stop, retain details, and ask the owner to inspect;
never resend automatically. Cancellation after dispatch, process loss, malformed
responses and cleanup failure are exercised synthetically, not by live fault
injection. Any expanded scope or second creation needs separate agreement.

## Compatibility limits

This acceptance covers the installed engine/client and one exact disposable
section. It does not establish relocated-path bootstrap/live writes, arbitrary
OneNote clients, broad notebook performance, concurrent external edits or recovery
after an interrupted real mutation. Earlier engine evidence remains separate.
