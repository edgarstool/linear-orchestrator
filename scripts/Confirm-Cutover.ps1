<#
.SYNOPSIS
    EDG-70 cutover 確認腳本。
    驗證「新 workspace（Windows 原生 linear-orchestrator + webhooks.edgars.tools）」
    已成為唯一有效主工作區，舊 webhook.whoasked.vip 路徑已停用。

.DESCRIPTION
    執行以下 5 項檢查：
      1. Windows orchestrator 程序是否在跑
      2. 本機 healthz (http://127.0.0.1:8645/healthz) 是否 200
      3. WSL port 8645 搶佔衝突是否已排除
      4. 公開 healthz (https://webhooks.edgars.tools/healthz) 是否 200
      5. 舊 URL (webhook.whoasked.vip) 是否已無法連線

    全部通過 → exit 0（cutover 完成）
    有任何失敗 → exit 1（顯示修復提示）

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\Confirm-Cutover.ps1
#>

param(
    [switch]$Quiet  # 僅輸出 FAIL 行；靜默 PASS；exit code 仍有效
)

$ErrorActionPreference = "Continue"
Import-Module (Join-Path $PSScriptRoot "LinearOrchestratorCommon.psm1") -Force

$passCount = 0
$failCount = 0

function Write-Check {
    param(
        [string]$Label,
        [bool]$Ok,
        [string]$FixHint = ""
    )
    if ($Ok) {
        $script:passCount++
        if (-not $Quiet) {
            Write-Host "  [PASS] $Label" -ForegroundColor Green
        }
    } else {
        $script:failCount++
        Write-Host "  [FAIL] $Label" -ForegroundColor Red
        if ($FixHint) {
            Write-Host "         → $FixHint" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "=== EDG-70 Cutover 確認 ===" -ForegroundColor Cyan
Write-Host "  新工作區：Windows 原生 linear-orchestrator，port 8645"
Write-Host "  公開端點：https://webhooks.edgars.tools/webhooks/linear"
Write-Host ""

# 1. Windows orchestrator 程序在跑？
$proc = Get-OrchestratorProcess
Write-Check `
    "Windows orchestrator 程序在跑 (pid=$(if ($proc) { $proc.Id } else { 'N/A' }))" `
    ($null -ne $proc) `
    "啟動：powershell -ExecutionPolicy Bypass -File scripts\Start-LinearOrchestrator.ps1 -Wait"

# 2. 本機 healthz 200
$localOk = Test-OrchestratorHealth
Write-Check `
    "本機 healthz OK ($(Get-OrchestratorHealthUrl))" `
    $localOk `
    "先確認 orchestrator 有在跑，或查 G:\AI_WORK_512\run\linear-orchestrator\orchestrator.err.log"

# 3. WSL port 8645 衝突排除
$wslConflict = Test-WslOrchestratorConflict
Write-Check `
    "無 WSL port-8645 搶佔衝突" `
    ($null -eq $wslConflict) `
    "停掉 WSL 舊服務：wsl -e bash -lc `"pkill -f 'python -m linear_orchestrator' || true`""

# 4. 公開 healthz 200（webhooks.edgars.tools）
$pubOk = $false
$pubLabel = ""
try {
    $pub = Invoke-WebRequest -UseBasicParsing `
        -Uri "https://webhooks.edgars.tools/healthz" `
        -TimeoutSec 10
    $pubOk = ([int]$pub.StatusCode -eq 200)
    $pubLabel = "HTTP $($pub.StatusCode)"
} catch {
    $pubLabel = "ERROR: $($_.Exception.Message)"
}
Write-Check `
    "公開 healthz OK (https://webhooks.edgars.tools/healthz) — $pubLabel" `
    $pubOk `
    "Cloudflare Dashboard → edgar-local-01-tunnel → Public Hostname → webhooks.edgars.tools → http://localhost:8645"

# 5. 舊 URL 已停用（webhook.whoasked.vip）
$oldGone = $false
try {
    $old = Invoke-WebRequest -UseBasicParsing `
        -Uri "https://webhook.whoasked.vip/healthz" `
        -TimeoutSec 5
    # 若能連到表示舊路由還活著
    $oldGone = $false
    $oldLabel = "仍回應 HTTP $($old.StatusCode)！"
} catch {
    # 連線失敗／逾時 = 舊 URL 已停用，符合預期
    $oldGone = $true
    $oldLabel = "無法連線（預期行為）"
}
Write-Check `
    "舊 URL 已停用 (webhook.whoasked.vip) — $oldLabel" `
    $oldGone `
    "Cloudflare Dashboard 刪除 webhook.whoasked.vip 的 Public Hostname 路由"

# 結果摘要
$total = $passCount + $failCount
Write-Host ""
if ($failCount -eq 0) {
    Write-Host "--- 結果：$passCount/$total 項通過 ---" -ForegroundColor Green
    Write-Host "Cutover 完成！新 workspace 已是唯一主工作區。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "--- 結果：$passCount/$total 項通過，$failCount 項失敗 ---" -ForegroundColor Yellow
    Write-Host "Cutover 未完成。請修正上方 FAIL 項目後重新執行：" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\Confirm-Cutover.ps1"
    exit 1
}
