param(
    [string]$TargetPath,

    [switch]$SkipCli
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
).TrimEnd("\")
$sourceRoot = Join-Path $repositoryRoot "src\global"
$manifestSchemaPath = Join-Path $repositoryRoot "src\harness-manifest.schema.json"
$sourceConfigPath = Join-Path $sourceRoot "opencode.json"
$sourceAgentRoot = Join-Path $sourceRoot "agents"
$sourceSkillRoot = Join-Path $sourceRoot "skills"
$modulePath = Join-Path $PSScriptRoot "Biexce.OpenCode.Common.psm1"

Import-Module -Name $modulePath -Force
$manifest = Get-BiexceHarnessManifest -RepositoryRoot $repositoryRoot
$agentContracts = @($manifest.agents)
$expectedAgents = @($agentContracts | ForEach-Object { [string]$_.id })
$expectedModes = [ordered]@{}
$expectedAgentHashes = [ordered]@{}
foreach ($agentContract in $agentContracts) {
    $agentId = [string]$agentContract.id
    $expectedModes[$agentId] = [string]$agentContract.mode
    $expectedAgentHashes[$agentId] = [string]$agentContract.sha256
}
$skillContracts = @($manifest.skills)
$expectedSkillIds = @($skillContracts | ForEach-Object { [string]$_.id })
$expectedSkillHashes = [ordered]@{}
$expectedSkillPaths = [ordered]@{}
foreach ($skillContract in $skillContracts) {
    $skillId = [string]$skillContract.id
    $expectedSkillHashes[$skillId] = [string]$skillContract.sha256
    $expectedSkillPaths[$skillId] = [string]$skillContract.path
}
$runtimeContracts = @($manifest.runtime_files)
$expectedRuntimeHashes = [ordered]@{}
foreach ($runtimeContract in $runtimeContracts) {
    $expectedRuntimeHashes[[string]$runtimeContract.id] = (
        [string]$runtimeContract.sha256
    )
}
$expectedProviderId = [string]$manifest.provider.id
$expectedProviderName = [string]$manifest.provider.name
$expectedProviderPackage = [string]$manifest.provider.npm
$expectedProviderBaseUrl = [string]$manifest.provider.base_url
$expectedModelId = [string]$manifest.provider.model.id
$expectedModelName = [string]$manifest.provider.model.name
$expectedModelContext = [int64]$manifest.provider.model.context
$expectedModelOutput = [int64]$manifest.provider.model.output
$minimumOpenCodeVersion = [string]$manifest.supported_opencode.minimum
$maximumOpenCodeVersionExclusive = (
    [string]$manifest.supported_opencode.maximum_exclusive
)
$supportedOpenCodeVersionRange = (
    ">= $minimumOpenCodeVersion and < $maximumOpenCodeVersionExclusive"
)
$cliWarning = (
    "OpenCode CLI is not available in PATH. Static installation passed. " +
    "Restart OpenCode Desktop and verify agents/model in the UI."
)

function Assert-Biexce {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw "FAIL: $Message"
    }

    Write-Host "PASS: $Message"
}

