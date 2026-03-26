<# :
@echo off
setlocal
title KURO System Launch Suite
:: This is a hybrid Batch + PowerShell script.
:: The Batch part launches the PowerShell part, which contains the logic.
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((Get-Content '%~f0') -join [Environment]::NewLine)"
exit /b
#>

$header = @'
 _  __ _   _ ____   ___  
| |/ /| | | |  _ \ / _ \ 
| ' / | | | | |_) | | | |
|   \ | |_| |  _ <| |_| |
|_|\_\ \___/|_| \_\\___/ 
'@

$LOG_FILE = "$env:TEMP\kuro_boot.log"
if (Test-Path $LOG_FILE) { Remove-Item $LOG_FILE -Force }

function Draw-UI($part, $percent) {
    Clear-Host
    Write-Host $header -ForegroundColor Cyan
    Write-Host '          [ System Intelligence: KURO ]' -ForegroundColor White
    Write-Host ''
    
    $barWidth = 40
    $filled = [math]::Min($barWidth, [math]::Round(($percent / 100) * $barWidth))
    $empty = $barWidth - $filled
    $bar = ('#' * $filled) + ('-' * $empty)
    
    Write-Host (" |$bar| $percent%") -ForegroundColor Yellow
    Write-Host (" Status: $part") -ForegroundColor Gray
    Write-Host ''
    
    Write-Host '--- LATEST LOGS ---' -ForegroundColor DarkGray
    if (Test-Path $LOG_FILE) {
        Get-Content $LOG_FILE | Select-Object -Last 10
    }
}

$tasks = @(
    @{Name='Booting Infrastructure (Redis/Qdrant)'; Cmd='docker compose up -d'}
    @{Name='Starting REST API Server'; Cmd='cmd.exe /c start /min uvicorn api:app --host 0.0.0.0 --port 8000'}
    @{Name='Launching Streamlit Interface'; Cmd='cmd.exe /c start /min streamlit run app.py'}
)

foreach ($task in $tasks) {
    # Simulated progress for smoothness
    for ($i=0; $i -le 100; $i+=10) {
        Draw-UI $task.Name $i
        Start-Sleep -Milliseconds 50
    }
    
    try {
        # Execute actual command and capture log
        $out = Invoke-Expression $task.Cmd 2>&1
        $out | Out-File -FilePath $LOG_FILE -Append
    } catch {
        "Error: $($_.Exception.Message)" | Out-File -FilePath $LOG_FILE -Append
    }
}

Draw-UI 'All Components Online' 100
Write-Host ''
Write-Host '>>> System operational. Entering Kuro Agent environment...' -ForegroundColor Green
Start-Sleep -Seconds 1

# Launch the Telegram bot
python telegram_bot.py

pause
