package com.placementtracker.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONArray
import org.json.JSONObject

class DatabaseHelper(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {

    companion object {
        private const val DATABASE_NAME = "placement_tracker_mobile.db"
        private const val DATABASE_VERSION = 1

        const val TABLE_DRIVES = "drives"
        const val TABLE_UPDATES = "drive_updates"
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""
            CREATE TABLE IF NOT EXISTS $TABLE_DRIVES (
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
        """.trimIndent())

        db.execSQL("""
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
                grad_batch INTEGER DEFAULT 2027,
                resume_link TEXT,
                linkedin_url TEXT,
                github_url TEXT
            );
        """.trimIndent())

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drive_id INTEGER,
                filename TEXT,
                verification_type TEXT,
                is_matched INTEGER DEFAULT 0,
                matched_text TEXT,
                summary TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """.trimIndent())

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS $TABLE_UPDATES (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drive_id INTEGER NOT NULL,
                field_changed TEXT,
                old_value TEXT,
                new_value TEXT,
                change_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (drive_id) REFERENCES $TABLE_DRIVES(id) ON DELETE CASCADE
            );
        """.trimIndent())
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        try {
            db.execSQL("ALTER TABLE $TABLE_DRIVES ADD COLUMN app_status TEXT DEFAULT 'Announced'")
        } catch (e: Exception) {}
        onCreate(db)
    }

    fun insertDrive(data: JSONObject): Long {
        val db = writableDatabase
        val values = ContentValues().apply {
            put("company_name", data.optString("company_name", "Unknown"))
            put("role", data.optString("role", "Software / Tech Role"))
            put("job_type", data.optString("job_type", "Full-time"))
            put("ctc_or_stipend", data.optString("ctc_or_stipend", "Not disclosed"))
            put("eligibility_criteria", data.optString("eligibility_criteria", "Check announcement"))
            put("deadline", data.optString("deadline", "TBD"))
            put("drive_date", data.optString("drive_date", "TBD"))
            put("apply_link", data.optString("apply_link", ""))
            put("description", data.optString("description", ""))
            put("status", data.optString("status", "Upcoming"))
            put("raw_message", data.optString("raw_message", ""))
        }
        return db.insert(TABLE_DRIVES, null, values)
    }

    fun findDriveByCompany(companyName: String): JSONObject? {
        val cleaned = companyName.trim().lowercase()
        if (cleaned.length < 2) return null
        val db = readableDatabase
        val cursor = db.rawQuery(
            "SELECT * FROM $TABLE_DRIVES WHERE LOWER(company_name) = ? OR LOWER(company_name) LIKE ? ORDER BY id DESC LIMIT 1",
            arrayOf(cleaned, "%$cleaned%")
        )
        cursor.use {
            if (it.moveToFirst()) {
                val json = JSONObject()
                for (col in it.columnNames) {
                    json.put(col, it.getString(it.getColumnIndexOrThrow(col)))
                }
                return json
            }
        }
        return null
    }

    fun updateDrive(driveId: Long, updates: JSONObject): Boolean {
        val db = writableDatabase
        val values = ContentValues()
        val keys = updates.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            values.put(key, updates.getString(key))
        }
        values.put("updated_at", System.currentTimeMillis().toString())
        val count = db.update(TABLE_DRIVES, values, "id = ?", arrayOf(driveId.toString()))
        return count > 0
    }

    fun recordUpdate(driveId: Long, field: String, oldVal: String, newVal: String, summary: String): Long {
        val db = writableDatabase
        val values = ContentValues().apply {
            put("drive_id", driveId)
            put("field_changed", field)
            put("old_value", oldVal)
            put("new_value", newVal)
            put("change_summary", summary)
        }
        return db.insert(TABLE_UPDATES, null, values)
    }

    fun getAllDrives(status: String? = null, search: String? = null): JSONArray {
        val db = readableDatabase
        var query = "SELECT * FROM $TABLE_DRIVES WHERE 1=1"
        val args = mutableListOf<String>()

        if (!status.isNullOrEmpty() && !status.equals("all", ignoreCase = true)) {
            query += " AND status = ?"
            args.add(status)
        }
        if (!search.isNullOrEmpty()) {
            query += " AND (company_name LIKE ? OR role LIKE ? OR eligibility_criteria LIKE ?)"
            val term = "%$search%"
            args.add(term)
            args.add(term)
            args.add(term)
        }
        query += " ORDER BY id DESC"

        val cursor = db.rawQuery(query, args.toTypedArray())
        val array = JSONArray()
        cursor.use {
            while (it.moveToNext()) {
                val obj = JSONObject()
                for (col in it.columnNames) {
                    obj.put(col, it.getString(it.getColumnIndexOrThrow(col)))
                }
                array.put(obj)
            }
        }
        return array
    }

    fun getDriveById(id: Long): JSONObject? {
        val db = readableDatabase
        val cursor = db.rawQuery("SELECT * FROM $TABLE_DRIVES WHERE id = ?", arrayOf(id.toString()))
        cursor.use {
            if (it.moveToFirst()) {
                val obj = JSONObject()
                for (col in it.columnNames) {
                    obj.put(col, it.getString(it.getColumnIndexOrThrow(col)))
                }
                // Fetch updates
                val upCursor = db.rawQuery("SELECT * FROM $TABLE_UPDATES WHERE drive_id = ? ORDER BY id DESC", arrayOf(id.toString()))
                val updatesArr = JSONArray()
                upCursor.use { uc ->
                    while (uc.moveToNext()) {
                        val uObj = JSONObject()
                        for (col in uc.columnNames) {
                            uObj.put(col, uc.getString(uc.getColumnIndexOrThrow(col)))
                        }
                        updatesArr.put(uObj)
                    }
                }
                obj.put("updates", updatesArr)
                return obj
            }
        }
        return null
    }

    fun getStats(): JSONObject {
        val db = readableDatabase
        val total = db.compileStatement("SELECT COUNT(*) FROM $TABLE_DRIVES").simpleQueryForLong()
        val active = db.compileStatement("SELECT COUNT(*) FROM $TABLE_DRIVES WHERE status IN ('Upcoming', 'Ongoing')").simpleQueryForLong()
        val applied = db.compileStatement("SELECT COUNT(*) FROM $TABLE_DRIVES WHERE status = 'Applied'").simpleQueryForLong()
        val updates = db.compileStatement("SELECT COUNT(*) FROM $TABLE_UPDATES").simpleQueryForLong()

        return JSONObject().apply {
            put("total_drives", total)
            put("active_drives", active)
            put("applied_drives", applied)
            put("total_updates", updates)
        }
    }
}