function Get-BiexcePropertyValue {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Object,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

function Assert-BiexcePropertyNames {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Object,

        [Parameter(Mandatory = $true)]
        [string[]]$Expected,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $actual = @($Object.PSObject.Properties.Name)
    Assert-Biexce (
        $actual.Count -eq $Expected.Count -and
        @(Compare-Object $Expected $actual).Count -eq 0
    ) "$Label has the expected properties"
}

function Assert-BiexceLocalProviderContract {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,

        [Parameter(Mandatory = $true)]
        [string]$Label,

        [bool]$RequireOnlyProvider = $false
    )

    $providers = Get-BiexcePropertyValue -Object $Config -Name "provider"
    Assert-Biexce (
        $providers -is [pscustomobject]
    ) "$Label provider config is an object"

    if ($RequireOnlyProvider) {
        Assert-BiexcePropertyNames `
            -Object $providers `
            -Expected @($expectedProviderId) `
            -Label "$Label canonical provider map"
    }

    $provider = Get-BiexcePropertyValue `
        -Object $providers `
        -Name $expectedProviderId
    Assert-Biexce (
        $provider -is [pscustomobject]
    ) "$Label contains provider $expectedProviderId"
    Assert-BiexcePropertyNames `
        -Object $provider `
        -Expected @("npm", "name", "options", "models") `
        -Label "$Label $expectedProviderId"
    Assert-Biexce (
        $provider.npm -eq $expectedProviderPackage
    ) "$Label local provider package is exact"
    Assert-Biexce (
        $provider.name -eq $expectedProviderName
    ) "$Label local provider display name is exact"

    Assert-Biexce (
        $provider.options -is [pscustomobject]
    ) "$Label local provider options are an object"
    Assert-BiexcePropertyNames `
        -Object $provider.options `
        -Expected @("baseURL") `
        -Label "$Label local provider options"
    Assert-Biexce (
        $provider.options.baseURL -eq $expectedProviderBaseUrl
    ) "$Label local provider base URL is exact"

    Assert-Biexce (
        $provider.models -is [pscustomobject]
    ) "$Label local provider models are an object"
    Assert-BiexcePropertyNames `
        -Object $provider.models `
        -Expected @($expectedModelId) `
        -Label "$Label local provider model map"

    $model = Get-BiexcePropertyValue `
        -Object $provider.models `
        -Name $expectedModelId
    Assert-Biexce (
        $model -is [pscustomobject]
    ) "$Label contains local model $expectedModelId"
    Assert-BiexcePropertyNames `
        -Object $model `
        -Expected @("name", "limit") `
        -Label "$Label local model"
    Assert-Biexce (
        $model.name -eq $expectedModelName
    ) "$Label local model display name is exact"

    Assert-Biexce (
        $model.limit -is [pscustomobject]
    ) "$Label local model limits are an object"
    Assert-BiexcePropertyNames `
        -Object $model.limit `
        -Expected @("context", "output") `
        -Label "$Label local model limits"
    Assert-Biexce (
        $model.limit.context -eq $expectedModelContext
    ) "$Label local model context limit is $expectedModelContext"
    Assert-Biexce (
        $model.limit.output -eq $expectedModelOutput
    ) "$Label local model output limit is $expectedModelOutput"
    Assert-Biexce (
        $model.limit.output -le $model.limit.context
    ) "$Label local model output limit does not exceed context"

    Assert-Biexce (
        $null -eq $provider.options.PSObject.Properties["apiKey"] -and
        $null -eq $provider.options.PSObject.Properties["headers"]
    ) "$Label local provider has no API key or Authorization header"
    Assert-Biexce (
        $null -eq $provider.PSObject.Properties["variant"] -and
        $null -eq $provider.PSObject.Properties["variants"] -and
        $null -eq $model.PSObject.Properties["variant"] -and
        $null -eq $model.PSObject.Properties["variants"] -and
        $null -eq $model.PSObject.Properties["options"]
    ) "$Label local provider has no variant or effort config"
}

function Get-BiexceAgentFrontmatter {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $match = [regex]::Match(
        $content,
        "\A---\r?\n(?<header>.*?)\r?\n---(?:\r?\n|\z)",
        [Text.RegularExpressions.RegexOptions]::Singleline
    )

    Assert-Biexce $match.Success "Frontmatter parses: $([IO.Path]::GetFileName($Path))"
    return $match.Groups["header"].Value
}

function Assert-BiexcePermissionContract {
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    Assert-Biexce (
        $Config.permission -is [pscustomobject]
    ) "$Label permission config is an object"
    Assert-Biexce (
        @($Config.permission.PSObject.Properties)[0].Name -eq "*"
    ) "$Label permission wildcard is first"
    Assert-Biexce (
        $Config.permission."*" -eq "ask"
    ) "$Label unmatched permissions require approval"
    Assert-Biexce (
        $Config.permission.external_directory -eq "deny"
    ) "$Label external directory access is denied"

    $secretPatterns = @(
        "*.env", "*.env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.jks",
        "*.keystore", "*.mobileprovision", "*id_rsa*", "*id_ed25519*",
        "*.npmrc", "*.pypirc", "*.netrc", "*secrets*.yaml", "*secrets*.yml",
        "*credentials*.json", "*service-account*.json", "*google-services.json",
        "*GoogleService-Info.plist", "*gradle.properties", "*.tfvars",
        "*.tfvars.json"
    )

    Assert-Biexce (
        @($Config.permission.read.PSObject.Properties)[0].Name -eq "*"
    ) "$Label read wildcard precedes secret rules"

    foreach ($pattern in $secretPatterns) {
        Assert-Biexce (
            (Get-BiexcePropertyValue `
                -Object $Config.permission.read `
                -Name $pattern
            ) -eq "deny"
        ) "$Label secret read pattern is denied: $pattern"
    }

    $bash = $Config.permission.bash
    Assert-Biexce (
        @($bash.PSObject.Properties)[0].Name -eq "*"
    ) "$Label shell wildcard precedes command rules"

    foreach ($prefix in @(
        "git add*", "git * add*", "git commit*", "git * commit*",
        "git push*", "git * push*", "git reset*", "git * reset*",
        "git clean*", "git * clean*", "git checkout*", "git * checkout*",
        "git merge*", "git * merge*", "git branch*", "git * branch*",
        "git tag*", "git * tag*", "git apply*", "git * apply*",
        "git worktree*", "git * worktree*", "git rm*", "git * rm*",
        "rm *", "rmdir *", "del *", "Remove-Item *",
        "kubectl *", "helm *", "aws *", "az *", "gcloud *",
        "terraform apply*", "terraform destroy*", "docker push*",
        "npm publish*", "dotnet nuget push*", "gh release*",
        "vercel *", "netlify *", "firebase deploy*", "fastlane *"
    )) {
        Assert-Biexce (
            (Get-BiexcePropertyValue -Object $bash -Name $prefix) -eq "deny"
        ) "$Label mutation/deploy rule is denied: $prefix"
    }
}

function Assert-BiexceAgentPermissionContract {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AgentName,

        [Parameter(Mandatory = $true)]
        [string]$Header
    )

    Assert-Biexce (
        $Header -match "(?m)^\s*['""']\*['""']:\s*deny\s*$"
    ) "$AgentName defaults tools to deny"
    Assert-Biexce (
        $Header -match "(?m)^\s*external_directory:\s*deny\s*$"
    ) "$AgentName denies external directories"

    if ($AgentName -in @("bx-code", "bx-fix")) {
        Assert-Biexce (
            $Header -match "(?m)^\s*edit:\s*ask\s*$"
        ) "$AgentName asks before source edits"
    }
    elseif ($AgentName -in @("bx-test", "bx-review")) {
        Assert-Biexce (
            $Header -match "(?m)^\s*edit:\s*deny\s*$"
        ) "$AgentName denies edits"
    }
    elseif ($AgentName -in @("bx-director", "bx-plan")) {
        Assert-Biexce (
            $Header -match "(?m)^\s*\.biexce/\*\*:\s*ask\s*$"
        ) "$AgentName asks before artifact edits"
    }
    elseif ($AgentName -eq "bx-explore") {
        Assert-Biexce (
            $Header -match "(?m)^\s*\.biexce/CODEBASE_BRIEF\.md:\s*allow\s*$"
        ) "bx-explore may write only the managed Codebase Brief"
    }

    Assert-Biexce (
        $Header -match "(?m)^\s*task:\s*deny\s*$"
    ) "$AgentName is fail-closed for static delegation"
}

