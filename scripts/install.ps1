param(
    [string]$TargetPath = (Join-Path $env:USERPROFILE ".config\opencode"),
    [switch]$ActivateCommand
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
).TrimEnd("\")
$sourceRoot = Join-Path $repositoryRoot "src\global"
$modulePath = Join-Path $PSScriptRoot "Biexce.OpenCode.Common.psm1"
$verifyScriptPath = Join-Path $PSScriptRoot "verify.ps1"
$repositoryOpenCodePath = Join-Path $repositoryRoot ".opencode"
$versionPath = Join-Path $repositoryRoot "VERSION"
$cliWarning = (
    "OpenCode CLI is not available in PATH. Static installation passed. " +
    "Restart OpenCode Desktop and verify agents/model in the UI."
)

function Get-BiexceCliCopyPairs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $pairs = [ordered]@{
        'biexce-cli\scripts\biexce.py' = (
            Join-Path $RepositoryRoot 'scripts\biexce.py'
        )
        'biexce-cli\src\global\opencode.json' = (
            Join-Path $RepositoryRoot 'src\global\opencode.json'
        )
    }
    foreach ($definition in @(
        [pscustomobject]@{
            Source = Join-Path $RepositoryRoot 'src\biexce_control'
            Destination = 'biexce-cli\src\biexce_control'
        },
        [pscustomobject]@{
            Source = Join-Path $RepositoryRoot 'src\global\basic'
            Destination = 'biexce-cli\src\global\basic'
        },
        [pscustomobject]@{
            Source = Join-Path $RepositoryRoot 'src\global\skills'
            Destination = 'biexce-cli\src\global\skills'
        }
    )) {
        $base = [IO.Path]::GetFullPath($definition.Source).TrimEnd(
            [IO.Path]::DirectorySeparatorChar
        )
        foreach ($file in @(
            Get-ChildItem -LiteralPath $base -Recurse -File |
                Where-Object {
                    $_.Extension -ne '.pyc' -and
                    $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
                    $_.FullName -notmatch '[\\/]_TEMPLATE[\\/]'
                } |
                Sort-Object FullName
        )) {
            $relative = $file.FullName.Substring($base.Length + 1)
            $destination = Join-Path $definition.Destination $relative
            $pairs[$destination] = $file.FullName
        }
    }
    $pairs['biexce-bin\biexce.cmd'] = Join-Path (
        $RepositoryRoot
    ) 'bin\windows\biexce-global.cmd'
    return $pairs
}

function Add-BiexceUserPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandDirectory
    )

    $resolved = [IO.Path]::GetFullPath($CommandDirectory).TrimEnd(
        [IO.Path]::DirectorySeparatorChar
    )
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @(
        ([string]$userPath).Split(';') |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    $present = $false
    foreach ($entry in $entries) {
        try {
            $candidate = [IO.Path]::GetFullPath($entry.Trim()).TrimEnd(
                [IO.Path]::DirectorySeparatorChar
            )
            if ($candidate.Equals($resolved, [StringComparison]::OrdinalIgnoreCase)) {
                $present = $true
                break
            }
        }
        catch {
            continue
        }
    }
    if (-not $present) {
        $nextPath = (@($resolved) + $entries) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $nextPath, 'User')
        Write-Host "Added to user PATH: $resolved"
    }
    else {
        Write-Host "User PATH already contains: $resolved"
    }
    if (-not (($env:PATH -split ';') -contains $resolved)) {
        $env:PATH = "$resolved;$env:PATH"
    }
}

Import-Module -Name $modulePath -Force
$manifest = Get-BiexceHarnessManifest -RepositoryRoot $repositoryRoot
$expectedProviderId = [string]$manifest.provider.id
$expectedModelId = [string]$manifest.provider.model.id
$expectedModel = "$expectedProviderId/$expectedModelId"

