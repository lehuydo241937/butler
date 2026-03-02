@echo off
echo Starting Redis...
docker compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Docker Compose failed to start. Redis might not be available.
)
echo Starting Butler REST API...
set API_PORT=8000
uvicorn api:app --host 0.0.0.0 --port %API_PORT% --reload
pause
