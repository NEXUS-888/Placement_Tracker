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
    status: str

class IncomingMessageRequest(BaseModel):
    text: str
    sender: Optional[str] = "WhatsApp Coordinator"

@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "placement-tracker"}

@app.get("/api/stats")
def get_stats():
    return db.get_stats()

@app.get("/api/drives")
def list_drives(status: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    return db.get_all_drives(status=status, search=search)

@app.get("/api/drives/{drive_id}")
def get_drive(drive_id: int):
    drive = db.get_drive_by_id(drive_id)
    if not drive:
        raise HTTPException(status_code=404, detail="Drive not found")
    return drive

@app.patch("/api/drives/{drive_id}/status")
def update_status(drive_id: int, payload: StatusUpdateRequest):
    valid_statuses = ["Upcoming", "Applied", "Ongoing", "Shortlisted", "Rejected", "Closed"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of {valid_statuses}")
    
    success = db.update_drive(drive_id, {"status": payload.status})
    if not success:
        raise HTTPException(status_code=404, detail="Drive not found or could not be updated")
    return {"success": True, "new_status": payload.status}

@app.post("/api/webhook/incoming")
async def incoming_webhook(
    text: Optional[str] = Form(None),
    sender: Optional[str] = Form("WhatsApp"),
    file: Optional[UploadFile] = File(None)
):
    """
    Webhook endpoint called by whatsapp_listener.js or UI Simulator.
    Accepts message text and optional uploaded file (PDF / image).
    """
    saved_file_path = None
    original_filename = None

    if file and file.filename:
        original_filename = file.filename
        safe_name = f"{int(os.path.getmtime(db.DB_FILE))}_{file.filename.replace(' ', '_')}" if os.path.exists(db.DB_FILE) else file.filename.replace(' ', '_')
        saved_file_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

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
    return JSONResponse({"message": "Placement Tracker API is running. UI not found in static/index.html."})

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Placement Tracker on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)