Assert-Biexce (
    -not (Test-Path -LiteralPath (Join-Path $repositoryRoot ".opencode"))
) "Source repository has no .opencode directory"
Assert-Biexce (
    [int]$manifest.schema_version -eq 2
) "Harness manifest schema is supported"
Assert-Biexce (
    Test-Path -LiteralPath $manifestSchemaPath -PathType Leaf
) "Harness manifest JSON Schema exists"
$manifestSchema = (
    Get-Content -LiteralPath $manifestSchemaPath -Raw -Encoding UTF8
) | ConvertFrom-Json -ErrorAction Stop
Assert-Biexce (
    [int]$manifestSchema.properties.schema_version.const -eq 2
) "Harness manifest JSON Schema declares v2"
Assert-Biexce (
    @(
        Compare-Object `
            @(
                "bx-director", "bx-plan", "bx-explore", "bx-code",
                "bx-fix", "bx-test", "bx-review"
            ) `
            $expectedAgents
    ).Count -eq 0
) "Harness manifest contains exactly seven Biexce agents"
Assert-Biexce (
    @($expectedAgents | Select-Object -Unique).Count -eq $expectedAgents.Count
) "Harness manifest agent IDs are unique"
Assert-Biexce (
    Test-Path -LiteralPath $sourceConfigPath -PathType Leaf
) "Canonical opencode.json exists"
Assert-Biexce (
    Test-Path -LiteralPath $sourceAgentRoot -PathType Container
) "Canonical agent directory exists"
Assert-Biexce (
    Test-Path -LiteralPath $sourceSkillRoot -PathType Container
) "Canonical skill tree exists"
Assert-Biexce (
    @($expectedSkillIds | Select-Object -Unique).Count -eq $expectedSkillIds.Count
) "Harness manifest skill IDs are unique"

