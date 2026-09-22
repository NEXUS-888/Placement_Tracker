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

def extract_text_and_links_from_docx(docx_path: str) -> str:
    """Extracts text content and all embedded hyperlinks from a Word .docx file."""
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(docx_path) as docx:
            # 1. Read relationships to extract embedded hyperlinks
            rels = {}
            if 'word/_rels/document.xml.rels' in docx.namelist():
                rels_xml = docx.read('word/_rels/document.xml.rels')
                rels_tree = ET.fromstring(rels_xml)
                for rel in rels_tree:
                    if 'Hyperlink' in rel.attrib.get('Type', ''):
                        rels[rel.attrib.get('Id')] = rel.attrib.get('Target', '')

            # 2. Read document XML paragraphs and tables
            xml_content = docx.read('word/document.xml')
            tree = ET.fromstring(xml_content)

            full_text = []
            for p in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                p_texts = []
                for elem in p.iter():
                    if elem.tag.endswith('hyperlink'):
                        r_id = elem.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                        if r_id in rels:
                            p_texts.append(f" [Link: {rels[r_id]}] ")
                    elif elem.tag.endswith('t') and elem.text:
                        p_texts.append(elem.text)
                if p_texts:
                    full_text.append(''.join(p_texts))

            # Also extract from tables
            for table in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl'):
                for row in table.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tr'):
                    row_texts = []
                    for cell in row.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc'):
                        cell_text = ''.join(cell.itertext()).strip()
                        if cell_text:
                            row_texts.append(cell_text)
                    if row_texts:
                        full_text.append(' | '.join(row_texts))

            return '\n'.join(full_text)
    except Exception as e:
        print(f"[Analyzer] Error extracting Word document {docx_path}: {e}")
        return ""

