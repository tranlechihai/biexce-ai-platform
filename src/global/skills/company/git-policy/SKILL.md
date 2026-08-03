---
name: git-policy
description: Organization-specific Git policy for repository access, branches, reviews, merges and releases. Apply only after an approved policy is supplied.
compatibility: opencode
metadata:
  owner: biexce-ai-workflow
  status: skeleton
  applies_to: bx-director, bx-code, bx-fix, bx-review
  sources: organization Git governance policy not supplied
---

# Organization Git policy

This skill is intentionally unavailable. Agents must not infer repository
hosting, branch naming, commit identity, merge strategy, release authority or
retention requirements.

To activate it, provide an approved policy covering access, protected
branches, review requirements, CI gates, merge and rollback ownership, tags,
releases and audit. Replace this file with a reviewed `ready` skill and
regenerate the manifest. Until then, `core/git-flow-ai` remains read-only.