$sourceConfigText = Get-Content `
    -LiteralPath $sourceConfigPath `
    -Raw `
    -Encoding UTF8
Assert-BiexceStrictJsonText `
    -Text $sourceConfigText `
    -PathLabel $sourceConfigPath
$sourceConfig = $sourceConfigText | ConvertFrom-Json -ErrorAction Stop
Assert-Biexce ($sourceConfig -is [pscustomobject]) "Canonical opencode.json parses"
Assert-Biexce (
    $sourceConfig.default_agent -eq [string]$manifest.defaults.default_agent
) "Canonical default agent matches the harness manifest"
Assert-Biexce (
    $sourceConfig.subagent_depth -eq [int]$manifest.defaults.subagent_depth
) "Canonical subagent depth matches the harness manifest"
Assert-Biexce (
    $sourceConfig.share -eq [string]$manifest.defaults.share
) "Canonical session sharing matches the harness manifest"
Assert-Biexce (
    $sourceConfig.autoupdate -eq [bool]$manifest.defaults.autoupdate
) "Canonical automatic update matches the harness manifest"

foreach ($propertyName in @("model", "small_model", "variant")) {
    $expectedBinding = Get-BiexcePropertyValue `
        -Object $manifest.model_binding.global `
        -Name $propertyName
    Assert-Biexce (
        (Get-BiexcePropertyValue `
            -Object $sourceConfig `
            -Name $propertyName) -eq $expectedBinding
    ) "Canonical config binding matches manifest: $propertyName"
}

Assert-BiexceLocalProviderContract `
    -Config $sourceConfig `
    -Label "Canonical" `
    -RequireOnlyProvider $true

foreach ($builtin in @($manifest.disabled_builtin_agents)) {
    $definition = Get-BiexcePropertyValue `
        -Object $sourceConfig.agent `
        -Name $builtin
    Assert-Biexce (
        $null -ne $definition -and $definition.disable -eq $true
    ) "Canonical built-in agent is disabled: $builtin"
}

$sourceAgentFiles = @(
    Get-ChildItem -LiteralPath $sourceAgentRoot -File -Filter "*.md" |
        Sort-Object BaseName
)
$sourceAgentNames = @($sourceAgentFiles | ForEach-Object BaseName)
Assert-Biexce (
    @(Compare-Object $expectedAgents $sourceAgentNames).Count -eq 0
) "Canonical source has exactly seven Biexce agents"

