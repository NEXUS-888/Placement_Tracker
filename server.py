import os
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv
import re
from datetime import datetime, timezone, timedelta

import db
import analyzer

load_dotenv()

# Initialize database
db.init_db()

# Uploads directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="Placement Tracker API",
    description="Automated Ingestion, Parsing, Change-Tracking, and Discord Notifier for College Placements",
    version="1.0.0"
)

# CORS middleware for local frontend dev or external tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StatusUpdateRequest(BaseModel):
    status: Optional[str] = None
    app_status: Optional[str] = None

class ProfileRequest(BaseModel):
    usn: Optional[str] = ""
    full_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    branch: Optional[str] = "CSE"
    cgpa: Optional[float] = 0.0
    tenth_percentage: Optional[float] = 0.0
    twelfth_percentage: Optional[float] = 0.0
    active_backlogs: Optional[int] = 0
    history_backlogs: Optional[int] = 0
    grad_batch: Optional[int] = 2027
    resume_link: Optional[str] = ""
    linkedin_url: Optional[str] = ""
    github_url: Optional[str] = ""

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "placement-tracker"}

@app.get("/api/stats")
def get_stats():
    return db.get_stats()

@app.get("/api/profile")
def get_profile():
    return db.get_student_profile()

@app.post("/api/profile")
def save_profile(payload: ProfileRequest):
    return db.save_student_profile(payload.model_dump())

MONTHS_MAP = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
    'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
}

def parse_deadline_datetime(text: str) -> Optional[datetime]:
    if not text:
        return None
    s = text.strip()
    
    # Extract time (e.g. 4:00PM or 11:30 AM)
    time_m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', s, re.I)
    hours, minutes = 17, 0
    if time_m:
        h = int(time_m.group(1))
        m = int(time_m.group(2)) if time_m.group(2) else 0
        meridian = time_m.group(3).lower()
        if meridian == 'pm' and h < 12: h += 12
        if meridian == 'am' and h == 12: h = 0
        hours, minutes = h, m
    else:
        time_24 = re.search(r'\b(\d{1,2}):(\d{2})\b', s)
        if time_24:
            hours, minutes = int(time_24.group(1)), int(time_24.group(2))

    day, month, year = None, None, None
    # Case 1: 17th Sep 2026 or 17 September 2026
    dmy = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})[,\s]+(\d{4})', s, re.I)
    if dmy and dmy.group(2).lower() in MONTHS_MAP:
        day = int(dmy.group(1))
        month = MONTHS_MAP[dmy.group(2).lower()]
        year = int(dmy.group(3))

    # Case 2: Sep 17th, 2026
    if not year:
        mdy = re.search(r'([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?[,\s]+(\d{4})', s, re.I)
        if mdy and mdy.group(1).lower() in MONTHS_MAP:
            month = MONTHS_MAP[mdy.group(1).lower()]
            day = int(mdy.group(2))
            year = int(mdy.group(3))

    # Case 3: 24-09-2026 or 24/09/2026
    if not year:
        num = re.search(r'(\d{1,2})[-\/](\d{1,2})[-\/](\d{4})', s)
        if num:
            day = int(num.group(1))
            month = int(num.group(2))
            year = int(num.group(3))

    if year and month and day:
        # Create in Indian Standard Time (UTC+05:30)
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime(year, month, day, hours, minutes, tzinfo=ist)
    return None

