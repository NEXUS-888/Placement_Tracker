#!/bin/bash
# 24/7 Hosting Launcher for Linux VPS
echo "===================================================="
echo "      Placement Tracker Linux VPS Launcher"
echo "===================================================="

cd "$(dirname "$0")"

# Setup python venv if needed
if [ ! -d "venv" ]; then
    echo "[Setup] Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Setup node dependencies
if [ ! -d "node_modules" ]; then
    echo "[Setup] Installing Node dependencies for WhatsApp bridge..."
    npm install
fi

# Ensure .env exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[Config] Created .env file. Please edit it with your GEMINI_API_KEY and DISCORD_WEBHOOK_URL."
fi

# Start FastAPI server in background
echo "[1/2] Starting FastAPI backend on port 8000..."
nohup ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
SERVER_PID=$!
echo "Backend running (PID: $SERVER_PID). Logs in server.log"

# Check if pm2 is available for 24/7 process management
if command -v pm2 &> /dev/null; then
    echo "[2/2] Launching WhatsApp Bridge via PM2 for 24/7 persistence..."
    pm2 start whatsapp_listener.js --name "placement-whatsapp"
    pm2 logs placement-whatsapp
else
    echo "[2/2] Starting WhatsApp Bridge in foreground..."
    node whatsapp_listener.js
fi