foreach ($agentFile in $sourceAgentFiles) {
    $agentName = $agentFile.BaseName
    Assert-Biexce (
        (Get-FileHash `
            -LiteralPath $agentFile.FullName `
            -Algorithm SHA256
        ).Hash -eq $expectedAgentHashes[$agentName]
    ) "$agentName source hash matches immutable baseline"
    $header = Get-BiexceAgentFrontmatter -Path $agentFile.FullName

    Assert-Biexce (
        $header -match "(?m)^description:\s*\S"
    ) "$agentName has a description"
    Assert-Biexce (
        $header -match (
            "(?m)^mode:\s*" +
            [regex]::Escape($expectedModes[$agentName]) +
            "\s*$"
        )
    ) "$agentName mode is $($expectedModes[$agentName])"
    $modelMatch = [regex]::Match($header, "(?m)^model:\s*(\S+)\s*$")
    $actualAgentModel = if ($modelMatch.Success) {
        $modelMatch.Groups[1].Value
    }
    else {
        $null
    }
    $agentContract = @($agentContracts | Where-Object id -eq $agentName)[0]
    Assert-Biexce (
        $actualAgentModel -eq $agentContract.model
    ) "$agentName model binding matches manifest"
    Assert-Biexce (
        $header -notmatch "(?m)^(provider|variant):"
    ) "$agentName does not bind provider or variant"
    Assert-BiexceAgentPermissionContract `
        -AgentName $agentName `
        -Header $header
}

