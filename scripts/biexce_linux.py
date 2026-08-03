#!/usr/bin/env python3

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.parse import urlparse


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "src" / "harness-manifest.json"
HARNESS_MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
AGENT_MODES = {
    agent["id"]: agent["mode"] for agent in HARNESS_MANIFEST["agents"]
}
AGENT_HASHES = {
    agent["id"]: agent["sha256"] for agent in HARNESS_MANIFEST["agents"]
}
SKILL_CONTRACTS = tuple(HARNESS_MANIFEST["skills"])
SKILL_HASHES = {
    skill["id"]: skill["sha256"] for skill in SKILL_CONTRACTS
}
RUNTIME_CONTRACTS = tuple(HARNESS_MANIFEST["runtime_files"])
RUNTIME_HASHES = {
    runtime["id"]: runtime["sha256"] for runtime in RUNTIME_CONTRACTS
}
PLUGIN_DEPENDENCY = "@opencode-ai/plugin"
PLUGIN_DEPENDENCY_VERSION = "1.18.4"
PROVIDER_ID = HARNESS_MANIFEST["provider"]["id"]
PROVIDER_NAME = HARNESS_MANIFEST["provider"]["name"]
PROVIDER_PACKAGE = HARNESS_MANIFEST["provider"]["npm"]
PROVIDER_BASE_URL = HARNESS_MANIFEST["provider"]["base_url"]
MODEL_ID = HARNESS_MANIFEST["provider"]["model"]["id"]
MODEL_NAME = HARNESS_MANIFEST["provider"]["model"]["name"]
MODEL_CONTEXT = HARNESS_MANIFEST["provider"]["model"]["context"]
MODEL_OUTPUT = HARNESS_MANIFEST["provider"]["model"]["output"]
CLI_WARNING = (
    "OpenCode CLI is not available in PATH. Static installation passed. "
    "Restart OpenCode Desktop and verify agents/model in the UI."
)
MINIMUM_OPENCODE_VERSION_TEXT = HARNESS_MANIFEST["supported_opencode"]["minimum"]
MAXIMUM_OPENCODE_VERSION_EXCLUSIVE_TEXT = HARNESS_MANIFEST[
    "supported_opencode"
]["maximum_exclusive"]
MINIMUM_OPENCODE_VERSION = tuple(
    int(part) for part in MINIMUM_OPENCODE_VERSION_TEXT.split(".")
)
MAXIMUM_OPENCODE_VERSION_EXCLUSIVE = tuple(
    int(part) for part in MAXIMUM_OPENCODE_VERSION_EXCLUSIVE_TEXT.split(".")
)
SUPPORTED_OPENCODE_VERSION_RANGE = (
    f">= {MINIMUM_OPENCODE_VERSION_TEXT} "
    f"and < {MAXIMUM_OPENCODE_VERSION_EXCLUSIVE_TEXT}"
)
MANAGED_FILES = tuple(
    agent["path"] for agent in HARNESS_MANIFEST["agents"]
) + tuple(skill["path"] for skill in SKILL_CONTRACTS) + tuple(
    runtime["path"] for runtime in RUNTIME_CONTRACTS
)
SOURCE_TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".example",
    ".ps1",
    ".psm1",
    ".cmd",
    ".sh",
    ".command",
    ".py",
}
CREDENTIAL_PATTERN = re.compile(
    r"(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|sk-[a-z0-9_-]{16,}"
    r"|ghp_[a-z0-9]{16,}"
    r"|AIza[0-9A-Za-z_-]{20,}"
    r"|bearer\s+[a-z0-9._-]{16,}"
    r"|(?:api[_-]?key|client[_-]?secret)\s*[:=]\s*"
    r"""['"][^'"]{8,}['"])""",
    re.IGNORECASE,
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json_object(path, label):
    try:
        text = path.read_text(encoding="utf-8-sig")
        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot safely parse {label} as strict JSON: {error}")
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} root must be a JSON object.")
    return value


def resolve_environment_reference(value):
    if not isinstance(value, str) or not value:
        return None
    match = re.fullmatch(r'\{env:([A-Za-z_][A-Za-z0-9_]*)\}', value)
    if match is None:
        return value
    return os.environ.get(match.group(1)) or None


def exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object.")
    if set(value) != set(expected) or len(value) != len(expected):
        raise RuntimeError(f"{label} has unexpected properties.")


