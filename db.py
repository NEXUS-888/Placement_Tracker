import sqlite3
import os
import contextlib
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(__file__), "placement_tracker.db")

@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS drives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            role TEXT,
            job_type TEXT DEFAULT 'Full-time',
            ctc_or_stipend TEXT,
            eligibility_criteria TEXT,
            deadline TEXT,
            drive_date TEXT,
            apply_link TEXT,
            description TEXT,
            status TEXT DEFAULT 'Upcoming',
            app_status TEXT DEFAULT 'Announced',
            raw_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS student_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            usn TEXT,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            branch TEXT,
            cgpa REAL DEFAULT 0.0,
            tenth_percentage REAL DEFAULT 0.0,
            twelfth_percentage REAL DEFAULT 0.0,
            active_backlogs INTEGER DEFAULT 0,
            history_backlogs INTEGER DEFAULT 0,
            grad_batch INTEGER DEFAULT 2027,
            resume_link TEXT,
            linkedin_url TEXT,
            github_url TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_id INTEGER,
            filename TEXT,
            verification_type TEXT,
            is_matched INTEGER DEFAULT 0,
            matched_text TEXT,
            summary TEXT,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS drive_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_id INTEGER NOT NULL,
            field_changed TEXT,
            old_value TEXT,
            new_value TEXT,
            change_summary TEXT,
            raw_update_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS drive_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_id INTEGER,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT,
            file_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (drive_id) REFERENCES drives(id) ON DELETE SET NULL
        );
        """)
        # Safe migration if table exists without app_status
        try:
            conn.execute("ALTER TABLE drives ADD COLUMN app_status TEXT DEFAULT 'Announced'")
        except Exception:
            pass

def insert_drive(data: Dict[str, Any]) -> int:
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO drives (
                company_name, role, job_type, ctc_or_stipend, eligibility_criteria,
                deadline, drive_date, apply_link, description, status, raw_message,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            data.get("company_name", "Unknown"),
            data.get("role", "Not specified"),
            data.get("job_type", "Full-time"),
            data.get("ctc_or_stipend", "Not disclosed"),
            data.get("eligibility_criteria", "Check details"),
            data.get("deadline", "TBD"),
            data.get("drive_date", "TBD"),
            data.get("apply_link", ""),
            data.get("description", ""),
            data.get("status", "Upcoming"),
            data.get("raw_message", "")
        ))
        return cursor.lastrowid

def update_drive(drive_id: int, updates: Dict[str, Any]) -> bool:
    if not updates:
        return False
    fields = []
    values = []
    for k, v in updates.items():
        if k in ("company_name", "role", "job_type", "ctc_or_stipend",
                 "eligibility_criteria", "deadline", "drive_date",
                 "apply_link", "description", "status", "app_status"):
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return False
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(drive_id)
    
    query = f"UPDATE drives SET {', '.join(fields)} WHERE id = ?"
    with get_db() as conn:
        cursor = conn.execute(query, values)
        return cursor.rowcount > 0

def record_update(drive_id: int, field_changed: str, old_value: str, new_value: str, change_summary: str, raw_update_message: str = "") -> int:
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO drive_updates (drive_id, field_changed, old_value, new_value, change_summary, raw_update_message)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (drive_id, field_changed, str(old_value or ""), str(new_value or ""), change_summary, raw_update_message))
        return cursor.lastrowid

def attach_file(drive_id: Optional[int], filename: str, file_path: str, file_type: str = "", file_size: int = 0) -> int:
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO drive_files (drive_id, filename, file_path, file_type, file_size)
            VALUES (?, ?, ?, ?, ?)
        """, (drive_id, filename, file_path, file_type, file_size))
        return cursor.lastrowid

