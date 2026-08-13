param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
).TrimEnd("\")
$verifyPath = Join-Path $repositoryRoot "scripts\verify.ps1"
$canonicalConfig = Join-Path $repositoryRoot "src\global\opencode.json"
$manifest = Get-Content `
    -LiteralPath (Join-Path $repositoryRoot "src\harness-manifest.json") `
    -Raw `
    -Encoding UTF8 |
    ConvertFrom-Json -ErrorAction Stop
$minimumVersion = [string]$manifest.supported_opencode.minimum
$maximumVersion = [string]$manifest.supported_opencode.maximum_exclusive
$supportedRange = ">= $minimumVersion and < $maximumVersion"
$expectedModel = (
    [string]$manifest.provider.id +
    "/" +
    [string]$manifest.provider.model.id
)
$expectedAgentList = @(
    $manifest.agents |
        ForEach-Object { "$($_.id) ($($_.mode))" }
) -join [Environment]::NewLine
$expectedSkillList = @(
    $manifest.skills |
        ForEach-Object { '{"name":"' + [string]$_.id + '"}' }
) -join [Environment]::NewLine
$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\")
$testRoot = Join-Path (
    $temporaryBase
) ("biexce-cli-version-test-" + [guid]::NewGuid().ToString("N"))
$cliDirectory = Join-Path $testRoot "CLI With Spaces"
$fakeCommand = Join-Path $cliDirectory "opencode.cmd"
$fakeScript = Join-Path $cliDirectory "fake-opencode.ps1"
$systemPath = @(
    "$env:SystemRoot\System32",
    "$env:SystemRoot",
    "$env:SystemRoot\System32\WindowsPowerShell\v1.0"
) -join ";"

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    [IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object Text.UTF8Encoding($false))
    )
}

function Invoke-VerifyCase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Mode,

        [bool]$IncludeCli = $true
    )

    $powerShellPath = Join-Path $PSHOME "powershell.exe"
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $powerShellPath
    $startInfo.Arguments = (
        "-NoProfile -ExecutionPolicy Bypass -File `"$verifyPath`""
    )
    $startInfo.WorkingDirectory = $repositoryRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    $startInfo.EnvironmentVariables["PATH"] = if ($IncludeCli) {
        "$cliDirectory;$systemPath"
    }
    else {
        $systemPath
    }
    $startInfo.EnvironmentVariables["BIEXCE_TEST_VERSION_MODE"] = $Mode
    $startInfo.EnvironmentVariables["BIEXCE_TEST_CONFIG"] = $canonicalConfig
    $startInfo.EnvironmentVariables["BIEXCE_TEST_MODEL"] = $expectedModel
    $startInfo.EnvironmentVariables["BIEXCE_TEST_AGENTS"] = $expectedAgentList
    $startInfo.EnvironmentVariables["BIEXCE_TEST_SKILLS"] = $expectedSkillList
    $startInfo.EnvironmentVariables.Remove("OPENCODE_CONFIG")
    $startInfo.EnvironmentVariables.Remove("OPENCODE_CONFIG_CONTENT")

    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = ($stdout + [Environment]::NewLine + $stderr).Trim()
    }
}

function Assert-PassCase {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Result,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string]$ExpectedVersion
    )

    if (
        $Result.ExitCode -ne 0 -or
        $Result.Output -notmatch [regex]::Escape(
            "PASS: OpenCode CLI version $ExpectedVersion is supported " +
            "($supportedRange)"
        )
    ) {
        throw "$Label failed.`n$($Result.Output)"
    }
    Write-Host "PASS: $Label"
}

New-Item -ItemType Directory -Path $cliDirectory -Force | Out-Null

$fakeCommandContent = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0fake-opencode.ps1" %*
exit /b %ERRORLEVEL%
'@
$fakeScriptContent = @'
if (
    $env:OPENCODE_DISABLE_EXTERNAL_SKILLS -ne "1" -or
    $env:OPENCODE_DISABLE_CLAUDE_CODE_SKILLS -ne "1"
) {
    [Console]::Error.Write("external skill discovery was not isolated")
    exit 26
}

$mode = $env:BIEXCE_TEST_VERSION_MODE

if ($args.Count -eq 1 -and $args[0] -eq "--version") {
    switch ($mode) {
        "minimum" {
            [Console]::Out.Write("1.18.4")
            exit 0
        }
        "compatible" {
            [Console]::Out.Write("1.18.7")
            exit 0
        }
        "crlf" {
            [Console]::Out.Write("  1.18.7  `r`n`r`n")
            exit 0
        }
        "stderr" {
            [Console]::Error.Write("1.18.7`r`n")
            exit 0
        }
        "ansi" {
            [Console]::Out.Write(
                "$([char]27)[32m1.18.7$([char]27)[0m`r`n"
            )
            exit 0
        }
        "below" {
            [Console]::Out.Write("1.18.3`r`n")
            exit 0
        }
        "maximum" {
            [Console]::Out.Write("1.19.0`r`n")
            exit 0
        }
        "failure" {
            [Console]::Error.Write("simulated version failure`r`n")
            exit 23
        }
        default {
            [Console]::Error.Write("unknown test mode")
            exit 24
        }
    }
}

