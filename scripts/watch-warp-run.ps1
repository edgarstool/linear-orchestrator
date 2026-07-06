# 盯 Warp Oz 任務狀態：輪詢、follow-up、失敗白話摘要
param(
  [Parameter(Mandatory = $true)]
  [string]$RunId,

  [string]$FollowUp,

  [int]$IntervalSec = 15,

  [switch]$Json
)

$ErrorActionPreference = "Stop"

$apiKey = [Environment]::GetEnvironmentVariable("WARP_API_KEY", "User")
if (-not $apiKey) {
  throw "尚未設定 WARP_API_KEY。請先執行：cd V:\projects\linear-orchestrator; .\scripts\setup-warp-api.ps1 -CreateApiKeyIfMissing"
}

$baseUri = "https://app.warp.dev/api/v1/agent/runs"
$headers = @{
  Authorization  = "Bearer $apiKey"
  "Content-Type" = "application/json"
}

function Get-WarpRun([string]$Id) {
  return Invoke-RestMethod -Uri "$baseUri/$Id" -Headers @{ Authorization = "Bearer $apiKey" }
}

function Send-WarpFollowUp([string]$Id, [string]$Message) {
  $body = @{ message = $Message } | ConvertTo-Json
  return Invoke-RestMethod -Uri "$baseUri/$Id/followups" -Method POST -Headers $headers -Body $body
}

function Format-FailureMessage($run) {
  $state = $run.state
  $msg = $run.status_message
  $lines = @("Warp 任務沒有成功完成。")
  switch ($state) {
    "FAILED" { $lines += "狀態：失敗。" }
    "CANCELLED" { $lines += "狀態：已取消。" }
    default { $lines += "狀態：$state" }
  }
  if ($msg) { $lines += "原因：$msg" }
  if ($run.session_link) { $lines += "詳情連結：$($run.session_link)" }
  $lines += "你可以點連結看 Oz 做了什麼，或把 Run ID 貼給 Agent 再試。"
  return ($lines -join "`n")
}

if ($FollowUp) {
  Write-Host "送出 follow-up 到 Run $RunId ..." -ForegroundColor Cyan
  Send-WarpFollowUp -Id $RunId -Message $FollowUp | Out-Null
  Write-Host "Follow-up 已送出。" -ForegroundColor Green
}

Write-Host "監看 Run $RunId（每 $IntervalSec 秒查一次）..." -ForegroundColor Yellow
$run = $null
do {
  Start-Sleep -Seconds $IntervalSec
  $run = Get-WarpRun -Id $RunId
  Write-Host "狀態：$($run.state) — $($run.updated_at)"
} while ($run.state -in @("QUEUED", "INPROGRESS"))

$result = [ordered]@{
  run_id        = $RunId
  state         = $run.state
  session_link  = $run.session_link
  status_message = $run.status_message
  updated_at    = $run.updated_at
  succeeded     = ($run.state -eq "SUCCEEDED")
}

if ($run.state -eq "SUCCEEDED") {
  Write-Host ""
  Write-Host "完成！" -ForegroundColor Green
  if ($run.session_link) { Write-Host "結果頁：$($run.session_link)" }
  $result.summary = "Warp 任務已完成。點 session link 查看 Oz 做了什麼（含可能的 PR）。"
} else {
  Write-Host ""
  $plain = Format-FailureMessage $run
  Write-Host $plain -ForegroundColor Red
  $result.summary = $plain
}

if ($Json) {
  $result | ConvertTo-Json -Depth 4
}

return $result
