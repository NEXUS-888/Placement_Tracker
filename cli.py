import sys
import argparse
from datetime import datetime
import db

def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title.upper()}")
    print("=" * 60)

def cmd_status(args):
    stats = db.get_stats()
    print_header("Placement Tracker Overview")
    print(f"Total Drives Tracked : {stats['total_drives']}")
    print(f"Active Drives        : {stats['active_drives']}")
    print(f"Applied Drives       : {stats['applied_drives']}")
    print(f"Updates Logged       : {stats['total_updates']}")
    
    if stats['recent_updates']:
        print("\n--- Recent Coordinator Updates ---")
        for u in stats['recent_updates']:
            print(f"* [{u['company_name']}] {u['change_summary']} (at {u['created_at']})")
    print()

def cmd_list(args):
    drives = db.get_all_drives(status=args.status, search=args.search)
    print_header(f"Placement Drives ({len(drives)} found)")
    if not drives:
        print("No drives found matching criteria.\n")
        return

    for d in drives:
        print(f"#{d['id']:<3} | {d['company_name']:<20} | {d['role']:<25} | Status: {d['status']}")
        print(f"     Package: {d['ctc_or_stipend']} | Deadline: {d['deadline']}")
        if d['apply_link']:
            print(f"     Apply: {d['apply_link']}")
        print("-" * 60)
    print()

def cmd_deadlines(args):
    drives = db.get_all_drives()
    active = [d for d in drives if d['status'] in ('Upcoming', 'Ongoing')]
    print_header(f"Upcoming Active Deadlines ({len(active)})")
    for d in active:
        print(f"* {d['company_name']} ({d['role']})")
        print(f"  Deadline : {d['deadline']}")
        print(f"  Drive Date: {d['drive_date']}")
        print(f"  Apply    : {d['apply_link'] or 'No link provided'}")
        print()

def cmd_inspect(args):
    # Search by ID or company name
    identifier = args.query.strip()
    drive = None
    if identifier.isdigit():
        drive = db.get_drive_by_id(int(identifier))
    if not drive:
        drive = db.find_drive_by_company(identifier)
        if drive:
            drive = db.get_drive_by_id(drive['id'])

    if not drive:
        print(f"No drive found matching '{identifier}'.")
        return

    print_header(f"Drive Details: {drive['company_name']}")
    print(f"ID          : {drive['id']}")
    print(f"Company     : {drive['company_name']}")
    print(f"Role        : {drive['role']} ({drive['job_type']})")
    print(f"Package/CTC : {drive['ctc_or_stipend']}")
    print(f"Eligibility : {drive['eligibility_criteria']}")
    print(f"Deadline    : {drive['deadline']}")
    print(f"Drive Date  : {drive['drive_date']}")
    print(f"Apply Link  : {drive['apply_link']}")
    print(f"Status      : {drive['status']}")
    print(f"Created At  : {drive['created_at']}")
    print(f"Updated At  : {drive['updated_at']}")
    
    if drive.get("updates"):
        print("\n--- Change & Update History ---")
        for u in drive["updates"]:
            old_str = f" (was: {u['old_value']})" if u['old_value'] else ""
            print(f"[{u['created_at']}] {u['change_summary']}{old_str}")

    if drive.get("files"):
        print("\n--- Attached Files / Documents ---")
        for f in drive["files"]:
            print(f"* {f['filename']} ({f['file_path']})")
    print()

def cmd_set_status(args):
    drive_id = args.id
    status = args.status
    success = db.update_drive(drive_id, {"status": status})
    if success:
        print(f"Drive #{drive_id} status updated to '{status}'.")
    else:
        print(f"Failed to update drive #{drive_id}.")

def main():
    parser = argparse.ArgumentParser(description="Placement Tracker CLI (for User & Antigravity Agent)")
    subparsers = parser.add_subparsers(dest="command")

    # status
    p_status = subparsers.add_parser("status", help="Show system summary & metrics")
    p_status.set_defaults(func=cmd_status)

    # list
    p_list = subparsers.add_parser("list", help="List drives")
    p_list.add_argument("--status", choices=["Upcoming", "Applied", "Ongoing", "Shortlisted", "Rejected", "Closed", "all"], default="all")
    p_list.add_argument("--search", type=str, default="")
    p_list.set_defaults(func=cmd_list)

    # deadlines
    p_deadlines = subparsers.add_parser("deadlines", help="Show upcoming deadlines")
    p_deadlines.set_defaults(func=cmd_deadlines)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect drive by ID or Company name")
    p_inspect.add_argument("query", type=str, help="Drive ID or Company Name")
    p_inspect.set_defaults(func=cmd_inspect)

    # set-status
    p_status_set = subparsers.add_parser("set-status", help="Update drive status")
    p_status_set.add_argument("id", type=int, help="Drive ID")
    p_status_set.add_argument("status", choices=["Upcoming", "Applied", "Ongoing", "Shortlisted", "Rejected", "Closed"])
    p_status_set.set_defaults(func=cmd_set_status)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_status(args)

if __name__ == "__main__":
    main()