function New-BiexceSelectiveBackup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Changes,

        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    if ($Changes.Count -eq 0) {
        return $null
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
    $basePath = "$Root.biexce-backup-$timestamp"
    $backupPath = $basePath
    $suffix = 0

    while (Test-Path -LiteralPath $backupPath) {
        $suffix++
        $backupPath = "$basePath-$suffix"
    }

    New-Item -ItemType Directory -Path $backupPath | Out-Null
    $entries = @()
    $copiedCount = 0

    foreach ($change in $Changes) {
        $existed = Test-Path -LiteralPath $change.DestinationPath -PathType Leaf
        $originalHash = $null
        $backupRelativePath = $null

        if ($existed) {
            $backupRelativePath = $change.RelativePath
            $backupFilePath = Join-Path $backupPath (
                $backupRelativePath.Replace("/", "\")
            )
            $backupDirectory = Split-Path -Parent $backupFilePath
            if (-not (Test-Path -LiteralPath $backupDirectory -PathType Container)) {
                New-Item -ItemType Directory -Path $backupDirectory | Out-Null
            }

            Copy-Item `
                -LiteralPath $change.DestinationPath `
                -Destination $backupFilePath
            $originalHash = (
                Get-FileHash `
                    -LiteralPath $change.DestinationPath `
                    -Algorithm SHA256
            ).Hash
            $backupHash = (
                Get-FileHash `
                    -LiteralPath $backupFilePath `
                    -Algorithm SHA256
            ).Hash
            if ($originalHash -ne $backupHash) {
                throw "Backup verification failed: $($change.RelativePath)"
            }

            $copiedCount++
            Write-Host "Backed up: $($change.DestinationPath) -> $backupFilePath"
        }
        else {
            Write-Host "Rollback record: $($change.RelativePath) did not exist"
        }

        $entries += [pscustomobject][ordered]@{
            path = $change.RelativePath
            existed = $existed
            sha256 = $originalHash
            backup = $backupRelativePath
        }
    }

    $manifest = [pscustomobject][ordered]@{
        version = $Version
        target = $Root
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        files = $entries
    }
    $manifestPath = Join-Path $backupPath "backup-manifest.json"
    Write-BiexceUtf8NoBom `
        -Path $manifestPath `
        -Content (($manifest | ConvertTo-Json -Depth 20) + [Environment]::NewLine)

    return [pscustomobject]@{
        Path = $backupPath
        FileCount = $copiedCount
        ChangedCount = $Changes.Count
        ManifestPath = $manifestPath
    }
}

function Restore-BiexceSelectiveBackup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,

        [Parameter(Mandatory = $true)]
        [psobject]$Backup
    )

    $manifestText = Get-Content `
        -LiteralPath $Backup.ManifestPath `
        -Raw `
        -Encoding UTF8
    $manifest = $manifestText | ConvertFrom-Json -ErrorAction Stop
    $manifestRoot = [IO.Path]::GetFullPath([string]$manifest.target).TrimEnd("\")
    $expectedRoot = [IO.Path]::GetFullPath($Root).TrimEnd("\")
    if (-not $manifestRoot.Equals(
        $expectedRoot,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Backup manifest target does not match install target."
    }

    $entries = @($manifest.files)
    [array]::Reverse($entries)
    foreach ($entry in $entries) {
        $destinationPath = Join-Path $expectedRoot (
            ([string]$entry.path).Replace("/", "\")
        )

        if ([bool]$entry.existed) {
            $backupFilePath = Join-Path $Backup.Path (
                ([string]$entry.backup).Replace("/", "\")
            )
            if (-not (Test-Path -LiteralPath $backupFilePath -PathType Leaf)) {
                throw "Rollback source is missing: $backupFilePath"
            }
            $destinationDirectory = Split-Path -Parent $destinationPath
            if (-not (Test-Path -LiteralPath $destinationDirectory -PathType Container)) {
                New-Item -ItemType Directory -Path $destinationDirectory | Out-Null
            }
            Copy-Item `
                -LiteralPath $backupFilePath `
                -Destination $destinationPath `
                -Force
            $restoredHash = (
                Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256
            ).Hash
            if ($restoredHash -ne [string]$entry.sha256) {
                throw "Rollback hash verification failed: $($entry.path)"
            }
            Write-Host "Restored: $destinationPath"
        }
        elseif (Test-Path -LiteralPath $destinationPath -PathType Leaf) {
            Remove-Item -LiteralPath $destinationPath -Force
            Write-Host "Removed during rollback: $destinationPath"
        }
        elseif (Test-Path -LiteralPath $destinationPath) {
            throw "Rollback target is not a file: $destinationPath"
        }
    }

    Write-Host "Rollback: PASS ($($Backup.Path))"
}

