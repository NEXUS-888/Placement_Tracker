@echo off
title Placement Tracker Hub
echo ====================================================
echo      Placement Tracker & Intelligence Hub
echo ====================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [Setup] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
)

if not exist ".env" (
    copy .env.example .env
    echo [Config] Created .env file. Please edit it to add your GEMINI_API_KEY and DISCORD_WEBHOOK_URL.
)

echo [1/2] Starting FastAPI Backend on http://localhost:8000 ...
start "Placement Tracker API" venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload

echo [2/2] Opening Dashboard in browser...
start http://localhost:8000

echo.
echo ====================================================
echo Backend is running at http://localhost:8000
echo.
echo To start the WhatsApp Bridge (QR scan once):
echo   1. npm install
echo   2. node whatsapp_listener.js
echo ====================================================
echo.
pause
