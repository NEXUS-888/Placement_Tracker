package com.placementtracker.app

import android.app.Activity
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.webkit.JavascriptInterface
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.json.JSONObject

class WebAppInterface(private val activity: Activity) {

    private val db = DatabaseHelper.getInstance(activity)
    private val scope = CoroutineScope(Dispatchers.Main)

    @JavascriptInterface
    fun getStats(): String {
        return db.getStats().toString()
    }

    @JavascriptInterface
    fun getDrives(status: String?, search: String?): String {
        return db.getAllDrives(status, search).toString()
    }

    @JavascriptInterface
    fun getDriveDetails(id: Long): String {
        val drive = db.getDriveById(id)
        return drive?.toString() ?: "{}"
    }

    @JavascriptInterface
    fun updateDriveStatus(id: Long, newStatus: String): Boolean {
        val updates = JSONObject().apply { put("status", newStatus) }
        return db.updateDrive(id, updates)
    }

    @JavascriptInterface
    fun isNotificationAccessGranted(): Boolean {
        val enabledListeners = Settings.Secure.getString(
            activity.contentResolver,
            "enabled_notification_listeners"
        )
        val myService = ComponentName(activity, WhatsAppNotificationListener::class.java).flattenToString()
        return enabledListeners != null && enabledListeners.contains(myService)
    }

    @JavascriptInterface
    fun openNotificationSettings() {
        val intent = Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        activity.startActivity(intent)
    }

    @JavascriptInterface
    fun setTargetGroup(groupName: String) {
        activity.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
            .edit()
            .putString("target_group_name", groupName.trim())
            .apply()
    }

    @JavascriptInterface
    fun getTargetGroup(): String {
        return activity.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
            .getString("target_group_name", "") ?: ""
    }

    @JavascriptInterface
    fun setApiKey(key: String) {
        activity.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
            .edit()
            .putString("gemini_api_key", key.trim())
            .apply()
    }

    @JavascriptInterface
    fun getApiKey(): String {
        return activity.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
            .getString("gemini_api_key", "") ?: ""
    }

    @JavascriptInterface
    fun simulateMessage(text: String): String {
        return runBlocking {
            PlacementAnalyzer.analyzeAndProcess(activity, text).toString()
        }
    }

    @JavascriptInterface
    fun getProfile(): String {
        return activity.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
            .getString("student_profile_json", "{}") ?: "{}"
    }

    @JavascriptInterface
    fun saveProfile(profileJson: String): Boolean {
        activity.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
            .edit()
            .putString("student_profile_json", profileJson)
            .apply()
        return true
    }
}