def get_all_drives(status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM drives WHERE 1=1"
    params = []
    if status and status.lower() != 'all':
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (company_name LIKE ? OR role LIKE ? OR eligibility_criteria LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    query += " ORDER BY updated_at DESC"
    
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

def get_drive_by_id(drive_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM drives WHERE id = ?", (drive_id,)).fetchone()
        if not row:
            return None
        drive = dict(row)
        updates = conn.execute("SELECT * FROM drive_updates WHERE drive_id = ? ORDER BY created_at DESC", (drive_id,)).fetchall()
        files = conn.execute("SELECT * FROM drive_files WHERE drive_id = ?", (drive_id,)).fetchall()
        drive["updates"] = [dict(u) for u in updates]
        drive["files"] = [dict(f) for f in files]
        return drive

def find_drive_by_company(company_name: str) -> Optional[Dict[str, Any]]:
    cleaned = company_name.strip().lower()
    if not cleaned or len(cleaned) < 2:
        return None
    with get_db() as conn:
        # Exact match
        row = conn.execute("SELECT * FROM drives WHERE LOWER(company_name) = ? ORDER BY id DESC LIMIT 1", (cleaned,)).fetchone()
        if row:
            return dict(row)
        # Substring match
        row = conn.execute("SELECT * FROM drives WHERE LOWER(company_name) LIKE ? OR ? LIKE ('%' || LOWER(company_name) || '%') ORDER BY id DESC LIMIT 1", (f"%{cleaned}%", cleaned)).fetchone()
        if row:
            return dict(row)
    return None

def get_stats() -> Dict[str, Any]:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM drives").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM drives WHERE status IN ('Upcoming', 'Ongoing')").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM drives WHERE status = 'Applied'").fetchone()[0]
        updates_count = conn.execute("SELECT COUNT(*) FROM drive_updates").fetchone()[0]
        recent_updates = conn.execute("""
            SELECT u.*, d.company_name, d.role 
            FROM drive_updates u 
            JOIN drives d ON u.drive_id = d.id 
            ORDER BY u.created_at DESC LIMIT 5
        """).fetchall()
        return {
            "total_drives": total,
            "active_drives": active,
            "applied_drives": applied,
            "total_updates": updates_count,
            "recent_updates": [dict(r) for r in recent_updates]
        }

def get_student_profile() -> Dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM student_profile WHERE id = 1").fetchone()
        if row:
            return dict(row)
        # Default placeholder profile if not yet saved
        return {
            "id": 1,
            "usn": "",
            "full_name": "",
            "email": "",
            "phone": "",
            "branch": "CSE",
            "cgpa": 0.0,
            "tenth_percentage": 0.0,
            "twelfth_percentage": 0.0,
            "active_backlogs": 0,
            "history_backlogs": 0,
            "grad_batch": 2027,
            "resume_link": "",
            "linkedin_url": "",
            "github_url": ""
        }

def save_student_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    with get_db() as conn:
        conn.execute("""
            INSERT INTO student_profile (
                id, usn, full_name, email, phone, branch, cgpa,
                tenth_percentage, twelfth_percentage, active_backlogs,
                history_backlogs, grad_batch, resume_link, linkedin_url,
                github_url, updated_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                usn = excluded.usn,
                full_name = excluded.full_name,
                email = excluded.email,
                phone = excluded.phone,
                branch = excluded.branch,
                cgpa = excluded.cgpa,
                tenth_percentage = excluded.tenth_percentage,
                twelfth_percentage = excluded.twelfth_percentage,
                active_backlogs = excluded.active_backlogs,
                history_backlogs = excluded.history_backlogs,
                grad_batch = excluded.grad_batch,
                resume_link = excluded.resume_link,
                linkedin_url = excluded.linkedin_url,
                github_url = excluded.github_url,
                updated_at = CURRENT_TIMESTAMP
        """, (
            data.get("usn", "").strip(),
            data.get("full_name", "").strip(),
            data.get("email", "").strip(),
            data.get("phone", "").strip(),
            data.get("branch", "CSE").strip(),
            float(data.get("cgpa") or 0.0),
            float(data.get("tenth_percentage") or 0.0),
            float(data.get("twelfth_percentage") or 0.0),
            int(data.get("active_backlogs") or 0),
            int(data.get("history_backlogs") or 0),
            int(data.get("grad_batch") or 2027),
            data.get("resume_link", "").strip(),
            data.get("linkedin_url", "").strip(),
            data.get("github_url", "").strip()
        ))
    return get_student_profile()

def update_drive_app_status(drive_id: int, app_status: str) -> bool:
    with get_db() as conn:
        res = conn.execute("UPDATE drives SET app_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (app_status, drive_id))
        return res.rowcount > 0

def log_verification(
    drive_id: Optional[int],
    filename: str,
    verification_type: str,
    is_matched: bool,
    matched_text: str = "",
    summary: str = ""
) -> int:
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO verifications (
                drive_id, filename, verification_type, is_matched, matched_text, summary, scanned_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            drive_id,
            filename,
            verification_type,
            1 if is_matched else 0,
            matched_text,
            summary
        ))
        return cursor.lastrowid

def get_verifications_for_drive(drive_id: int) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM verifications WHERE drive_id = ? ORDER BY scanned_at DESC", (drive_id,)).fetchall()
        return [dict(r) for r in rows]

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_FILE)
