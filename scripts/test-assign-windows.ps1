# Simulate Linear AgentSessionEvent (assign/delegate flow).
# Per Linear agent protocol: thought ack within ~10s via agentActivityCreate.
param(
  [string]$Url = "http://127.0.0.1:8645/webhooks/linear",
  [string]$IssueId = "",
  [string]$IssueIdentifier = "EDG-286",
  [string]$AgentSessionId = "",
  [switch]$UseLatestPendingSession
)

$envFile = Join-Path $env:USERPROFILE ".hermes\.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
  }
}
if (-not $env:LINEAR_WEBHOOK_SECRET) { throw "LINEAR_WEBHOOK_SECRET not set" }

if ($UseLatestPendingSession -and -not $AgentSessionId) {
  $q = @{ query = "query { issue(id: `"$IssueIdentifier`") { id agentSessions { nodes { id status createdAt } } } }" } | ConvertTo-Json
  $r = Invoke-RestMethod -Uri "https://api.linear.app/graphql" -Method POST `
    -Headers @{ Authorization = $env:LINEAR_API_KEY } -Body $q -ContentType "application/json"
  $nodes = $r.data.issue.agentSessions.nodes
  $pick = $nodes | Where-Object { $_.status -eq "pending" } | Sort-Object createdAt -Descending | Select-Object -First 1
  if (-not $pick) { $pick = $nodes | Sort-Object createdAt -Descending | Select-Object -First 1 }
  if (-not $pick) { throw "No agent session on $IssueIdentifier" }
  $AgentSessionId = $pick.id
  Write-Host "Using latest session: $AgentSessionId (status=$($pick.status))"
}

if (-not $AgentSessionId) {
  $AgentSessionId = "as-test-win-$(Get-Date -Format 'HHmmss')"
}

if (-not $IssueId) {
  $q = @{ query = "query { issue(id: `"$IssueIdentifier`") { id identifier title url } }" } | ConvertTo-Json
  $r = Invoke-RestMethod -Uri "https://api.linear.app/graphql" -Method POST `
    -Headers @{ Authorization = $env:LINEAR_API_KEY } -Body $q -ContentType "application/json"
  $IssueId = $r.data.issue.id
}

$ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$bodyObj = @{
  action = "created"
  type = "AgentSessionEvent"
  webhookTimestamp = $ts
  agentSession = @{
    id = $AgentSessionId
    issueId = $IssueId
    title = "Assign smoke test for $IssueIdentifier"
    issue = @{
      id = $IssueId
      identifier = $IssueIdentifier
      title = "[TEST-Hermes] assign smoke test"
      url = "https://linear.app/edgarstool/issue/$IssueIdentifier"
    }
  }
}
$body = $bodyObj | ConvertTo-Json -Compress -Depth 8

$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [Text.Encoding]::UTF8.GetBytes($env:LINEAR_WEBHOOK_SECRET)
$sig = -join ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body)) | ForEach-Object { $_.ToString("x2") })

Write-Host "POST $Url (AgentSessionEvent assign simulation)"
Write-Host "session=$AgentSessionId issue=$IssueIdentifier"
$r = Invoke-WebRequest -Uri $Url -Method POST -Body $body -ContentType "application/json" `
  -Headers @{ "Linear-Signature" = $sig; "Linear-Delivery" = [guid]::NewGuid().ToString() } -UseBasicParsing
Write-Host "HTTP $($r.StatusCode)"
Write-Host $r.Content
