# Install all Warp Oz skills to agent skill directories.
# Canonical source: V:\projects\linear-orchestrator\skills\
param(
  [string]$SkillsRoot = (Join-Path (Split-Path $PSScriptRoot -Parent) "skills")
)

$ErrorActionPreference = "Stop"

$skillNames = @(
  "warp-oz-linear",
  "warp-oz-cursor",
  "warp-oz-router",
  "warp-oz-deploy",
  "warp-oz-monitor",
  "warp-oz-github-actions"
)

$agentRoots = @(
  @{ Label = "Hermes";        SkillsDir = Join-Path $env:USERPROFILE ".hermes\skills" },
  @{ Label = "Codex";         SkillsDir = Join-Path $env:USERPROFILE ".codex\skills" },
  @{ Label = "Claude Code";   SkillsDir = Join-Path $env:USERPROFILE ".claude\skills" },
  @{ Label = "Agents shared"; SkillsDir = Join-Path $env:USERPROFILE ".agents\skills" },
  @{ Label = "Cursor";        SkillsDir = Join-Path $env:USERPROFILE ".cursor\skills" },
  @{ Label = "AgentKB母本";   SkillsDir = "G:\AgentKB\skills" }
)

$installed = @()

foreach ($name in $skillNames) {
  $src = Join-Path $SkillsRoot "$name\SKILL.md"
  if (-not (Test-Path $src)) {
    Write-Warning "Skip $name`: missing $src"
    continue
  }

  foreach ($agent in $agentRoots) {
    if (-not (Test-Path $agent.SkillsDir)) {
      Write-Warning "Skip $($agent.Label) / $name`: parent missing $($agent.SkillsDir)"
      continue
    }
    $destDir = Join-Path $agent.SkillsDir $name
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item $src (Join-Path $destDir "SKILL.md") -Force
    $installed += "$($agent.Label)/$name"
    Write-Host "OK $($agent.Label) -> $destDir" -ForegroundColor Green
  }
}

function Get-FinalPath([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force
  if ($item.LinkType -eq "SymbolicLink") {
    $target = $item.Target
    if ($target -is [System.Array]) { $target = $target[0] }
    return (Resolve-Path -LiteralPath $target).Path
  }
  return $item.FullName
}

# Hermes default profile shortcuts (single-file form)
$profileSkills = Join-Path $env:USERPROFILE ".hermes\profiles\default\skills"
if (Test-Path $profileSkills) {
  foreach ($name in $skillNames) {
    $src = Join-Path $SkillsRoot "$name\SKILL.md"
    $dest = Join-Path $profileSkills "$name.md"
    if (-not (Test-Path -LiteralPath $src)) { continue }
    if (Test-Path -LiteralPath $dest) {
      if ((Get-FinalPath $src) -ieq (Get-FinalPath $dest)) { continue }
    }
    Copy-Item -LiteralPath $src -Destination $dest -Force
    Write-Host "OK Hermes profile -> $dest" -ForegroundColor Green
  }
}

Write-Host ""
Write-Host "Installed $($skillNames.Count) Warp skills to agent directories." -ForegroundColor Cyan
Write-Host "Skills: $($skillNames -join ', ')"