$command = $args -join " "
switch ($command) {
    "agent list --pure" {
        $env:BIEXCE_TEST_AGENTS
        exit 0
    }
    "debug config --pure" {
        [Console]::Out.Write(
            [IO.File]::ReadAllText($env:BIEXCE_TEST_CONFIG)
        )
        exit 0
    }
    "models biexce-local --pure" {
        $env:BIEXCE_TEST_MODEL
        exit 0
    }
    "debug skill --pure" {
        $env:BIEXCE_TEST_SKILLS
        exit 0
    }
    default {
        [Console]::Error.Write("unexpected fake command: $command")
        exit 25
    }
}
'@

Write-Utf8NoBom -Path $fakeCommand -Content $fakeCommandContent
Write-Utf8NoBom -Path $fakeScript -Content $fakeScriptContent

try {
    if ($cliDirectory -notmatch "\s") {
        throw "CLI test directory must contain a space."
    }

    Assert-PassCase `
        -Result (Invoke-VerifyCase -Mode "minimum") `
        -Label "minimum supported version 1.18.4" `
        -ExpectedVersion "1.18.4"
    Assert-PassCase `
        -Result (Invoke-VerifyCase -Mode "compatible") `
        -Label "compatible version 1.18.7" `
        -ExpectedVersion "1.18.7"
    Assert-PassCase `
        -Result (Invoke-VerifyCase -Mode "crlf") `
        -Label "CRLF and trailing-space version output" `
        -ExpectedVersion "1.18.7"
    Assert-PassCase `
        -Result (Invoke-VerifyCase -Mode "stderr") `
        -Label "version output written to stderr" `
        -ExpectedVersion "1.18.7"
    Assert-PassCase `
        -Result (Invoke-VerifyCase -Mode "ansi") `
        -Label "ANSI-decorated version output" `
        -ExpectedVersion "1.18.7"
    Write-Host "PASS: executable path contains spaces"

    $noCli = Invoke-VerifyCase -Mode "minimum" -IncludeCli $false
    if (
        $noCli.ExitCode -ne 0 -or
        $noCli.Output -notmatch "Static verification: PASS" -or
        $noCli.Output -notmatch [regex]::Escape(
            "OpenCode CLI is not available in PATH. Static installation passed."
        )
    ) {
        throw "No-CLI case failed.`n$($noCli.Output)"
    }
    Write-Host "PASS: missing CLI defers runtime verification"

    foreach ($unsupportedCase in @(
        [pscustomobject]@{ Mode = "below"; Version = "1.18.3" },
        [pscustomobject]@{ Mode = "maximum"; Version = "1.19.0" }
    )) {
        $unsupported = Invoke-VerifyCase -Mode $unsupportedCase.Mode
        $unsupportedMessage = (
            "Unsupported OpenCode CLI version '$($unsupportedCase.Version)'. " +
            "Supported range: $supportedRange."
        )
        if (
            $unsupported.ExitCode -eq 0 -or
            $unsupported.Output -notmatch [regex]::Escape($unsupportedMessage)
        ) {
            throw (
                "Unsupported-version case failed: " +
                "$($unsupportedCase.Version).`n$($unsupported.Output)"
            )
        }
        Write-Host (
            "PASS: unsupported version $($unsupportedCase.Version) " +
            "reports the supported range"
        )
    }

    $failure = Invoke-VerifyCase -Mode "failure"
    $failureMessage = (
        "OpenCode command failed with exit code 23: opencode --version. " +
        "Output: simulated version failure"
    )
    if (
        $failure.ExitCode -eq 0 -or
        $failure.Output -notmatch [regex]::Escape($failureMessage)
    ) {
        throw "Nonzero-exit case failed.`n$($failure.Output)"
    }
    Write-Host "PASS: nonzero CLI exit reports command, exit code, and output"

    Write-Host "CLI version regression matrix: PASS"
}
finally {
    $resolvedRoot = [IO.Path]::GetFullPath($testRoot)
    if (
        $resolvedRoot.StartsWith(
            $temporaryBase + "\",
            [StringComparison]::OrdinalIgnoreCase
        ) -and
        (Test-Path -LiteralPath $resolvedRoot -PathType Container)
    ) {
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
}
