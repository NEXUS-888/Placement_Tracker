package com.placementtracker.app

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.regex.Pattern

object PlacementAnalyzer {

    suspend fun analyzeAndProcess(context: Context, rawText: String): JSONObject = withContext(Dispatchers.IO) {
        val db = DatabaseHelper(context)

        // 1. Fast keyword check: is this placement related?
        val placementRegex = "(?i)\\b(placement|internship|hiring|campus drive|recruitment|stipend|ctc|lpa|cgpa|deadline|rescheduled|postponed|drive date)\\b"
        if (!Pattern.compile(placementRegex).matcher(rawText).find()) {
            return@withContext JSONObject().put("status", "ignored").put("reason", "Not placement related")
        }

        // 2. Try Gemini Flash API (takes 0% phone CPU, zero phone heating)
        val apiKey = context.getSharedPreferences("placement_prefs", Context.MODE_PRIVATE)
            .getString("gemini_api_key", "") ?: ""

        var analysis = if (apiKey.isNotEmpty()) callGeminiFlash(apiKey, rawText) else null

        // 3. Fallback to local heuristic regex if offline
        if (analysis == null) {
            analysis = localHeuristicExtract(context, rawText)
        }

        val companyName = analysis.optString("company_name", "Unknown").trim()
        val msgType = analysis.optString("message_type", "NEW_DRIVE")

        // Check if student's USN is in this message
        val profileJsonStr = context.getSharedPreferences("placement_prefs", Context.MODE_PRIVATE)
            .getString("student_profile_json", "{}") ?: "{}"
        val profileObj = try { JSONObject(profileJsonStr) } catch (e: Exception) { JSONObject() }
        val myUsn = profileObj.optString("usn", "").trim().uppercase()

        if (myUsn.isNotEmpty() && rawText.uppercase().contains(myUsn)) {
            if (rawText.contains("shortlist", ignoreCase = true) || rawText.contains("round", ignoreCase = true) || rawText.contains("select", ignoreCase = true)) {
                PlacementNotifier.showShortlistNotification(context, companyName, "Your USN $myUsn was found in the Shortlist announcement!", rawText.take(300))
            } else if (rawText.contains("register", ignoreCase = true) || rawText.contains("submission", ignoreCase = true)) {
                PlacementNotifier.showRegistrationConfirmedNotification(context, companyName, "Your USN $myUsn was found in the confirmed registrations list!")
            }
        }

        // 4. Match against existing drives in phone SQLite database
        val existingDrive = if (companyName != "Unknown" && companyName.isNotEmpty()) {
            db.findDriveByCompany(companyName)
        } else null

        if (existingDrive != null) {
            // It's an UPDATE / MODIFICATION to an existing drive
            val driveId = existingDrive.getLong("id")
            val updatesToApply = JSONObject()
            val diffs = StringBuilder()

            val fieldKeys = arrayOf("deadline", "drive_date", "ctc_or_stipend", "eligibility_criteria", "apply_link", "role")
            val ignoredTokens = setOf("tbd", "not disclosed", "check details", "not mentioned", "unknown", "n/a", "none", "")

            for (field in fieldKeys) {
                val newVal = analysis.optString(field, "")
                val oldVal = existingDrive.optString(field, "")

                if (newVal.isNotEmpty() && !ignoredTokens.contains(newVal.trim().lowercase())) {
                    if (oldVal.isNotEmpty() && !ignoredTokens.contains(oldVal.trim().lowercase()) && oldVal != newVal) {
                        updatesToApply.put(field, newVal)
                        db.recordUpdate(driveId, field, oldVal, newVal, "${field.replace('_', ' ').capitalize()} updated")
                        diffs.append("• ${field.replace('_', ' ').capitalize()}: $oldVal ➔ $newVal\n")
                    } else if (oldVal.isEmpty() || ignoredTokens.contains(oldVal.trim().lowercase())) {
                        updatesToApply.put(field, newVal)
                    }
                }
            }

            val summary = analysis.optString("change_summary", "Update posted for $companyName")
            if (updatesToApply.length() > 0) {
                db.updateDrive(driveId, updatesToApply)
            } else {
                db.recordUpdate(driveId, "announcement", "", "", summary)
            }

            // Trigger on-device alert
            PlacementNotifier.showUpdateNotification(context, companyName, summary, diffs.toString())

            return@withContext JSONObject().apply {
                put("status", "updated")
                put("action", "UPDATE_DRIVE")
                put("company_name", companyName)
                put("summary", summary)
            }
        } else {
            // It's a BRAND NEW placement drive
            val driveData = JSONObject().apply {
                put("company_name", companyName)
                put("role", analysis.optString("role", "Software / Tech Role"))
                put("job_type", analysis.optString("job_type", "Full-time"))
                put("ctc_or_stipend", analysis.optString("ctc_or_stipend", "Not disclosed"))
                put("eligibility_criteria", analysis.optString("eligibility_criteria", "Refer announcement"))
                put("deadline", analysis.optString("deadline", "TBD"))
                put("drive_date", analysis.optString("drive_date", "TBD"))
                put("apply_link", analysis.optString("apply_link", ""))
                put("description", analysis.optString("description", rawText.take(200)))
                put("status", "Upcoming")
                put("raw_message", rawText)
            }

            val driveId = db.insertDrive(driveData)
            driveData.put("id", driveId)

            // Trigger on-device alert
            PlacementNotifier.showNewDriveNotification(context, driveData)

            return@withContext JSONObject().apply {
                put("status", "created")
                put("action", "NEW_DRIVE")
                put("company_name", companyName)
                put("drive", driveData)
            }
        }
    }