if (Test-Path -LiteralPath $repositoryOpenCodePath) {
    throw "Source repository must not contain a .opencode directory."
}
if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
    throw "VERSION file is missing: $versionPath"
}
if (-not (Test-Path -LiteralPath $verifyScriptPath -PathType Leaf)) {
    throw "Static verifier is missing: $verifyScriptPath"
}
$harnessVersion = (
    Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8
).Trim()

$targetRoot = [IO.Path]::GetFullPath($TargetPath).TrimEnd("\")
$driveRoot = [IO.Path]::GetPathRoot($targetRoot).TrimEnd("\")

if ($targetRoot -eq $driveRoot) {
    throw "Refusing to install into a drive root: $targetRoot"
}
if (
    $targetRoot -eq $repositoryRoot -or
    $targetRoot.StartsWith(
        $repositoryRoot + "\",
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "TargetPath must be outside the source repository."
}
if (
    (Test-Path -LiteralPath $targetRoot) -and
    -not (Test-Path -LiteralPath $targetRoot -PathType Container)
) {
    throw "TargetPath exists but is not a directory: $targetRoot"
}

$copyPairs = [ordered]@{}
$cliCopyPairs = Get-BiexceCliCopyPairs -RepositoryRoot $repositoryRoot
$managedContracts = (
    @($manifest.agents) +
    @($manifest.skills) +
    @($manifest.runtime_files)
)
foreach ($contract in $managedContracts) {
    $relativePath = ([string]$contract.path).Replace('/', '\')
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        throw 'Manifest contains an empty managed path.'
    }
    if ($copyPairs.Contains($relativePath)) {
        throw "Manifest contains a duplicate managed path: $relativePath"
    }
    $copyPairs[$relativePath] = $relativePath
}
$coreConfigPath = Join-Path $sourceRoot "opencode.json"
$corePackagePath = Join-Path $sourceRoot "package.json"

foreach ($sourceRelativePath in $copyPairs.Keys) {
    $sourcePath = Join-Path $sourceRoot $sourceRelativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Source file is missing: $sourcePath"
    }
}
foreach ($destinationRelativePath in $cliCopyPairs.Keys) {
    $sourcePath = $cliCopyPairs[$destinationRelativePath]
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "CLI source file is missing: $sourcePath"
    }
}
if (-not (Test-Path -LiteralPath $coreConfigPath -PathType Leaf)) {
    throw "Core config is missing: $coreConfigPath"
}
if (-not (Test-Path -LiteralPath $corePackagePath -PathType Leaf)) {
    throw "Plugin package config is missing: $corePackagePath"
}

$targetConfigPath = Join-Path $targetRoot "opencode.json"
$jsoncPath = Join-Path $targetRoot "opencode.jsonc"
$jsonExists = Test-Path -LiteralPath $targetConfigPath
$jsoncExists = Test-Path -LiteralPath $jsoncPath

if ($jsonExists -and $jsoncExists) {
    throw (
        "Both opencode.json and opencode.jsonc exist. " +
        "Resolve the config conflict before installing."
    )
}
foreach ($configCandidate in @($targetConfigPath, $jsoncPath)) {
    if (
        (Test-Path -LiteralPath $configCandidate) -and
        -not (Test-Path -LiteralPath $configCandidate -PathType Leaf)
    ) {
        throw "Managed target exists but is not a file: $configCandidate"
    }
}

$migrateJsonc = $jsoncExists
$existingConfigPath = if ($jsonExists) {
    $targetConfigPath
}
elseif ($jsoncExists) {
    $jsoncPath
}
else {
    $null
}
$existingConfig = [pscustomobject][ordered]@{}
if ($null -ne $existingConfigPath) {
    $existingConfigText = Get-Content `
        -LiteralPath $existingConfigPath `
        -Raw `
        -Encoding UTF8

    try {
        Assert-BiexceStrictJsonText `
            -Text $existingConfigText `
            -PathLabel $existingConfigPath
        $existingConfig = $existingConfigText |
            ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        if ($migrateJsonc) {
            throw (
                "Cannot automatically migrate $jsoncPath because it is not " +
                "strict JSON. JSONC comments and trailing commas are not " +
                "supported automatically. No files were changed."
            )
        }
        throw (
            "Cannot safely parse $targetConfigPath as strict JSON: " +
            "$($_.Exception.Message) No files were changed."
        )
    }

    if ($existingConfig -isnot [pscustomobject]) {
        throw "OpenCode config root must be a JSON object. No files were changed."
    }
}

$managedConfigText = Get-Content `
    -LiteralPath $coreConfigPath `
    -Raw `
    -Encoding UTF8

try {
    Assert-BiexceStrictJsonText `
        -Text $managedConfigText `
        -PathLabel $coreConfigPath
    $managedConfig = $managedConfigText |
        ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "Canonical Biexce config cannot be parsed: $($_.Exception.Message)"
}

$mergedConfig = Merge-BiexceManagedConfig `
    -Existing $existingConfig `
    -Managed $managedConfig
$mergedJson = ConvertTo-BiexceConfigJson -Config $mergedConfig

try {
    Assert-BiexceStrictJsonText `
        -Text $mergedJson `
        -PathLabel "merged OpenCode config"
    $null = $mergedJson | ConvertFrom-Json -ErrorAction Stop
}
catch {
    throw "Merged OpenCode config failed strict JSON validation: $($_.Exception.Message)"
}

$targetPackagePath = Join-Path $targetRoot "package.json"
if (
    (Test-Path -LiteralPath $targetPackagePath) -and
    -not (Test-Path -LiteralPath $targetPackagePath -PathType Leaf)
) {
    throw "Managed target exists but is not a file: $targetPackagePath"
}
$existingPackage = [pscustomobject][ordered]@{}
if (Test-Path -LiteralPath $targetPackagePath -PathType Leaf) {
    $existingPackageText = Get-Content `
        -LiteralPath $targetPackagePath `
        -Raw `
        -Encoding UTF8
    Assert-BiexceStrictJsonText `
        -Text $existingPackageText `
        -PathLabel $targetPackagePath
    $existingPackage = $existingPackageText |
        ConvertFrom-Json -ErrorAction Stop
    if ($existingPackage -isnot [pscustomobject]) {
        throw "package.json root must be a JSON object."
    }
}
$managedPackageText = Get-Content `
    -LiteralPath $corePackagePath `
    -Raw `
    -Encoding UTF8
Assert-BiexceStrictJsonText `
    -Text $managedPackageText `
    -PathLabel $corePackagePath
$managedPackage = $managedPackageText | ConvertFrom-Json -ErrorAction Stop
$mergedPackage = Merge-BiexcePackageConfig `
    -Existing $existingPackage `
    -Managed $managedPackage
$mergedPackageJson = ConvertTo-BiexceConfigJson -Config $mergedPackage
Assert-BiexceStrictJsonText `
    -Text $mergedPackageJson `
    -PathLabel "merged package.json"

$openCodeCommand = Resolve-BiexceOpenCodeCommand
$plannedChanges = @()
$mergedJsonHash = Get-BiexceStringSha256 -Content $mergedJson
$configChanged = (
    -not (Test-Path -LiteralPath $targetConfigPath -PathType Leaf) -or
    (Get-FileHash `
        -LiteralPath $targetConfigPath `
        -Algorithm SHA256
    ).Hash -ne $mergedJsonHash
)

if ($configChanged) {
    $plannedChanges += [pscustomobject]@{
        Kind = "config"
        RelativePath = "opencode.json"
        DestinationPath = $targetConfigPath
        SourcePath = $coreConfigPath
    }
}
$mergedPackageHash = Get-BiexceStringSha256 -Content $mergedPackageJson
$packageChanged = (
    -not (Test-Path -LiteralPath $targetPackagePath -PathType Leaf) -or
    (Get-FileHash `
        -LiteralPath $targetPackagePath `
        -Algorithm SHA256
    ).Hash -ne $mergedPackageHash
)
if ($packageChanged) {
    $plannedChanges += [pscustomobject]@{
        Kind = "package-config"
        RelativePath = "package.json"
        DestinationPath = $targetPackagePath
        SourcePath = $corePackagePath
    }
}
if ($migrateJsonc) {
    $plannedChanges += [pscustomobject]@{
        Kind = "remove"
        RelativePath = "opencode.jsonc"
        DestinationPath = $jsoncPath
        SourcePath = $null
    }
}

foreach ($sourceRelativePath in $copyPairs.Keys) {
    $sourcePath = Join-Path $sourceRoot $sourceRelativePath
    $destinationRelativePath = $copyPairs[$sourceRelativePath].Replace("\", "/")
    $destinationPath = Join-Path $targetRoot $copyPairs[$sourceRelativePath]

    if (
        (Test-Path -LiteralPath $destinationPath) -and
        -not (Test-Path -LiteralPath $destinationPath -PathType Leaf)
    ) {
        throw "Managed target exists but is not a file: $destinationPath"
    }

    $needsCopy = (
        -not (Test-Path -LiteralPath $destinationPath -PathType Leaf) -or
        (Get-FileHash `
            -LiteralPath $sourcePath `
            -Algorithm SHA256
        ).Hash -ne (
            Get-FileHash `
                -LiteralPath $destinationPath `
                -Algorithm SHA256
        ).Hash
    )
    if ($needsCopy) {
        $plannedChanges += [pscustomobject]@{
            Kind = "copy"
            RelativePath = $destinationRelativePath
            DestinationPath = $destinationPath
            SourcePath = $sourcePath
        }
    }
}

foreach ($destinationRelativePath in $cliCopyPairs.Keys) {
    $sourcePath = $cliCopyPairs[$destinationRelativePath]
    $destinationPath = Join-Path $targetRoot $destinationRelativePath
    if (
        (Test-Path -LiteralPath $destinationPath) -and
        -not (Test-Path -LiteralPath $destinationPath -PathType Leaf)
    ) {
        throw "Managed CLI target exists but is not a file: $destinationPath"
    }
    $needsCopy = (
        -not (Test-Path -LiteralPath $destinationPath -PathType Leaf) -or
        (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne (
            Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256
        ).Hash
    )
    if ($needsCopy) {
        $plannedChanges += [pscustomobject]@{
            Kind = 'copy'
            RelativePath = $destinationRelativePath.Replace(
                [IO.Path]::DirectorySeparatorChar,
                [IO.Path]::AltDirectorySeparatorChar
            )
            DestinationPath = $destinationPath
            SourcePath = $sourcePath
        }
    }
}

$backup = New-BiexceSelectiveBackup `
    -Root $targetRoot `
    -Changes @($plannedChanges) `
    -Version $harnessVersion

if ($null -eq $backup) {
    Write-Host "Backup: none (managed files already current)"
}
else {
    Write-Host "Backup: $($backup.Path)"
    Write-Host "Backup manifest: $($backup.ManifestPath)"
    Write-Host (
        "Backup scope: $($backup.ChangedCount) managed paths, " +
        "$($backup.FileCount) existing files copied"
    )
}

$mutationStarted = $false
try {
    $mutationStarted = $true
    if (-not (Test-Path -LiteralPath $targetRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $targetRoot | Out-Null
    }

    foreach ($change in @($plannedChanges | Where-Object Kind -eq "copy")) {
        $sourcePath = $change.SourcePath
        $destinationPath = $change.DestinationPath
        $destinationDirectory = Split-Path -Parent $destinationPath

        if (-not (Test-Path -LiteralPath $destinationDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $destinationDirectory | Out-Null
        }

        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force

        $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
        $installedHash = (
            Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256
        ).Hash
        if ($sourceHash -ne $installedHash) {
            throw "Installed file hash verification failed: $destinationPath"
        }

        Write-Host "Copied: $sourcePath -> $destinationPath"
    }

    foreach ($destinationRelativePath in $cliCopyPairs.Keys) {
        $sourcePath = $cliCopyPairs[$destinationRelativePath]
        $destinationPath = Join-Path $targetRoot $destinationRelativePath
        if (
            -not (Test-Path -LiteralPath $destinationPath -PathType Leaf) -or
            (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne (
                Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256
            ).Hash
        ) {
            throw "Installed CLI file verification failed: $destinationRelativePath"
        }
    }
    Write-Host (
        "Global command staged: " +
        (Join-Path $targetRoot 'biexce-bin\biexce.cmd')
    )

    if ($configChanged) {
        $temporaryConfigPath = Join-Path (
            $targetRoot
        ) (".opencode.json.biexce-" + [guid]::NewGuid().ToString("N") + ".tmp")

        try {
            Write-BiexceUtf8NoBom -Path $temporaryConfigPath -Content $mergedJson
            $temporaryConfigText = Get-Content `
                -LiteralPath $temporaryConfigPath `
                -Raw `
                -Encoding UTF8
            Assert-BiexceStrictJsonText `
                -Text $temporaryConfigText `
                -PathLabel $temporaryConfigPath
            $null = $temporaryConfigText | ConvertFrom-Json -ErrorAction Stop
            Move-Item `
                -LiteralPath $temporaryConfigPath `
                -Destination $targetConfigPath `
                -Force
            Write-Host "Merged: $coreConfigPath -> $targetConfigPath"
            Write-Host (
                "Managed config: default_agent, subagent_depth, share, " +
                "autoupdate, provider.biexce-local, permission, " +
                "disabled built-in agents"
            )
        }
        finally {
            if (Test-Path -LiteralPath $temporaryConfigPath -PathType Leaf) {
                Remove-Item -LiteralPath $temporaryConfigPath -Force
            }
        }
    }
    else {
        Write-Host "Merged: unchanged ($targetConfigPath)"
    }

    if ($packageChanged) {
        $temporaryPackagePath = Join-Path (
            $targetRoot
        ) (".package.json.biexce-" + [guid]::NewGuid().ToString("N") + ".tmp")
        try {
            Write-BiexceUtf8NoBom `
                -Path $temporaryPackagePath `
                -Content $mergedPackageJson
            $temporaryPackageText = Get-Content `
                -LiteralPath $temporaryPackagePath `
                -Raw `
                -Encoding UTF8
            Assert-BiexceStrictJsonText `
                -Text $temporaryPackageText `
                -PathLabel $temporaryPackagePath
            Move-Item `
                -LiteralPath $temporaryPackagePath `
                -Destination $targetPackagePath `
                -Force
        }
        finally {
            if (Test-Path -LiteralPath $temporaryPackagePath -PathType Leaf) {
                Remove-Item -LiteralPath $temporaryPackagePath -Force
            }
        }
        Write-Host "Merged: $corePackagePath -> $targetPackagePath"
    }
    else {
        Write-Host "Merged: unchanged ($targetPackagePath)"
    }

    if ($migrateJsonc) {
        Remove-Item -LiteralPath $jsoncPath -Force
        Write-Host "Migrated: $jsoncPath -> $targetConfigPath"
    }

    if ($env:BIEXCE_INSTALL_TEST_FAIL_AFTER_MUTATION -eq "1") {
        throw "Simulated failure after mutation."
    }

    Write-Host "Running required static verification..."
    & $verifyScriptPath -TargetPath $targetRoot -SkipCli
    if (-not $?) {
        throw "Static installation verification failed."
    }
    Write-Host "Static installation: PASS"

    if ($null -ne $openCodeCommand) {
        $agentList = Invoke-BiexceOpenCode `
            -ConfigDirectory $targetRoot `
            -OpenCodeCommand $openCodeCommand `
            -Arguments @("agent", "list", "--pure")
        $agentListText = $agentList -join "`n"
        $expectedModes = [ordered]@{}
        foreach ($agentContract in @($manifest.agents)) {
            $expectedModes[[string]$agentContract.id] = [string]$agentContract.mode
        }

        foreach ($agentName in $expectedModes.Keys) {
            if (
                $agentListText -notmatch (
                    "(?m)^" +
                    [regex]::Escape($agentName) +
                    " \(" +
                    [regex]::Escape($expectedModes[$agentName]) +
                    "\)"
                )
            ) {
                throw "OpenCode did not discover $agentName as $($expectedModes[$agentName])."
            }
        }

        $modelList = Invoke-BiexceOpenCode `
            -ConfigDirectory $targetRoot `
            -OpenCodeCommand $openCodeCommand `
            -Arguments @("models", $expectedProviderId, "--pure")
        if (
            ($modelList -join "`n") -notmatch (
                "(?m)^" + [regex]::Escape($expectedModel) + "\s*$"
            )
        ) {
            throw "OpenCode did not discover the Biexce local model."
        }

        $skillList = Invoke-BiexceOpenCode `
            -ConfigDirectory $targetRoot `
            -OpenCodeCommand $openCodeCommand `
            -Arguments @("debug", "skill", "--pure")
        $skillListText = $skillList -join "`n"
        foreach ($skillContract in @($manifest.skills)) {
            $skillPattern = (
                '"name"\s*:\s*"' +
                [regex]::Escape([string]$skillContract.id) +
                '"'
            )
            if ($skillListText -notmatch $skillPattern) {
                throw "OpenCode did not discover skill: $($skillContract.id)"
            }
        }

        Write-Host "Runtime verification: PASS"
        Write-Host "Verified agents: $($expectedModes.Keys -join ', ')"
        Write-Host "Verified skills: $(@($manifest.skills).Count)"
        Write-Host "Verified model: $expectedModel"
    }
    else {
        Write-Host "WARNING: $cliWarning" -ForegroundColor Yellow
    }

    if ($ActivateCommand) {
        Add-BiexceUserPath -CommandDirectory (
            Join-Path $targetRoot 'biexce-bin'
        )
        Write-Host "Command ready in new terminals: biexce"
    }

    if (Test-Path -LiteralPath $repositoryOpenCodePath) {
        throw "Installation created an unexpected .opencode directory in the source repository."
    }
}
catch {
    $installError = $_
    if ($mutationStarted -and $null -ne $backup) {
        try {
            Restore-BiexceSelectiveBackup -Root $targetRoot -Backup $backup
        }
        catch {
            throw (
                "Installation failed: $($installError.Exception.Message) " +
                "Rollback also failed: $($_.Exception.Message)"
            )
        }
    }
    throw $installError
}

Write-Host "BIEXCE CLI and compatibility files installed: $targetRoot"