def validate_local_provider(config, canonical_only=False):
    providers = config.get("provider")
    if not isinstance(providers, dict):
        raise RuntimeError("Provider config must be a JSON object.")
    if canonical_only:
        exact_keys(providers, (PROVIDER_ID,), "Canonical provider map")

    matching_ids = [name for name in providers if name.lower() == PROVIDER_ID]
    if matching_ids != [PROVIDER_ID]:
        raise RuntimeError("Provider biexce-local is missing, duplicated, or mis-cased.")

    provider = providers[PROVIDER_ID]
    exact_keys(provider, ("npm", "name", "options", "models"), PROVIDER_ID)
    if provider["npm"] != PROVIDER_PACKAGE:
        raise RuntimeError("Biexce provider package is incorrect.")
    if provider["name"] != PROVIDER_NAME:
        raise RuntimeError("Biexce provider display name is incorrect.")

    options = provider["options"]
    exact_keys(options, ("baseURL",), "Biexce provider options")
    if options["baseURL"] != PROVIDER_BASE_URL:
        raise RuntimeError("Biexce provider base URL is incorrect.")

    models = provider["models"]
    exact_keys(models, (MODEL_ID,), "Biexce provider model map")
    model = models[MODEL_ID]
    exact_keys(model, ("name", "limit"), "Biexce local model")
    if model["name"] != MODEL_NAME:
        raise RuntimeError("Biexce local model display name is incorrect.")

    limits = model["limit"]
    exact_keys(limits, ("context", "output"), "Biexce local model limits")
    if limits["context"] != MODEL_CONTEXT or limits["output"] != MODEL_OUTPUT:
        raise RuntimeError("Biexce local model limits are incorrect.")


def merge_rule_map(existing, managed, label):
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise RuntimeError(f"Existing {label} must be a JSON object.")
    if not isinstance(managed, dict) or "*" not in managed:
        raise RuntimeError(f"Managed {label} must define a wildcard.")

    merged = {"*": copy.deepcopy(managed["*"])}
    for name, value in existing.items():
        if name != "*" and name not in managed:
            merged[name] = copy.deepcopy(value)
    for name, value in managed.items():
        if name != "*":
            merged[name] = copy.deepcopy(value)
    return merged


def merge_permission(existing, managed):
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise RuntimeError("Existing permission config must be a JSON object.")
    if not isinstance(managed, dict) or "*" not in managed:
        raise RuntimeError("Managed permission config must define a wildcard.")

    merged = {"*": copy.deepcopy(managed["*"])}
    for name, value in existing.items():
        if name != "*" and name not in managed:
            merged[name] = copy.deepcopy(value)
    for name, value in managed.items():
        if name == "*":
            continue
        if name in ("read", "bash"):
            merged[name] = merge_rule_map(existing.get(name), value, name)
        else:
            merged[name] = copy.deepcopy(value)
    return merged


def merge_agents(existing, managed):
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise RuntimeError("Existing agent config must be a JSON object.")
    if not isinstance(managed, dict):
        raise RuntimeError("Managed agent config must be a JSON object.")

    merged = copy.deepcopy(existing)
    for name, managed_definition in managed.items():
        existing_definition = existing.get(name, {})
        if not isinstance(existing_definition, dict):
            raise RuntimeError(f"Existing agent {name} must be a JSON object.")
        if not isinstance(managed_definition, dict):
            raise RuntimeError(f"Managed agent {name} must be a JSON object.")
        definition = copy.deepcopy(existing_definition)
        definition.update(copy.deepcopy(managed_definition))
        merged[name] = definition
    return merged


def merge_providers(existing, managed):
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise RuntimeError("Existing provider config must be a JSON object.")
    if not isinstance(managed, dict):
        raise RuntimeError("Managed provider config must be a JSON object.")

    managed_names = {name.lower() for name in managed}
    merged = {
        name: copy.deepcopy(value)
        for name, value in existing.items()
        if name.lower() not in managed_names
    }
    for name, value in managed.items():
        if not isinstance(value, dict):
            raise RuntimeError(f"Managed provider {name} must be a JSON object.")
        merged[name] = copy.deepcopy(value)
    return merged


def merge_config(existing, managed):
    merged = copy.deepcopy(existing)
    for name in ("default_agent", "subagent_depth", "share", "autoupdate"):
        if name not in managed:
            raise RuntimeError(f"Canonical config is missing {name}.")
        merged[name] = copy.deepcopy(managed[name])
    merged["permission"] = merge_permission(
        existing.get("permission"), managed.get("permission")
    )
    merged["agent"] = merge_agents(existing.get("agent"), managed.get("agent"))
    merged["provider"] = merge_providers(
        existing.get("provider"), managed.get("provider")
    )
    return merged


