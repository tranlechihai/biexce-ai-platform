"""Schema-first, user-managed model routing for all BIEXCE agents."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
from typing import Iterable
from urllib.parse import urlparse

from .autopilot import ControlPlaneError


AGENTS = (
    "bx-director",
    "bx-plan",
    "bx-explore",
    "bx-code",
    "bx-fix",
    "bx-test",
    "bx-review",
)

LOCAL_PROVIDER = "biexce-local"
LOCAL_MODEL = "biexce-local/vllm/DeepSeek-V4-Flash-0731"
LOCAL_VIRTUAL_KEY_ENV = "BIEXCE_LOCAL_VIRTUAL_KEY"
PROFILES = ("local-only", "hybrid", "cloud-strong")
ROUTING_SCHEMA_ID = (
    "https://schemas.biexce.local/control-plane/model-routing-v1.schema.json"
)
APPLIED_SCHEMA_ID = (
    "https://schemas.biexce.local/control-plane/"
    "model-routing-applied-v1.schema.json"
)
SCHEMA_VERSION = 1
ROUTING_FILENAME = "model-routing.json"
APPLIED_FILENAME = "model-routing.applied.json"

_ROOT_KEYS = {
    "$schema",
    "schema_version",
    "inherit_parent_model",
    "unconfigured_policy",
    "active_profile",
    "revision",
    "updated_at_utc",
    "updated_by",
    "agents",
}
_BINDING_KEYS = {
    "primary",
    "fallbacks",
    "source",
    "confirmed_cross_zone_fallbacks",
}
_MODEL_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._/@:+-]*$"
)
_ENV_REFERENCE_PATTERN = re.compile(r'^\{env:([A-Za-z_][A-Za-z0-9_]*)\}$')


class ModelRoutingError(ControlPlaneError):
    """Model routing cannot be trusted or applied."""


class ModelPolicyError(ModelRoutingError):
    """A requested binding violates an explicit routing safety policy."""


def resolve_config_reference(value: object) -> str | None:
    """Resolve the OpenCode environment-reference form used by baseURL."""

    if not isinstance(value, str) or not value:
        return None
    match = _ENV_REFERENCE_PATTERN.fullmatch(value)
    if match is None:
        return value
    return os.environ.get(match.group(1)) or None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def config_home_path(value: str | os.PathLike[str] | Path | None = None) -> Path:
    selected = value or os.environ.get("BIEXCE_CONFIG_HOME")
    if selected:
        return Path(selected).expanduser().resolve()
    return (Path.home() / ".config" / "biexce").resolve()


def routing_path_for(
    config_home: str | os.PathLike[str] | Path | None = None,
) -> Path:
    return config_home_path(config_home) / ROUTING_FILENAME


def applied_path_for(
    config_home: str | os.PathLike[str] | Path | None = None,
) -> Path:
    return config_home_path(config_home) / APPLIED_FILENAME


def parse_model_id(model: object) -> tuple[str, str]:
    if not isinstance(model, str) or not _MODEL_PATTERN.fullmatch(model):
        raise ModelRoutingError(
            "Model must use the explicit provider/model format without spaces."
        )
    provider, model_id = model.split("/", 1)
    return provider, model_id


def model_zone(model: str) -> str:
    provider, _ = parse_model_id(model)
    return "local" if provider == LOCAL_PROVIDER else "cloud"


def _atomic_write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ModelRoutingError(f"Refusing to replace symlink: {path}")
    payload = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(name)
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        json.loads(temporary_path.read_text(encoding="utf-8"))
        os.replace(temporary_path, path)
        temporary_path = None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelRoutingError(f"Cannot write {path} atomically: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _read_json(path: Path, label: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ModelRoutingError(f"{label} is missing or not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelRoutingError(f"Cannot parse {label}: {error}")
    if not isinstance(value, dict):
        raise ModelRoutingError(f"{label} root must be a JSON object.")
    return value


def new_unconfigured_document(actor: str = "unknown") -> dict[str, object]:
    return {
        "$schema": ROUTING_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "inherit_parent_model": False,
        "unconfigured_policy": "block",
        "active_profile": None,
        "revision": 0,
        "updated_at_utc": utc_timestamp(),
        "updated_by": actor or "unknown",
        "agents": {
            agent: {
                "primary": None,
                "fallbacks": [],
                "source": "manual",
                "confirmed_cross_zone_fallbacks": [],
            }
            for agent in AGENTS
        },
    }


def validate_routing_document(
    document: object,
    *,
    available_models: Iterable[str] | None = None,
    require_configured: bool = True,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["Routing root must be a JSON object."]
    if set(document) != _ROOT_KEYS:
        errors.append(
            "Routing root properties mismatch; "
            f"missing={sorted(_ROOT_KEYS - set(document))}, "
            f"extra={sorted(set(document) - _ROOT_KEYS)}."
        )
        return errors
    if document.get("$schema") != ROUTING_SCHEMA_ID:
        errors.append("Routing schema identifier is invalid.")
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append("Routing schema version is unsupported.")
    if document.get("inherit_parent_model") is not False:
        errors.append("inherit_parent_model must be false.")
    if document.get("unconfigured_policy") != "block":
        errors.append("unconfigured_policy must be 'block'.")
    active_profile = document.get("active_profile")
    if active_profile is not None and active_profile not in PROFILES:
        errors.append("active_profile is not a supported profile.")
    revision = document.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        errors.append("revision must be a non-negative integer.")
    if not isinstance(document.get("updated_at_utc"), str):
        errors.append("updated_at_utc must be a string.")
    if not isinstance(document.get("updated_by"), str) or not document[
        "updated_by"
    ].strip():
        errors.append("updated_by must be a non-empty string.")

    bindings = document.get("agents")
    if not isinstance(bindings, dict):
        errors.append("agents must be a JSON object.")
        return errors
    if set(bindings) != set(AGENTS):
        errors.append(
            "Routing must contain exactly all seven agents; "
            f"missing={sorted(set(AGENTS) - set(bindings))}, "
            f"extra={sorted(set(bindings) - set(AGENTS))}."
        )
        return errors
    inventory = set(available_models) if available_models is not None else None
    for agent in AGENTS:
        binding = bindings[agent]
        if not isinstance(binding, dict) or set(binding) != _BINDING_KEYS:
            errors.append(f"{agent}: binding properties are invalid.")
            continue
        primary = binding.get("primary")
        if primary is None:
            if require_configured:
                errors.append(f"{agent}: primary model is not configured.")
            primary_zone = None
        else:
            try:
                primary_zone = model_zone(primary)
            except ModelRoutingError as error:
                errors.append(f"{agent}: {error}")
                primary_zone = None
            if inventory is not None and primary not in inventory:
                errors.append(f"{agent}: primary model is unavailable: {primary}")
        fallbacks = binding.get("fallbacks")
        confirmations = binding.get("confirmed_cross_zone_fallbacks")
        source = binding.get("source")
        if source not in ("manual", "profile"):
            errors.append(f"{agent}: source must be manual or profile.")
        if not isinstance(fallbacks, list) or len(fallbacks) > 4:
            errors.append(f"{agent}: fallbacks must be an array of at most 4 models.")
            continue
        if len(fallbacks) != len(set(fallbacks)):
            errors.append(f"{agent}: fallback models must be unique.")
        if primary in fallbacks:
            errors.append(f"{agent}: primary cannot also be a fallback.")
        if not isinstance(confirmations, list) or any(
            not isinstance(value, str) for value in confirmations
        ):
            errors.append(
                f"{agent}: confirmed_cross_zone_fallbacks must be a string array."
            )
            confirmations = []
        if not set(confirmations).issubset(set(fallbacks)):
            errors.append(f"{agent}: confirmation references an unknown fallback.")

        for fallback in fallbacks:
            try:
                fallback_zone = model_zone(fallback)
            except ModelRoutingError as error:
                errors.append(f"{agent}: fallback {error}")
                continue
            if inventory is not None and fallback not in inventory:
                errors.append(f"{agent}: fallback model is unavailable: {fallback}")
            if (
                primary_zone is not None
                and fallback_zone != primary_zone
                and fallback not in confirmations
            ):
                errors.append(
                    f"{agent}: cross-zone fallback requires explicit confirmation: "
                    f"{fallback}"
                )

    return errors


def load_routing(
    config_home: str | os.PathLike[str] | Path | None = None,
) -> dict[str, object]:
    document = _read_json(routing_path_for(config_home), "model routing")
    structural_errors = validate_routing_document(
        document, require_configured=False
    )
    if structural_errors:
        raise ModelRoutingError("; ".join(structural_errors))
    return document


def save_routing(
    document: dict[str, object],
    config_home: str | os.PathLike[str] | Path | None = None,
) -> Path:
    errors = validate_routing_document(document, require_configured=False)
    if errors:
        raise ModelRoutingError("; ".join(errors))
    path = routing_path_for(config_home)
    _atomic_write_json(path, document)
    return path


def _updated(document: dict[str, object], actor: str) -> dict[str, object]:
    result = deepcopy(document)
    result["revision"] = int(result["revision"]) + 1
    result["updated_at_utc"] = utc_timestamp()
    result["updated_by"] = actor.strip() or "unknown"
    return result


def build_profile(
    profile: str,
    *,
    actor: str,
    cloud_model: str | None = None,
) -> dict[str, object]:
    if profile not in PROFILES:
        raise ModelRoutingError(f"Unknown profile: {profile}")
    if profile != "local-only":
        if cloud_model is None:
            raise ModelRoutingError(
                f"Profile {profile} requires --cloud-model provider/model."
            )
        if model_zone(cloud_model) != "cloud":
            raise ModelRoutingError("--cloud-model must not use biexce-local.")
    document = new_unconfigured_document(actor)
    document["active_profile"] = profile
    document["revision"] = 1
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    for agent in AGENTS:
        primary = LOCAL_MODEL
        fallbacks: list[str] = []
        confirmations: list[str] = []
        if agent in {"bx-director", "bx-plan"} and profile == "hybrid":
            primary = cloud_model or ""
            fallbacks = [LOCAL_MODEL]
            confirmations = [LOCAL_MODEL]
        elif profile == "cloud-strong":
            primary = cloud_model or ""
            fallbacks = [LOCAL_MODEL]
            confirmations = [LOCAL_MODEL]
        bindings[agent] = {
            "primary": primary,
            "fallbacks": fallbacks,
            "source": "profile",
            "confirmed_cross_zone_fallbacks": confirmations,
        }
    errors = validate_routing_document(document)
    if errors:
        raise ModelRoutingError("; ".join(errors))
    return document


def set_primary(
    agent: str,
    model: str,
    *,
    actor: str,
    config_home: str | os.PathLike[str] | Path | None = None,
) -> dict[str, object]:
    if agent not in AGENTS:
        raise ModelRoutingError(f"Unknown BIEXCE agent: {agent}")

    try:
        document = load_routing(config_home)
    except ModelRoutingError as error:
        if routing_path_for(config_home).exists():
            raise error
        document = new_unconfigured_document(actor)
    document = _updated(document, actor)
    document["active_profile"] = None
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    binding = deepcopy(bindings[agent])
    assert isinstance(binding, dict)
    binding["primary"] = model
    binding["source"] = "manual"
    binding["confirmed_cross_zone_fallbacks"] = []
    bindings[agent] = binding
    save_routing(document, config_home)
    return document


def set_fallback(
    agent: str,
    model: str,
    *,
    actor: str,
    confirm_cross_zone: bool,
    config_home: str | os.PathLike[str] | Path | None = None,
) -> dict[str, object]:
    if agent not in AGENTS:
        raise ModelRoutingError(f"Unknown BIEXCE agent: {agent}")
    document = load_routing(config_home)
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    binding = deepcopy(bindings[agent])
    assert isinstance(binding, dict)
    primary = binding.get("primary")
    if not isinstance(primary, str):
        raise ModelRoutingError(f"Configure {agent} primary before its fallback.")
    fallback_zone = model_zone(model)
    primary_zone = model_zone(primary)

    if fallback_zone != primary_zone and not confirm_cross_zone:
        raise ModelPolicyError(
            "Cross-zone fallback is blocked without --confirm-cross-zone."
        )
    document = _updated(document, actor)
    document["active_profile"] = None
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    binding["fallbacks"] = [model]
    binding["source"] = "manual"
    binding["confirmed_cross_zone_fallbacks"] = (
        [model] if fallback_zone != primary_zone else []
    )
    bindings[agent] = binding
    save_routing(document, config_home)
    return document


def clear_fallback(
    agent: str,
    *,
    actor: str,
    config_home: str | os.PathLike[str] | Path | None = None,
) -> dict[str, object]:
    if agent not in AGENTS:
        raise ModelRoutingError(f"Unknown BIEXCE agent: {agent}")
    document = _updated(load_routing(config_home), actor)
    document["active_profile"] = None
    bindings = document["agents"]
    assert isinstance(bindings, dict)
    binding = deepcopy(bindings[agent])
    assert isinstance(binding, dict)
    binding["fallbacks"] = []
    binding["confirmed_cross_zone_fallbacks"] = []
    binding["source"] = "manual"
    bindings[agent] = binding
    save_routing(document, config_home)
    return document


def _source_global_root() -> Path:
    return Path(__file__).resolve().parents[1] / "global"


def opencode_config_root(
    value: str | os.PathLike[str] | Path | None = None,
) -> Path:
    selected = value or os.environ.get("BIEXCE_OPENCODE_CONFIG_DIR")
    if selected:
        return Path(selected).expanduser().resolve()
    installed = (Path.home() / ".config" / "opencode").resolve()
    if (installed / "opencode.json").is_file():
        return installed
    return _source_global_root()


def opencode_auth_path(
    value: str | os.PathLike[str] | Path | None = None,
) -> Path:
    """Return OpenCode's per-user credential store without reading secrets."""

    selected = value or os.environ.get("BIEXCE_OPENCODE_AUTH_FILE")
    if selected:
        return Path(selected).expanduser().resolve()
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return (Path(data_home).expanduser() / "opencode" / "auth.json").resolve()
    return (Path.home() / ".local" / "share" / "opencode" / "auth.json").resolve()


