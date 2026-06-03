param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$IntervalSeconds = 5,
    [switch]$Once,
    [switch]$Generate,
    [string]$ImageSize = "1024x1024",
    [string]$ImageQuality = "low"
)

$ErrorActionPreference = "Stop"

$rootPath = (Resolve-Path -LiteralPath $Root).Path
$requestRoot = Join-Path $rootPath "docs\claude\asset-requests"
$queuePath = Join-Path $requestRoot "queue.jsonl"
$activeDir = Join-Path $requestRoot "active"
$doneDir = Join-Path $requestRoot "done"
$failedDir = Join-Path $requestRoot "failed"
$stateDir = Join-Path $rootPath ".dipeen"
$statePath = Join-Path $stateDir "asset-loop-state.json"
$pidPath = Join-Path $stateDir "asset-loop.pid"
$logPath = Join-Path $stateDir "asset-loop.log"

New-Item -ItemType Directory -Force -Path $requestRoot, $activeDir, $doneDir, $failedDir, $stateDir | Out-Null
if (-not (Test-Path -LiteralPath $queuePath)) {
    New-Item -ItemType File -Path $queuePath | Out-Null
}
if ($Once) {
    $PID | Set-Content -LiteralPath (Join-Path $stateDir "asset-loop-last-once.pid") -Encoding UTF8
} else {
    $PID | Set-Content -LiteralPath $pidPath -Encoding UTF8
}

function Write-AssetLog {
    param([string]$Message)
    $stamp = (Get-Date).ToString("o")
    Add-Content -LiteralPath $logPath -Value "$stamp $Message" -Encoding UTF8
}

function ConvertTo-SafeName {
    param([string]$Value)
    $safe = $Value.ToLowerInvariant() -replace "[^a-z0-9._-]+", "-"
    $safe = $safe.Trim("-")
    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "asset-request"
    }
    return $safe
}

function Get-ProcessedMap {
    $map = @{}
    if (-not (Test-Path -LiteralPath $statePath)) {
        return $map
    }

    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($state.processed) {
            foreach ($entry in @($state.processed)) {
                if ($entry.id) {
                    $map[[string]$entry.id] = $entry
                }
            }
        }
    } catch {
        Write-AssetLog "WARN failed to read state: $($_.Exception.Message)"
    }

    return $map
}

function Save-ProcessedMap {
    param([hashtable]$Processed)

    $state = [pscustomobject]@{
        updatedAt = (Get-Date).ToString("o")
        processed = @($Processed.Values)
    }

    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statePath -Encoding UTF8
}