foreach ($skillContract in $skillContracts) {
    $skillId = [string]$skillContract.id
    $sourceSkillPath = Join-Path $sourceRoot (
        ([string]$skillContract.path).Replace('/', '\')
    )
    Assert-Biexce (
        Test-Path -LiteralPath $sourceSkillPath -PathType Leaf
    ) "Canonical skill exists: $skillId"
    $skillText = Get-Content -LiteralPath $sourceSkillPath -Raw -Encoding UTF8
    Assert-Biexce (
        $skillText -match (
            "(?m)^name:\s*" + [regex]::Escape($skillId) + "\s*$"
        )
    ) "Canonical skill identity is preserved: $skillId"
    Assert-Biexce (
        $skillText -match (
            "(?m)^[ \t]*status:[ \t]*" +
            [regex]::Escape([string]$skillContract.status) +
            "(?:[ \t]+#.*)?\r?$"
        )
    ) "Canonical skill status matches manifest: $skillId"
    Assert-Biexce (
        (Get-FileHash -LiteralPath $sourceSkillPath -Algorithm SHA256).Hash -eq
        $expectedSkillHashes[$skillId]
    ) "Canonical skill hash matches baseline: $skillId"
}
foreach ($runtimeContract in $runtimeContracts) {
    $runtimeId = [string]$runtimeContract.id
    $sourceRuntimePath = Join-Path $sourceRoot (
        ([string]$runtimeContract.path).Replace('/', '\')
    )
    Assert-Biexce (
        Test-Path -LiteralPath $sourceRuntimePath -PathType Leaf
    ) "Canonical runtime file exists: $runtimeId"
    Assert-Biexce (
        (Get-FileHash -LiteralPath $sourceRuntimePath -Algorithm SHA256).Hash -eq
        $expectedRuntimeHashes[$runtimeId]
    ) "Canonical runtime hash matches baseline: $runtimeId"
}
$sourcePackagePath = Join-Path $sourceRoot "package.json"
Assert-Biexce (
    Test-Path -LiteralPath $sourcePackagePath -PathType Leaf
) "Canonical plugin package config exists"
$sourcePackage = Get-Content `
    -LiteralPath $sourcePackagePath `
    -Raw `
    -Encoding UTF8 |
    ConvertFrom-Json -ErrorAction Stop
Assert-Biexce (
    [string]$sourcePackage.dependencies."@opencode-ai/plugin" -eq "1.18.4"
) "Canonical plugin dependency is pinned"
Assert-Biexce (
    @($skillContracts | Where-Object path -match '_TEMPLATE').Count -eq 0
) "Manifest excludes the skill template"

Assert-BiexcePermissionContract `
    -Config $sourceConfig `
    -Label "Canonical"

$maintainedFiles = Get-ChildItem `
    -LiteralPath $repositoryRoot `
    -Recurse `
    -Force `
    -File |
    Where-Object {
        $_.Extension -in @(
            ".json",
            ".md",
            ".example",
            ".ps1",
            ".psm1",
            ".cmd",
            ".sh",
            ".command",
            ".py"
        ) -or
        $_.Name -in @("VERSION", ".gitignore", ".gitattributes")
    }
$maintainedText = $maintainedFiles | ForEach-Object {
    Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8
}
$credentialRegex = (
    "(?i)(" +
    "-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|" +
    "sk-[a-z0-9_-]{16,}|" +
    "ghp_[a-z0-9]{16,}|" +
    "AIza[0-9A-Za-z_-]{20,}|" +
    "bearer\s+[a-z0-9._-]{16,}|" +
    "(?:api[_-]?key|client[_-]?secret)\s*[:=]\s*" +
    "['""][^'""]{8,}['""]" +
    ")"
)
Assert-Biexce (
    (($maintainedText -join [Environment]::NewLine) -notmatch $credentialRegex)
) "Canonical source has no credential or API-key literal"

$cliConfigDirectory = $null
$temporaryConfigDirectory = $null

if ($TargetPath) {
    $installedRoot = [IO.Path]::GetFullPath(
        (Resolve-Path -LiteralPath $TargetPath).Path
    ).TrimEnd("\")
    $installedConfigPath = Join-Path $installedRoot "opencode.json"
    $installedAgentRoot = Join-Path $installedRoot "agents"
    $installedSkillRoot = Join-Path $installedRoot "skills"

    Assert-Biexce (
        -not (Test-Path -LiteralPath (Join-Path $installedRoot "opencode.jsonc"))
    ) "Installed target does not contain opencode.jsonc"
    Assert-Biexce (
        Test-Path -LiteralPath $installedConfigPath -PathType Leaf
    ) "Installed opencode.json exists"
    Assert-Biexce (
        Test-Path -LiteralPath $installedAgentRoot -PathType Container
    ) "Installed agent directory exists"
    Assert-Biexce (
        Test-Path -LiteralPath $installedSkillRoot -PathType Container
    ) "Installed skill tree exists"

    $installedConfigText = Get-Content `
        -LiteralPath $installedConfigPath `
        -Raw `
        -Encoding UTF8
    Assert-BiexceStrictJsonText `
        -Text $installedConfigText `
        -PathLabel $installedConfigPath
    $installedConfig = $installedConfigText |
        ConvertFrom-Json -ErrorAction Stop
    Assert-Biexce (
        $installedConfig -is [pscustomobject]
    ) "Installed opencode.json parses"

    foreach ($name in @(
        "default_agent",
        "subagent_depth",
        "share",
        "autoupdate"
    )) {
        Assert-Biexce (
            (Get-BiexcePropertyValue -Object $installedConfig -Name $name) -eq
            (Get-BiexcePropertyValue -Object $sourceConfig -Name $name)
        ) "Installed managed value matches canonical: $name"
    }

    Assert-BiexceLocalProviderContract `
        -Config $installedConfig `
        -Label "Installed"

    foreach ($builtin in @("build", "plan", "general", "explore", "scout")) {
        $definition = Get-BiexcePropertyValue `
            -Object $installedConfig.agent `
            -Name $builtin
        Assert-Biexce (
            $null -ne $definition -and $definition.disable -eq $true
        ) "Installed built-in agent is disabled: $builtin"
    }

    Assert-BiexcePermissionContract `
        -Config $installedConfig `
        -Label "Installed"

    foreach ($agentName in $expectedAgents) {
        $sourcePath = Join-Path $sourceAgentRoot "$agentName.md"
        $installedPath = Join-Path $installedAgentRoot "$agentName.md"
        Assert-Biexce (
            Test-Path -LiteralPath $installedPath -PathType Leaf
        ) "Installed agent exists: $agentName"
        Assert-Biexce (
            (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -eq
            (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash
        ) "Installed agent hash matches canonical: $agentName"
    }

    foreach ($skillContract in $skillContracts) {
        $skillId = [string]$skillContract.id
        $relativePath = ([string]$skillContract.path).Replace('/', '\')
        $sourcePath = Join-Path $sourceRoot $relativePath
        $installedPath = Join-Path $installedRoot $relativePath
        Assert-Biexce (
            Test-Path -LiteralPath $installedPath -PathType Leaf
        ) "Installed skill exists: $skillId"
        Assert-Biexce (
            (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -eq
            (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash
        ) "Installed skill hash matches canonical: $skillId"
    }
    foreach ($runtimeContract in $runtimeContracts) {
        $runtimeId = [string]$runtimeContract.id
        $relativePath = ([string]$runtimeContract.path).Replace('/', '\')
        $sourcePath = Join-Path $sourceRoot $relativePath
        $installedPath = Join-Path $installedRoot $relativePath
        Assert-Biexce (
            Test-Path -LiteralPath $installedPath -PathType Leaf
        ) "Installed runtime file exists: $runtimeId"
        Assert-Biexce (
            (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -eq
            (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash
        ) "Installed runtime hash matches canonical: $runtimeId"
    }
    $installedPackagePath = Join-Path $installedRoot "package.json"
    Assert-Biexce (
        Test-Path -LiteralPath $installedPackagePath -PathType Leaf
    ) "Installed plugin package config exists"
    $installedPackage = Get-Content `
        -LiteralPath $installedPackagePath `
        -Raw `
        -Encoding UTF8 |
        ConvertFrom-Json -ErrorAction Stop
    Assert-Biexce (
        [string]$installedPackage.dependencies."@opencode-ai/plugin" -eq "1.18.4"
    ) "Installed plugin dependency is pinned"

    $cliConfigDirectory = $installedRoot
}

Write-Host "Static verification: PASS"

$openCodeCommand = $null
$runtimeVerificationAvailable = $false
if (-not $SkipCli) {
    $openCodeCommand = Resolve-BiexceOpenCodeCommand
    $runtimeVerificationAvailable = $null -ne $openCodeCommand
}

if (-not $TargetPath -and $runtimeVerificationAvailable) {
    $temporaryBase = [IO.Path]::GetFullPath(
        [IO.Path]::GetTempPath()
    ).TrimEnd("\")
    $temporaryConfigDirectory = Join-Path (
        $temporaryBase
    ) ("biexce-opencode-verify-" + [guid]::NewGuid().ToString("N"))
    $resolvedTemporaryDirectory = [IO.Path]::GetFullPath(
        $temporaryConfigDirectory
    )

    if (-not $resolvedTemporaryDirectory.StartsWith(
        $temporaryBase + "\",
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Temporary verification path escaped the system temp directory."
    }

    New-Item -ItemType Directory -Path $resolvedTemporaryDirectory | Out-Null
    Copy-Item `
        -LiteralPath $sourceConfigPath `
        -Destination (Join-Path $resolvedTemporaryDirectory "opencode.json")
    foreach (
        $contract in (
            @($agentContracts) +
            @($skillContracts) +
            @($runtimeContracts)
        )
    ) {
        $relativePath = ([string]$contract.path).Replace('/', '\')
        $sourcePath = Join-Path $sourceRoot $relativePath
        $destinationPath = Join-Path $resolvedTemporaryDirectory $relativePath
        $destinationDirectory = Split-Path -Parent $destinationPath
        if (-not (Test-Path -LiteralPath $destinationDirectory)) {
            New-Item -ItemType Directory -Path $destinationDirectory | Out-Null
        }
        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
    }
    Copy-Item `
        -LiteralPath $sourcePackagePath `
        -Destination (Join-Path $resolvedTemporaryDirectory "package.json")

    $cliConfigDirectory = $resolvedTemporaryDirectory
}

if ($runtimeVerificationAvailable) {
    try {
        $versionOutput = Invoke-BiexceOpenCode `
            -Arguments @("--version") `
            -ConfigDirectory $cliConfigDirectory `
            -OpenCodeCommand $openCodeCommand
        $detectedVersion = Get-BiexceOpenCodeVersion `
            -OutputObject $versionOutput
        if (-not (Test-BiexceOpenCodeVersionInRange `
            -Version $detectedVersion `
            -MinimumVersion $minimumOpenCodeVersion `
            -MaximumVersionExclusive $maximumOpenCodeVersionExclusive
        )) {
            throw (
                "Unsupported OpenCode CLI version '$detectedVersion'. " +
                "Supported range: $supportedOpenCodeVersionRange."
            )
        }
        Write-Host (
            "PASS: OpenCode CLI version $detectedVersion is supported " +
            "($supportedOpenCodeVersionRange)"
        ) -ForegroundColor Green

        $agentList = Invoke-BiexceOpenCode `
            -Arguments @("agent", "list", "--pure") `
            -ConfigDirectory $cliConfigDirectory `
            -OpenCodeCommand $openCodeCommand
        $agentListText = $agentList -join "`n"
        foreach ($agentName in $expectedModes.Keys) {
            Assert-Biexce (
                $agentListText -match (
                    "(?m)^" +
                    [regex]::Escape($agentName) +
                    " \(" +
                    [regex]::Escape($expectedModes[$agentName]) +
                    "\)"
                )
            ) "OpenCode discovers $agentName as $($expectedModes[$agentName])"
        }

        $resolvedConfigOutput = Invoke-BiexceOpenCode `
            -Arguments @("debug", "config", "--pure") `
            -ConfigDirectory $cliConfigDirectory `
            -OpenCodeCommand $openCodeCommand
        $resolvedConfigText = $resolvedConfigOutput -join "`n"
        $jsonStart = $resolvedConfigText.IndexOf("{")
        Assert-Biexce ($jsonStart -ge 0) "OpenCode returns resolved config JSON"
        $resolvedConfig = $resolvedConfigText.Substring($jsonStart) |
            ConvertFrom-Json -ErrorAction Stop
        Assert-Biexce (
            $resolvedConfig.default_agent -eq [string]$manifest.defaults.default_agent
        ) "OpenCode resolves the manifest default agent"
        Assert-BiexceLocalProviderContract `
            -Config $resolvedConfig `
            -Label "OpenCode resolved"

        $modelOutput = Invoke-BiexceOpenCode `
            -Arguments @("models", $expectedProviderId, "--pure") `
            -ConfigDirectory $cliConfigDirectory `
            -OpenCodeCommand $openCodeCommand
        Assert-Biexce (
            ($modelOutput -join "`n") -match (
                "(?m)^" +
                [regex]::Escape(
                    "$expectedProviderId/$expectedModelId"
                ) +
                "\s*$"
            )
        ) "OpenCode discovers the Biexce local model"

        $skillOutput = Invoke-BiexceOpenCode `
            -Arguments @("debug", "skill", "--pure") `
            -ConfigDirectory $cliConfigDirectory `
            -OpenCodeCommand $openCodeCommand
        $skillOutputText = $skillOutput -join "`n"
        foreach ($skillContract in $skillContracts) {
            $skillId = [string]$skillContract.id
            Assert-Biexce (
                $skillOutputText -match (
                    '"name"\s*:\s*"' + [regex]::Escape($skillId) + '"'
                )
            ) "OpenCode discovers skill: $skillId"
        }
    }
    finally {
        if (
            $temporaryConfigDirectory -and
            (Test-Path `
                -LiteralPath $temporaryConfigDirectory `
                -PathType Container
            )
        ) {
            Remove-Item `
                -LiteralPath $temporaryConfigDirectory `
                -Recurse `
                -Force
        }
    }
}
elseif (-not $SkipCli) {
    Write-Host "WARNING: $cliWarning" -ForegroundColor Yellow
}

Assert-Biexce (
    -not (Test-Path -LiteralPath (Join-Path $repositoryRoot ".opencode"))
) "Verification did not create .opencode in the source repository"

Write-Host ""
if ($TargetPath) {
    Write-Host "Biexce global OpenCode installation verification: PASS"
}
else {
    Write-Host "Biexce OpenCode canonical source verification: PASS"
}
