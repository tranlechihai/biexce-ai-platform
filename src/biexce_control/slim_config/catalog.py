"""Static BIEXCE role catalog for generated OpenCode + Slim config."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_GLOBAL = REPOSITORY_ROOT / "src" / "global"
SLIM_SOURCE = SOURCE_GLOBAL / "slim"
PROMPT_SOURCE = SLIM_SOURCE / "prompts"
PLUGIN_SOURCE = SLIM_SOURCE / "plugins"
RUNTIME_SOURCE = SLIM_SOURCE / "runtime"
COMMAND_SOURCE = SLIM_SOURCE / "commands"
TEMPLATE_SOURCE = SLIM_SOURCE / "templates"
COMPATIBILITY_PATH = SLIM_SOURCE / "compatibility.json"

ROLE_ORDER = (
    "bx-director",
    "bx-plan",
    "bx-explore",
    "bx-code",
    "bx-fix",
    "bx-test",
    "bx-review",
)

SLIM_IDS = {
    "bx-director": "orchestrator",
    "bx-plan": "bx-plan",
    "bx-explore": "bx-explore",
    "bx-code": "bx-code",
    "bx-fix": "bx-fix",
    "bx-test": "bx-test",
    "bx-review": "bx-review",
}

DISPLAY_NAMES = {
    "bx-director": "BX-Director",
    "bx-plan": "BX-Plan",
    "bx-explore": "BX-Explore",
    "bx-code": "BX-Code",
    "bx-fix": "BX-Fix",
    "bx-test": "BX-Test",
    "bx-review": "BX-Review",
}

SKILLS = {
    "bx-director": (
        "biexce-delivery",
        "task-spec",
        "review-verdict",
        "definition-of-done",
        "evidence-format",
    ),
    "bx-plan": (
        "task-spec",
        "acceptance-criteria",
        "system-design",
        "adr",
        "api-contract",
    ),
    "bx-explore": ("codebase-brief", "evidence-format"),
    "bx-code": (
        "task-spec",
        "definition-of-done",
        "evidence-format",
        "secure-coding",
    ),
    "bx-fix": (
        "task-spec",
        "definition-of-done",
        "evidence-format",
        "secure-coding",
    ),
    "bx-test": (
        "evidence-format",
        "test-strategy",
        "unit-integration-e2e",
        "regression",
        "definition-of-done",
    ),
    "bx-review": (
        "review-verdict",
        "definition-of-done",
        "evidence-format",
        "security-policy",
        "secure-coding",
    ),
}

DESCRIPTIONS = {
    "bx-plan": "Implementation planning and task-contract specialist.",
    "bx-explore": "Read-only codebase discovery specialist.",
    "bx-code": "Bounded implementation specialist.",
    "bx-fix": "Evidence-driven defect repair specialist.",
    "bx-test": "Independent test and verification specialist.",
    "bx-review": "Read-only plan, diff, and integration reviewer.",
}

ROUTING_BLOCKS = {
    "bx-plan": (
        "Create or revise implementation-ready plans and bounded task "
        "contracts. Do not implement product source."
    ),
    "bx-explore": (
        "Inspect and map the codebase. Use for discovery and evidence "
        "gathering; never delegate implementation."
    ),
    "bx-code": (
        "Implement a bounded objective with clear ownership and "
        "proportionate focused checks."
    ),
    "bx-fix": (
        "Repair a reproducible failure from supplied evidence with the "
        "smallest coherent change."
    ),
    "bx-test": (
        "Create or run tests and return honest PASS, FAIL, or INCONCLUSIVE "
        "evidence. Do not repair product source."
    ),
    "bx-review": (
        "Review a plan or completed workspace read-only and return findings "
        "with evidence."
    ),
}

EXPECTED_PROMPTS = {
    "orchestrator_append.md",
    "bx-plan.md",
    "bx-explore.md",
    "bx-code.md",
    "bx-fix.md",
    "bx-test.md",
    "bx-review.md",
}

EXPECTED_PLUGINS = {"biexce-recovery.js", "biexce-role-access.js"}
EXPECTED_RUNTIME = {"recovery-core.js", "role-access.js"}
EXPECTED_COMMANDS = {"bx-auto.md"}
EXPECTED_TEMPLATES = {
    "PROJECT_BRIEF.md",
    "CODEBASE_BRIEF.md",
    "MASTER_PLAN.md",
    "TASK.md",
    "CHECKPOINT.md",
    "FINAL_REPORT.md",
}
