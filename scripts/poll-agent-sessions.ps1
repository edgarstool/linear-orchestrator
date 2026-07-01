# 備援：當 Linear OAuth App webhook 沒送到 orchestrator 時，輪詢 pending/active agent session 並本機觸發 Hermes。
# 官方 webhook 仍應在 Linear Developer → Hermes Application → Webhooks 設好；此腳本是保險。
param(
  [int]$IntervalSec = 3,
  [string]$OrchestratorUrl = "http://127.0.0.1:8645/webhooks/linear"
)

$ErrorActionPreference = "Stop"
$envFile = Join-Path $env:USERPROFILE ".hermes\.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
  }
}
foreach ($k in @("LINEAR_API_KEY", "AGENT_LINEAR_USER_ID")) {
  if (-not (Get-Item "Env:$k" -ErrorAction SilentlyContinue)) { throw "Missing $k in $envFile" }
}

$secret = $env:LINEAR_OAUTH_WEBHOOK_SECRET
if (-not $secret) { $secret = $env:LINEAR_WEBHOOK_SECRET }
if (-not $secret) { throw "Need LINEAR_OAUTH_WEBHOOK_SECRET or LINEAR_WEBHOOK_SECRET" }

$stateDir = Join-Path $env:USERPROFILE ".local\share\linear-orchestrator"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$stateFile = Join-Path $stateDir "poller-seen.json"
$seen = @{}
if (Test-Path $stateFile) {
  try { $seen = Get-Content $stateFile -Raw | ConvertFrom-Json -AsHashtable } catch { $seen = @{} }
}

function Save-Seen {
  ($seen.Keys | ForEach-Object { [pscustomobject]@{ id = $_ } }) | ConvertTo-Json | Set-Content $stateFile -Encoding utf8
}

function Get-DelegatedSessions {
  $agent = $env:AGENT_LINEAR_USER_ID
  $query = "{`"query`":`"query { issues(first: 25, filter: { delegate: { id: { eq: \`"$agent\`" } } }) { nodes { id identifier title url agentSessions { nodes { id status createdAt } } } } }`"}"
  $r = Invoke-RestMethod -Uri "https://api.linear.app/graphql" -Method POST `
    -Headers @{ Authorization = $env:LINEAR_API_KEY } -Body $query -ContentType "application/json"
  $out = @()
  foreach ($issue in $r.data.issues.nodes) {
    foreach ($s in $issue.agentSessions.nodes) {
      if ($s.status -in @("pending", "active")) {
        $out += [pscustomobject]@{
          sessionId = $s.id
          status    = $s.status
          issueId   = $issue.id
          issue     = $issue.identifier
          title     = $issue.title
          url       = $issue.url
        }
      }
    }
  }
  return $out
}

function Send-AgentSessionEvent($sess) {
  $ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $bodyObj = @{
    action           = "created"
    type             = "AgentSessionEvent"
    webhookTimestamp = $ts
    agentSession     = @{
      id      = $sess.sessionId
      issueId = $sess.issueId
      issue   = @{
        id         = $sess.issueId
        identifier = $sess.issue
        title      = $sess.title
        url        = $sess.url
      }
    }
  }
  $body = $bodyObj | ConvertTo-Json -Compress -Depth 8
  $hmac = New-Object System.Security.Cryptography.HMACSHA256
  $hmac.Key = [Text.Encoding]::UTF8.GetBytes($secret)
  $sig = -join ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body)) | ForEach-Object { $_.ToString("x2") })
  $delivery = "poller-$($sess.sessionId)"
  Invoke-WebRequest -Uri $OrchestratorUrl -Method POST -Body $body -ContentType "application/json" `
    -Headers @{ "Linear-Signature" = $sig; "Linear-Delivery" = $delivery } -UseBasicParsing | Out-Null
}

Write-Host "Agent session poller started (every ${IntervalSec}s). Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "Orchestrator: $OrchestratorUrl"
Write-Host "Watching delegate: $($env:AGENT_LINEAR_USER_ID)"
Write-Host ""

while ($true) {
  try {
    $pending = Get-DelegatedSessions
    foreach ($sess in $pending) {
      if ($seen.ContainsKey($sess.sessionId)) { continue }
      Write-Host "[$(Get-Date -Format HH:mm:ss)] trigger $($sess.issue) session=$($sess.sessionId) status=$($sess.status)"
      Send-AgentSessionEvent $sess
      $seen[$sess.sessionId] = (Get-Date).ToUniversalTime().ToString("o")
      Save-Seen
    }
  } catch {
    Write-Warning "poll error: $_"
  }
  Start-Sleep -Seconds $IntervalSec
}
