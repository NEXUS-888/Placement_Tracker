# 🎓 Placement Tracker & Intelligence Hub

An automated, 24/7 pipeline that intercepts college placement drives and internship announcements from your WhatsApp group, extracts structured details using **Google Gemini**, detects updates & amendments to existing drives, dispatches instant color-coded notifications to **Discord**, and provides a web dashboard accessible by both you and your AI agent (Antigravity).

---

## ⚡ Features

- **📱 WhatsApp Ingestion**:
  - Passive, read-only bridge via `whatsapp-web.js` with `LocalAuth`.
  - **Scan QR once**: session is cached locally in `.wwebjs_auth`—no repeated scanning across restarts.
  - Automatically downloads attached PDFs, job descriptions, and images.
  - **Zero ban risk**: strictly 100% read-only (no outbound automated messages or spam).
- **🧠 Multimodal Extraction (Google Gemini)**:
  - Parses messy WhatsApp messages, circulars, and PDF attachments.
  - Extracts Company, Role, Type (Full-time / Internship), CTC/Stipend, Eligibility Criteria, Deadlines, Drive Dates, and Apply Links.
- **🔄 Change & Diff Tracking**:
  - Automatically matches incoming posts with active drives.
  - Detects changes (e.g. deadline postponed, eligibility expanded to other branches).
  - Logs an audit timeline of changes (`old_value` ➔ `new_value`).
  - Fires an urgent `⚠️ UPDATE` alert to Discord highlighting exact modifications.
- **💬 Discord Alerts**:
  - 🟢 **Green Embed**: New Placement Drive / Internship
  - 🟡 **Yellow Embed**: Update / Amendment to Existing Drive
  - 🔴 **Red Embed**: Urgent Deadline Warning
- **💻 Web Dashboard**:
  - Clean, responsive dark-mode UI at `http://localhost:8000`.
  - Live metric cards (Active Drives, Applications, Updates).
  - Search & filter by status (`Upcoming`, `Applied`, `Ongoing`, `Closed`).
  - Interactive Simulator: test any WhatsApp message or drop a PDF directly into the UI!
- **🤖 AI Agent & CLI Access**:
  - `python cli.py list`: Quick list of drives.
  - `python cli.py deadlines`: Upcoming active deadlines.
  - `python cli.py inspect <company>`: View details, attached files, and full update history.
  - `python cli.py status`: High-level summary.

---

## 🚀 Quick Setup (Local Windows)

### 1. Configure `.env`
Copy `.env.example` to `.env`:
```env
# 1. Free Gemini API Key from https://aistudio.google.com/
GEMINI_API_KEY=your_gemini_api_key_here

# 2. Discord Webhook URL (Channel Settings -> Integrations -> Webhooks)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# 3. Optional: WhatsApp Group Name keyword filter
TARGET_WHATSAPP_GROUP=Placement
PORT=8000
```

### 2. Start the Backend & Dashboard
Double-click `start.bat` or run:
```powershell
.\venv\Scripts\activate
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```
Open **`http://localhost:8000`** in your browser.

### 3. Start the WhatsApp Bridge (Scan QR Code Once)
In a separate terminal:
```powershell
npm install
node whatsapp_listener.js
```
- A QR code will display in your terminal.
- Open WhatsApp on your phone ➔ **Settings** ➔ **Linked Devices** ➔ **Link a Device** ➔ Scan the terminal QR code.
- That's it! Session is saved in `.wwebjs_auth`.

---

## 🌐 24/7 Hosting (VPS / Cloud / Server)

You can run this 24/7 on any Ubuntu / Debian VPS (e.g., Oracle Cloud Free Tier, DigitalOcean, AWS EC2, or Hetzner).

### Option A: 1-Click Docker Compose (Recommended)
```bash
# Clone or copy project files to your server
git clone <your-repo> placement-tracker
cd placement-tracker

# Fill in .env with your keys
cp .env.example .env
nano .env

# Start container in background
docker compose up -d

# View QR code on initial run (if using WhatsApp bridge)
docker compose logs -f placement-tracker
```
All database records (`placement_tracker.db`), uploaded files (`uploads/`), and WhatsApp session tokens (`.wwebjs_auth/`) are stored in persistent Docker volumes.

### Option B: Native Linux Systemd / PM2
```bash
chmod +x start.sh
./start.sh
```

---

## 🧪 Testing Without WhatsApp (UI Simulator)

Want to test the pipeline right now without scanning WhatsApp?
1. Open the dashboard at `http://localhost:8000`.
2. Click **"Simulate Ingestion"** at top right.
3. Click *"Load New Drive Sample"* or *"Load Date Change Update Sample"*.
4. Click **Run Analyzer & Dispatch**.
5. Watch the drive appear on your dashboard and check your Discord channel for the instant alert!
