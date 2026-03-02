@echo off
echo Starting Butler REST API...
set API_PORT=8000
uvicorn api:app --host 0.0.0.0 --port %API_PORT% --reload
