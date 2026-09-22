import os
import re
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

import db
import notifier

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts text content from a PDF file."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text_parts = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        print(f"[Analyzer] Error extracting PDF {pdf_path}: {e}")
        return ""

def call_gemini(prompt: str, content_text: str) -> Optional[Dict[str, Any]]:
    """Calls Gemini 1.5 Flash REST API with structured prompt and returns parsed JSON."""
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
    if not api_key:
        print("[Analyzer] No GEMINI_API_KEY configured. Falling back to local heuristic extraction.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    system_instruction = """
You are an expert College Placement Drive and Internship Information Extractor.
Extract structured placement data from the provided message/document.
You must respond with ONLY valid JSON, enclosed in no other markdown except ```json ... ``` or raw JSON.

Schema:
{
  "is_placement_related": true/false,
  "message_type": "NEW_DRIVE" | "UPDATE_DRIVE" | "GENERAL_ANNOUNCEMENT",
  "company_name": "Name of Company or 'Unknown'",
  "role": "Job Role / Designation",
  "job_type": "Full-time" | "Internship" | "Both",
  "ctc_or_stipend": "Stipend or CTC package details (e.g. 14 LPA, 40k/month)",
  "eligibility_criteria": "Branch, CGPA cutoff, batch, backlogs",
  "deadline": "Registration deadline date & time if mentioned",
  "drive_date": "Date of online test/interview if mentioned",
  "apply_link": "URL to apply / Google Form link",
  "description": "Brief 2-line summary of the drive",
  "change_summary": "If this is an update or date change, explain clearly what was changed",
  "changed_fields": [
     {"field": "deadline|drive_date|eligibility|ctc|other", "old_value": "old value if known or N/A", "new_value": "new value", "summary": "description of change"}
  ]
}
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_instruction}\n\nContext & Message to analyze:\n{content_text}"}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            candidate = res_json.get("candidates", [{}])[0]
            part = candidate.get("content", {}).get("parts", [{}])[0]
            raw_text = part.get("text", "{}").strip()
            
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
                
            return json.loads(raw_text.strip())
    except Exception as e:
        print(f"[Analyzer] Gemini API call failed: {e}")
        return None

def heuristic_fallback_extract(text: str) -> Dict[str, Any]:
    """Lightweight regex/keyword extraction if Gemini key is not set or offline."""
    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', text)
    apply_link = urls[0] if urls else ""

    is_update = bool(re.search(r'\b(update|postponed|rescheduled|extended|revised|amendment|date changed)\b', text, re.I))

    # Match against existing companies in DB first
    company = None
    all_drives = db.get_all_drives()
    for d in all_drives:
        c_name = d.get("company_name", "")
        if c_name and len(c_name) > 2 and re.search(r'\b' + re.escape(c_name) + r'\b', text, re.I):
            company = c_name
            break

    # If not found in DB, search with regex
    if not company:
        p1 = re.search(r'(?:company|firm|org)[\s:]+([A-Z][A-Za-z0-9\s&]{1,20})', text, re.I)
        p2 = re.search(r'([A-Z][A-Za-z0-9&]{1,20})\s+(?:is hiring|campus drive|recruitment|drive)', text, re.I)
        p3 = re.search(r'(?:hiring|drive|recruitment|campus|from|regarding|for)\s+([A-Z][A-Za-z0-9\s&]{2,25})', text, re.I)
        
        candidates = [m.group(1).strip() for m in (p1, p2, p3) if m]
        blacklist = {"software", "software engineer", "dear students", "students", "batch", "interns", "engineers", "recruitment", "campus", "drive", "eligibility", "b.tech", "all", "attention students"}
        
        for cand in candidates:
            if cand.lower() not in blacklist and not cand.lower().startswith("software") and not cand.lower().startswith("student"):
                company = cand
                break
        if not company:
            company = "Company Mentioned"

    ctc_match = re.search(r'(\b\d+(?:\.\d+)?\s*(?:LPA|L|lakhs?|k|pm|per month)\b)', text, re.I)
    ctc = ctc_match.group(1) if ctc_match else "Not disclosed"

    cgpa_match = re.search(r'(?:cgpa|cutoff|criteria)[\s:]*([0-9\.]+)', text, re.I)
    eligibility = f"CGPA: {cgpa_match.group(1)}" if cgpa_match else "Refer message details"

    # Deadline heuristic
    deadline_match = re.search(r'(?:deadline|extended to|last date|register by)[\s:]*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+[0-9]{4})?(?:\s+[0-9]{1,2}:[0-9]{2}\s*(?:AM|PM)?)?)', text, re.I)
    deadline = deadline_match.group(1).strip() if deadline_match else "Check announcement text"

    return {
        "is_placement_related": True,
        "message_type": "UPDATE_DRIVE" if is_update else "NEW_DRIVE",
        "company_name": company,
        "role": "Software / Tech Role",
        "job_type": "Full-time",
        "ctc_or_stipend": ctc,
        "eligibility_criteria": eligibility,
        "deadline": deadline,
        "drive_date": "TBD",
        "apply_link": apply_link,
        "description": text[:200] + "..." if len(text) > 200 else text,
        "change_summary": f"Schedule or details updated for {company}" if is_update else "",
        "changed_fields": [{"field": "deadline", "old_value": "Previous", "new_value": deadline, "summary": f"Deadline set to {deadline}"}] if (is_update and deadline != "Check announcement text") else []
    }

