import os
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

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