function Get-OutputTargets {
    param($Request, [string]$Kind, [string]$Slug)

    if ($Request.output -and $Request.output.source) {
        $source = [string]$Request.output.source
    } else {
        switch ($Kind) {
            "character" { $source = "docs/brand-assets/imagegen/characters/source/$Slug.png" }
            "office-prop" { $source = "docs/brand-assets/imagegen/office-props/source/$Slug.png" }
            "empty-state" { $source = "docs/brand-assets/imagegen/empty-states/source/$Slug.png" }
            default { $source = "docs/brand-assets/imagegen/mood/source/$Slug.png" }
        }
    }

    if ($Request.output -and $Request.output.transparent) {
        $transparent = [string]$Request.output.transparent
    } else {
        $transparent = $source -replace "/source/", "/transparent/"
    }

    return [pscustomobject]@{
        source = $source.Replace("\", "/")
        transparent = $transparent.Replace("\", "/")
    }
}

function Get-GenerationPrompt {
    param($Request, [string]$Kind, [string]$Slug)

    $subject = if ($Request.subject) { [string]$Request.subject } else { $Slug }
    $pose = if ($Request.pose) { [string]$Request.pose } else { "centered, three-quarter isometric view, generous padding" }
    $roleColor = if ($Request.roleColor) { [string]$Request.roleColor } elseif ($Request.accentColor) { [string]$Request.accentColor } else { "#647cff" }
    $notes = if ($Request.notes) { [string]$Request.notes } else { "No extra notes." }

    switch ($Kind) {
        "character" {
            return @"
Create a Dipeen product character asset on a perfectly flat solid #ff00ff chroma-key background for background removal.
Subject: $subject.
Style: compact isometric/pixel-inspired 3D character for a dark glassmorphism SaaS interface, readable at 48-96 px, clean silhouette, friendly but professional, no photorealism.
Role accent: $roleColor appears only as a badge, small clothing accent, or UI label.
Pose: $pose.
Background: one uniform #ff00ff color only, no floor, no shadow, no reflection, no texture, no text, no watermark.
Avoid using #ff00ff anywhere in the subject.
Notes: $notes
"@
        }
        "office-prop" {
            return @"
Create a modular Dipeen virtual-office prop asset on a perfectly flat solid #ff00ff chroma-key background for background removal.
Subject: $subject.
Style: compact isometric/pixel-inspired 3D office prop for a dark glassmorphism SaaS interface, crisp edges, readable at dashboard scale, no photorealism.
Accent color: use $roleColor sparingly for small LEDs, labels, or UI glow.
Composition: $pose.
Background: one uniform #ff00ff color only, no floor, no shadow, no reflection, no texture, no text, no watermark.
Avoid using #ff00ff anywhere in the subject.
Notes: $notes
"@
        }
        "empty-state" {
            return @"
Create a polished Dipeen empty-state illustration on a transparent-friendly solid #ff00ff chroma-key background.
Subject: $subject.
Style: compact isometric SaaS illustration for a dark enterprise UI, calm and professional, no photorealism, no large text, no UI mockup.
Accent color: use $roleColor as a restrained brand accent.
Composition: centered with generous padding, readable inside a 320px panel.
Background: one uniform #ff00ff color only, no shadow, no reflection, no texture, no text, no watermark.
Avoid using #ff00ff anywhere in the subject.
Notes: $notes
"@
        }
        default {
            return @"
Create a Dipeen visual mood-reference asset.
Subject: $subject.
Style: dark glassmorphism SaaS, compact isometric/pixel-inspired product visual language, professional and production-grade, no photorealism.
Accent color: $roleColor.
Composition: $pose.
Do not include text, logos, watermarks, or full UI screenshots.
Notes: $notes
"@
        }
    }
}

function Invoke-AssetGeneration {
    param($Entry, [string]$Prompt, $Targets, [string]$PacketPath)

    $scriptPath = Join-Path $rootPath "scripts\gen_asset.py"
    $args = @(
        $scriptPath,
        "--root", $rootPath,
        "--prompt", $Prompt,
        "--source", $Targets.source,
        "--transparent", $Targets.transparent,
        "--size", $ImageSize,
        "--quality", $ImageQuality,
        "--background", "transparent"
    )

    $output = & python @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        $failPath = Join-Path $failedDir "$($Entry.id).md"
        Add-Content -LiteralPath $PacketPath -Value "`n## Generation Failure`n`n$output" -Encoding UTF8
        Move-Item -LiteralPath $PacketPath -Destination $failPath -Force
        throw "generation failed for $($Entry.id): $output"
    }

    Add-Content -LiteralPath $PacketPath -Value "`n## Generation Result`n`n$output" -Encoding UTF8
    Move-Item -LiteralPath $PacketPath -Destination (Join-Path $doneDir "$($Entry.id).md") -Force
    return $output
}

function Write-RequestPacket {
    param($Request, [int]$LineNumber)

    if (-not $Request.id) {
        throw "line $LineNumber is missing required field: id"
    }

    $id = ConvertTo-SafeName ([string]$Request.id)
    $kind = if ($Request.kind) { ([string]$Request.kind).ToLowerInvariant() } else { "mood-reference" }
    $slug = if ($Request.slug) { ConvertTo-SafeName ([string]$Request.slug) } else { $id }
    $targets = Get-OutputTargets -Request $Request -Kind $kind -Slug $slug
    $prompt = Get-GenerationPrompt -Request $Request -Kind $kind -Slug $slug
    $originalJson = $Request | ConvertTo-Json -Depth 10
    $packetPath = Join-Path $activeDir "$id.md"

    $packet = @"
# Asset Request: $id

Status: waiting_for_codex_imagegen
Kind: $kind
Slug: $slug
Queue line: $LineNumber
Created: $((Get-Date).ToString("o"))

## Generation Prompt

~~~text
$prompt
~~~

## Output Targets

- Source: $($targets.source)
- Transparent: $($targets.transparent)

## Handling Checklist

- Generate one raster image from the prompt.
- Save the unmodified source file to the Source target.
- If the prompt uses #ff00ff, remove the chroma key and save the transparent PNG target.
- Move this packet to done/ when complete, or failed/ with a short reason.

## Original Request

~~~json
$originalJson
~~~
"@

    $packet | Set-Content -LiteralPath $packetPath -Encoding UTF8

    $entry = [pscustomobject]@{
        id = $id
        sourceId = [string]$Request.id
        status = "waiting_for_codex_imagegen"
        kind = $kind
        slug = $slug
        packet = $packetPath.Replace($rootPath + "\", "").Replace("\", "/")
        createdAt = (Get-Date).ToString("o")
    }

    if ($Generate) {
        $result = Invoke-AssetGeneration -Entry $entry -Prompt $prompt -Targets $targets -PacketPath $packetPath
        $entry.status = "generated"
        $entry.result = [string]$result
        $entry.completedAt = (Get-Date).ToString("o")
        $entry.packet = (Join-Path "docs/claude/asset-requests/done" "$id.md").Replace("\", "/")
    }

    return $entry
}

function Invoke-QueuePass {
    $processed = Get-ProcessedMap
    $changed = $false
    $lineNumber = 0

    foreach ($line in Get-Content -LiteralPath $queuePath -ErrorAction SilentlyContinue) {
        $lineNumber++
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        try {
            $request = $trimmed | ConvertFrom-Json -ErrorAction Stop
            $requestId = if ($request.id) { ConvertTo-SafeName ([string]$request.id) } else { "" }
            $status = if ($request.status) { ([string]$request.status).ToLowerInvariant() } else { "requested" }

            if ($status -notin @("requested", "new", "pending")) {
                continue
            }
            if ($processed.ContainsKey($requestId)) {
                continue
            }

            $entry = Write-RequestPacket -Request $request -LineNumber $lineNumber
            $processed[$entry.id] = $entry
            $changed = $true
            Write-AssetLog "$($entry.status.ToUpperInvariant()) packet=$($entry.packet) kind=$($entry.kind) slug=$($entry.slug)"
        } catch {
            Write-AssetLog "ERROR line=$lineNumber $($_.Exception.Message)"
        }
    }

    if ($changed) {
        Save-ProcessedMap -Processed $processed
    }
}

Write-AssetLog "START pid=$PID queue=$queuePath interval=$IntervalSeconds once=$Once generate=$Generate quality=$ImageQuality size=$ImageSize"
Write-Host "Watching Claude asset queue: $queuePath"

do {
    Invoke-QueuePass
    if ($Once) {
        break
    }
    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
