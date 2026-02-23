@echo off
echo Starting Redis...
docker compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start Docker Compose. Make sure Docker is running.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Starting Telegram Bot...
python telegram_bot.py
pause
