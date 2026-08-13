param(
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
).TrimEnd("\")
$versionPath = Join-Path $repositoryRoot "VERSION"
$version = (Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8).Trim()
$manifestPath = Join-Path $repositoryRoot "src\harness-manifest.json"
$manifest = (
    Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
) | ConvertFrom-Json -ErrorAction Stop

if ($version -notmatch "^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$") {
    throw "VERSION has an unsupported format: $version"
}

if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputRoot | Out-Null
}

$resolvedOutputRoot = [IO.Path]::GetFullPath(
    (Resolve-Path -LiteralPath $OutputRoot).Path
).TrimEnd("\")
if (
    $resolvedOutputRoot -eq $repositoryRoot -or
    $resolvedOutputRoot.StartsWith(
        $repositoryRoot + "\",
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "Package output must be outside the source repository."
}

$packageName = "biexce-opencode-agent-harness-$version"
$finalPackageRoot = Join-Path $resolvedOutputRoot $packageName
$finalZipPath = "$finalPackageRoot.zip"
if (
    (Test-Path -LiteralPath $finalPackageRoot) -or
    (Test-Path -LiteralPath $finalZipPath)
) {
    throw "Refusing to overwrite an existing package: $packageName"
}

$python = Get-Command python -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $python) {
    throw "Python 3 is required to validate the cross-platform package."
}

function Invoke-BiexcePython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    # Python unittest writes verbose progress to stderr. Windows PowerShell 5
    # promotes native stderr to NativeCommandError when the script-wide error
    # preference is Stop, even when the process exits 0. Capture both streams
    # and decide only from the native exit code.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $nativeOutput = @(& $python.Source @Arguments 2>&1)
        $nativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    foreach ($line in $nativeOutput) {
        Write-Host ([string]$line)
    }
    if ($nativeExitCode -ne 0) {
        throw "$FailureMessage (exit $nativeExitCode)"
    }
}

Write-Host "Running package preflight..."
& (Join-Path $PSScriptRoot "verify.ps1") -SkipCli
& (Join-Path $repositoryRoot "tests\unit\verify-cli-version.ps1")
& (Join-Path $repositoryRoot "tests\integration\test-windows-installer.ps1")

$previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
try {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    Invoke-BiexcePython `
        -Arguments @(
            "-B", "-m", "unittest", "discover",
            "-s", (Join-Path $repositoryRoot "tests\unit"),
            "-p", "test_*.py", "-v"
        ) `
        -FailureMessage "Python unit tests failed."
    Invoke-BiexcePython `
        -Arguments @(
            "-B", "-m", "unittest", "discover",
            "-s", (Join-Path $repositoryRoot "tests\integration"),
            "-p", "test_*.py", "-v"
        ) `
        -FailureMessage "Python integration tests failed."
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
}
Write-Host "Package preflight: PASS"

$releaseFiles = @(
    "bin\windows\install.cmd",
    "bin\windows\verify.cmd",
    "bin\windows\doctor.cmd",
    "bin\windows\biexce.cmd",
    "bin\windows\biexce-global.cmd",
    "bin\linux\install.sh",
    "bin\linux\verify.sh",
    "bin\linux\doctor.sh",
    "bin\linux\biexce.sh",
    "bin\linux\biexce-global",
    "bin\macos\install.command",
    "bin\macos\verify.command",
    "bin\macos\doctor.command",
    "bin\macos\biexce.command",
    "bin\macos\biexce-global",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "VERSION",
    "docs\AGENT-GUIDE.md",
    "docs\AGENT-ROLES.md",
    "docs\AGENT-SKILL-CATALOG.md",
    "docs\CONTROL-QUICKSTART.md",
    "docs\INSTALL-WINDOWS.md",
    "docs\INSTALL-UBUNTU.md",
    "docs\INSTALL-MACOS.md",
    "src\harness-manifest.json",
    "src\harness-manifest.schema.json",
    "src\global\opencode.json",
    "src\global\package.json",
    "scripts\Biexce.OpenCode.Common.psm1",
    "scripts\biexce.py",
    "scripts\biexce_linux.py",
    "scripts\install.ps1",
    "scripts\verify.ps1",
    "scripts\doctor.ps1",
    "scripts\update_manifest.py",
    "scripts\validate_skills.py",
    "src\biexce_control\__init__.py",
    "src\biexce_control\autopilot.py",
    "src\biexce_control\cli.py",
    "src\biexce_control\fixture.py",
    "src\biexce_control\gate0.py",
    "src\biexce_control\model_routing.py",
    "src\biexce_control\validation.py",
    "src\biexce_control\workflow.py",
    "src\biexce_control\schemas\autopilot-state-v1.schema.json",
    "src\biexce_control\schemas\agent-result-v1.schema.json",
    "src\biexce_control\schemas\job-board-v1.schema.json",
    "src\biexce_control\schemas\scheduler-state-v1.schema.json",
    "src\biexce_control\schemas\workflow-policy-v1.schema.json",
    "src\biexce_control\schemas\session-registry-v1.schema.json",
    "src\biexce_control\schemas\autopilot-command-v1.schema.json",
    "src\biexce_control\schemas\autopilot-workflow-v1.schema.json",
    "src\biexce_control\schemas\autopilot-workflow-v2.schema.json",
    "src\biexce_control\schemas\model-routing-v1.schema.json",
    "src\biexce_control\schemas\model-routing-applied-v1.schema.json",
    "src\biexce_control\schemas\server-evidence-v1.schema.json"
)
$releaseFiles += @(
    @($manifest.agents) + @($manifest.skills) + @($manifest.runtime_files) |
        ForEach-Object {
            'src\global\' + ([string]$_.path).Replace('/', '\')
        }
)
$releaseFiles += @(
    Get-ChildItem `
        -LiteralPath (Join-Path $repositoryRoot "src\biexce_control\resources") `
        -Recurse `
        -Force `
        -File |
        ForEach-Object {
            $_.FullName.Substring($repositoryRoot.Length + 1)
        }
)

