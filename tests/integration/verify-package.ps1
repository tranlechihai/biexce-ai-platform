param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [string]$PackageName
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
).TrimEnd("\")
$resolvedZip = [IO.Path]::GetFullPath(
    (Resolve-Path -LiteralPath $ZipPath).Path
)
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\")
$testRoot = Join-Path (
    $temporaryBase
) ("biexce-package-test-" + [guid]::NewGuid().ToString("N"))
$extractRoot = Join-Path $testRoot "extract"
$installedRoot = Join-Path $testRoot "installed"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

try {
    $archive = [IO.Compression.ZipFile]::OpenRead($resolvedZip)
    try {
        $entries = @(
            $archive.Entries |
                Where-Object { -not [string]::IsNullOrEmpty($_.Name) }
        )
    }
    finally {
        $archive.Dispose()
    }

    $entryNames = @($entries | ForEach-Object FullName)
    if (@($entryNames | Where-Object { $_.Contains("\") }).Count -ne 0) {
        throw "Package contains a ZIP entry with a Windows backslash."
    }

    foreach ($relativePath in @(
        "bin/windows/install.cmd",
        "bin/windows/verify.cmd",
        "bin/windows/doctor.cmd",
        "bin/windows/biexce.cmd",
        "bin/windows/biexce-global.cmd",
        "bin/linux/install.sh",
        "bin/linux/verify.sh",
        "bin/linux/doctor.sh",
        "bin/linux/biexce.sh",
        "bin/linux/biexce-global",
        "bin/macos/install.command",
        "bin/macos/verify.command",
        "bin/macos/doctor.command",
        "bin/macos/biexce.command",
        "bin/macos/biexce-global",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/CONTROL-QUICKSTART.md",
        "docs/AGENT-SKILL-CATALOG.md",
        "docs/AGENT-ROLES.md",
        "src/harness-manifest.json",
        "src/harness-manifest.schema.json",
        "src/global/opencode.json",
        "src/global/package.json",
        "src/global/plugins/biexce-control.js",
        "src/global/runtime/job-board.js",
        "src/global/runtime/resilience.js",
        "src/global/runtime/scheduler.js",
        "src/global/runtime/session-registry.js",
        "src/global/runtime/supervisor.js",
        "scripts/install.ps1",
        "scripts/verify.ps1",
        "scripts/doctor.ps1",
        "scripts/biexce.py",
        "scripts/biexce_linux.py",
        "scripts/update_manifest.py",
        "scripts/validate_skills.py",
        "src/biexce_control/__init__.py",
        "src/biexce_control/autopilot.py",
        "src/biexce_control/workflow.py",
        "src/biexce_control/cli.py",
        "src/biexce_control/model_routing.py",
        "src/biexce_control/gate0.py",
        "src/biexce_control/validation.py",
        "src/biexce_control/schemas/autopilot-state-v1.schema.json",
        "src/biexce_control/schemas/agent-result-v1.schema.json",
        "src/biexce_control/schemas/job-board-v1.schema.json",
        "src/biexce_control/schemas/scheduler-state-v1.schema.json",
        "src/biexce_control/schemas/workflow-policy-v1.schema.json",
        "src/biexce_control/schemas/session-registry-v1.schema.json",
        "src/biexce_control/schemas/autopilot-command-v1.schema.json",
        "src/biexce_control/schemas/autopilot-workflow-v1.schema.json",
        "src/biexce_control/schemas/autopilot-workflow-v2.schema.json",
        "src/biexce_control/schemas/model-routing-v1.schema.json",
        "src/biexce_control/schemas/model-routing-applied-v1.schema.json",
        "src/biexce_control/schemas/server-evidence-v1.schema.json",
        "src/biexce_control/resources/self-test-project/.biexce/FIXTURE.json"
    )) {
        $expected = "$PackageName/$relativePath"
        if ($expected -notin $entryNames) {
            throw "Required package entry is missing: $expected"
        }
    }

    $forbidden = @(
        $entryNames |
            Where-Object {
                -not $_.StartsWith("$PackageName/src/biexce_control/resources/self-test-project/") -and (
                    $_ -match "(^|/)tests/" -or
                    $_ -match "(^|/)__pycache__/" -or
                    $_ -match "\.pyc$" -or
                    $_ -match "(^|/)\.gitignore$" -or
                    $_ -match "(^|/)package\.ps1$"
                )
            }
    )
    if ($forbidden.Count -ne 0) {
        throw "Package contains source-only files: $($forbidden -join ', ')"
    }

    foreach ($privatePath in @(
        'CHANGELOG.md',
        'docs/PLAN-V040-AI-DELIVERY-TEAM.md',
        'docs/TASKS-V040.md',
        'docs/GATE0-TEST-MATRIX.md',
        'docs/DASHBOARD-STATUS-V040.md',
        'docs/SMOKE-TEST-V040.md'
    )) {
        if ("$PackageName/$privatePath" -in $entryNames) {
            throw "Package contains private document: $privatePath"
        }
    }
    if (@($entryNames | Where-Object { $_.StartsWith("$PackageName/dashboard/") }).Count -ne 0) {
        throw 'Package contains source-only dashboard files.'
    }

    foreach ($relativePath in @(
        "bin/linux/install.sh",
        "bin/linux/verify.sh",
        "bin/linux/doctor.sh",
        "bin/linux/biexce.sh",
        "bin/linux/biexce-global",
        "bin/macos/install.command",
        "bin/macos/verify.command",
        "bin/macos/doctor.command",
        "bin/macos/biexce.command",
        "bin/macos/biexce-global"
    )) {
        $expected = "$PackageName/$relativePath"
        $entry = $entries |
            Where-Object FullName -eq $expected |
            Select-Object -First 1
        if ($null -eq $entry -or $entry.ExternalAttributes -ne -2115174400) {
            throw "Package executable mode is missing: $expected"
        }
    }

    New-Item -ItemType Directory -Path $extractRoot | Out-Null
    [IO.Compression.ZipFile]::ExtractToDirectory($resolvedZip, $extractRoot)
    $packageRoot = Join-Path $extractRoot $PackageName
    foreach ($relativePath in @(
        "bin\windows\install.cmd",
        "bin\linux\install.sh",
        "bin\macos\install.command",
        "bin\windows\biexce.cmd",
        "bin\windows\biexce-global.cmd",
        "bin\linux\biexce-global",
        "bin\macos\biexce-global",
        "src\harness-manifest.json",
        "src\global\runtime\job-board.js",
        "src\global\runtime\resilience.js",
        "src\global\runtime\scheduler.js",
        "src\global\runtime\session-registry.js",
        "src\global\runtime\supervisor.js",
        "src\global\runtime\workflow-policy.js",
        "src\global\runtime\observability.js",
        "src\biexce_control\autopilot.py",
        "src\biexce_control\workflow.py",
        "src\biexce_control\schemas\scheduler-state-v1.schema.json",
        "src\biexce_control\schemas\workflow-policy-v1.schema.json",
        "scripts\install.ps1"
    )) {
        if (
            -not (
                Test-Path `
                    -LiteralPath (Join-Path $packageRoot $relativePath) `
                    -PathType Leaf
            )
        ) {
            throw "Extracted package path is missing: $relativePath"
        }
    }

    $previousPath = $env:PATH
    $previousFailureSwitch = $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION
    try {
        $env:PATH = @(
            "$env:SystemRoot\System32",
            "$env:SystemRoot",
            "$env:SystemRoot\System32\WindowsPowerShell\v1.0"
        ) -join ";"
        $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION = $null

        & (Join-Path $packageRoot "scripts\install.ps1") `
            -TargetPath $installedRoot
        & (Join-Path $packageRoot "scripts\verify.ps1") `
            -TargetPath $installedRoot `
            -SkipCli
    }
    finally {
        $env:PATH = $previousPath
        $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION = $previousFailureSwitch
    }

    $resolvedPackageRoot = [IO.Path]::GetFullPath($packageRoot)
    if (
        -not $resolvedPackageRoot.StartsWith(
            $temporaryBase + "\",
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Extracted package escaped the system temp directory."
    }
    Remove-Item -LiteralPath $resolvedPackageRoot -Recurse -Force

    & (Join-Path $repositoryRoot "scripts\verify.ps1") `
        -TargetPath $installedRoot `
        -SkipCli

    Write-Host "Windows package extraction/install verification: PASS"
}
finally {
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    if (
        $resolvedTestRoot.StartsWith(
            $temporaryBase + "\",
            [StringComparison]::OrdinalIgnoreCase
        ) -and
        (Test-Path -LiteralPath $resolvedTestRoot -PathType Container)
    ) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