def authenticated_providers(
    auth_file: str | os.PathLike[str] | Path | None = None,
) -> tuple[set[str], list[str]]:
    """Read only provider identifiers from OpenCode's credential store."""

    path = opencode_auth_path(auth_file)
    if not path.is_file():
        return set(), []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return set(), [f"Cannot inspect OpenCode credentials: {error}"]
    if not isinstance(document, dict):
        return set(), ["OpenCode credential store root is not a JSON object."]
    return {
        provider
        for provider in document
        if isinstance(provider, str) and provider.strip()
    }, []


def referenced_provider_ids(document: object) -> set[str]:
    """Collect providers referenced by primary and fallback agent bindings."""

    if not isinstance(document, dict):
        return set()
    bindings = document.get("agents")
    if not isinstance(bindings, dict):
        return set()
    providers: set[str] = set()
    for binding in bindings.values():
        if not isinstance(binding, dict):
            continue
        models: list[object] = [binding.get("primary")]
        fallbacks = binding.get("fallbacks")
        if isinstance(fallbacks, list):
            models.extend(fallbacks)
        for model in models:
            if isinstance(model, str) and _MODEL_PATTERN.fullmatch(model):
                providers.add(model.split("/", 1)[0])
    return providers


def discover_models(
    opencode_root: str | os.PathLike[str] | Path | None = None,
    *,
    include_runtime: bool = True,
) -> tuple[list[str], list[str]]:
    root = opencode_config_root(opencode_root)
    models: set[str] = set()
    warnings: list[str] = []
    config_path = root / "opencode.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            providers = config.get("provider", {})
            if isinstance(providers, dict):
                for provider_id, provider in providers.items():
                    if not isinstance(provider, dict):
                        continue
                    configured = provider.get("models", {})
                    if isinstance(configured, dict):
                        for model_id in configured:
                            models.add(f"{provider_id}/{model_id}")
            default_model = config.get("model")
            if isinstance(default_model, str) and _MODEL_PATTERN.fullmatch(
                default_model
            ):
                models.add(default_model)
            agents = config.get("agent", {})
            if isinstance(agents, dict):
                for agent in agents.values():
                    if not isinstance(agent, dict):
                        continue
                    model = agent.get("model")
                    if isinstance(model, str) and _MODEL_PATTERN.fullmatch(model):
                        models.add(model)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            warnings.append(f"Cannot parse OpenCode config: {error}")
    else:
        warnings.append(f"OpenCode config not found: {config_path}")

    executable = shutil.which("opencode") if include_runtime else None
    if executable:
        environment = os.environ.copy()
        environment["OPENCODE_CONFIG_DIR"] = str(root)
        environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
        try:
            result = subprocess.run(
                [executable, "models", "--pure"],
                cwd=tempfile.gettempdir(),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    candidate = line.strip()
                    if _MODEL_PATTERN.fullmatch(candidate):
                        models.add(candidate)
            else:
                detail = (result.stderr or result.stdout).strip()
                warnings.append(
                    f"opencode models failed ({result.returncode}): {detail}"
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            warnings.append(f"opencode models unavailable: {error}")
    elif include_runtime:
        warnings.append("OpenCode CLI not found in PATH; using static config inventory.")
    return sorted(models), warnings


def sync_native_agent_models(
    document: dict[str, object],
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> Path | None:
    """Persist each primary binding in OpenCode's native agent config.

    The BIEXCE routing/applied files remain the audit and runtime guard layer.
    OpenCode itself only understands the primary model under agent.<name>.model;
    fallbacks stay BIEXCE-only and are never written as implicit OpenCode config.
    """
    selected = opencode_root or os.environ.get("BIEXCE_OPENCODE_CONFIG_DIR")
    if selected:
        root = Path(selected).expanduser().resolve()
    else:
        root = (Path.home() / ".config" / "opencode").resolve()
    config_path = root / "opencode.json"
    if not config_path.is_file():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModelRoutingError(
            f"Cannot parse OpenCode config before native agent binding: {error}"
        )
    if not isinstance(config, dict):
        raise ModelRoutingError("OpenCode config root must be a JSON object.")

    configured_agents = config.get("agent", {})
    if configured_agents is None:
        configured_agents = {}
    if not isinstance(configured_agents, dict):
        raise ModelRoutingError("OpenCode config agent must be a JSON object.")

    bindings = document.get("agents")
    if not isinstance(bindings, dict):
        raise ModelRoutingError("Routing agents must be a JSON object.")
    updated_agents = deepcopy(configured_agents)
    for agent in AGENTS:
        binding = bindings.get(agent)
        if not isinstance(binding, dict):
            raise ModelRoutingError(f"Routing binding is missing for {agent}.")
        primary = binding.get("primary")
        if not isinstance(primary, str) or not primary:
            raise ModelRoutingError(f"Routing primary model is missing for {agent}.")
        existing = updated_agents.get(agent, {})
        if existing is None:
            existing = {}
        if not isinstance(existing, dict):
            raise ModelRoutingError(f"OpenCode agent config is invalid for {agent}.")
        merged = deepcopy(existing)
        merged["model"] = primary
        updated_agents[agent] = merged

    updated = deepcopy(config)
    updated["agent"] = updated_agents
    if updated != config:
        _atomic_write_json(config_path, updated)
    return config_path


def apply_routing(
    *,
    actor: str,
    config_home: str | os.PathLike[str] | Path | None = None,
    available_models: Iterable[str] | None = None,
) -> Path:
    source_path = routing_path_for(config_home)
    document = load_routing(config_home)
    errors = validate_routing_document(
        document, available_models=available_models, require_configured=True
    )
    if errors:
        raise ModelRoutingError("; ".join(errors))
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    applied = {
        "$schema": APPLIED_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "source_path": str(source_path),
        "source_sha256": source_hash,
        "applied_at_utc": utc_timestamp(),
        "applied_by": actor.strip() or "unknown",
        "routing": document,
    }
    path = applied_path_for(config_home)
    _atomic_write_json(path, applied)
    return path


def load_applied_routing(
    config_home: str | os.PathLike[str] | Path | None = None,
) -> dict[str, object]:
    path = applied_path_for(config_home)
    applied = _read_json(path, "applied model routing")
    expected = {
        "$schema",
        "schema_version",
        "source_path",
        "source_sha256",
        "applied_at_utc",
        "applied_by",
        "routing",
    }
    if set(applied) != expected:
        raise ModelRoutingError("Applied routing properties are invalid.")
    if applied.get("$schema") != APPLIED_SCHEMA_ID or applied.get(
        "schema_version"
    ) != SCHEMA_VERSION:
        raise ModelRoutingError("Applied routing schema is invalid.")
    source_path = routing_path_for(config_home)
    if Path(str(applied.get("source_path"))).resolve() != source_path:
        raise ModelRoutingError("Applied routing references a different source path.")
    try:
        actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ModelRoutingError(f"Model routing source is unreadable: {error}")
    if applied.get("source_sha256") != actual_hash:
        raise ModelRoutingError(
            "Model routing changed after apply; run 'biexce model apply'."
        )
    routing = applied.get("routing")
    errors = validate_routing_document(routing)
    if errors:
        raise ModelRoutingError("; ".join(errors))
    current = load_routing(config_home)
    if current != routing:
        raise ModelRoutingError("Applied routing content does not match its source.")
    return applied


def routing_status(
    config_home: str | os.PathLike[str] | Path | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "routing_path": str(routing_path_for(config_home)),
        "applied_path": str(applied_path_for(config_home)),
        "configured": False,
        "valid": False,
        "applied": False,
        "errors": [],
        "agents": {},
    }
    try:
        document = load_routing(config_home)
        result["configured"] = True
        errors = validate_routing_document(document)
        result["errors"] = errors
        result["valid"] = not errors
        result["active_profile"] = document["active_profile"]
        result["revision"] = document["revision"]
        result["agents"] = document["agents"]
    except ModelRoutingError as error:
        result["errors"] = [str(error)]
        return result
    try:
        load_applied_routing(config_home)
        result["applied"] = True
    except ModelRoutingError as error:
        result["apply_error"] = str(error)
    return result


def provider_health(
    opencode_root: str | os.PathLike[str] | Path | None = None,
) -> list[dict[str, object]]:
    root = opencode_config_root(opencode_root)
    config_path = root / "opencode.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [{"provider": None, "status": "ERROR", "detail": str(error)}]
    results: list[dict[str, object]] = []
    providers = config.get("provider", {})
    if not isinstance(providers, dict):
        return [{"provider": None, "status": "ERROR", "detail": "invalid map"}]
    for provider_id, provider in providers.items():
        endpoint = None
        if isinstance(provider, dict):
            options = provider.get("options")
            if isinstance(options, dict):
                endpoint = options.get("baseURL")
        resolved_endpoint = resolve_config_reference(endpoint)
        if resolved_endpoint is None:
            detail = (
                f"Environment variable {endpoint[5:-1]} is not set."
                if isinstance(endpoint, str) and endpoint.startswith("{env:")
                else "No probeable baseURL; credentials are not inspected."
            )
            results.append(
                {
                    "provider": provider_id,
                    "status": "WARN",
                    "detail": detail,
                }
            )
            continue
        parsed = urlparse(resolved_endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            results.append(
                {
                    "provider": provider_id,
                    "status": "WARN",
                    "detail": "baseURL must be an absolute HTTP(S) URL.",
                }
            )
            continue
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            with socket.create_connection((parsed.hostname, port), timeout=2):
                pass
            status = "PASS"
            detail = f"TCP reachable at {parsed.hostname}:{port}"
        except OSError as error:
            status = "WARN"
            detail = f"TCP unreachable at {parsed.hostname}:{port}: {error}"
        results.append(
            {"provider": provider_id, "status": status, "detail": detail}
        )
    return results


def _provider_has_configured_credential(provider: object) -> bool:
    if not isinstance(provider, dict):
        return False
    candidates = [provider.get("apiKey")]
    options = provider.get("options")
    if isinstance(options, dict):
        candidates.append(options.get("apiKey"))
    return any(
        isinstance(candidate, str) and resolve_config_reference(candidate) is not None
        for candidate in candidates
    )


def provider_readiness(
    provider_ids: Iterable[str],
    opencode_root: str | os.PathLike[str] | Path | None = None,
    *,
    auth_file: str | os.PathLike[str] | Path | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    """Describe credential and connectivity readiness without blocking routing."""

    requested = sorted({value for value in provider_ids if value})
    authenticated, warnings = authenticated_providers(auth_file)
    root = opencode_config_root(opencode_root)
    try:
        config = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
        configured = config.get("provider", {}) if isinstance(config, dict) else {}
        if not isinstance(configured, dict):
            configured = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        configured = {}
        warnings.append(f"Cannot inspect OpenCode provider config: {error}")

    health_by_provider = {
        str(item["provider"]): item
        for item in provider_health(root)
        if isinstance(item.get("provider"), str)
    }
    results: list[dict[str, object]] = []
    for provider_id in requested:
        health = health_by_provider.get(provider_id)
        inference_status = "NOT VERIFIED"
        if provider_id == LOCAL_PROVIDER:
            status = str(health.get("status")) if health else "WARN"
            detail = (
                str(health.get("detail"))
                if health
                else "Local provider is not present in OpenCode config."
            )
            virtual_key_configured = bool(os.environ.get(LOCAL_VIRTUAL_KEY_ENV))
            credential_status = (
                "CONFIGURED" if virtual_key_configured else "NOT CONFIGURED"
            )
            credential_detail = (
                f"{LOCAL_VIRTUAL_KEY_ENV} is configured."
                if virtual_key_configured
                else f"{LOCAL_VIRTUAL_KEY_ENV} is not configured; a gateway "
                "that enforces Bifrost Virtual Keys will reject inference."
            )
            results.append(
                {
                    "provider": provider_id,
                    "status": status,
                    "credential_status": credential_status,
                    "inference_status": inference_status,
                    "detail": f"{detail}; {credential_detail}",
                }
            )
            continue

        if provider_id in authenticated:
            status = "AUTHENTICATED"
            credential_status = "AUTHENTICATED"
            detail = "Saved OpenCode credential found; inference is not tested here."
        elif _provider_has_configured_credential(configured.get(provider_id)):
            status = "CREDENTIAL CONFIGURED"
            credential_status = "CONFIGURED"
            detail = (
                "Provider credential reference is configured; inference is not tested here."
            )
        else:
            status = "NOT AUTHENTICATED"
            credential_status = "NOT AUTHENTICATED"
            detail = (
                "No saved OpenCode credential found. Catalog visibility does not prove "
                "inference access; use /connect in OpenCode."
            )
        results.append(
            {
                "provider": provider_id,
                "status": status,
                "credential_status": credential_status,
                "inference_status": inference_status,
                "detail": detail,
            }
        )
    return results, warnings


def readiness_warnings(readiness: Iterable[dict[str, object]]) -> list[str]:
    """Convert non-ready provider states into explicit non-blocking warnings."""

    warnings: list[str] = []
    for item in readiness:
        provider_id = item.get("provider") or "unknown"
        status = item.get("status")
        if status == "NOT AUTHENTICATED":
            warnings.append(
                f"Provider {provider_id}: NOT AUTHENTICATED. Catalog models may be "
                "selected, but inference can fail. Use /connect in OpenCode; routing "
                "remains allowed."
            )
        elif status in {"WARN", "ERROR"}:
            warnings.append(
                f"Provider {provider_id}: {status}. {item.get('detail') or ''}".strip()
            )
    return warnings
