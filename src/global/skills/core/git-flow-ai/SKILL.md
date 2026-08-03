---
name: git-flow-ai
description: Read-only Git safety rules for BIEXCE agents. Apply before an agent inspects repository history or proposes a Git operation.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: draft
  applies_to: bx-director, bx-code, bx-fix, bx-review
  sources: canonical OpenCode permission policy; Pro Git repository inspection guidance
---

# Git safety for BIEXCE agents

## Active contract

- Agents have no Git write permission. Do not add, commit, branch, switch,
  merge, rebase, push, reset, clean, tag or modify remotes.
- Read-only `git status`, `git diff` and bounded `git log` may be used as
  evidence when the repository and permission policy allow them.
- Autopilot progress is recorded through `.biexce/` artifacts and focused
  change reports. A human owns repository history and publication.
- A Git command must not be suggested as completed evidence unless its output
  was actually observed.

## Future write workflow

No write workflow is defined by this draft. Enabling Git mutation requires an
approved organization policy covering repository host, branch protection,
identity, allowed branch names, review, merge, rollback and audit. Until then,
the runtime permission remains deny.

## Limits

- Do not use shell workarounds to bypass denied Git commands.
- Do not modify `.git/` directly.
- Do not treat ownership of a task as permission to change repository history.