def merge_package_config(existing, managed):
    merged = copy.deepcopy(existing)
    existing_dependencies = existing.get("dependencies", {})
    managed_dependencies = managed.get("dependencies", {})
    if not isinstance(existing_dependencies, dict):
        raise RuntimeError("Existing package.json dependencies must be an object.")
    if managed_dependencies != {PLUGIN_DEPENDENCY: PLUGIN_DEPENDENCY_VERSION}:
        raise RuntimeError("Canonical package.json plugin dependency is invalid.")
    dependencies = copy.deepcopy(existing_dependencies)
    dependencies[PLUGIN_DEPENDENCY] = PLUGIN_DEPENDENCY_VERSION
    merged["dependencies"] = dependencies
    return merged


def source_path(root, relative):
    return root / "src" / "global" / Path(relative)


def validate_source_credentials(root):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if (
            path.suffix not in SOURCE_TEXT_SUFFIXES
            and path.name not in {"VERSION", ".gitignore", ".gitattributes"}
        ):
            continue
        text = path.read_text(encoding="utf-8")
        if CREDENTIAL_PATTERN.search(text):
            raise RuntimeError(f"Credential literal detected in source: {path}")


def validate_source(root):
    if (root / ".opencode").exists():
        raise RuntimeError("Source package must not contain a .opencode directory.")
    version_path = root / "VERSION"
    manifest_path = root / "src" / "harness-manifest.json"
    schema_path = root / "src" / "harness-manifest.schema.json"
    config_path = source_path(root, "opencode.json")
    for path in (version_path, manifest_path, schema_path, config_path):
        if not path.is_file():
            raise RuntimeError(f"Source file is missing: {path}")
    read_json_object(schema_path, str(schema_path))
    packaged_manifest = read_json_object(manifest_path, str(manifest_path))
    if packaged_manifest != HARNESS_MANIFEST:
        raise RuntimeError("Loaded harness manifest does not match the package.")
    if HARNESS_MANIFEST.get("schema_version") != 2:
        raise RuntimeError("Unsupported harness manifest schema.")

    for agent_contract in HARNESS_MANIFEST["agents"]:
        agent = agent_contract["id"]
        path = source_path(root, agent_contract["path"])
        if not path.is_file():
            raise RuntimeError(f"Source agent is missing: {path}")
        if sha256_file(path) != AGENT_HASHES[agent]:
            raise RuntimeError(f"Source agent hash changed: {agent}")
        frontmatter = path.read_text(encoding="utf-8").split("---", 2)[1]
        mode_match = re.search(r"(?m)^mode:\s*(\S+)\s*$", frontmatter)
        if mode_match is None or mode_match.group(1) != agent_contract["mode"]:
            raise RuntimeError(f"Source agent mode changed: {agent}")
        model_match = re.search(r"(?m)^model:\s*(\S+)\s*$", frontmatter)
        actual_model = model_match.group(1) if model_match else None
        if actual_model != agent_contract.get("model"):
            raise RuntimeError(f"Source agent model binding changed: {agent}")
    for skill_contract in SKILL_CONTRACTS:
        skill_id = skill_contract["id"]
        path = source_path(root, skill_contract["path"])
        if not path.is_file():
            raise RuntimeError(f"Source skill is missing: {path}")
        if sha256_file(path) != SKILL_HASHES[skill_id]:
            raise RuntimeError(f"Source skill hash changed: {skill_id}")
    for runtime_contract in RUNTIME_CONTRACTS:
        runtime_id = runtime_contract["id"]
        path = source_path(root, runtime_contract["path"])
        if not path.is_file():
            raise RuntimeError(f"Source runtime file is missing: {path}")
        if sha256_file(path) != RUNTIME_HASHES[runtime_id]:
            raise RuntimeError(f"Source runtime hash changed: {runtime_id}")
    package = read_json_object(
        source_path(root, "package.json"), "canonical package.json"
    )
    if package.get("dependencies") != {
        PLUGIN_DEPENDENCY: PLUGIN_DEPENDENCY_VERSION
    }:
        raise RuntimeError("Canonical plugin dependency is not pinned.")

    canonical = read_json_object(config_path, str(config_path))
    validate_local_provider(canonical, canonical_only=True)
    for name, value in HARNESS_MANIFEST["defaults"].items():
        if canonical.get(name) != value:
            raise RuntimeError(f"Canonical config does not match default {name}.")
    for agent in HARNESS_MANIFEST["disabled_builtin_agents"]:
        definition = canonical.get("agent", {}).get(agent)
        if not isinstance(definition, dict) or definition.get("disable") is not True:
            raise RuntimeError(f"Canonical config must disable built-in agent {agent}.")
    global_binding = HARNESS_MANIFEST["model_binding"]["global"]
    for name in ("model", "small_model", "variant"):
        if canonical.get(name) != global_binding.get(name):
            raise RuntimeError(f"Canonical model binding changed: {name}")
    binding_values = list(global_binding.values()) + list(
        HARNESS_MANIFEST["model_binding"]["agents"].values()
    )
    expected_state = "bound" if any(binding_values) else "unset"
    if HARNESS_MANIFEST["model_binding"]["state"] != expected_state:
        raise RuntimeError("Manifest model binding state is inconsistent.")
    validate_source_credentials(root)
    return version_path.read_text(encoding="utf-8").strip(), canonical


