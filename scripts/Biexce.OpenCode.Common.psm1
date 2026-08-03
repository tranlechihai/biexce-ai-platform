Set-StrictMode -Version Latest

function Get-BiexceHarnessManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $manifestPath = Join-Path $RepositoryRoot "src\harness-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Harness manifest is missing: $manifestPath"
    }

    $text = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
    $null = Assert-BiexceStrictJsonText -Text $text -PathLabel $manifestPath
    return $text | ConvertFrom-Json -ErrorAction Stop
}

function ConvertTo-BiexceCommandOutputText {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$OutputObject
    )

    $lines = @(
        foreach ($item in @($OutputObject)) {
            if ($null -eq $item) {
                continue
            }

            if ($item -is [Management.Automation.ErrorRecord]) {
                $item.ToString()
            }
            else {
                [string]$item
            }
        }
    )

    return ($lines -join [Environment]::NewLine).Trim()
}

function Get-BiexceOpenCodeVersion {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [AllowEmptyCollection()]
        [object[]]$OutputObject
    )

    $text = ConvertTo-BiexceCommandOutputText -OutputObject $OutputObject
    $ansiPattern = "$([char]27)\[[0-?]*[ -/]*[@-~]"
    $normalized = [regex]::Replace($text, $ansiPattern, "").Trim()
    $semanticVersion = "\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"
    $lineMatch = [regex]::Match(
        $normalized,
        "(?im)^\s*(?:opencode(?:\s+version)?\s+)?v?(?<version>$semanticVersion)\s*$"
    )

    if ($lineMatch.Success) {
        return $lineMatch.Groups["version"].Value
    }

    $tokenMatches = [regex]::Matches(
        $normalized,
        "(?<![0-9A-Za-z])v?(?<version>$semanticVersion)(?![0-9A-Za-z])",
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $versions = @(
        $tokenMatches |
            ForEach-Object { $_.Groups["version"].Value } |
            Select-Object -Unique
    )

    if ($versions.Count -eq 1) {
        return $versions[0]
    }

    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "OpenCode CLI version output is empty."
    }

    throw "OpenCode CLI version output could not be parsed safely: $normalized"
}

function Test-BiexceOpenCodeVersionInRange {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version,

        [Parameter(Mandatory = $true)]
        [string]$MinimumVersion,

        [Parameter(Mandatory = $true)]
        [string]$MaximumVersionExclusive
    )

    if ($Version -notmatch "^\d+\.\d+\.\d+$") {
        return $false
    }

    $parsedVersion = [version]$Version
    $minimum = [version]$MinimumVersion
    $maximumExclusive = [version]$MaximumVersionExclusive
    return (
        $parsedVersion -ge $minimum -and
        $parsedVersion -lt $maximumExclusive
    )
}

function Resolve-BiexceOpenCodeCommand {
    [CmdletBinding()]
    param()

    $command = Get-Command opencode.cmd -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        $command = Get-Command opencode -ErrorAction SilentlyContinue |
            Select-Object -First 1
    }
    if ($null -eq $command) {
        return $null
    }

    return $command.Source
}

function Invoke-BiexceOpenCode {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$ConfigDirectory,

        [Parameter(Mandatory = $true)]
        [string]$OpenCodeCommand
    )

    $environmentNames = @(
        "OPENCODE_CONFIG",
        "OPENCODE_CONFIG_CONTENT",
        "OPENCODE_CONFIG_DIR",
        "OPENCODE_DISABLE_PROJECT_CONFIG",
        "OPENCODE_DISABLE_EXTERNAL_SKILLS",
        "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS",
        "XDG_CONFIG_HOME"
    )
    $previousEnvironment = @{}
    foreach ($name in $environmentNames) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable(
            $name,
            "Process"
        )
    }

    try {
        [Environment]::SetEnvironmentVariable(
            "OPENCODE_CONFIG",
            $null,
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            "OPENCODE_CONFIG_CONTENT",
            $null,
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            "OPENCODE_CONFIG_DIR",
            $ConfigDirectory,
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            "OPENCODE_DISABLE_PROJECT_CONFIG",
            "1",
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            "OPENCODE_DISABLE_EXTERNAL_SKILLS",
            "1",
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS",
            "1",
            "Process"
        )
        [Environment]::SetEnvironmentVariable(
            "XDG_CONFIG_HOME",
            (Split-Path -Parent $ConfigDirectory),
            "Process"
        )

        Push-Location ([IO.Path]::GetTempPath())
        try {
            $previousErrorActionPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = "Continue"
                $output = @(& $OpenCodeCommand @Arguments 2>&1)
                $exitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $previousErrorActionPreference
            }
        }
        finally {
            Pop-Location
        }
    }
    finally {
        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $previousEnvironment[$name],
                "Process"
            )
        }
    }

    if ($exitCode -ne 0) {
        $outputText = ConvertTo-BiexceCommandOutputText -OutputObject $output
        $joinedArguments = $Arguments -join " "
        $message = (
            "OpenCode command failed with exit code ${exitCode}: " +
            "opencode $joinedArguments."
        )
        if (-not [string]::IsNullOrWhiteSpace($outputText)) {
            $message += " Output: $outputText"
        }
        throw $message
    }

    return $output
}