def call_gemini(prompt: str, content_text: str) -> Optional[Dict[str, Any]]:
    """Calls Gemini 1.5 Flash REST API with structured prompt and returns parsed JSON."""
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
    if not api_key:
        print("[Analyzer] No GEMINI_API_KEY configured. Falling back to local heuristic extraction.")
        return None

    models_to_try = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]
    
    system_instruction = """
You are an expert College Placement Drive and Internship Information Extractor.
Extract structured placement data from the provided message/document.
You must respond with ONLY valid JSON, enclosed in no other markdown except ```json ... ``` or raw JSON.

Schema:
{
  "is_placement_related": true/false,
  "message_type": "NEW_DRIVE" | "UPDATE_DRIVE" | "GENERAL_ANNOUNCEMENT",
  "company_name": "Name of Company (e.g. Besant Technologies)",
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
                    {"text": f"{system_instruction}\n\nContext & Message to analyze:\n{content_text[:8000]}"}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1
        }
    }

    data_bytes = json.dumps(payload).encode("utf-8")

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as response:
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
            continue

    print("[Analyzer] All Gemini models busy/unreachable. Using local circular heuristic extractor.")
    return None

def heuristic_fallback_extract(text: str, filename: Optional[str] = None) -> Dict[str, Any]:
    """Lightweight regex/keyword extraction for placement circulars and Word docs."""
    # 1. Registration links: Prioritize forms (forms.gle, google docs, typeform) over institution domains
    all_urls = re.findall(r'https?://[^\s<>"\')]+', text)
    form_urls = [u for u in all_urls if any(k in u.lower() for k in ("forms.gle", "forms.office", "docs.google.com", "form", "register", "apply"))]
    apply_link = form_urls[0] if form_urls else (all_urls[0] if all_urls else "")

    is_update = bool(re.search(r'\b(update|postponed|rescheduled|extended|revised|amendment|date changed)\b', text, re.I))

    # 2. Company Name
    company = None
    all_drives = db.get_all_drives()
    for d in all_drives:
        c_name = d.get("company_name", "")
        if c_name and len(c_name) > 2 and re.search(r'\b' + re.escape(c_name) + r'\b', text, re.I):
            company = c_name
            break

    # If not found in DB, check filename (e.g. DBIT-T&P-2027-032-Besant Technologies.docx)
    if not company and filename:
        name_no_ext = re.sub(r'\.(docx?|pdf)$', '', filename, flags=re.I)
        parts = [p.strip() for p in re.split(r'[-_]', name_no_ext) if p.strip()]
        for part in reversed(parts):
            if not re.search(r'^(dbit|t&p|batch|\d+|placement|drive)$', part, re.I) and len(part) > 2:
                company = part
                break

    # Check "Greetings from <Company>"
    if not company:
        m_greet = re.search(r'Greetings from\s+([A-Z][A-Za-z0-9\s&]{2,30})[\.,\n\r]', text)
        if m_greet:
            company = m_greet.group(1).strip()

    # Check "Who We Are:\s*<Company>"
    if not company:
        m_who = re.search(r'Who We Are:\s*([A-Z][A-Za-z0-9\s&]{2,30})', text)
        if m_who:
            company = m_who.group(1).strip()

    # Regex candidates
    if not company:
        p1 = re.search(r'(?:company|firm|org)[\s:]+([A-Z][A-Za-z0-9\s&]{1,20})', text, re.I)
        p2 = re.search(r'([A-Z][A-Za-z0-9&]{1,20})\s+(?:is hiring|campus drive|recruitment|drive)', text, re.I)
        p3 = re.search(r'(?:hiring|drive|recruitment|campus|from|regarding|for)\s+([A-Z][A-Za-z0-9\s&]{2,25})', text, re.I)
        
        candidates = [m.group(1).strip() for m in (p1, p2, p3) if m]
        blacklist = {"software", "software engineer", "dear students", "students", "batch", "interns", "engineers", "recruitment", "campus", "drive", "eligibility", "b.tech", "all", "attention students", "training & placement", "placement officer", "upcoming"}
        
        for cand in candidates:
            if cand.lower() not in blacklist and not cand.lower().startswith("software") and not cand.lower().startswith("student") and not cand.lower().startswith("training"):
                company = cand
                break

    if not company:
        company = "Company Mentioned"

    # 3. CTC / Stipend / Terms
    ctc_match = re.search(r'(\b\d+(?:\.\d+)?\s*(?:LPA|L|lakhs?|k|pm|per month)\b)', text, re.I)
    ctc = ctc_match.group(1) if ctc_match else ("Unpaid Training + Direct Deployment" if "unpaid" in text.lower() else "Not disclosed")

    # 4. Eligibility / Streams / Batch
    elig_parts = []
    m_streams = re.search(r'Streams:\s*([^\n\r]+)', text, re.I)
    m_batch = re.search(r'Batch:\s*([^\n\r]+)', text, re.I)
    cgpa_match = re.search(r'(?:cgpa|cutoff|criteria)[\s:]*([0-9\.]+)', text, re.I)

    if m_streams: elig_parts.append(f"Streams: {m_streams.group(1).strip()}")
    if m_batch: elig_parts.append(f"Batch: {m_batch.group(1).strip()}")
    if cgpa_match: elig_parts.append(f"CGPA: {cgpa_match.group(1)}")
    eligibility = " | ".join(elig_parts) if elig_parts else "Refer document details"

    # 5. Deadline heuristic
    m_dl = re.search(r'(?:deadline|last date|register by|submit your response:?)\s*(?:before)?[\s:]*([^\n\r]+)', text, re.I)
    deadline = m_dl.group(1).strip() if m_dl else "Check announcement text"

    return {
        "is_placement_related": True,
        "message_type": "UPDATE_DRIVE" if is_update else "NEW_DRIVE",
        "company_name": company,
        "role": "Campus Recruitment / Training & Deployment",
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
    if file_path:
        f_lower = file_path.lower()
        if f_lower.endswith(".pdf"):
            pdf_text = extract_text_from_pdf(file_path)
            if pdf_text:
                full_content += f"\n\n[Attached PDF Content - {original_filename or 'Document'}]:\n{pdf_text[:12000]}"
        elif f_lower.endswith(".docx") or f_lower.endswith(".doc"):
            docx_text = extract_text_and_links_from_docx(file_path)
            if docx_text:
                full_content += f"\n\n[Attached Word Document - {original_filename or 'Document'}]:\n{docx_text[:12000]}"

    if not full_content.strip():
        return {"status": "ignored", "reason": "Empty content"}

    analysis = call_gemini("", full_content)
    if not analysis:
        analysis = heuristic_fallback_extract(full_content, original_filename)

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
