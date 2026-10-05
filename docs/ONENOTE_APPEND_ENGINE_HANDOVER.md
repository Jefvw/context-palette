# Python OneNote handover: append to one existing page

Prepared 2026-10-05. Status: required engine work; no implementation or live
permission is supplied by this document. Context Palette's engine reference
remains read-only in this host task.

The owner wants Input / Output sent to an explicitly chosen existing OneNote
page, **added at the end while preserving existing content**. Capture Inbox,
its Action-creation/AI proposal UI, and Harvest are retired. Stored Actions and
legacy private capture data are preserved. This append operation is the next
integration dependency; Action maintenance/management is the next product focus.

## Implementation prompt for the Python OneNote owner

Work in D:\dev\python-onenote. Treat D:\dev\context-palette as a read-only host
reference. Read your AGENTS, current architecture/status and these documents:
CONTEXT_PALETTE_INTEGRATION.md, INTERFACES.md, CREATE_PAGE_EXECUTION_CONTRACT.md,
and STATUS.md. Inspect Git status and existing work before editing. Preserve
all changes. Do not commit, push, publish or operate on live OneNote content
without separately scoped authorization.

Add the smallest public versioned plan/execute contract for appending plain
text to **one exact existing page**. Current production machine operations
only create a new page; do not repurpose the create operation or bypass its
acknowledgements. Proposed names are plan_append_desktop_page and
execute_append_desktop_page; the engine owner decides the final additive
contract and documents it for host integration.

Required behavior:

- Explicit notebook/section/page selection resolves an exact page identity.
  Never infer the destination from the active page or rebind by title; never
  broaden an unavailable target to all notebooks.
- A zero-write plan binds normalized incoming text, exact target, current
  page/version evidence and effect. Execution requires fresh explicit consent,
  the exact reviewed fingerprint and an unchanged target/page state. Preserve
  existing session identity, bounded owned transport, cancellation and stale
  guards. Keep the original consent lifetime; do not refresh it during work.
- Append one plain-text block at the end. Preserve the existing title, text,
  formatting, tables, attachments, ink and other content. Do not extract the
  page as plain text and replace its body; use a bounded partial update, or
  refuse a shape that cannot be handled safely.
- No page/notebook/section creation, deletion, navigation, automatic startup or
  synchronization. No generic workflow engine or new dependency without need.
- Verify the appended block and report the exact target and authoritative
  outcome. Distinguish verified success, known no-effect failure, partial and
  unknown outcomes. Do not automatically retry an unknown or partial write or
  pretend cancellation proves rollback. Preserve receipts for manual inspection.
- Describe capability/version/availability and exact request, acknowledgement,
  plan/receipt schemas through the existing public process boundary. Keep new
  fields/operations additive; retain current new-page callers.

Host acceptance after the contract is published:

Choose an exact page once and remember it privately per PC. Display its
notebook/section/page breadcrumb and the incoming text, with one **Add to page**
command. Opening/editing must not read or mutate OneNote. An explicit picker or
send can perform acknowledged scoped reads/checks. A double-click or held send
shortcut must not duplicate the append. Input / Output stays unchanged.

Verification:

Use synthetic protocol/backend fixtures first: exact identity, changed page,
unsupported/rich content, Unicode/newlines/tabs, blank input, expired consent,
wrong acknowledgement/fingerprint, duplicate callbacks, interrupted or partial
writes, verification failures and cleanup. Run the engine's focused and complete
gate once after final changes. Update its integration/interface/status docs and
provide the exact deployable commit and host-facing JSON examples.

Then propose a fresh attended test on an owner-agreed disposable existing page.
Include existing formatted text and representative rich content, append one
fixed harmless block once, and independently verify the old content remains.
No live test or reuse of earlier page-creation UAT is authorized by this prompt.
The host requires its own focused fakes and separately scoped end-to-end UAT.

Report actual changes/tests, live checks performed or unperformed, compatibility
limits and any blocker. An engine report alone is not host acceptance.

## Model and review recommendation

Use an available Sol-class model with high reasoning, following MODEL_SELECTION.md.
Existing-content preservation and ambiguous mutation outcomes need one writer
and an independent read-only reviewer of the XML/update and receipt boundaries.