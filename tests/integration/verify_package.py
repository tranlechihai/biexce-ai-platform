import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, dest="zip_path")
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--repository-root", required=True)
    arguments = parser.parse_args()

    zip_path = Path(arguments.zip_path).resolve()
    repository_root = Path(arguments.repository_root).resolve()
    with zipfile.ZipFile(zip_path) as archive:
        names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
        if any("\\" in name for name in names):
            raise RuntimeError("ZIP contains a Windows backslash.")
        if len(names) != len(set(names)):
            raise RuntimeError("ZIP contains duplicate entries.")

        required = {
            f"{arguments.package_name}/bin/linux/install.sh",
            f"{arguments.package_name}/bin/linux/doctor.sh",
            f"{arguments.package_name}/bin/linux/biexce.sh",
            f"{arguments.package_name}/bin/linux/biexce-global",
            f"{arguments.package_name}/bin/linux/verify.sh",
            f"{arguments.package_name}/bin/macos/biexce-global",
            f"{arguments.package_name}/bin/windows/biexce-global.cmd",
            f"{arguments.package_name}/THIRD_PARTY_NOTICES.md",
            f"{arguments.package_name}/docs/CONTROL-QUICKSTART.md",
            f"{arguments.package_name}/docs/AGENT-SKILL-CATALOG.md",
            f"{arguments.package_name}/docs/AGENT-ROLES.md",
            f"{arguments.package_name}/src/harness-manifest.json",
            f"{arguments.package_name}/src/harness-manifest.schema.json",
            f"{arguments.package_name}/src/global/package.json",
            (
                f"{arguments.package_name}/src/global/plugins/"
                "biexce-control.js"
            ),
            (
                f"{arguments.package_name}/src/global/runtime/"
                "job-board.js"
            ),
            (
                f"{arguments.package_name}/src/global/runtime/"
                "failure-policy.js"
            ),
            (
                f"{arguments.package_name}/src/global/runtime/"
                "scope-policy.js"
            ),
            (
                f"{arguments.package_name}/src/global/runtime/"
                "reconciler.js"
            ),
            (
                f"{arguments.package_name}/src/global/runtime/"
                "scheduler.js"
            ),
            (
                f"{arguments.package_name}/src/global/runtime/"
                "supervisor.js"
            ),
            f"{arguments.package_name}/scripts/biexce.py",
            f"{arguments.package_name}/scripts/biexce_linux.py",
            f"{arguments.package_name}/scripts/validate_skills.py",
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/autopilot-state-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/agent-result-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/job-board-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/autopilot-command-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/autopilot-workflow-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/autopilot-workflow-v2.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/model-routing-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/model-routing-applied-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/"
                "schemas/server-evidence-v1.schema.json"
            ),
            (
                f"{arguments.package_name}/src/biexce_control/resources/self-test-project/"
                ".biexce/FIXTURE.json"
            ),
        }
        missing = required.difference(names)
        if missing:
            raise RuntimeError(f"Required ZIP entries are missing: {sorted(missing)}")

        forbidden_publication = {
            f'{arguments.package_name}/CHANGELOG.md',
            f'{arguments.package_name}/docs/PLAN-V040-AI-DELIVERY-TEAM.md',
            f'{arguments.package_name}/docs/TASKS-V040.md',
            f'{arguments.package_name}/docs/GATE0-TEST-MATRIX.md',
            f'{arguments.package_name}/docs/DASHBOARD-STATUS-V040.md',
            f'{arguments.package_name}/docs/SMOKE-TEST-V040.md',
        }
        leaked = forbidden_publication.intersection(names)
        leaked.update(
            name
            for name in names
            if name.startswith(f'{arguments.package_name}/dashboard/')
        )
        if leaked:
            raise RuntimeError(
                f'Package contains private or source-only files: {sorted(leaked)}'
            )

        with tempfile.TemporaryDirectory(prefix="biexce-python-zip-test-") as temporary:
            temporary_root = Path(temporary)
            archive.extractall(temporary_root)
            package_root = temporary_root / arguments.package_name
            target = temporary_root / "installed"

            for relative in (
                "bin/linux/install.sh",
                "bin/linux/biexce.sh",
                "bin/linux/biexce-global",
                "bin/linux/verify.sh",
                "docs/CONTROL-QUICKSTART.md",
                "docs/AGENT-SKILL-CATALOG.md",
                "docs/AGENT-ROLES.md",
                "src/harness-manifest.json",
                "src/global/opencode.json",
                "src/global/package.json",
                "src/global/plugins/biexce-control.js",
                "src/global/runtime/failure-policy.js",
                "src/global/runtime/scope-policy.js",
                "src/global/runtime/job-board.js",
                "src/global/runtime/reconciler.js",
                "src/global/runtime/scheduler.js",
                "src/global/runtime/supervisor.js",
                "scripts/biexce.py",
                "scripts/biexce_linux.py",
                "src/biexce_control/autopilot.py",
                "src/biexce_control/workflow.py",
                "src/biexce_control/model_routing.py",
                "src/biexce_control/schemas/model-routing-applied-v1.schema.json",
                "src/biexce_control/gate0.py",
                "src/biexce_control/validation.py",
                "src/biexce_control/resources/self-test-project/.biexce/FIXTURE.json",
            ):
                if not (package_root / relative).is_file():
                    raise RuntimeError(f"Extracted path is missing: {relative}")

            environment = os.environ.copy()
            environment["PATH"] = ""
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            install = subprocess.run(
                [
                    sys.executable,
                    str(package_root / "scripts" / "biexce_linux.py"),
                    "install",
                    "--root",
                    str(package_root),
                    "--target",
                    str(target),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            if install.returncode != 0:
                raise RuntimeError(install.stdout + install.stderr)

            manifest = json.loads(
                (package_root / "src" / "harness-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            shutil.rmtree(package_root)

            for agent in manifest["agents"]:
                if not (target / agent["path"]).is_file():
                    raise RuntimeError(
                        f"Installed agent is missing after package removal: {agent['id']}"
                    )
            for skill in manifest["skills"]:
                if not (target / skill["path"]).is_file():
                    raise RuntimeError(
                        f"Installed skill is missing after package removal: {skill['id']}"
                    )
            for runtime in manifest["runtime_files"]:
                if not (target / runtime["path"]).is_file():
                    raise RuntimeError(
                        "Installed runtime file is missing after package "
                        f"removal: {runtime['id']}"
                    )

            verify = subprocess.run(
                [
                    sys.executable,
                    str(repository_root / "scripts" / "biexce_linux.py"),
                    "verify",
                    "--root",
                    str(repository_root),
                    "--target",
                    str(target),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            if verify.returncode != 0:
                raise RuntimeError(verify.stdout + verify.stderr)

    print("Python zipfile extraction/install verification: PASS")


if __name__ == "__main__":
    run()
