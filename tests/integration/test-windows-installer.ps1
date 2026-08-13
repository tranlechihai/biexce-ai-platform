param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
).TrimEnd("\")
$installer = Join-Path $repositoryRoot "scripts\install.ps1"
$verifier = Join-Path $repositoryRoot "scripts\verify.ps1"
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\")
$testRoot = Join-Path (
    $temporaryBase
) ("biexce-windows-install-test-" + [guid]::NewGuid().ToString("N"))
$utf8 = New-Object Text.UTF8Encoding($false)

function Invoke-ExpectedInstallFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $failed = $false
    try {
        & $installer -TargetPath $TargetPath *> $null
    }
    catch {
        $failed = $true
    }
    if (-not $failed) {
        throw "Installer unexpectedly succeeded: $TargetPath"
    }
}

function Write-TestText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    [IO.File]::WriteAllText($Path, $Content, $utf8)
}

New-Item -ItemType Directory -Path $testRoot | Out-Null
$previousPath = $env:PATH
$pythonCommand = (Get-Command python.exe -ErrorAction Stop).Source
$previousFailureSwitch = $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION
try {
    $env:PATH = @(
        "$env:SystemRoot\System32",
        "$env:SystemRoot",
        "$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    ) -join ";"
    $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION = $null

    $freshTarget = Join-Path $testRoot "fresh"
    & $installer -TargetPath $freshTarget *> $null
    & $verifier -TargetPath $freshTarget -SkipCli *> $null
    & $installer -TargetPath $freshTarget *> $null
    foreach ($relativePath in @(
        'biexce-bin\biexce.cmd',
        'biexce-cli\scripts\biexce.py',
        'biexce-cli\src\biexce_control\cli.py',
        'biexce-cli\src\global\opencode.json',
        'biexce-cli\src\biexce_control\resources\self-test-project\.biexce\FIXTURE.json'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $freshTarget $relativePath) -PathType Leaf)) {
            throw "Installed global CLI file is missing: $relativePath"
        }
    }
    $env:PATH = (Split-Path -Parent $pythonCommand) + ';' + $env:PATH
    $arbitraryFolder = Join-Path $testRoot 'arbitrary-project'
    New-Item -ItemType Directory -Path $arbitraryFolder | Out-Null
    Push-Location $arbitraryFolder
    try {
        & (Join-Path $freshTarget 'biexce-bin\biexce.cmd') --help *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Installed biexce command failed outside the source repository."
        }
    }
    finally {
        Pop-Location
    }
    Write-Host "PASS: Windows fresh install and idempotent reinstall"

    $mergeTarget = Join-Path $testRoot "merge"
    New-Item -ItemType Directory -Path $mergeTarget | Out-Null
    Write-TestText `
        -Path (Join-Path $mergeTarget "opencode.json") `
        -Content '{"plugin":["keep"],"mcp":{"keep":{"type":"local"}}}'
    & $installer -TargetPath $mergeTarget *> $null
    $merged = Get-Content `
        -LiteralPath (Join-Path $mergeTarget "opencode.json") `
        -Raw `
        -Encoding UTF8 |
        ConvertFrom-Json
    if (
        @($merged.plugin).Count -ne 1 -or
        $merged.plugin[0] -ne "keep" -or
        $null -eq $merged.mcp.keep
    ) {
        throw "Windows merge did not preserve custom config."
    }
    Write-Host "PASS: Windows merge preserves custom config"

    $jsoncTarget = Join-Path $testRoot "jsonc"
    New-Item -ItemType Directory -Path $jsoncTarget | Out-Null
    $jsoncPath = Join-Path $jsoncTarget "opencode.jsonc"
    $jsoncBytes = $utf8.GetBytes("{`r`n  `"plugin`": [`"keep`"]`r`n}`r`n")
    [IO.File]::WriteAllBytes($jsoncPath, $jsoncBytes)
    & $installer -TargetPath $jsoncTarget *> $null
    if (
        (Test-Path -LiteralPath $jsoncPath) -or
        -not (Test-Path -LiteralPath (Join-Path $jsoncTarget "opencode.json"))
    ) {
        throw "Windows strict JSONC migration did not complete."
    }
    $backup = Get-ChildItem `
        -LiteralPath $testRoot `
        -Directory `
        -Filter "jsonc.biexce-backup-*" |
        Select-Object -First 1
    if (
        $null -eq $backup -or
        [Convert]::ToBase64String(
            [IO.File]::ReadAllBytes(
                (Join-Path $backup.FullName "opencode.jsonc")
            )
        ) -ne [Convert]::ToBase64String($jsoncBytes)
    ) {
        throw "Windows JSONC backup did not preserve original bytes."
    }
    Write-Host "PASS: Windows strict JSONC migration preserves backup bytes"

    foreach ($case in @(
        [pscustomobject]@{
            Name = "real-jsonc"
            Files = [ordered]@{
                "opencode.jsonc" = "{`n// keep`n`"plugin`":[]`n}`n"
            }
        },
        [pscustomobject]@{
            Name = "both-configs"
            Files = [ordered]@{
                "opencode.json" = "{}"
                "opencode.jsonc" = "{}"
            }
        },
        [pscustomobject]@{
            Name = "malformed-json"
            Files = [ordered]@{
                "opencode.json" = "{`"plugin`":[}"
            }
        }
    )) {
        $target = Join-Path $testRoot $case.Name
        New-Item -ItemType Directory -Path $target | Out-Null
        $original = @{}
        foreach ($name in $case.Files.Keys) {
            $path = Join-Path $target $name
            Write-TestText -Path $path -Content $case.Files[$name]
            $original[$name] = [IO.File]::ReadAllBytes($path)
        }
        Invoke-ExpectedInstallFailure -TargetPath $target
        foreach ($name in $case.Files.Keys) {
            $actualBytes = [IO.File]::ReadAllBytes(
                (Join-Path $target $name)
            )
            if (
                [Convert]::ToBase64String($actualBytes) -ne
                [Convert]::ToBase64String($original[$name])
            ) {
                throw "Windows preflight failure mutated $($case.Name)/$name."
            }
        }
    }
    Write-Host "PASS: Windows invalid/conflicting configs fail without mutation"

    $rollbackTarget = Join-Path $testRoot "rollback"
    New-Item -ItemType Directory -Path (
        Join-Path $rollbackTarget "agents"
    ) | Out-Null
    $rollbackJsonc = Join-Path $rollbackTarget "opencode.jsonc"
    $rollbackAgent = Join-Path $rollbackTarget "agents\bx-code.md"
    Write-TestText -Path $rollbackJsonc -Content '{"plugin":["keep"]}'
    Write-TestText -Path $rollbackAgent -Content "existing user agent"
    $originalJsonc = [IO.File]::ReadAllBytes($rollbackJsonc)
    $originalAgent = [IO.File]::ReadAllBytes($rollbackAgent)
    $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION = "1"
    Invoke-ExpectedInstallFailure -TargetPath $rollbackTarget
    $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION = $null
    if (
        (Test-Path -LiteralPath (Join-Path $rollbackTarget "opencode.json")) -or
        [Convert]::ToBase64String(
            [IO.File]::ReadAllBytes($rollbackJsonc)
        ) -ne [Convert]::ToBase64String($originalJsonc) -or
        [Convert]::ToBase64String(
            [IO.File]::ReadAllBytes($rollbackAgent)
        ) -ne [Convert]::ToBase64String($originalAgent)
    ) {
        throw "Windows rollback did not restore original managed files."
    }
    Write-Host "PASS: Windows failure after mutation rolls back"
    Write-Host "Windows installer integration matrix: PASS"
}
finally {
    $env:PATH = $previousPath
    $env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION = $previousFailureSwitch
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