function Assert-BiexceStrictJsonText {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$PathLabel
    )

    $inString = $false
    $escaped = $false

    for ($index = 0; $index -lt $Text.Length; $index++) {
        $character = $Text[$index]

        if ($inString) {
            if ($escaped) {
                $escaped = $false
                continue
            }
            if ($character -eq [char]92) {
                $escaped = $true
                continue
            }
            if ($character -eq [char]34) {
                $inString = $false
            }
            continue
        }

        if ($character -eq [char]34) {
            $inString = $true
            continue
        }

        if (
            $character -eq [char]47 -and
            $index + 1 -lt $Text.Length -and
            $Text[$index + 1] -in @([char]47, [char]42)
        ) {
            throw "JSONC comments are not supported in $PathLabel."
        }

        if ($character -eq [char]44) {
            $nextIndex = $index + 1
            while (
                $nextIndex -lt $Text.Length -and
                [char]::IsWhiteSpace($Text[$nextIndex])
            ) {
                $nextIndex++
            }

            if (
                $nextIndex -lt $Text.Length -and
                $Text[$nextIndex] -in @([char]125, [char]93)
            ) {
                throw "JSONC trailing commas are not supported in $PathLabel."
            }
        }
    }
}

function Merge-BiexceRuleMap {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [psobject]$Existing,

        [Parameter(Mandatory = $true)]
        [psobject]$Managed
    )

    if ($Managed -isnot [pscustomobject]) {
        throw "Managed permission rule map must be a JSON object."
    }

    $managedNames = @{}
    foreach ($property in $Managed.PSObject.Properties) {
        $managedNames[$property.Name] = $true
    }

    $wildcard = $Managed.PSObject.Properties["*"]
    if ($null -eq $wildcard) {
        throw "Managed permission rule map must define a wildcard."
    }

    $merged = [ordered]@{
        "*" = $wildcard.Value
    }

    if ($Existing -is [pscustomobject]) {
        foreach ($property in $Existing.PSObject.Properties) {
            if (
                $property.Name -ne "*" -and
                -not $managedNames.ContainsKey($property.Name)
            ) {
                $merged[$property.Name] = $property.Value
            }
        }
    }

    foreach ($property in $Managed.PSObject.Properties) {
        if ($property.Name -ne "*") {
            $merged[$property.Name] = $property.Value
        }
    }

    return [pscustomobject]$merged
}

function Merge-BiexcePermissionObject {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [psobject]$Existing,

        [Parameter(Mandatory = $true)]
        [psobject]$Managed
    )

    if ($Managed -isnot [pscustomobject]) {
        throw "Managed permission config must be a JSON object."
    }

    $managedNames = @{}
    foreach ($property in $Managed.PSObject.Properties) {
        $managedNames[$property.Name] = $true
    }

    $wildcard = $Managed.PSObject.Properties["*"]
    if ($null -eq $wildcard) {
        throw "Managed permission config must define a wildcard."
    }

    $merged = [ordered]@{
        "*" = $wildcard.Value
    }

    if ($Existing -is [pscustomobject]) {
        foreach ($property in $Existing.PSObject.Properties) {
            if (
                $property.Name -ne "*" -and
                -not $managedNames.ContainsKey($property.Name)
            ) {
                $merged[$property.Name] = $property.Value
            }
        }
    }

    foreach ($property in $Managed.PSObject.Properties) {
        if ($property.Name -eq "*") {
            continue
        }

        if ($property.Name -in @("read", "bash")) {
            $existingValue = $null
            if ($Existing -is [pscustomobject]) {
                $existingProperty = $Existing.PSObject.Properties[$property.Name]
                if ($null -ne $existingProperty) {
                    $existingValue = $existingProperty.Value
                }
            }

            $merged[$property.Name] = Merge-BiexceRuleMap `
                -Existing $existingValue `
                -Managed $property.Value
        }
        else {
            $merged[$property.Name] = $property.Value
        }
    }

    return [pscustomobject]$merged
}

