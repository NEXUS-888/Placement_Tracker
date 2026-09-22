import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

def send_discord_notification(payload: Dict[str, Any]) -> bool:
    """Sends a raw payload to the configured Discord Webhook."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", DISCORD_WEBHOOK_URL).strip()
    if not webhook_url:
        print("[Notifier] No DISCORD_WEBHOOK_URL configured. Notification skipped.")
        return False

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PlacementTrackerBot/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 204)
    except urllib.error.HTTPError as e:
        print(f"[Notifier] Discord HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
        return False
    except Exception as e:
        print(f"[Notifier] Error sending Discord notification: {e}")
        return False

def notify_new_drive(drive: Dict[str, Any]) -> bool:
    """Dispatches a rich green embed notification for a newly announced drive."""
    company = drive.get("company_name", "Unknown Company")
    role = drive.get("role", "N/A")
    job_type = drive.get("job_type", "Full-time")
    ctc = drive.get("ctc_or_stipend", "Not disclosed")
    eligibility = drive.get("eligibility_criteria", "Check link / attachment")
    deadline = drive.get("deadline", "TBD")
    drive_date = drive.get("drive_date", "TBD")
    apply_link = drive.get("apply_link", "")

    description = f"**{company}** announced a new **{job_type}** opportunity for **{role}**."

    fields = [
        {"name": "💰 Package / CTC", "value": ctc or "Not disclosed", "inline": True},
        {"name": "⏳ Deadline", "value": deadline or "TBD", "inline": True},
        {"name": "📅 Drive Date", "value": drive_date or "TBD", "inline": True},
        {"name": "🎯 Eligibility", "value": eligibility[:500] or "See attachment", "inline": False},
    ]

    if apply_link:
        fields.append({"name": "🔗 Application Link", "value": f"[Click here to Apply]({apply_link})", "inline": False})

    payload = {
        "username": "Placement Tracker",
        "avatar_url": "https://img.icons8.com/fluency/96/briefcase.png",
        "embeds": [{
            "title": f"🚀 NEW DRIVE: {company} - {role}",
            "description": description,
            "color": 3066993,  # Emerald Green (#2ecc71)
            "fields": fields,
            "footer": {"text": "Placement Tracker • Automated Ingestion"}
        }]
    }
    return send_discord_notification(payload)

def notify_drive_update(company_name: str, role: str, changes: list, summary: str) -> bool:
    """Dispatches a yellow embed notification when placement details are modified."""
    fields = []
    for change in changes:
        field_name = change.get("field", "Detail").replace("_", " ").title()
        old_val = change.get("old_value", "N/A")
        new_val = change.get("new_value", "N/A")
        fields.append({
            "name": f"🔄 {field_name} Changed",
            "value": f"~~{old_val}~~ ➔ **{new_val}**",
            "inline": False
        })

    if not fields:
        fields.append({"name": "Details", "value": summary or "Details updated.", "inline": False})

    payload = {
        "username": "Placement Tracker",
        "avatar_url": "https://img.icons8.com/fluency/96/briefcase.png",
        "embeds": [{
            "title": f"⚠️ UPDATE / AMENDMENT: {company_name}",
            "description": f"Placement coordinator posted an update regarding **{company_name}** ({role or 'Drive'}).\n\n**Summary:** {summary}",
            "color": 16763904,  # Amber Yellow (#f1c40f)
            "fields": fields,
            "footer": {"text": "Placement Tracker • Change Detection"}
        }]
    }
    return send_discord_notification(payload)

def notify_general_announcement(title: str, message: str) -> bool:
    """Dispatches general placement notice / schedule announcement."""
    payload = {
        "username": "Placement Tracker",
        "avatar_url": "https://img.icons8.com/fluency/96/briefcase.png",
        "embeds": [{
            "title": f"📢 {title}",
            "description": message[:2000],
            "color": 3447003,  # Blue (#3498db)
            "footer": {"text": "Placement Tracker • Notice"}
        }]
    }
    return send_discord_notification(payload)

if __name__ == "__main__":
    test_drive = {
        "company_name": "Google",
        "role": "Software Engineer Intern",
        "job_type": "Internship",
        "ctc_or_stipend": "1.2 Lakh / month",
        "eligibility_criteria": "B.Tech CSE/IT/ECE with >= 7.5 CGPA, 2026 Batch",
        "deadline": "2026-09-28 23:59 IST",
        "drive_date": "2026-10-05",
        "apply_link": "https://careers.google.com/jobs"
    }
    print("Testing Discord notification (Make sure DISCORD_WEBHOOK_URL is set in .env)")
    res = notify_new_drive(test_drive)
    print("Sent:", res)