def process_placement_message(
    message_text: str,
    file_path: Optional[str] = None,
    original_filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main processing pipeline:
    1. Extracts text from message and optional PDF.
    2. Runs Gemini (or fallback heuristic).
    3. Detects if it's a new drive or an update to an existing drive.
    4. Updates SQLite database.
    5. Fires Discord notification.
    """
    full_content = message_text or ""
    if file_path and file_path.lower().endswith(".pdf"):
        pdf_text = extract_text_from_pdf(file_path)
        if pdf_text:
            full_content += f"\n\n[Attached PDF Content - {original_filename or 'Document'}]:\n{pdf_text[:10000]}"

    if not full_content.strip():
        return {"status": "ignored", "reason": "Empty content"}

    analysis = call_gemini("", full_content)
    if not analysis:
        analysis = heuristic_fallback_extract(full_content)

    if not analysis.get("is_placement_related", True):
        return {"status": "ignored", "reason": "Not placement related"}

    company_name = (analysis.get("company_name") or "Unknown").strip()
    msg_type = analysis.get("message_type", "NEW_DRIVE")
    
    # Check if this company already exists in our database
    existing_drive = db.find_drive_by_company(company_name) if company_name != "Unknown" else None

    # If it's an update OR an existing drive was matched
    if existing_drive and (msg_type == "UPDATE_DRIVE" or existing_drive):
        drive_id = existing_drive["id"]
        changes = []
        updates_to_apply = {}

        field_mappings = [
            ("deadline", "deadline"),
            ("drive_date", "drive_date"),
            ("ctc_or_stipend", "ctc_or_stipend"),
            ("eligibility_criteria", "eligibility_criteria"),
            ("apply_link", "apply_link"),
            ("role", "role")
        ]

        for field_key, db_col in field_mappings:
            new_val = analysis.get(field_key)
            old_val = existing_drive.get(db_col)
            ignored_tokens = {"tbd", "not disclosed", "check details", "check announcement text", "not mentioned", "unknown", "n/a", "none", ""}
            if new_val and str(new_val).strip().lower() not in ignored_tokens:
                if old_val and old_val != new_val and str(old_val).strip().lower() not in ignored_tokens:
                    changes.append({
                        "field": field_key,
                        "old_value": old_val,
                        "new_value": new_val,
                        "summary": f"{field_key.replace('_', ' ').title()} updated"
                    })
                    updates_to_apply[db_col] = new_val
                elif not old_val or str(old_val).strip().lower() in ignored_tokens:
                    updates_to_apply[db_col] = new_val

        if analysis.get("changed_fields"):
            for cf in analysis["changed_fields"]:
                if cf not in changes:
                    changes.append(cf)

        summary = analysis.get("change_summary") or f"Update posted for {company_name}"
        
        if changes:
            for ch in changes:
                db.record_update(
                    drive_id=drive_id,
                    field_changed=ch.get("field", "general"),
                    old_value=ch.get("old_value", ""),
                    new_value=ch.get("new_value", ""),
                    change_summary=ch.get("summary", summary),
                    raw_update_message=message_text
                )
        else:
            db.record_update(
                drive_id=drive_id,
                field_changed="announcement",
                old_value="",
                new_value="",
                change_summary=summary,
                raw_update_message=message_text
            )

        if updates_to_apply:
            db.update_drive(drive_id, updates_to_apply)

        if file_path:
            db.attach_file(drive_id, original_filename or os.path.basename(file_path), file_path, "pdf" if file_path.endswith(".pdf") else "attachment")

        notifier.notify_drive_update(
            company_name=company_name,
            role=existing_drive.get("role", ""),
            changes=changes,
            summary=summary
        )

        return {
            "status": "updated",
            "action": "UPDATE_DRIVE",
            "drive_id": drive_id,
            "company_name": company_name,
            "changes": changes,
            "summary": summary
        }

    else:
        drive_data = {
            "company_name": company_name,
            "role": analysis.get("role") or "Software Engineer",
            "job_type": analysis.get("job_type") or "Full-time",
            "ctc_or_stipend": analysis.get("ctc_or_stipend") or "Not disclosed",
            "eligibility_criteria": analysis.get("eligibility_criteria") or "Check notification",
            "deadline": analysis.get("deadline") or "TBD",
            "drive_date": analysis.get("drive_date") or "TBD",
            "apply_link": analysis.get("apply_link") or "",
            "description": analysis.get("description") or message_text[:300],
            "status": "Upcoming",
            "raw_message": message_text
        }

        drive_id = db.insert_drive(drive_data)
        drive_data["id"] = drive_id

        if file_path:
            db.attach_file(drive_id, original_filename or os.path.basename(file_path), file_path, "pdf" if file_path.endswith(".pdf") else "attachment")

        notifier.notify_new_drive(drive_data)

        return {
            "status": "created",
            "action": "NEW_DRIVE",
            "drive_id": drive_id,
            "company_name": company_name,
            "drive_data": drive_data
        }