function Merge-BiexceAgentObject {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [psobject]$Existing,

        [Parameter(Mandatory = $true)]
        [psobject]$Managed
    )

    if ($null -ne $Existing -and $Existing -isnot [pscustomobject]) {
        throw "Existing 'agent' config must be a JSON object."
    }
    if ($Managed -isnot [pscustomobject]) {
        throw "Managed 'agent' config must be a JSON object."
    }

    $merged = [ordered]@{}
    if ($Existing -is [pscustomobject]) {
        foreach ($property in $Existing.PSObject.Properties) {
            $merged[$property.Name] = $property.Value
        }
    }

    foreach ($managedAgent in $Managed.PSObject.Properties) {
        $existingDefinition = $null
        if ($Existing -is [pscustomobject]) {
            $existingProperty = $Existing.PSObject.Properties[$managedAgent.Name]
            if ($null -ne $existingProperty) {
                $existingDefinition = $existingProperty.Value
            }
        }

        if (
            $null -ne $existingDefinition -and
            $existingDefinition -isnot [pscustomobject]
        ) {
            throw "Existing agent '$($managedAgent.Name)' must be a JSON object."
        }
        if ($managedAgent.Value -isnot [pscustomobject]) {
            throw "Managed agent '$($managedAgent.Name)' must be a JSON object."
        }

        $definition = [ordered]@{}
        if ($existingDefinition -is [pscustomobject]) {
            foreach ($property in $existingDefinition.PSObject.Properties) {
                $definition[$property.Name] = $property.Value
            }
        }
        foreach ($property in $managedAgent.Value.PSObject.Properties) {
            $definition[$property.Name] = $property.Value
        }

        $merged[$managedAgent.Name] = [pscustomobject]$definition
    }

    return [pscustomobject]$merged
}

function Merge-BiexceProviderObject {
    [CmdletBinding()]
    param(
        [AllowNull()]
        [object]$Existing,

        [Parameter(Mandatory = $true)]
        [psobject]$Managed
    )

    if ($null -ne $Existing -and $Existing -isnot [pscustomobject]) {
        throw "Existing 'provider' config must be a JSON object."
    }
    if ($Managed -isnot [pscustomobject]) {
        throw "Managed 'provider' config must be a JSON object."
    }

    $managedNames = @($Managed.PSObject.Properties.Name)
    $merged = [ordered]@{}

    if ($Existing -is [pscustomobject]) {
        foreach ($property in $Existing.PSObject.Properties) {
            $isManaged = $false
            foreach ($managedName in $managedNames) {
                if ([string]::Equals(
                    $property.Name,
                    $managedName,
                    [StringComparison]::OrdinalIgnoreCase
                )) {
                    $isManaged = $true
                    break
                }
            }

            if (-not $isManaged) {
                $merged[$property.Name] = $property.Value
            }
        }
    }

    foreach ($property in $Managed.PSObject.Properties) {
        if ($property.Value -isnot [pscustomobject]) {
            throw "Managed provider '$($property.Name)' must be a JSON object."
        }
        $merged[$property.Name] = $property.Value
    }

    return [pscustomobject]$merged
}

