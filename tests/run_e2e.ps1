# Audio Separation Async E2E Test (PowerShell, simplified escaping)
$ErrorActionPreference = "Continue"
$RenderBase = "https://ai-music-backend-db6h.onrender.com"
$TestAudio = "C:\Users\dingx\Desktop\test_audio\test_3s.wav"

if (-not (Test-Path $TestAudio)) {
    Write-Error "Test audio not found: $TestAudio"
    exit 1
}

Write-Host "Step 1: health" -ForegroundColor Cyan
curl.exe -s -o $null -w "Render /health -> %{http_code} (%{time_total}s)`n" "$RenderBase/health"

Write-Host ""
Write-Host "Step 2: POST /separate" -ForegroundColor Cyan
$resp = curl.exe -s --max-time 300 -w "`nHTTP_STATUS:%{http_code}`nTIME_TOTAL:%{time_total}s" -X POST "$RenderBase/api/v1/audio/separate" -F "file=@$TestAudio" -F "model=htdemucs"
Write-Host $resp

$taskId = $null
if ($resp -match '"task_id"\s*:\s*"([^"]+)"') {
    $taskId = $Matches[1]
    Write-Host ("Got task_id = {0}" -f $taskId) -ForegroundColor Green
} else {
    Write-Host "No task_id returned. The Render branch/env vars may not be ready yet." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Step 3: poll /status" -ForegroundColor Cyan
$final = $null
for ($i=0; $i -lt 60; $i++) {
    $st = curl.exe -s "$RenderBase/api/v1/audio/separate/status/$taskId"
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $st)
    if ($st -match '"status"\s*:\s*"completed"') {
        $final = $st
        break
    }
    if ($st -match '"status"\s*:\s*"failed"') {
        $final = $st
        break
    }
    Start-Sleep -Seconds 3
}

if ($final -match '"status"\s*:\s*"completed"' -and $final -match '"vocals"\s*:\s*"([^"]+)"') {
    $vocalsUrl = $Matches[1]
    Write-Host ""
    Write-Host "Step 4: download vocals" -ForegroundColor Cyan
    $ts = Get-Date -Format "HHmmss"
    $out = "C:\Users\dingx\Desktop\test_audio\vocals_e2e_${ts}.wav"
    curl.exe -L -o $out $vocalsUrl | Out-Null
    if ((Test-Path $out) -and (Get-Item $out).Length -gt 1000) {
        $kb = [math]::Round((Get-Item $out).Length / 1024, 1)
        Write-Host ("Downloaded {0} KB -> {1}" -f $kb, $out) -ForegroundColor Green
    } else {
        Write-Host "Vocals download failed / file too small" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Final response:" -ForegroundColor Cyan
Write-Host $final
