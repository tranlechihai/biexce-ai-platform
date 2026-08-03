param(
    [string]$TargetPath = (Join-Path $env:USERPROFILE '.config\opencode')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
).TrimEnd('\')
$modulePath = Join-Path $PSScriptRoot 'Biexce.OpenCode.Common.psm1'
$verifyPath = Join-Path $PSScriptRoot 'verify.ps1'
Import-Module -Name $modulePath -Force
$manifest = Get-BiexceHarnessManifest -RepositoryRoot $repositoryRoot

Write-Host 'Biexce Doctor'
Write-Host "Manifest schema: $($manifest.schema_version)"
Write-Host "Agents: $(@($manifest.agents).Count)"
$ready = @($manifest.skills | Where-Object status -eq 'ready').Count
$draft = @($manifest.skills | Where-Object status -eq 'draft').Count
$skeleton = @($manifest.skills | Where-Object status -eq 'skeleton').Count
Write-Host (
    "Skills: $(@($manifest.skills).Count) " +
    "(ready=$ready, draft=$draft, skeleton=$skeleton)"
)
Write-Host "Model binding: $($manifest.model_binding.state)"

& $verifyPath -SkipCli *> $null
if (-not $?) {
    throw 'Canonical source verification failed.'
}
Write-Host 'Source contract: PASS'

$resolvedTarget = [IO.Path]::GetFullPath($TargetPath).TrimEnd('\')
if (Test-Path -LiteralPath $resolvedTarget -PathType Container) {
    & $verifyPath -TargetPath $resolvedTarget -SkipCli *> $null
    if (-not $?) {
        throw 'Installed target verification failed.'
    }
    Write-Host "Installed target: PASS ($resolvedTarget)"
}
else {
    Write-Host "Installed target: WARN (not found: $resolvedTarget)"
}

$openCodeCommand = Resolve-BiexceOpenCodeCommand
if ($null -eq $openCodeCommand) {
    Write-Host 'OpenCode CLI: WARN (not found in PATH)'
}
else {
    $versionOutput = Invoke-BiexceOpenCode `
        -Arguments @('--version') `
        -ConfigDirectory (Join-Path $repositoryRoot 'src\global') `
        -OpenCodeCommand $openCodeCommand
    $version = Get-BiexceOpenCodeVersion -OutputObject $versionOutput
    $supported = Test-BiexceOpenCodeVersionInRange `
        -Version $version `
        -MinimumVersion ([string]$manifest.supported_opencode.minimum) `
        -MaximumVersionExclusive ([string]$manifest.supported_opencode.maximum_exclusive)
    if (-not $supported) {
        throw "Unsupported OpenCode CLI version: $version"
    }
    Write-Host "OpenCode CLI: PASS ($version)"
}

$baseUrl = [string]$manifest.provider.base_url
$environmentMatch = [regex]::Match(
    $baseUrl,
    '^\{env:([A-Za-z_][A-Za-z0-9_]*)\}$'
)
if ($environmentMatch.Success) {
    $variableName = $environmentMatch.Groups[1].Value
    $baseUrl = [Environment]::GetEnvironmentVariable($variableName, 'Process')
    if ([string]::IsNullOrWhiteSpace($baseUrl)) {
        $baseUrl = [Environment]::GetEnvironmentVariable($variableName, 'User')
    }
}

if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    Write-Host 'Bifrost endpoint: WARN (BIEXCE_LOCAL_BASE_URL is not set)'
}
else {
    $endpoint = [uri]$baseUrl
    $port = if ($endpoint.IsDefaultPort) {
        if ($endpoint.Scheme -eq 'https') { 443 } else { 80 }
    }
    else {
        $endpoint.Port
    }
    $client = New-Object Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect($endpoint.Host, $port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(2000, $false)) {
            Write-Host "Bifrost endpoint: WARN ($($endpoint.Host):$port timeout)"
        }
        else {
            $client.EndConnect($connect)
            Write-Host "Bifrost endpoint: PASS ($($endpoint.Host):$port)"
        }
    }
    catch {
        Write-Host "Bifrost endpoint: WARN ($($endpoint.Host):$port unreachable)"
    }
    finally {
        $client.Dispose()
    }
}

Write-Host 'Credentials: PASS (no secret literal in managed config)'
Write-Host 'Doctor result: PASS (endpoint warnings are non-fatal)'