def generate_ical_feed() -> str:
    drives = db.get_all_drives()
    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Placement Tracker//Campus Drives//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Campus Placement Deadlines",
        "X-WR-TIMEZONE:Asia/Kolkata",
    ]

    for d in drives:
        deadline_str = d.get("deadline", "")
        dt = parse_deadline_datetime(deadline_str)
        if not dt:
            continue
        
        end_utc = dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        start_utc = (dt - timedelta(hours=1)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        
        company = d.get("company_name", "Company")
        role = d.get("role", "Software Role")
        apply_link = d.get("apply_link", "")
        ctc = d.get("ctc_or_stipend", "Not disclosed")
        drive_id = d.get("id")
        
        summary = f"Deadline: {company} Placement Registration"
        description = f"Company: {company}\\nRole: {role}\\nCTC: {ctc}\\nApply Link: {apply_link}\\nDeadline: {deadline_str}"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:placement-drive-{drive_id}@placementtracker",
            f"DTSTAMP:{now_utc}",
            f"DTSTART:{start_utc}",
            f"DTEND:{end_utc}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "LOCATION:Online",
            "STATUS:CONFIRMED",
            "BEGIN:VALARM",
            "TRIGGER:-PT2H",
            "ACTION:DISPLAY",
            "DESCRIPTION:Placement Registration Deadline Approaching!",
            "END:VALARM",
            "BEGIN:VALARM",
            "TRIGGER:-PT30M",
            "ACTION:DISPLAY",
            "DESCRIPTION:URGENT: Placement Form closes in 30 minutes!",
            "END:VALARM",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

@app.get("/api/calendar.ics")
def get_calendar_ics():
    """
    Live subscribable iCal / Webcal feed.
    When added to Google Calendar, any updated deadline or rescheduled drive
    automatically syncs and shifts the event to the new time!
    """
    content = generate_ical_feed()
    return Response(
        content=content,
        media_type="text/calendar",
        headers={"Content-Disposition": "inline; filename=placement_deadlines.ics"}
    )

@app.get("/api/drives")
def list_drives(status: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    drives = db.get_all_drives(status=status, search=search)
    profile = db.get_student_profile()
    
    # Enrich each drive with real-time eligibility evaluation
    for d in drives:
        d["eligibility"] = analyzer.evaluate_eligibility(profile, d.get("eligibility_criteria", ""))
        d["verifications"] = db.get_verifications_for_drive(d["id"])
    return drives

@app.get("/api/drives/{drive_id}")
def get_drive(drive_id: int):
    drive = db.get_drive_by_id(drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    profile = db.get_student_profile()
    drive["eligibility"] = analyzer.evaluate_eligibility(profile, drive.get("eligibility_criteria", ""))
    drive["verifications"] = db.get_verifications_for_drive(drive_id)
    drive["prep_pack"] = analyzer.get_or_generate_oa_prep_pack(drive.get("company_name", ""), drive.get("role"))
    return drive

@app.get("/api/drives/{drive_id}/prep-pack")
def get_prep_pack(drive_id: int):
    drive = db.get_drive_by_id(drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    return analyzer.get_or_generate_oa_prep_pack(drive.get("company_name", ""), drive.get("role"))

@app.patch("/api/drives/{drive_id}/status")
def update_status(drive_id: int, payload: StatusUpdateRequest):
    updates = {}
    if payload.status:
        updates["status"] = payload.status
    if payload.app_status:
        updates["app_status"] = payload.app_status
    
    if not updates:
        raise HTTPException(status_code=400, detail="No status updates provided")
        
    success = db.update_drive(drive_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Drive not found or could not be updated")
    return {"success": True, "updated": updates}

@app.post("/api/verify-file")
async def verify_file(
    file: UploadFile = File(...),
    drive_id: Optional[int] = Form(None),
    usn: Optional[str] = Form(None)
):
    """
    Uploads an Excel, CSV, or PDF file (e.g. Registered Students sheet or Shortlist).
    Scans for candidate USN and updates drive status.
    """
    safe_name = f"verify_{int(os.path.getmtime(db.DB_FILE))}_{file.filename.replace(' ', '_')}"
    saved_file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = analyzer.scan_file_for_candidate(
        file_path=saved_file_path,
        original_filename=file.filename,
        target_usn=usn,
        drive_id=drive_id
    )
    return result

@app.post("/api/webhook/incoming")
async def incoming_webhook(
    text: Optional[str] = Form(None),
    sender: Optional[str] = Form("WhatsApp"),
    file: Optional[UploadFile] = File(None)
):
    """
    Webhook endpoint called by whatsapp_listener.js or UI Simulator.
    Accepts message text and optional uploaded file (PDF / Word / Excel).
    """
    saved_file_path = None
    original_filename = None

    if file and file.filename:
        original_filename = file.filename
        safe_name = f"{int(os.path.getmtime(db.DB_FILE))}_{file.filename.replace(' ', '_')}" if os.path.exists(db.DB_FILE) else file.filename.replace(' ', '_')
        saved_file_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    # If the file is an Excel/spreadsheet or PDF and contains shortlist/registered keywords, also run verification scanner
    f_lower = (original_filename or "").lower()
    if saved_file_path and (f_lower.endswith(".xlsx") or f_lower.endswith(".csv") or ("shortlist" in f_lower or "registered" in f_lower)):
        # Run scanner
        scan_res = analyzer.scan_file_for_candidate(saved_file_path, original_filename)
        if scan_res.get("status") == "matched":
            print(f"[Server] Candidate matched in file: {scan_res.get('summary')}")

    if not text and not saved_file_path:
        raise HTTPException(status_code=400, detail="Either 'text' or 'file' must be provided.")

    result = analyzer.process_placement_message(
        message_text=text or "",
        file_path=saved_file_path,
        original_filename=original_filename
    )

    return result

# Static files for the web dashboard
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

@app.get("/")
def serve_dashboard():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Placement Tracker API is running."})

@app.get("/preview")
def serve_preview():
    preview_path = os.path.join(STATIC_DIR, "preview.html")
    if os.path.exists(preview_path):
        return FileResponse(preview_path)
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/mobile")
def serve_mobile():
    mobile_path = os.path.join(os.path.dirname(__file__), "android", "app", "src", "main", "assets", "index.html")
    if os.path.exists(mobile_path):
        return FileResponse(mobile_path)
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Placement Tracker on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