def plan_changes(
    root, target, merged_bytes, package_bytes, migrate_jsonc=False,
    platform_name="linux",
):
    changes = []
    config_path = target / "opencode.json"
    if config_path.exists() and not config_path.is_file():
        raise RuntimeError(f"Managed target is not a file: {config_path}")
    if not config_path.is_file() or config_path.read_bytes() != merged_bytes:
        changes.append(
            {
                "kind": "config",
                "relative": "opencode.json",
                "destination": config_path,
                "source": source_path(root, "opencode.json"),
            }
        )
    package_path = target / "package.json"
    if package_path.exists() and not package_path.is_file():
        raise RuntimeError(f"Managed target is not a file: {package_path}")
    if not package_path.is_file() or package_path.read_bytes() != package_bytes:
        changes.append(
            {
                "kind": "package_config",
                "relative": "package.json",
                "destination": package_path,
                "source": source_path(root, "package.json"),
            }
        )

    if migrate_jsonc:
        changes.append(
            {
                "kind": "remove",
                "relative": "opencode.jsonc",
                "destination": target / "opencode.jsonc",
                "source": None,
            }
        )

    for relative in MANAGED_FILES:
        source = source_path(root, relative)
        destination = target / Path(relative)
        if destination.exists() and not destination.is_file():
            raise RuntimeError(f"Managed target is not a file: {destination}")
        if not destination.is_file() or sha256_file(source) != sha256_file(destination):
            changes.append(
                {
                    "kind": "copy",
                    "relative": relative,
                    "destination": destination,
                    "source": source,
                }
            )
    for relative, source in cli_bundle_sources(root, platform_name):
        destination = target / Path(relative)
        if destination.exists() and not destination.is_file():
            raise RuntimeError(f"Managed CLI target is not a file: {destination}")
        if not destination.is_file() or sha256_file(source) != sha256_file(destination):
            changes.append(
                {
                    "kind": "copy",
                    "relative": relative,
                    "destination": destination,
                    "source": source,
                }
            )
    return changes


def cli_bundle_sources(root, platform_name):
    if platform_name not in {"linux", "macos"}:
        raise RuntimeError(f"Unsupported CLI platform: {platform_name}")
    pairs = [
        ("biexce-cli/scripts/biexce.py", root / "scripts" / "biexce.py"),
        (
            "biexce-cli/src/global/opencode.json",
            root / "src" / "global" / "opencode.json",
        ),
    ]
    base = root / "src" / "biexce_control"
    destination_base = "biexce-cli/src/biexce_control"
    for source in sorted(base.rglob("*")):
        if not source.is_file() or source.suffix == ".pyc" or "__pycache__" in source.parts:
            continue
        relative = source.relative_to(base).as_posix()
        pairs.append((f"{destination_base}/{relative}", source))
    shim_source = root / "bin" / platform_name / "biexce-global"
    pairs.append(("biexce-bin/biexce", shim_source))
    for relative, source in pairs:
        if not source.is_file():
            raise RuntimeError(f"CLI source file is missing: {source}")
    return tuple(pairs)


