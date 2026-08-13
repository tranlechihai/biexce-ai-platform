"""Command-line surface for the shared BIEXCE Gate 0 control plane."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys
import tempfile

from .autopilot import (
    ACTIONS,
    ControlPlaneError,
    StateValidationError,
    apply_action,
    load_state,
    resolve_project_root,
    state_path_for,
)
from .fixture import fixture_status, init_fixture, reset_fixture
from .gate0 import run_gate0_matrix
from .model_routing import (
    AGENTS,
    PROFILES,
    ModelRoutingError,
    apply_routing,
    build_profile,
    clear_fallback,
    discover_models,
    load_routing,
    model_zone,
    new_unconfigured_document,
    opencode_config_root,
    provider_readiness,
    readiness_warnings,
    referenced_provider_ids,
    routing_status,
    save_routing,
    set_fallback,
    set_primary,
    sync_native_agent_models,
    validate_routing_document,
)
from .validation import GateValidationError, arm_validator, require_project_valid, validate_project
from .workflow import (
    WorkflowStateError,
    initialize_workflow,
    load_workflow,
    resolve_blocked_workflow,
    workflow_payload,
)


def _actor() -> str:
    return getpass.getuser().strip() or "unknown"


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="as_json")


def _add_config_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config-home",
        help="BIEXCE config root; defaults to ~/.config/biexce.",
    )
    parser.add_argument(
        "--opencode-config-dir",
        help="OpenCode config root used for model inventory and runtime guard.",
    )
    _add_json(parser)


def _add_autopilot_arguments(
    parser: argparse.ArgumentParser, *, mutate: bool
) -> None:
    parser.add_argument("--project", required=True)
    _add_json(parser)
    if mutate:
        parser.add_argument("--reason")
        parser.add_argument("--session-id")
    if any(
        parser.prog.endswith(suffix)
        for suffix in (" arm", " validate", " approve")
    ):
        parser.add_argument("--config-home")
        parser.add_argument("--opencode-config-dir")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="biexce")
    commands = parser.add_subparsers(dest="command", required=True)

    quick_setup = commands.add_parser(
        "setup",
        help="Configure and apply all seven agent models in one step.",
    )
    quick_setup.add_argument(
        "--model",
        help="Default provider/model for all seven agents.",
    )
    quick_setup.add_argument(
        "--agent",
        action="append",
        default=[],
        metavar="AGENT=PROVIDER/MODEL",
        help="Override one agent; may be repeated.",
    )
    quick_setup.add_argument("--yes", action="store_true")
    _add_config_arguments(quick_setup)

    quick_status = commands.add_parser(
        "status",
        help="Show routing, runtime guard, provider and Autopilot status.",
    )
    quick_status.add_argument("--project", default=".")
    _add_config_arguments(quick_status)

    self_test = commands.add_parser(
        "self-test",
        help="Run an offline control-plane smoke test and clean its fixture.",
    )
    self_test.add_argument(
        "--live-inference",
        action="store_true",
        help="Also probe Bifrost and the configured local model.",
    )
    _add_config_arguments(self_test)

    quick_auto = commands.add_parser(
        "auto",
        help="Short Autopilot switch; advanced commands remain under autopilot.",
    )
    quick_auto_actions = quick_auto.add_subparsers(dest="action", required=True)
    for action in ("status", "check", "on", "start", "pause", "off"):
        action_parser = quick_auto_actions.add_parser(action)
        action_parser.add_argument("--project", default=".")
        if action in {"on", "start", "pause", "off"}:
            action_parser.add_argument("--reason")
        if action == "start":
            action_parser.add_argument("--session")
        _add_config_arguments(action_parser)

    autopilot = commands.add_parser("autopilot")
    autopilot_actions = autopilot.add_subparsers(dest="action", required=True)
    status = autopilot_actions.add_parser("status")
    _add_autopilot_arguments(status, mutate=False)
    validate = autopilot_actions.add_parser("validate")
    _add_autopilot_arguments(validate, mutate=False)
    for action in ACTIONS:
        action_parser = autopilot_actions.add_parser(action)
        _add_autopilot_arguments(action_parser, mutate=True)
    approve = autopilot_actions.add_parser("approve")
    _add_autopilot_arguments(approve, mutate=True)
    approve.add_argument("--gate", type=int, choices=(1, 2), required=True)
    resolve = autopilot_actions.add_parser(
        "resolve",
        help="Authorize an audited recovery for a blocked task.",
    )
    resolve.add_argument("--project", required=True)
    resolve.add_argument(
        "--action",
        dest="resolution",
        choices=("manual-fix",),
        required=True,
    )
    resolve.add_argument("--reason", required=True)
    _add_json(resolve)

    model = commands.add_parser("model")
    model_actions = model.add_subparsers(dest="action", required=True)
    setup = model_actions.add_parser("setup")
    setup.add_argument("--profile", choices=PROFILES, default="local-only")
    setup.add_argument("--cloud-model")
    setup.add_argument("--yes", action="store_true")
    _add_config_arguments(setup)
    model_list = model_actions.add_parser("list")
    _add_config_arguments(model_list)
    model_status = model_actions.add_parser("status")
    model_status.add_argument("--all", action="store_true")
    _add_config_arguments(model_status)
    model_set = model_actions.add_parser("set")
    model_set.add_argument("agent", choices=AGENTS)
    model_set.add_argument("model")
    _add_config_arguments(model_set)
    model_validate = model_actions.add_parser("validate")
    _add_config_arguments(model_validate)
    model_apply = model_actions.add_parser("apply")
    _add_config_arguments(model_apply)
    fallback = model_actions.add_parser("fallback")
    fallback_actions = fallback.add_subparsers(dest="fallback_action", required=True)
    fallback_set = fallback_actions.add_parser("set")
    fallback_set.add_argument("agent", choices=AGENTS)
    fallback_set.add_argument("model")
    fallback_set.add_argument("--confirm-cross-zone", action="store_true")
    _add_config_arguments(fallback_set)
    fallback_clear = fallback_actions.add_parser("clear")
    fallback_clear.add_argument("agent", choices=AGENTS)
    _add_config_arguments(fallback_clear)

    profile = commands.add_parser("profile")
    profile_actions = profile.add_subparsers(dest="action", required=True)
    profile_list = profile_actions.add_parser("list")
    _add_config_arguments(profile_list)
    profile_use = profile_actions.add_parser("use")
    profile_use.add_argument("profile", choices=PROFILES)
    profile_use.add_argument("--cloud-model")
    profile_use.add_argument("--yes", action="store_true")
    _add_config_arguments(profile_use)

    fixture = commands.add_parser("fixture")
    fixture_actions = fixture.add_subparsers(dest="action", required=True)
    fixture_init = fixture_actions.add_parser("init")
    fixture_init.add_argument("--project", required=True)
    _add_json(fixture_init)
    fixture_reset = fixture_actions.add_parser("reset")
    fixture_reset.add_argument("--project", required=True)
    fixture_reset.add_argument("--confirm-reset", required=True)
    _add_json(fixture_reset)
    fixture_show = fixture_actions.add_parser("status")
    fixture_show.add_argument("--project", required=True)
    _add_json(fixture_show)

    doctor = commands.add_parser("doctor")
    doctor.add_argument("--project")
    _add_config_arguments(doctor)

    gate0 = commands.add_parser("gate0")
    gate0_actions = gate0.add_subparsers(dest="action", required=True)
    matrix = gate0_actions.add_parser("matrix")
    matrix.add_argument("--project", required=True)
    matrix.add_argument("--server-evidence")
    matrix.add_argument("--live-inference", action="store_true")
    _add_config_arguments(matrix)
    return parser


def _print(payload: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _state_payload(state, state_path: Path, changed: bool) -> dict[str, object]:
    return {
        "ok": True,
        "project_root": str(state.project_root),
        "state_path": str(state_path),
        "mode": state.mode,
        "revision": state.revision,
        "persisted": state.persisted,
        "changed": changed,
        "updated_at_utc": state.updated_at_utc,
        "updated_by": state.updated_by,
        "reason": state.reason,
        "source": state.source,
        "action": state.action,
        "session_id": state.session_id,
        "workflow": workflow_payload(load_workflow(state.project_root)),
        "workflow_policy": _workflow_policy_summary(state.project_root),
        "scheduler": _scheduler_summary(state.project_root),
    }


def _workflow_policy_summary(project_root: Path) -> dict[str, object] | None:
    path = project_root / ".biexce" / "state" / "AUTOPILOT_POLICY.json"
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "$schema", "schema_version", "project_root", "requested_profile",
            "effective_profile", "source", "risk_flags", "policy",
            "driver_status", "last_terminal_reason", "updated_at_utc", "updated_by",
        }
        if not isinstance(document, dict) or set(document) != required:
            raise ValueError("properties mismatch")
        if document.get("schema_version") != 1:
            raise ValueError("schema version is unsupported")
        if Path(document["project_root"]).resolve() != project_root.resolve():
            raise ValueError("policy belongs to another project")
        return {
            "path": str(path),
            "requested_profile": document["requested_profile"],
            "effective_profile": document["effective_profile"],
            "source": document["source"],
            "risk_flags": document["risk_flags"],
            "driver_status": document["driver_status"],
            "last_terminal_reason": document["last_terminal_reason"],
        }
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return {"path": str(path), "error": str(error)}


def _scheduler_summary(project_root: Path) -> dict[str, object] | None:
    path = project_root / ".biexce" / "state" / "AUTOPILOT_SCHEDULER.json"
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        tasks = document["tasks"]
        if not isinstance(tasks, dict):
            raise ValueError("tasks must be an object")
        active = []
        ready = []
        blocked = []
        for task_id, task in sorted(tasks.items()):
            if not isinstance(task, dict):
                raise ValueError(f"task {task_id} must be an object")
            item = {
                "task_id": task_id,
                "phase": task.get("phase"),
                "status": task.get("status"),
                "agent": task.get("agent"),
                "model": task.get("model"),
                "job_id": task.get("active_job_id") or task.get("last_job_id"),
            }
            if task.get("status") == "RUNNING":
                active.append(item)
            elif task.get("status") == "READY":
                ready.append(item)
            elif task.get("status") == "BLOCKED":
                blocked.append(item)
        return {
            "path": str(path),
            "revision": document.get("revision"),
            "wip_limit": document.get("wip_limit"),
            "active": active,
            "ready": ready,
            "blocked": blocked,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as error:
        return {"path": str(path), "error": str(error)}


def _print_state(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        _print(payload, as_json=True)
        return
    persistence = "persisted" if payload["persisted"] else "default"
    print(f"Project: {payload['project_root']}")
    print(f"Autopilot: {payload['mode']} ({persistence})")
    print(f"Revision: {payload['revision']}")
    print(f"Session: {payload['session_id'] or '-'}")
    print(f"State file: {payload['state_path']}")
    print(f"Reason: {payload['reason']}")
    workflow = payload.get("workflow")
    if isinstance(workflow, dict):
        print(f"Workflow: {workflow['phase']}")
        print(f"Next agent: {workflow['expected_agent'] or '-'}")
        print(f"Current task: {workflow['current_task_id'] or '-'}")
        print(f"Human gates: G1={workflow['gate_1']} G2={workflow['gate_2']}")
    policy = payload.get("workflow_policy")
    if isinstance(policy, dict):
        if policy.get("error"):
            print(f"Workflow profile: ERROR ({policy['error']})")
        else:
            print(
                f"Workflow profile: {policy['effective_profile']} | "
                f"driver={policy['driver_status']} | source={policy['source']}"
            )
    scheduler = payload.get("scheduler")
    if isinstance(scheduler, dict):
        if scheduler.get("error"):
            print(f"Scheduler: ERROR ({scheduler['error']})")
        else:
            print(
                "Scheduler: "
                f"active={len(scheduler['active'])} "
                f"ready={len(scheduler['ready'])} "
                f"blocked={len(scheduler['blocked'])} "
                f"WIP={scheduler['wip_limit']}"
            )
            for job in scheduler["active"]:
                print(
                    f"  RUNNING {job['task_id']} {job['phase']} "
                    f"{job['agent'] or '-'} {job['model'] or '-'}"
                )


def _handle_autopilot(arguments: argparse.Namespace) -> int:
    project_root = resolve_project_root(arguments.project)
    if arguments.action == "validate":
        report = validate_project(
            project_root,
            config_home=arguments.config_home,
            opencode_root=arguments.opencode_config_dir,
        )
        _print(report.to_document(), as_json=arguments.as_json)
        return 0 if report.ok else 2
    state_path = state_path_for(project_root)
    if arguments.action == "resolve":
        state = load_state(project_root)
        if state.mode != "RUNNING":
            raise WorkflowStateError(
                "Blocked workflow recovery requires Autopilot RUNNING, "
                f"found {state.mode}."
            )
        _workflow, recovery = resolve_blocked_workflow(
            project_root,
            action=arguments.resolution,
            actor=_actor(),
            reason=arguments.reason,
        )
        payload = _state_payload(state, state_path, True)
        payload["recovery"] = recovery
        if arguments.as_json:
            _print(payload, as_json=True)
        else:
            _print_state(payload, False)
            print(
                "Runtime request queued: "
                f"{recovery['command']} ({recovery['task_id']})"
            )
            print(
                "Request: "
                f"{project_root / '.biexce' / 'state' / 'AUTOPILOT_COMMAND.json'}"
            )
        return 0
    if arguments.action == "approve":
        raise WorkflowStateError(
            "Human Gate approval is available only inside OpenCode Desktop or "
            "TUI. The CLI cannot approve or bypass a Gate."
        )
    if arguments.action == "status":
        state = load_state(project_root)
        changed = False
    else:
        validator = None
        if arguments.action == "arm":
            validator = arm_validator(
                config_home=arguments.config_home,
                opencode_root=arguments.opencode_config_dir,
            )
        state, changed = apply_action(
            project_root,
            arguments.action,
            actor=_actor(),
            reason=arguments.reason
            or f"CLI request: autopilot {arguments.action}",
            source="cli",
            session_id=arguments.session_id,
            arm_validator=validator,
        )
        if arguments.action == "start":
            initialize_workflow(project_root, actor=_actor())
    _print_state(_state_payload(state, state_path, changed), arguments.as_json)
    return 0


def _inventory(arguments: argparse.Namespace) -> tuple[list[str], list[str]]:
    return discover_models(arguments.opencode_config_dir, include_runtime=True)


def _unique_warnings(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group))


def _document_readiness(
    document: dict[str, object], arguments: argparse.Namespace
) -> tuple[list[dict[str, object]], list[str]]:
    providers, inspection_warnings = provider_readiness(
        referenced_provider_ids(document), arguments.opencode_config_dir
    )
    return providers, _unique_warnings(
        inspection_warnings, readiness_warnings(providers)
    )


def _routing_table(document: dict[str, object]) -> list[dict[str, object]]:
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    table = []
    for agent in AGENTS:
        binding = bindings[agent]
        assert isinstance(binding, dict)
        primary = binding["primary"]
        table.append(
            {
                "agent": agent,
                "primary": primary,
                "primary_zone": model_zone(primary)
                if isinstance(primary, str)
                else None,
                "fallbacks": binding["fallbacks"],
                "source": binding["source"],
            }
        )
    return table


def _confirm_profile(
    document: dict[str, object], arguments: argparse.Namespace
) -> None:
    if arguments.yes:
        return
    if not sys.stdin.isatty():
        raise ModelRoutingError("Non-interactive profile setup requires --yes.")
    _print(_routing_table(document), as_json=False)
    answer = input("Apply these seven explicit bindings? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise ModelRoutingError("Model setup cancelled; routing was not changed.")


def _apply_document(
    document: dict[str, object], arguments: argparse.Namespace
) -> dict[str, object]:
    models, warnings = _inventory(arguments)
    providers, provider_warnings = _document_readiness(document, arguments)
    warnings = _unique_warnings(warnings, provider_warnings)
    errors = validate_routing_document(document, available_models=models or None)
    if errors:
        raise ModelRoutingError("; ".join(errors))
    save_routing(document, arguments.config_home)
    native_path = sync_native_agent_models(
        document, arguments.opencode_config_dir
    )
    if native_path is None:
        warnings.append(
            "OpenCode config not found; native agent model bindings were not written."
        )
    path = apply_routing(
        actor=_actor(),
        config_home=arguments.config_home,
        available_models=models or None,
    )
    return {
        "ok": True,
        "profile": document["active_profile"],
        "applied_path": str(path),
        "opencode_config_path": str(native_path) if native_path else None,
        "bindings": _routing_table(document),
        "providers": providers,
        "warnings": warnings,
    }


def _parse_agent_overrides(values: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ModelRoutingError(
                "--agent must use AGENT=PROVIDER/MODEL, for example "
                "bx-code=openai/gpt-5.6-sol-fast."
            )
        agent, model = (part.strip() for part in value.split("=", 1))
        if agent not in AGENTS:
            raise ModelRoutingError(f"Unknown BIEXCE agent: {agent}")
        if not model:
            raise ModelRoutingError(f"{agent}: model cannot be empty.")
        if agent in overrides:
            raise ModelRoutingError(f"Duplicate --agent override: {agent}")
        overrides[agent] = model
    return overrides


def _model_selection(raw: str, models: list[str]) -> str:
    selected = raw.strip()
    if selected.isdigit():
        index = int(selected) - 1
        if index < 0 or index >= len(models):
            raise ModelRoutingError("Model number is outside the displayed list.")
        return models[index]
    return selected


def _interactive_model_setup(arguments: argparse.Namespace) -> tuple[str, dict[str, str]]:
    if not sys.stdin.isatty():
        raise ModelRoutingError(
            "Non-interactive setup requires --model provider/model and --yes."
        )
    models, warnings = _inventory(arguments)
    if not models:
        raise ModelRoutingError(
            "No OpenCode models were discovered. Run /connect and /models first."
        )
    print("Available OpenCode models:")
    for index, model in enumerate(models, start=1):
        print(f"  {index:>2}. {model}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    default = _model_selection(
        input("Default model for all 7 agents (number or provider/model): "),
        models,
    )
    overrides: dict[str, str] = {}
    customize = input("Customize individual agents? [y/N] ").strip().lower()
    if customize in {"y", "yes"}:
        print("Press Enter to keep the default model.")
        for agent in AGENTS:
            value = input(f"  {agent} [{default}]: ").strip()
            if value:
                overrides[agent] = _model_selection(value, models)
    return default, overrides


def _manual_routing_document(
    default_model: str,
    overrides: dict[str, str],
) -> dict[str, object]:
    document = new_unconfigured_document(_actor())
    document["revision"] = 1
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    for agent in AGENTS:
        bindings[agent] = {
            "primary": overrides.get(agent, default_model),
            "fallbacks": [],
            "source": "manual",
            "confirmed_cross_zone_fallbacks": [],
        }
    return document


def _handle_quick_setup(arguments: argparse.Namespace) -> int:
    overrides = _parse_agent_overrides(arguments.agent)
    default_model = arguments.model
    if default_model is None:
        if overrides:
            raise ModelRoutingError(
                "Quick setup needs --model as the default for all seven agents."
            )
        default_model, overrides = _interactive_model_setup(arguments)
    document = _manual_routing_document(default_model, overrides)
    _confirm_profile(document, arguments)
    result = _apply_document(document, arguments)
    result["next"] = "Restart OpenCode, select an agent with Tab, then run biexce status."
    _print(result, as_json=arguments.as_json)
    return 0


def _handle_model(arguments: argparse.Namespace) -> int:
    if arguments.action == "list":
        models, warnings = _inventory(arguments)
        provider_ids = {model.split("/", 1)[0] for model in models}
        providers, inspection_warnings = provider_readiness(
            provider_ids, arguments.opencode_config_dir
        )
        provider_map = {item["provider"]: item for item in providers}
        model_readiness = []
        for model in models:
            provider_id = model.split("/", 1)[0]
            readiness = provider_map[provider_id]
            model_readiness.append(
                {
                    "id": model,
                    "provider": provider_id,
                    "catalog_status": "DISCOVERED",
                    "credential_status": readiness["credential_status"],
                    "inference_status": readiness["inference_status"],
                }
            )
        warnings = _unique_warnings(
            warnings, inspection_warnings, readiness_warnings(providers)
        )
        _print(
            {
                "models": models,
                "model_readiness": model_readiness,
                "providers": providers,
                "warnings": warnings,
            },
            as_json=arguments.as_json,
        )
        return 0
    if arguments.action == "status":
        status = routing_status(arguments.config_home)
        providers, warnings = _document_readiness(
            {"agents": status.get("agents", {})}, arguments
        )
        status["providers"] = providers
        status["warnings"] = warnings
        _print(status, as_json=arguments.as_json)
        return 0 if status["valid"] and status["applied"] else 2
    if arguments.action == "setup":
        document = build_profile(
            arguments.profile, actor=_actor(), cloud_model=arguments.cloud_model
        )
        _confirm_profile(document, arguments)
        result = _apply_document(document, arguments)
        _print(result, as_json=arguments.as_json)
        return 0
    if arguments.action == "set":
        document = set_primary(
            arguments.agent,
            arguments.model,
            actor=_actor(),
            config_home=arguments.config_home,
        )
        _print(
            {
                "ok": True,
                "applied": False,
                "next": "biexce model validate; biexce model apply",
                "bindings": _routing_table(document),
            },
            as_json=arguments.as_json,
        )
        return 0
    if arguments.action == "fallback":
        if arguments.fallback_action == "set":
            document = set_fallback(
                arguments.agent,
                arguments.model,
                actor=_actor(),
                confirm_cross_zone=arguments.confirm_cross_zone,
                config_home=arguments.config_home,
            )
        else:
            document = clear_fallback(
                arguments.agent,
                actor=_actor(),
                config_home=arguments.config_home,
            )
        _print(
            {"ok": True, "applied": False, "bindings": _routing_table(document)},
            as_json=arguments.as_json,
        )
        return 0
    if arguments.action == "validate":
        document = load_routing(arguments.config_home)
        models, warnings = _inventory(arguments)
        providers, provider_warnings = _document_readiness(document, arguments)
        errors = validate_routing_document(
            document, available_models=models or None
        )
        payload = {
            "ok": not errors,
            "errors": errors,
            "providers": providers,
            "warnings": _unique_warnings(warnings, provider_warnings),
        }
        _print(payload, as_json=arguments.as_json)
        return 0 if not errors else 2
    if arguments.action == "apply":
        document = load_routing(arguments.config_home)
        result = _apply_document(document, arguments)
        _print(result, as_json=arguments.as_json)
        return 0
    raise ModelRoutingError(f"Unsupported model action: {arguments.action}")


def _handle_profile(arguments: argparse.Namespace) -> int:
    if arguments.action == "list":
        payload = {
            "profiles": [
                {
                    "name": "local-only",
                    "ready": True,
                    "description": "All seven agents use the approved local model.",
                },
                {
                    "name": "hybrid",
                    "ready": True,
                    "description": (
                        "Optional preset: Director/Plan use the selected cloud primary "
                        "with confirmed local fallback; other agents use local."
                    ),
                },
                {
                    "name": "cloud-strong",
                    "ready": True,
                    "description": (
                        "All seven agents use cloud primary plus confirmed local fallback; "
                        "requires --cloud-model."
                    ),
                },
            ]
        }
        _print(payload, as_json=arguments.as_json)
        return 0
    document = build_profile(
        arguments.profile, actor=_actor(), cloud_model=arguments.cloud_model
    )
    _confirm_profile(document, arguments)
    result = _apply_document(document, arguments)
    _print(result, as_json=arguments.as_json)
    return 0


def _handle_fixture(arguments: argparse.Namespace) -> int:
    if arguments.action == "init":
        target = init_fixture(arguments.project)
    elif arguments.action == "reset":
        target = reset_fixture(
            arguments.project, confirmation=arguments.confirm_reset
        )
    else:
        target = Path(arguments.project).expanduser().resolve()
    payload = fixture_status(target)
    payload["ok"] = True
    _print(payload, as_json=arguments.as_json)
    return 0


def _handle_doctor(arguments: argparse.Namespace) -> int:
    status = routing_status(arguments.config_home)
    runtime_root = opencode_config_root(arguments.opencode_config_dir)
    providers, warnings = _document_readiness(
        {"agents": status.get("agents", {})}, arguments
    )
    plugin = runtime_root / "plugins" / "biexce-control.js"
    runtime_guard = {
        "path": str(plugin),
        "present": plugin.is_file() and not plugin.is_symlink(),
        "builtin_task_permission": "deny",
        "delegate_tool": "biexce_delegate",
    }
    payload: dict[str, object] = {
        "routing": status,
        "runtime_guard": runtime_guard,
        "providers": providers,
        "warnings": warnings,
    }
    ok = bool(status["valid"] and status["applied"] and runtime_guard["present"])
    if arguments.project:
        report = require_project_valid(
            arguments.project,
            config_home=arguments.config_home,
            opencode_root=runtime_root,
        )
        payload["project"] = report.to_document()
    payload["ok"] = ok
    _print(payload, as_json=arguments.as_json)
    return 0 if ok else 2


def _handle_quick_status(arguments: argparse.Namespace) -> int:
    routing = routing_status(arguments.config_home)
    runtime_root = opencode_config_root(arguments.opencode_config_dir)
    plugin = runtime_root / "plugins" / "biexce-control.js"
    guard_present = plugin.is_file() and not plugin.is_symlink()
    state = load_state(resolve_project_root(arguments.project))
    bindings = routing.get("agents", {})
    configured_count = 0
    if isinstance(bindings, dict):
        configured_count = sum(
            1
            for agent in AGENTS
            if isinstance(bindings.get(agent), dict)
            and isinstance(bindings[agent].get("primary"), str)
        )
    providers, warnings = _document_readiness(
        {"agents": bindings if isinstance(bindings, dict) else {}}, arguments
    )
    ok = bool(
        routing.get("valid")
        and routing.get("applied")
        and configured_count == len(AGENTS)
        and guard_present
    )
    payload = {
        "ok": ok,
        "routing": routing,
        "configured_agents": configured_count,
        "runtime_guard": {"present": guard_present, "path": str(plugin)},
        "providers": providers,
        "warnings": warnings,
        "autopilot": _state_payload(
            state, state_path_for(state.project_root), changed=False
        ),
    }
    if arguments.as_json:
        _print(payload, as_json=True)
    else:
        print("BIEXCE Status")
        print(
            f"Routing: {'READY' if routing.get('valid') and routing.get('applied') else 'NOT READY'} "
            f"({configured_count}/7 agents)"
        )
        if isinstance(bindings, dict):
            for agent in AGENTS:
                binding = bindings.get(agent)
                primary = binding.get("primary") if isinstance(binding, dict) else None
                print(f"  {agent:<11} {primary or '-'}")
        print(f"Runtime guard: {'READY' if guard_present else 'MISSING'}")
        print(f"Autopilot: {state.mode}")
        workflow = payload["autopilot"].get("workflow")
        if isinstance(workflow, dict):
            print(
                f"Workflow: {workflow['phase']} | "
                f"next={workflow['expected_agent'] or '-'} | "
                f"task={workflow['current_task_id'] or '-'}"
            )
        policy = payload["autopilot"].get("workflow_policy")
        if isinstance(policy, dict):
            if policy.get("error"):
                print(f"Workflow profile: ERROR ({policy['error']})")
            else:
                print(
                    f"Workflow profile: {policy['effective_profile']} | "
                    f"driver={policy['driver_status']} | source={policy['source']}"
                )
        scheduler = payload["autopilot"].get("scheduler")
        if isinstance(scheduler, dict) and not scheduler.get("error"):
            print(
                "Scheduler: "
                f"active={len(scheduler['active'])} "
                f"ready={len(scheduler['ready'])} "
                f"blocked={len(scheduler['blocked'])} "
                f"WIP={scheduler['wip_limit']}"
            )
            for job in scheduler["active"]:
                print(
                    f"  RUNNING {job['task_id']} {job['phase']} "
                    f"{job['agent'] or '-'} {job['model'] or '-'}"
                )
        print(f"Project: {state.project_root}")
        for provider in providers:
            print(
                f"Provider {provider.get('provider') or '-'}: "
                f"{provider.get('status')} | "
                f"credential={provider.get('credential_status')} | "
                f"inference={provider.get('inference_status')}"
            )
        for warning in warnings:
            print(f"WARNING: {warning}")
    return 0 if ok else 2


def _handle_quick_auto(arguments: argparse.Namespace) -> int:
    project_root = resolve_project_root(arguments.project)
    if arguments.action == "check":
        report = validate_project(
            project_root,
            config_home=arguments.config_home,
            opencode_root=arguments.opencode_config_dir,
        )
        _print(report.to_document(), as_json=arguments.as_json)
        return 0 if report.ok else 2

    steps: list[str] = []
    state = load_state(project_root)
    changed = False
    if arguments.action == "status":
        pass
    elif arguments.action in {"on", "start"}:
        reason = arguments.reason or "CLI quick start"
        if state.mode == "OFF":
            state, changed = apply_action(
                project_root,
                "on",
                actor=_actor(),
                reason=reason,
                source="cli",
            )
            steps.append("ON_IDLE")
        if state.mode == "ON_IDLE":
            state, arm_changed = apply_action(
                project_root,
                "arm",
                actor=_actor(),
                reason=reason,
                source="cli",
                arm_validator=arm_validator(
                    config_home=arguments.config_home,
                    opencode_root=arguments.opencode_config_dir,
                ),
            )
            changed = changed or arm_changed
            steps.extend(("RUNTIME_VALIDATED", "ARMED"))
        if state.mode in {"ARMED", "PAUSED"}:
            state, start_changed = apply_action(
                project_root,
                "start",
                actor=_actor(),
                reason=reason,
                source="cli",
                session_id=getattr(arguments, "session", None),
            )
            changed = changed or start_changed
            steps.append("RUNNING")
        elif state.mode == "RUNNING":
            steps.append("RUNNING (unchanged)")
        workflow, workflow_changed = initialize_workflow(
            project_root, actor=_actor()
        )
        changed = changed or workflow_changed
        steps.append(f"WORKFLOW:{workflow.phase}")
    else:
        action = arguments.action
        state, changed = apply_action(
            project_root,
            action,
            actor=_actor(),
            reason=arguments.reason or f"CLI quick auto {action}",
            source="cli",
        )
        steps.append(state.mode)

    payload = _state_payload(
        state, state_path_for(project_root), changed=changed
    )
    payload["steps"] = steps
    if arguments.as_json:
        _print(payload, as_json=True)
    else:
        _print_state(payload, as_json=False)
        if steps:
            print(f"Steps: {' -> '.join(steps)}")
    return 0


def _handle_self_test(arguments: argparse.Namespace) -> int:
    routing = routing_status(arguments.config_home)
    runtime_root = opencode_config_root(arguments.opencode_config_dir)
    plugin = runtime_root / "plugins" / "biexce-control.js"
    if not routing.get("valid") or not routing.get("applied"):
        raise ModelRoutingError(
            "Seven-agent routing is not valid and applied; run biexce setup first."
        )
    if not plugin.is_file() or plugin.is_symlink():
        raise ControlPlaneError(
            f"BIEXCE runtime guard is missing or invalid: {plugin}"
        )

    fixture_path: str
    live_check: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="biexce-self-test-") as temporary:
        project_root = Path(temporary) / "project"
        fixture_path = str(project_root)
        init_fixture(project_root)
        transitions: list[str] = ["OFF"]
        state, _ = apply_action(
            project_root,
            "on",
            actor=_actor(),
            reason="BIEXCE offline self-test",
        )
        transitions.append(state.mode)
        state, _ = apply_action(
            project_root,
            "arm",
            actor=_actor(),
            reason="BIEXCE offline self-test",
            arm_validator=arm_validator(
                config_home=arguments.config_home,
                opencode_root=runtime_root,
            ),
        )
        transitions.append(state.mode)
        state, _ = apply_action(
            project_root,
            "start",
            actor=_actor(),
            reason="BIEXCE offline self-test",
            session_id="self-test",
        )
        transitions.append(state.mode)
        workflow, _ = initialize_workflow(project_root, actor=_actor())
        if workflow.phase != "EXPLORE" or workflow.expected_agent != "bx-explore":
            raise WorkflowStateError("Offline workflow did not initialize at EXPLORE.")
        state, _ = apply_action(
            project_root,
            "pause",
            actor=_actor(),
            reason="BIEXCE offline self-test",
        )
        transitions.append(state.mode)
        state, _ = apply_action(
            project_root,
            "off",
            actor=_actor(),
            reason="BIEXCE offline self-test",
        )
        transitions.append(state.mode)
        if arguments.live_inference:
            matrix = run_gate0_matrix(
                project_root,
                config_home=arguments.config_home,
                opencode_root=runtime_root,
                live_inference=True,
            )
            live_check = next(
                check
                for check in matrix["checks"]
                if check["name"] == "gateway_to_model"
            )

    live_status = live_check["status"] if live_check else "SKIPPED"
    ok = live_status in {"PASS", "SKIPPED"}
    payload = {
        "ok": ok,
        "routing": "PASS",
        "runtime_guard": "PASS",
        "autopilot_state_chain": "PASS",
        "autopilot_workflow": "PASS (EXPLORE -> bx-explore)",
        "transitions": transitions,
        "fixture_removed": not Path(fixture_path).exists(),
        "live_inference": live_check
        or "SKIPPED (rerun with --live-inference on VPN)",
    }
    _print(payload, as_json=arguments.as_json)
    return 0 if ok else 3


def _handle_gate0(arguments: argparse.Namespace) -> int:
    payload = run_gate0_matrix(
        arguments.project,
        config_home=arguments.config_home,
        opencode_root=arguments.opencode_config_dir,
        server_evidence=arguments.server_evidence,
        live_inference=arguments.live_inference,
    )
    _print(payload, as_json=arguments.as_json)
    return 0 if payload["ok"] else 3


def _print_error(error: ControlPlaneError, *, as_json: bool) -> None:
    fail_closed = isinstance(error, (StateValidationError, GateValidationError))
    payload: dict[str, object] = {
        "ok": False,
        "effective_mode": "OFF" if fail_closed else None,
        "error": str(error),
    }
    if isinstance(error, GateValidationError):
        payload["validation"] = error.report.to_document()
    if as_json:
        print(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return
    if fail_closed:
        print("Autopilot: OFF (fail-closed)", file=sys.stderr)
    print(f"ERROR: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "setup":
            return _handle_quick_setup(arguments)
        if arguments.command == "status":
            return _handle_quick_status(arguments)
        if arguments.command == "self-test":
            return _handle_self_test(arguments)
        if arguments.command == "auto":
            return _handle_quick_auto(arguments)
        if arguments.command == "autopilot":
            return _handle_autopilot(arguments)
        if arguments.command == "model":
            return _handle_model(arguments)
        if arguments.command == "profile":
            return _handle_profile(arguments)
        if arguments.command == "fixture":
            return _handle_fixture(arguments)
        if arguments.command == "doctor":
            return _handle_doctor(arguments)
        if arguments.command == "gate0":
            return _handle_gate0(arguments)
        raise ControlPlaneError(f"Unsupported command: {arguments.command}")
    except ControlPlaneError as error:
        _print_error(error, as_json=getattr(arguments, "as_json", False))
        return 2