function Merge-BiexceManagedConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Existing,

        [Parameter(Mandatory = $true)]
        [psobject]$Managed
    )

    if ($Existing -isnot [pscustomobject]) {
        throw "Existing OpenCode config root must be a JSON object."
    }
    if ($Managed -isnot [pscustomobject]) {
        throw "Managed OpenCode config root must be a JSON object."
    }

    $merged = [ordered]@{}
    foreach ($property in $Existing.PSObject.Properties) {
        $merged[$property.Name] = $property.Value
    }

    foreach ($name in @(
        "default_agent",
        "subagent_depth",
        "share",
        "autoupdate"
    )) {
        $property = $Managed.PSObject.Properties[$name]
        if ($null -eq $property) {
            throw "Managed OpenCode config is missing '$name'."
        }
        $merged[$name] = $property.Value
    }

    $existingPermission = $null
    $permissionProperty = $Existing.PSObject.Properties["permission"]
    if ($null -ne $permissionProperty) {
        $existingPermission = $permissionProperty.Value
    }
    $merged["permission"] = Merge-BiexcePermissionObject `
        -Existing $existingPermission `
        -Managed $Managed.permission

    $existingAgent = $null
    $agentProperty = $Existing.PSObject.Properties["agent"]
    if ($null -ne $agentProperty) {
        $existingAgent = $agentProperty.Value
    }
    $merged["agent"] = Merge-BiexceAgentObject `
        -Existing $existingAgent `
        -Managed $Managed.agent

    $managedProviderProperty = $Managed.PSObject.Properties["provider"]
    if ($null -eq $managedProviderProperty) {
        throw "Managed OpenCode config is missing 'provider'."
    }

    $existingProvider = $null
    $providerProperty = $Existing.PSObject.Properties["provider"]
    if ($null -ne $providerProperty) {
        $existingProvider = $providerProperty.Value
    }
    $merged["provider"] = Merge-BiexceProviderObject `
        -Existing $existingProvider `
        -Managed $managedProviderProperty.Value

    return [pscustomobject]$merged
}

function Merge-BiexcePackageConfig {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Existing,

        [Parameter(Mandatory = $true)]
        [psobject]$Managed
    )

    if ($Existing -isnot [pscustomobject] -or $Managed -isnot [pscustomobject]) {
        throw "package.json roots must be JSON objects."
    }
    $managedDependencies = $Managed.PSObject.Properties["dependencies"]
    if (
        $null -eq $managedDependencies -or
        $managedDependencies.Value -isnot [pscustomobject] -or
        @($managedDependencies.Value.PSObject.Properties).Count -ne 1 -or
        [string]$managedDependencies.Value."@opencode-ai/plugin" -ne "1.18.4"
    ) {
        throw "Canonical plugin dependency must pin @opencode-ai/plugin 1.18.4."
    }

    $merged = [ordered]@{}
    foreach ($property in $Existing.PSObject.Properties) {
        $merged[$property.Name] = $property.Value
    }

    $dependencies = [ordered]@{}
    $existingDependencies = $Existing.PSObject.Properties["dependencies"]
    if ($null -ne $existingDependencies) {
        if ($existingDependencies.Value -isnot [pscustomobject]) {
            throw "Existing package.json dependencies must be a JSON object."
        }
        foreach ($property in $existingDependencies.Value.PSObject.Properties) {
            $dependencies[$property.Name] = $property.Value
        }
    }
    $dependencies["@opencode-ai/plugin"] = "1.18.4"
    $merged["dependencies"] = [pscustomobject]$dependencies
    return [pscustomobject]$merged
}

function ConvertTo-BiexceConfigJson {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [psobject]$Config
    )

    return ($Config | ConvertTo-Json -Depth 100) + [Environment]::NewLine
}

function Write-BiexceUtf8NoBom {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-BiexceStringSha256 {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($Content)
    $algorithm = [Security.Cryptography.SHA256]::Create()

    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace("-", "")
    }
    finally {
        $algorithm.Dispose()
    }
}

Export-ModuleMember -Function `
    Get-BiexceHarnessManifest, `
    ConvertTo-BiexceCommandOutputText, `
    Get-BiexceOpenCodeVersion, `
    Test-BiexceOpenCodeVersionInRange, `
    Resolve-BiexceOpenCodeCommand, `
    Invoke-BiexceOpenCode, `
    Assert-BiexceStrictJsonText, `
    Merge-BiexceManagedConfig, `
    Merge-BiexcePackageConfig, `
    ConvertTo-BiexceConfigJson, `
    Write-BiexceUtf8NoBom, `
    Get-BiexceStringSha256
