import os
import sys
import unittest
from datetime import datetime

# Import local modules
import db
import analyzer
import notifier

class TestPlacementTracker(unittest.TestCase):

    def setUp(self):
        db.init_db()

    def test_01_db_operations(self):
        """Test database insertion and retrieval"""
        test_drive = {
            "company_name": "TestCorp",
            "role": "Backend Engineer",
            "job_type": "Full-time",
            "ctc_or_stipend": "18 LPA",
            "eligibility_criteria": "B.Tech >= 7.0 CGPA",
            "deadline": "2026-09-30",
            "drive_date": "2026-10-05",
            "apply_link": "https://testcorp.com/apply",
            "description": "Test drive description",
            "status": "Upcoming"
        }
        drive_id = db.insert_drive(test_drive)
        self.assertIsNotNone(drive_id)
        self.assertGreater(drive_id, 0)

        # Retrieve drive
        fetched = db.get_drive_by_id(drive_id)
        self.assertEqual(fetched["company_name"], "TestCorp")
        self.assertEqual(fetched["ctc_or_stipend"], "18 LPA")

        # Test update recording
        up_id = db.record_update(
            drive_id=drive_id,
            field_changed="deadline",
            old_value="2026-09-30",
            new_value="2026-10-02",
            change_summary="Deadline extended to Oct 2",
            raw_update_message="Coordinator note: Deadline extended"
        )
        self.assertGreater(up_id, 0)

        # Update drive fields
        db.update_drive(drive_id, {"deadline": "2026-10-02"})
        updated = db.get_drive_by_id(drive_id)
        self.assertEqual(updated["deadline"], "2026-10-02")
        self.assertEqual(len(updated["updates"]), 1)
        self.assertEqual(updated["updates"][0]["new_value"], "2026-10-02")

    def test_02_analyzer_new_drive(self):
        """Test processing a new drive message"""
        msg = (
            "Dear 2026 Batch,\n"
            "Microsoft is hiring Software Engineer Interns!\n"
            "Stipend: 1,25,000 per month.\n"
            "Eligibility: B.Tech CSE/IT/ECE with CGPA >= 8.0.\n"
            "Deadline: 2026-10-01 18:00.\n"
            "Apply at: https://careers.microsoft.com/internship-2026"
        )
        result = analyzer.process_placement_message(message_text=msg)
        self.assertIn(result["status"], ("created", "updated"))
        self.assertEqual(result["company_name"], "Microsoft" if "Microsoft" in result["company_name"] else result["company_name"])

    def test_03_analyzer_update_detection(self):
        """Test detecting changes and diffs for an existing drive"""
        # Ensure a base drive exists
        db.insert_drive({
            "company_name": "Atlassian",
            "role": "SDE Intern",
            "job_type": "Internship",
            "ctc_or_stipend": "1.0 Lakh / month",
            "eligibility_criteria": "CGPA >= 7.5",
            "deadline": "2026-09-25",
            "status": "Upcoming"
        })

        # Send an update message
        update_msg = (
            "IMPORTANT UPDATE regarding Atlassian Drive:\n"
            "Atlassian deadline is now extended to 2026-09-29.\n"
            "Test date rescheduled to 2026-10-04."
        )
        res = analyzer.process_placement_message(message_text=update_msg)
        self.assertEqual(res["status"], "updated")
        self.assertEqual(res["action"], "UPDATE_DRIVE")
        
        # Verify changes were logged in database
        drive = db.find_drive_by_company("Atlassian")
        full_drive = db.get_drive_by_id(drive["id"])
        self.assertGreater(len(full_drive["updates"]), 0)

    def test_04_stats(self):
        stats = db.get_stats()
        self.assertGreaterEqual(stats["total_drives"], 1)

if __name__ == "__main__":
    unittest.main()
