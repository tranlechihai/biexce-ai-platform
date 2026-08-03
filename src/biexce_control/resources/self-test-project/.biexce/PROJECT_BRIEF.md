# Clean Calculator Fixture

Project ID: biexce-self-test-calculator

## Goal

Build a tiny, deterministic Python calculator through three sequential tasks so
the BIEXCE Autopilot control plane can be validated without network, Git, deploy,
or production data.

## Runtime

- Python 3 standard library only.
- Verification command: `python -m unittest discover -s tests -v`.
- No external packages or services.

## Boundaries

- Work only inside this fixture.
- Git operations and deployment are forbidden.
- Human Gate 1 and Gate 2 remain mandatory.
