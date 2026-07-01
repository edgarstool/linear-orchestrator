# 設定 Hermes OAuth App webhook 簽章密鑰（瀏覽器 delegate 必備）
# 官方：https://linear.app/developers/agents — Agent session events 走 OAuth App webhook
param(
  [string]$WebhookUrl = "https://webhooks.edgars.tools/webhooks/linear",
  [string]$Secret = ""
)

$ErrorActionPreference = "Stop"
$envFile = Join-Path $env:USERPROFILE ".hermes\.env"

Write-Host @"

=== 為什麼瀏覽器 Delegate 會「Did not respond」？ ===

Linear 在你按 Delegate → Hermes 時，送的是 **OAuth App 專用 webhook**，
簽章密鑰跟 workspace webhook (LINEAR_WEBHOOK_SECRET) **不一樣**。
orchestrator 若只有一把鑰匙，會 401 擋掉 → 10 秒內沒 thought → Did not respond。

=== 請在瀏覽器做（約 2 分鐘）===

1. 開 https://linear.app/settings/api/applications
2. 點你的 **Hermes** OAuth Application
3. Webhooks 區：
   - URL 設為：$WebhookUrl
   - 勾選 **Agent session events**（必選）
4. 複製頁面上的 **Signing secret**（通常 lin_wh_ 開頭）

"@ -ForegroundColor Yellow

if (-not $Secret) {
  $Secret = Read-Host "貼上 OAuth App Signing secret（lin_wh_...）"
}
$Secret = $Secret.Trim()
if (-not $Secret) { throw "Secret 不能為空" }

$lines = if (Test-Path $envFile) { Get-Content $envFile } else { @() }
$found = $false
$newLines = foreach ($line in $lines) {
  if ($line -match '^LINEAR_OAUTH_WEBHOOK_SECRET=') {
    $found = $true
    "LINEAR_OAUTH_WEBHOOK_SECRET=$Secret"
  } else { $line }
}
if (-not $found) { $newLines += "LINEAR_OAUTH_WEBHOOK_SECRET=$Secret" }
$bak = "$envFile.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $envFile $bak -ErrorAction SilentlyContinue
$newLines | Set-Content $envFile -Encoding utf8
Write-Host "已寫入 LINEAR_OAUTH_WEBHOOK_SECRET（備份 $bak）" -ForegroundColor Green

Write-Host "重啟 orchestrator ..."
Get-NetTCPConnection -LocalPort 8645 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 1
$root = Split-Path $PSScriptRoot -Parent
Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList '-m','linear_orchestrator' -WindowStyle Hidden
Start-Sleep -Seconds 2
curl -s http://127.0.0.1:8645/healthz
Write-Host ""
curl -s http://127.0.0.1:8645/diag
Write-Host ""
Write-Host "建議另開一個 PowerShell 常駐備援輪詢：" -ForegroundColor Yellow
Write-Host "  .\scripts\poll-agent-sessions.ps1" -ForegroundColor White
Write-Host ""
Write-Host "完成。回 Linear 對 EDG-159 再 Delegate → Hermes 一次測試。" -ForegroundColor Cyan