def create_selective_backup(target, changes, version):
    if not changes:
        print("Backup: none (managed files already current)")
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    base = Path(f"{target}.biexce-backup-{timestamp}")
    backup = base
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = Path(f"{base}-{suffix}")
    backup.mkdir(parents=True)
    try:
        backup.chmod(0o700)
    except OSError:
        pass

    entries = []
    copied_count = 0
    for change in changes:
        destination = change["destination"]
        existed = destination.is_file()
        original_hash = None
        backup_relative = None
        if existed:
            backup_relative = change["relative"]
            backup_file = backup / Path(backup_relative)
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup_file)
            original_hash = sha256_file(destination)
            if sha256_file(backup_file) != original_hash:
                raise RuntimeError(f"Backup verification failed: {backup_relative}")
            copied_count += 1
            print(f"Backed up: {destination} -> {backup_file}")
        else:
            print(f"Rollback record: {change['relative']} did not exist")
        entries.append(
            {
                "path": change["relative"],
                "existed": existed,
                "sha256": original_hash,
                "backup": backup_relative,
            }
        )

    manifest = {
        "version": version,
        "target": str(target),
        "created_at_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "files": entries,
    }
    manifest_path = backup / "backup-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        manifest_path.chmod(0o600)
    except OSError:
        pass

    print(f"Backup: {backup}")
    print(f"Backup manifest: {manifest_path}")
    print(
        f"Backup scope: {len(changes)} managed paths, "
        f"{copied_count} existing files copied"
    )
    return backup


