---
description: Run the BIEXCE end-to-end delivery workflow
agent: orchestrator
---

Run the BIEXCE workflow for this user objective:

$ARGUMENTS

The user is the highest workflow authority. Honor requests to pause, cancel, reprioritize, revise, retry, waive, or accept work unless a platform safety boundary prevents it.

Use native OpenCode TODOs and Slim background agents for live coordination. Do not create a custom scheduler, lock, WIP counter, lease, or runtime state JSON. Project artifacts under `.biexce/` are documentation and evidence, not runtime authority.

1. Intake: inspect the workspace and create or update `.biexce/PROJECT_BRIEF.md`. Ask only about a material product decision, unsafe action, missing access, or irreducible ambiguity.
2. Discovery and plan: dispatch BX Explore, then BX Plan using its evidence. Send the result to BX Review. Use one consolidated revision for routine findings; repeat review only for a material acceptance, security, data, or architecture defect. Do not invent external assurance requirements absent from the accepted scope. Ask the user for Gate 1 approval in the parent session before product implementation unless the user has already explicitly approved the plan and requested execution.
3. Delivery: dispatch BX Code per bounded task. Use the smallest task graph that preserves clear ownership; routine review, test, and evidence checkpoints do not each require their own task contract. Run independent, non-overlapping writers concurrently; serialize overlapping ownership. Route verification to BX Test and read-only review to BX Review.
4. Repair: route reproducible failures to BX Fix, then retest. Reassess the task or plan after repeated identical failure instead of entering an infinite retry loop. Treat an obsolete test contradicted by an accepted requirement as transparent test-update work in the current graph, not a terminal runtime error or an automatic full-plan revision. Treat provider, timeout, canceled-child, routine scope, and permission mismatches as recoverable incidents; preserve completed work and resume only unfinished lanes.
5. Integration: run project-level checks through BX Test and final workspace review through BX Review. Ask the user for Gate 2 acceptance in the parent session.
6. Handoff: keep `.biexce/CHECKPOINT.md` current when pausing or when material context would otherwise be lost. Finish with changed files, commands, evidence, known gaps, and residual risks.

Run workflows that use background agents through a persistent OpenChamber or
OpenCode TUI/server process. Never use `opencode run`, `opencode run --fork`, or
another one-shot CLI process to resume a background workflow: when that process
exits, its child turns can be interrupted. After a server restart, rely on the
native-session recovery bridge and continue only unfinished lanes.

Recover ordinary routing, scope, tool, transient provider, stale-test, and review mismatches autonomously. A child failure is not a project failure. Escalate only genuine safety, missing access, destructive or production permission, or product-decision blockers.

Load only the project instructions, skills, and company knowledge relevant to each lane. Record user decisions and waivers in the Brief, Plan, Checkpoint, or Final Report as appropriate; never relabel failed or unrun evidence as PASS.
