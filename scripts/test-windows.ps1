# Signed Linear webhook test (Windows). Per https://linear.app/developers/webhooks
param(
  [string]$Url = "http://127.0.0.1:8645/webhooks/linear"
)

$envFile = Join-Path $env:USERPROFILE ".hermes\.env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
  }
}
if (-not $env:LINEAR_WEBHOOK_SECRET) { throw "LINEAR_WEBHOOK_SECRET not set in $envFile" }

$ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$body = @{
  action = "create"
  type = "Comment"
  data = @{
    id = "c-test-win"
    body = "@hermes please ack"
    issueId = "i-test"
    issue = @{
      id = "i-test"
      identifier = "TEST-1"
      title = "orchestrator e2e windows"
    }
  }
  webhookTimestamp = $ts
} | ConvertTo-Json -Compress -Depth 6

$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [Text.Encoding]::UTF8.GetBytes($env:LINEAR_WEBHOOK_SECRET)
$sig = -join ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body)) | ForEach-Object { $_.ToString("x2") })

Write-Host "POST $Url"
$r = Invoke-WebRequest -Uri $Url -Method POST -Body $body -ContentType "application/json" `
  -Headers @{ "Linear-Signature" = $sig } -UseBasicParsing
Write-Host "HTTP $($r.StatusCode)"
Write-Host $r.Content
