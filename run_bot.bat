@echo off
echo Starting Redis...
docker compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start Docker Compose. Make sure Docker is running.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Launching Monitoring Dashboard...
start https://cloud.langfuse.com

echo.
echo Starting REST API in new window...
start "Butler REST API" cmd /c "uvicorn api:app --host 0.0.0.0 --port 8000"

echo.
echo Starting Streamlit Interface in new window...
start "Butler Streamlit" cmd /c "streamlit run app.py"

echo.
echo Starting Telegram Bot...
python telegram_bot.py
pause
