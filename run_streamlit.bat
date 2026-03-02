@echo off
echo Starting Redis...
docker compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Docker Compose failed to start. Redis might not be available.
)
echo Starting Butler Streamlit Interface...
streamlit run app.py
pause
