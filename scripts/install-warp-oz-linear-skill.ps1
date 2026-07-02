# Install warp-oz-linear skill to all agent skill directories.
# Canonical source: V:\projects\linear-orchestrator\skills\warp-oz-linear\SKILL.md
param(
  [string]$SourceDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "skills\warp-oz-linear")
)

$ErrorActionPreference = "Stop"
$src = Join-Path $SourceDir "SKILL.md"
if (-not (Test-Path $src)) { throw "Missing $src" }

$targets = @(
  @{ Label = "Hermes";        Dir = Join-Path $env:USERPROFILE ".hermes\skills\warp-oz-linear" },
  @{ Label = "Codex";         Dir = Join-Path $env:USERPROFILE ".codex\skills\warp-oz-linear" },
  @{ Label = "Claude Code";   Dir = Join-Path $env:USERPROFILE ".claude\skills\warp-oz-linear" },
  @{ Label = "Agents shared"; Dir = Join-Path $env:USERPROFILE ".agents\skills\warp-oz-linear" },
  @{ Label = "Cursor";        Dir = Join-Path $env:USERPROFILE ".cursor\skills\warp-oz-linear" },
  @{ Label = "AgentKB母本";   Dir = "G:\AgentKB\skills\warp-oz-linear" }
)

$installed = @()
foreach ($t in $targets) {
  $parent = Split-Path $t.Dir -Parent
  if (-not (Test-Path $parent)) {
    Write-Warning "Skip $($t.Label): parent missing $parent"
    continue
  }
  New-Item -ItemType Directory -Force -Path $t.Dir | Out-Null
  Copy-Item $src (Join-Path $t.Dir "SKILL.md") -Force
  $installed += $t.Label
  Write-Host "OK $($t.Label) -> $($t.Dir)" -ForegroundColor Green
}

# Hermes default profile shortcut (single-file form)
$profileSkills = Join-Path $env:USERPROFILE ".hermes\profiles\default\skills"
if (Test-Path $profileSkills) {
  Copy-Item $src (Join-Path $profileSkills "warp-oz-linear.md") -Force
  Write-Host "OK Hermes profile -> $profileSkills\warp-oz-linear.md" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installed warp-oz-linear to: $($installed -join ', ')" -ForegroundColor Cyan
Write-Host "Skill ID: warp-oz-linear"