$stageRoot = Join-Path (
    $resolvedOutputRoot
) (".biexce-package-stage-" + [guid]::NewGuid().ToString("N"))
$stagePackageRoot = Join-Path $stageRoot $packageName
$stageZipPath = Join-Path $stageRoot "$packageName.zip"
$publishedDirectory = $false
$publishedZip = $false

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

try {
    New-Item -ItemType Directory -Path $stagePackageRoot | Out-Null

    foreach ($relativePath in $releaseFiles) {
        $sourcePath = Join-Path $repositoryRoot $relativePath
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Release source file is missing: $relativePath"
        }

        $destinationPath = Join-Path $stagePackageRoot $relativePath
        $destinationDirectory = Split-Path -Parent $destinationPath
        if (
            -not (
                Test-Path `
                    -LiteralPath $destinationDirectory `
                    -PathType Container
            )
        ) {
            New-Item `
                -ItemType Directory `
                -Path $destinationDirectory |
                Out-Null
        }
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
    }

    $expectedAgents = @($manifest.agents | ForEach-Object { [string]$_.id })
    $packagedAgents = @(
        Get-ChildItem `
            -LiteralPath (Join-Path $stagePackageRoot "src\global\agents") `
            -File `
            -Filter "*.md" |
            Sort-Object BaseName |
            ForEach-Object BaseName
    )
    if (@(Compare-Object $expectedAgents $packagedAgents).Count -ne 0) {
        throw "Package does not contain exactly the manifest agents."
    }

    $hashLines = Get-ChildItem `
        -LiteralPath $stagePackageRoot `
        -Recurse `
        -Force `
        -File |
        Sort-Object FullName |
        ForEach-Object {
            $hash = (
                Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            ).Hash
            $relative = $_.FullName.Substring(
                $stagePackageRoot.Length + 1
            ).Replace("\", "/")
            "$hash  $relative"
        }
    [IO.File]::WriteAllLines(
        (Join-Path $stagePackageRoot "SHA256SUMS.txt"),
        $hashLines,
        (New-Object Text.UTF8Encoding($false))
    )

    $packageFiles = @(
        Get-ChildItem `
            -LiteralPath $stagePackageRoot `
            -Recurse `
            -Force `
            -File |
            Sort-Object FullName
    )
    $zipStream = [IO.File]::Open(
        $stageZipPath,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )
    try {
        $archive = New-Object IO.Compression.ZipArchive(
            $zipStream,
            [IO.Compression.ZipArchiveMode]::Create,
            $false
        )
        try {
            foreach ($file in $packageFiles) {
                $relativePath = $file.FullName.Substring(
                    $stagePackageRoot.Length + 1
                ).Replace("\", "/")
                $entryName = "$packageName/$relativePath"
                if ($entryName.Contains("\")) {
                    throw "ZIP entry contains a Windows backslash: $entryName"
                }

                $entry = [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    $file.FullName,
                    $entryName,
                    [IO.Compression.CompressionLevel]::Optimal
                )
                if (
                    $file.Extension -in @(".sh", ".command") -or
                    $relativePath -in @(
                        "bin/linux/biexce-global",
                        "bin/macos/biexce-global"
                    )
                ) {
                    # POSIX regular file mode 0755 is required by shell and Finder.
                    $entry.ExternalAttributes = -2115174400
                }
            }
        }
        finally {
            $archive.Dispose()
        }
    }
    finally {
        $zipStream.Dispose()
    }

    $readArchive = [IO.Compression.ZipFile]::OpenRead($stageZipPath)
    try {
        $archiveEntries = @(
            $readArchive.Entries |
                Where-Object { -not [string]::IsNullOrEmpty($_.Name) } |
                ForEach-Object {
                    [pscustomobject]@{
                        Name = $_.FullName
                        ExternalAttributes = $_.ExternalAttributes
                    }
                }
        )
    }
    finally {
        $readArchive.Dispose()
    }

    $entryNames = @($archiveEntries | ForEach-Object Name)
    $expectedEntryNames = @(
        $packageFiles |
            ForEach-Object {
                $relativePath = $_.FullName.Substring(
                    $stagePackageRoot.Length + 1
                ).Replace("\", "/")
                "$packageName/$relativePath"
            }
    )
    if (@($entryNames | Where-Object { $_.Contains("\") }).Count -ne 0) {
        throw "ZIP validation failed: an entry contains a Windows backslash."
    }
    if (
        @(
            Compare-Object `
                ($expectedEntryNames | Sort-Object) `
                ($entryNames | Sort-Object)
        ).Count -ne 0
    ) {
        throw "ZIP validation failed: archive entries do not match package files."
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
        $expected = "$packageName/$relativePath"
        $entry = $archiveEntries |
            Where-Object Name -eq $expected |
            Select-Object -First 1
        if ($null -eq $entry -or $entry.ExternalAttributes -ne -2115174400) {
            throw "ZIP executable mode is missing: $expected"
        }
    }

    & (Join-Path $repositoryRoot "tests\integration\verify-package.ps1") `
        -ZipPath $stageZipPath `
        -PackageName $packageName

    $previousBytecodeSetting = $env:PYTHONDONTWRITEBYTECODE
    try {
        $env:PYTHONDONTWRITEBYTECODE = "1"
        Invoke-BiexcePython `
            -Arguments @(
                "-B",
                (Join-Path $repositoryRoot "tests\integration\verify_package.py"),
                "--zip", $stageZipPath,
                "--package-name", $packageName,
                "--repository-root", $repositoryRoot
            ) `
            -FailureMessage "Python zipfile package verification failed."
    }
    finally {
        $env:PYTHONDONTWRITEBYTECODE = $previousBytecodeSetting
    }

    Move-Item -LiteralPath $stagePackageRoot -Destination $finalPackageRoot
    $publishedDirectory = $true
    Move-Item -LiteralPath $stageZipPath -Destination $finalZipPath
    $publishedZip = $true

    $zipHash = (
        Get-FileHash -LiteralPath $finalZipPath -Algorithm SHA256
    ).Hash
    Write-Host "Created package directory: $finalPackageRoot"
    Write-Host "Created package archive:   $finalZipPath"
    Write-Host "Package SHA-256:           $zipHash"
    Write-Host "Validated ZIP entries:     $($entryNames.Count)"
    Write-Host "Validated Unix launchers:   mode 0755"
}
catch {
    if ($publishedZip -and (Test-Path -LiteralPath $finalZipPath)) {
        Remove-Item -LiteralPath $finalZipPath -Force
    }
    if ($publishedDirectory -and (Test-Path -LiteralPath $finalPackageRoot)) {
        Remove-Item -LiteralPath $finalPackageRoot -Recurse -Force
    }
    throw
}
finally {
    $resolvedStageRoot = [IO.Path]::GetFullPath($stageRoot)
    if (
        $resolvedStageRoot.StartsWith(
            $resolvedOutputRoot + "\",
            [StringComparison]::OrdinalIgnoreCase
        ) -and
        (Split-Path -Leaf $resolvedStageRoot).StartsWith(
            ".biexce-package-stage-",
            [StringComparison]::Ordinal
        ) -and
        (Test-Path -LiteralPath $resolvedStageRoot -PathType Container)
    ) {
        Remove-Item -LiteralPath $resolvedStageRoot -Recurse -Force
    }
}
