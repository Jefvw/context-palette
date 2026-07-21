# Roadmap

The roadmap describes ordered product outcomes, not commitments or implemented behavior. Current behavior is defined by [MVP](MVP.md) and [Architecture](ARCHITECTURE.md); concrete tasks live in the root [Backlog](../BACKLOG.md).

## Now — make repeated actions effortless

- Validate the guided Configure experience with real personal actions, contexts, and Quick actions.
- Complete Work Items Phase 5: representative manual Windows checks on another
  computer/path and record the result.
- Improve discoverability of actions and action effects without exposing technical IDs.
- Complete manual Windows accessibility and responsive-layout checks.
- Continue reducing `launcher.py` responsibilities through behavior-preserving extraction.

## Next — deepen safe context workflows

- Refine the implemented Work Items discovery and creation workflows only from
  recorded validation findings; the discovery, configuration, local tags, and
  generic-template creation foundation is complete.
- Add richer context composition and ranking while preserving explicit focus and global search.
- Design clipboard preservation/restoration as an explicit transaction with tests.
- Design a small previewable linear sequence model; no loops, conditions, or arbitrary commands.
- Expand AI-proposable action types only where type-specific validation and review are adequate.

## Later — richer actions

- Application-aware context suggestions that never switch focus silently.
- Rich text, HTML, image, and character-picker actions with explicit clipboard behavior.
- A guarded action-ID automation API only after Trusted authorization, confirmation policy, structured results, and security tests exist.

## Explicit non-goals

- Arbitrary shell-command execution.
- Hidden or automatic execution of unreviewed actions.
- Cloud storage as a requirement.
- Automatic context switching without user control.
- Replacing the lightweight Tkinter application with a heavy framework solely for appearance.
