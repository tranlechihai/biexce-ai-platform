# Master Plan — Clean Calculator Fixture

Project ID: biexce-self-test-calculator
WIP limit: 1
Fix cap: 3
Reports path: .biexce/reports
Git/deploy: forbidden

## Task DAG

- t-001 — implement addition and subtraction
- t-002 — implement multiplication and guarded division; depends on t-001
- t-003 — add deterministic unit coverage; depends on t-002

## Gates

- Gate 1: a human approves this plan before source execution.
- Gate 2: a human accepts test and review evidence before completion.

## Execution

Run tasks sequentially in DAG order. Keep one active task, stop after three fix
rounds, write evidence to `.biexce/reports/`, and never run Git or deploy.