    private fun callGeminiFlash(apiKey: String, text: String): JSONObject? {
        if (apiKey.isEmpty()) return null
        return try {
            val endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key=$apiKey"
            val url = URL(endpoint)
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.connectTimeout = 10000
            conn.readTimeout = 15000
            conn.doOutput = true

            val systemInstruction = """
                Extract placement drive info into JSON:
                {
                  "company_name": "Company Name",
                  "role": "Job Role",
                  "job_type": "Full-time" or "Internship",
                  "ctc_or_stipend": "CTC/Stipend",
                  "eligibility_criteria": "Eligibility",
                  "deadline": "Deadline",
                  "drive_date": "Drive Date",
                  "apply_link": "URL",
                  "description": "Short summary",
                  "change_summary": "If this is an update, what changed"
                }
            """.trimIndent()

            val payload = JSONObject().apply {
                put("contents", JSONArray().put(JSONObject().apply {
                    put("parts", JSONArray().put(JSONObject().apply {
                        put("text", "$systemInstruction\n\nMessage:\n$text")
                    }))
                }))
                put("generationConfig", JSONObject().apply {
                    put("responseMimeType", "application/json")
                    put("temperature", 0.1)
                })
            }

            OutputStreamWriter(conn.outputStream).use { it.write(payload.toString()) }

            if (conn.responseCode == 200) {
                val responseText = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
                val root = JSONObject(responseText)
                val candidateText = root.getJSONArray("candidates")
                    .getJSONObject(0)
                    .getJSONObject("content")
                    .getJSONArray("parts")
                    .getJSONObject(0)
                    .getString("text")

                val clean = candidateText.removePrefix("```json").removePrefix("```").removeSuffix("```").trim()
                JSONObject(clean)
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    private fun localHeuristicExtract(context: Context, text: String): JSONObject {
        val db = DatabaseHelper(context)
        var company: String? = null

        // Match against existing registered companies first
        val allDrives = db.getAllDrives()
        for (i in 0 until allDrives.length()) {
            val cName = allDrives.getJSONObject(i).optString("company_name", "")
            if (cName.length > 2 && Pattern.compile("\\b${Pattern.quote(cName)}\\b", Pattern.CASE_INSENSITIVE).matcher(text).find()) {
                company = cName
                break
            }
        }

        if (company == null) {
            val matcher = Pattern.compile("(?i)(?:hiring|drive|recruitment|company|from|for)\\s+([A-Z][A-Za-z0-9&]{2,20})").matcher(text)
            if (matcher.find()) {
                val cand = matcher.group(1)?.trim()
                val blacklist = setOf("software", "dear", "students", "batch", "interns", "all", "campus")
                if (cand != null && !blacklist.contains(cand.lowercase())) {
                    company = cand
                }
            }
        }

        val urlMatcher = Pattern.compile("https?://[^\\s<>\"']+").matcher(text)
        val link = if (urlMatcher.find()) urlMatcher.group() else ""

        val ctcMatcher = Pattern.compile("(?i)\\b(\\d+(?:\\.\\d+)?\\s*(?:LPA|L|lakhs?|k|pm|per month))\\b").matcher(text)
        val ctc = if (ctcMatcher.find()) ctcMatcher.group() else "Not disclosed"

        val deadlineMatcher = Pattern.compile("(?i)(?:deadline|last date|register by)[\\s:]*([0-9]{1,2}(?:st|nd|rd|th)?[\\sA-Za-z0-9:,]+)").matcher(text)
        val deadline = if (deadlineMatcher.find()) deadlineMatcher.group(1)?.trim() ?: "TBD" else "TBD"

        return JSONObject().apply {
            put("company_name", company ?: "Company Mentioned")
            put("role", "Software / Tech Role")
            put("job_type", "Full-time")
            put("ctc_or_stipend", ctc)
            put("eligibility_criteria", "Refer message")
            put("deadline", deadline)
            put("drive_date", "TBD")
            put("apply_link", link)
            put("description", text.take(150))
            put("change_summary", if (text.contains("update", ignoreCase = true) || text.contains("postponed", ignoreCase = true)) "Details updated" else "")
        }
    }
}