def restore_selective_backup(target, backup):
    manifest_path = backup / "backup-manifest.json"
    manifest = read_json_object(manifest_path, str(manifest_path))
    if Path(manifest.get("target", "")).resolve() != target.resolve():
        raise RuntimeError("Backup manifest target does not match install target.")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise RuntimeError("Backup manifest files must be an array.")

    for entry in reversed(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("Backup manifest contains an invalid file entry.")
        destination = target / Path(entry["path"])
        if entry.get("existed") is True:
            backup_relative = entry.get("backup")
            if not isinstance(backup_relative, str):
                raise RuntimeError(f"Rollback source is invalid: {entry['path']}")
            backup_file = backup / Path(backup_relative)
            if not backup_file.is_file():
                raise RuntimeError(f"Rollback source is missing: {backup_file}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, destination)
            if sha256_file(destination) != entry.get("sha256"):
                raise RuntimeError(
                    f"Rollback hash verification failed: {entry['path']}"
                )
            print(f"Restored: {destination}")
        elif destination.is_file() or destination.is_symlink():
            destination.unlink()
            print(f"Removed during rollback: {destination}")
        elif destination.exists():
            raise RuntimeError(f"Rollback target is not a file: {destination}")

    print(f"Rollback: PASS ({backup})")


def opencode_prefix():
    executable = shutil.which("opencode")
    if executable is None:
        return None
    if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat"):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", executable]
    return [executable]


def run_opencode(prefix, target, arguments):
    environment = os.environ.copy()
    environment.pop("OPENCODE_CONFIG", None)
    environment.pop("OPENCODE_CONFIG_CONTENT", None)
    environment["OPENCODE_CONFIG_DIR"] = str(target)
    environment["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    environment["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"
    environment["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] = "1"
    environment["XDG_CONFIG_HOME"] = str(target.parent)

    # OpenCode can emit more than the Unix pipe buffer for debug skill JSON.
    # Regular temporary files prevent truncated UTF-8 and are removed on close.
    with (
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        result = subprocess.run(
            prefix + list(arguments),
            cwd=tempfile.gettempdir(),
            env=environment,
            stdout=stdout_file,
            stderr=stderr_file,
            check=False,
        )
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout_text = stdout_file.read().decode("utf-8", errors="replace")
        stderr_text = stderr_file.read().decode("utf-8", errors="replace")

    if result.returncode != 0:
        message = (stderr_text or stdout_text).strip()
        raise RuntimeError(
            f"OpenCode command failed with exit code {result.returncode}: {message}"
        )
    return (stdout_text + "\n" + stderr_text).strip()


def parse_opencode_version(output):
    normalized = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output).strip()
    semantic_version = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"
    line_match = re.search(
        rf"^\s*(?:opencode(?:\s+version)?\s+)?v?({semantic_version})\s*$",
        normalized,
        re.IGNORECASE | re.MULTILINE,
    )
    if line_match:
        return line_match.group(1)

    versions = list(
        dict.fromkeys(
            match.group(1)
            for match in re.finditer(
                rf"(?<![0-9A-Za-z])v?({semantic_version})(?![0-9A-Za-z])",
                normalized,
                re.IGNORECASE,
            )
        )
    )
    if len(versions) == 1:
        return versions[0]
    if not normalized:
        raise RuntimeError("OpenCode CLI version output is empty.")
    raise RuntimeError(
        f"OpenCode CLI version output could not be parsed safely: {normalized}"
    )


def is_supported_opencode_version(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return False
    parsed = tuple(int(part) for part in match.groups())
    return (
        parsed >= MINIMUM_OPENCODE_VERSION
        and parsed < MAXIMUM_OPENCODE_VERSION_EXCLUSIVE
    )


def verify_permission(installed, canonical):
    permission = installed.get("permission")
    managed = canonical.get("permission")
    if not isinstance(permission, dict) or not isinstance(managed, dict):
        raise RuntimeError("Permission config must be a JSON object.")
    if not permission or next(iter(permission)) != "*" or permission["*"] != managed["*"]:
        raise RuntimeError("Permission wildcard is missing or out of order.")

    for name, managed_value in managed.items():
        if name in ("read", "bash"):
            actual = permission.get(name)
            if not isinstance(actual, dict) or not actual or next(iter(actual)) != "*":
                raise RuntimeError(f"Permission {name} wildcard is missing or out of order.")
            for rule, value in managed_value.items():
                if actual.get(rule) != value:
                    raise RuntimeError(f"Permission rule changed: {name}.{rule}")
            managed_specific = [rule for rule in managed_value if rule != "*"]
            if list(actual)[-len(managed_specific) :] != managed_specific:
                raise RuntimeError(f"Managed {name} rules are not last.")
        elif permission.get(name) != managed_value:
            raise RuntimeError(f"Permission field changed: {name}")


def verify_installation(root, target, runtime=True, platform_name="linux"):
    _, canonical = validate_source(root)
    if (target / "opencode.jsonc").is_file():
        raise RuntimeError("Installed target contains opencode.jsonc.")
    installed_path = target / "opencode.json"
    if not installed_path.is_file():
        raise RuntimeError(f"Installed config is missing: {installed_path}")
    installed = read_json_object(installed_path, str(installed_path))

    for name in ("default_agent", "subagent_depth", "share", "autoupdate"):
        if installed.get(name) != canonical.get(name):
            raise RuntimeError(f"Installed managed value is incorrect: {name}")
    validate_local_provider(installed)
    verify_permission(installed, canonical)

    installed_agents = installed.get("agent")
    if not isinstance(installed_agents, dict):
        raise RuntimeError("Installed agent config must be a JSON object.")
    for name in ("build", "plan", "general", "explore", "scout"):
        definition = installed_agents.get(name)
        if not isinstance(definition, dict) or definition.get("disable") is not True:
            raise RuntimeError(f"Built-in agent is not disabled: {name}")

    for agent in AGENT_MODES:
        source = source_path(root, f"agents/{agent}.md")
        destination = target / "agents" / f"{agent}.md"
        if not destination.is_file() or sha256_file(destination) != sha256_file(source):
            raise RuntimeError(f"Installed agent hash is incorrect: {agent}")
    for skill_contract in SKILL_CONTRACTS:
        source_skill = source_path(root, skill_contract["path"])
        installed_skill = target / Path(skill_contract["path"])
        if (
            not installed_skill.is_file()
            or sha256_file(installed_skill) != sha256_file(source_skill)
        ):
            raise RuntimeError(
                f"Installed skill hash is incorrect: {skill_contract['id']}"
            )
    for runtime_contract in RUNTIME_CONTRACTS:
        source = source_path(root, runtime_contract["path"])
        installed_runtime = target / Path(runtime_contract["path"])
        if (
            not installed_runtime.is_file()
            or sha256_file(installed_runtime) != sha256_file(source)
        ):
            raise RuntimeError(
                f"Installed runtime hash is incorrect: {runtime_contract['id']}"
            )
    for relative, source in cli_bundle_sources(root, platform_name):
        destination = target / Path(relative)
        if not destination.is_file() or sha256_file(destination) != sha256_file(source):
            raise RuntimeError(f"Installed CLI file is incorrect: {relative}")
    if not os.access(target / "biexce-bin" / "biexce", os.X_OK):
        raise RuntimeError("Installed biexce command is not executable.")
    package = read_json_object(target / "package.json", "installed package.json")
    dependencies = package.get("dependencies")
    if (
        not isinstance(dependencies, dict)
        or dependencies.get(PLUGIN_DEPENDENCY) != PLUGIN_DEPENDENCY_VERSION
    ):
        raise RuntimeError("Installed plugin dependency is missing or unpinned.")

    print("Static verification: PASS")
    if not runtime:
        return

    prefix = opencode_prefix()
    if prefix is None:
        print(f"WARNING: {CLI_WARNING}")
        return

    version = parse_opencode_version(
        run_opencode(prefix, target, ("--version",))
    )
    if not is_supported_opencode_version(version):
        raise RuntimeError(
            f"Unsupported OpenCode CLI version '{version}'. "
            f"Supported range: {SUPPORTED_OPENCODE_VERSION_RANGE}."
        )

    agent_output = run_opencode(prefix, target, ("agent", "list", "--pure"))
    for agent, mode in AGENT_MODES.items():
        if not re.search(
            rf"^{re.escape(agent)} \({re.escape(mode)}\)", agent_output, re.MULTILINE
        ):
            raise RuntimeError(f"OpenCode did not discover {agent} as {mode}.")

    model_output = run_opencode(prefix, target, ("models", PROVIDER_ID, "--pure"))
    full_model_id = f"{PROVIDER_ID}/{MODEL_ID}"
    if not re.search(rf"^{re.escape(full_model_id)}\s*$", model_output, re.MULTILINE):
        raise RuntimeError("OpenCode did not discover the Biexce local model.")

    skill_output = run_opencode(prefix, target, ("debug", "skill", "--pure"))
    for skill_contract in SKILL_CONTRACTS:
        if not re.search(
            rf'"name"\s*:\s*"{re.escape(skill_contract["id"])}"',
            skill_output,
        ):
            raise RuntimeError(
                f"OpenCode did not discover skill: {skill_contract['id']}"
            )

    print(f"Verified agents: {', '.join(AGENT_MODES)}")
    print(
        f"Verified OpenCode CLI version: {version} "
        f"({SUPPORTED_OPENCODE_VERSION_RANGE})"
    )
    print(f"Verified provider: {PROVIDER_ID}")
    print(f"Verified model: {full_model_id}")
    print(f"Verified skills: {len(SKILL_CONTRACTS)}")
    print(f"Verified runtime files: {len(RUNTIME_CONTRACTS)}")
    print("Runtime verification: PASS")


def doctor(root, target, platform_name="linux"):
    version, canonical = validate_source(root)
    verify_permission(canonical, canonical)
    counts = {status: 0 for status in ("ready", "draft", "skeleton")}
    for skill in SKILL_CONTRACTS:
        counts[skill["status"]] += 1

    print("Biexce Doctor")
    print(f"Harness version: {version}")
    print(f"Manifest schema: {HARNESS_MANIFEST['schema_version']}")
    print(f"Agents: {len(AGENT_MODES)}")
    print(
        "Skills: "
        f"{len(SKILL_CONTRACTS)} "
        f"(ready={counts['ready']}, draft={counts['draft']}, "
        f"skeleton={counts['skeleton']})"
    )
    print(f"Model binding: {HARNESS_MANIFEST['model_binding']['state']}")
    print("Source contract: PASS")

    if target.is_dir():
        verify_installation(
            root, target, runtime=False, platform_name=platform_name
        )
        print(f"Installed target: PASS ({target})")
    else:
        print(f"Installed target: WARN (not found: {target})")

    prefix = opencode_prefix()
    if prefix is None:
        print("OpenCode CLI: WARN (not found in PATH)")
    else:
        config_dir = target if target.is_dir() else source_path(root, ".")
        detected = parse_opencode_version(
            run_opencode(prefix, config_dir, ("--version",))
        )
        if not is_supported_opencode_version(detected):
            raise RuntimeError(
                f"Unsupported OpenCode CLI version '{detected}'. "
                f"Supported range: {SUPPORTED_OPENCODE_VERSION_RANGE}."
            )
        print(f"OpenCode CLI: PASS ({detected})")

    base_url = resolve_environment_reference(PROVIDER_BASE_URL)
    if base_url is None:
        print('Bifrost endpoint: WARN (BIEXCE_LOCAL_BASE_URL is not set)')
    else:
        endpoint = urlparse(base_url)
        port = endpoint.port or (443 if endpoint.scheme == 'https' else 80)
        try:
            with socket.create_connection((endpoint.hostname, port), timeout=2):
                pass
            print(f'Bifrost endpoint: PASS ({endpoint.hostname}:{port})')
        except OSError as error:
            print(
                f'Bifrost endpoint: WARN ({endpoint.hostname}:{port} '
                f'unreachable: {error})'
            )
    print("Credentials: PASS (no secret literal in managed config)")
    print('Doctor result: PASS (endpoint warnings are non-fatal)')


def install(root, target, platform_name="linux"):
    version, canonical = validate_source(root)
    config_path = target / "opencode.json"
    jsonc_path = target / "opencode.jsonc"
    json_exists = config_path.exists()
    jsonc_exists = jsonc_path.exists()

    if json_exists and jsonc_exists:
        raise RuntimeError(
            "Both opencode.json and opencode.jsonc exist. "
            "Resolve the config conflict before installing."
        )
    for candidate in (config_path, jsonc_path):
        if candidate.exists() and not candidate.is_file():
            raise RuntimeError(f"Managed target is not a file: {candidate}")

    migrate_jsonc = jsonc_exists
    existing_path = config_path if json_exists else jsonc_path if jsonc_exists else None
    if existing_path is None:
        existing = {}
    else:
        try:
            existing = read_json_object(existing_path, str(existing_path))
        except RuntimeError:
            if migrate_jsonc:
                raise RuntimeError(
                    f"Cannot automatically migrate {jsonc_path} because it is not "
                    "strict JSON. JSONC comments and trailing commas are not "
                    "supported in v0.3.9. No files were changed."
                )
            raise

    merged = merge_config(existing, canonical)
    merged_bytes = (
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    json.loads(merged_bytes.decode("utf-8"))

    package_path = target / "package.json"
    if package_path.exists() and not package_path.is_file():
        raise RuntimeError(f"Managed target is not a file: {package_path}")
    existing_package = (
        read_json_object(package_path, str(package_path))
        if package_path.is_file()
        else {}
    )
    managed_package = read_json_object(
        source_path(root, "package.json"), "canonical package.json"
    )
    merged_package = merge_package_config(existing_package, managed_package)
    package_bytes = (
        json.dumps(merged_package, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    json.loads(package_bytes.decode("utf-8"))

    changes = plan_changes(
        root, target, merged_bytes, package_bytes, migrate_jsonc, platform_name
    )
    backup = create_selective_backup(target, changes, version)
    mutation_started = False
    try:
        mutation_started = True
        target.mkdir(parents=True, exist_ok=True)

        for change in changes:
            if change["kind"] != "copy":
                continue
            destination = change["destination"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(change["source"], destination)
            if change["relative"] == "biexce-bin/biexce":
                destination.chmod(0o755)
            if sha256_file(change["source"]) != sha256_file(destination):
                raise RuntimeError(
                    f"Installed file hash verification failed: {destination}"
                )
            print(f"Copied: {change['source']} -> {destination}")

        config_changed = any(change["kind"] == "config" for change in changes)
        if config_changed:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".opencode.json.biexce-", suffix=".tmp", dir=target
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)
            try:
                temporary_path.write_bytes(merged_bytes)
                read_json_object(temporary_path, str(temporary_path))
                os.replace(temporary_path, config_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            print(f"Merged: {source_path(root, 'opencode.json')} -> {config_path}")
        else:
            print(f"Merged: unchanged ({config_path})")

        package_changed = any(
            change["kind"] == "package_config" for change in changes
        )
        if package_changed:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".package.json.biexce-", suffix=".tmp", dir=target
            )
            os.close(file_descriptor)
            temporary_path = Path(temporary_name)
            try:
                temporary_path.write_bytes(package_bytes)
                read_json_object(temporary_path, str(temporary_path))
                os.replace(temporary_path, package_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            print(
                f"Merged: {source_path(root, 'package.json')} -> {package_path}"
            )
        else:
            print(f"Merged: unchanged ({package_path})")

        if migrate_jsonc:
            jsonc_path.unlink()
            print(f"Migrated: {jsonc_path} -> {config_path}")

        if os.environ.get("BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION") == "1":
            raise RuntimeError("Simulated failure after mutation.")

        verify_installation(root, target, runtime=True, platform_name=platform_name)
    except Exception as install_error:
        if mutation_started and backup is not None:
            try:
                restore_selective_backup(target, backup)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Installation failed: {install_error} "
                    f"Rollback also failed: {rollback_error}"
                )
        raise

    print(f"Global Biexce OpenCode agent harness installed: {target}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "verify", "doctor"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--platform",
        choices=("linux", "macos"),
        default="macos" if sys.platform == "darwin" else "linux",
    )
    arguments = parser.parse_args()

    root = Path(arguments.root).expanduser().resolve()
    target = Path(arguments.target).expanduser().resolve()
    if target == root or root in target.parents:
        raise RuntimeError("Target must be outside the source package.")

    if arguments.action == "install":
        install(root, target, platform_name=arguments.platform)
    elif arguments.action == "verify":
        verify_installation(root, target, platform_name=arguments.platform)
    else:
        doctor(root, target, platform_name=arguments.platform)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
