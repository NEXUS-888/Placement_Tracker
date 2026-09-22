package com.placementtracker.app

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class WhatsAppNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    companion object {
        private const val TAG = "WhatsAppListener"
        private val WHATSAPP_PACKAGES = setOf("com.whatsapp", "com.whatsapp.w4b")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        super.onNotificationPosted(sbn)
        if (sbn == null) return

        val packageName = sbn.packageName
        if (!WHATSAPP_PACKAGES.contains(packageName)) return

        val extras = sbn.notification.extras ?: return
        val title = extras.getString(Notification.EXTRA_TITLE) ?: ""
        val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
        val bigText = extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString() ?: ""
        val fullContent = if (bigText.isNotEmpty()) bigText else text

        val prefs = applicationContext.getSharedPreferences("placement_prefs", android.content.Context.MODE_PRIVATE)
        val targetGroup = prefs.getString("target_group_name", "")?.trim() ?: ""
        val subText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString() ?: ""

        val isTargetGroup = if (targetGroup.isNotEmpty()) {
            title.contains(targetGroup, ignoreCase = true) || subText.contains(targetGroup, ignoreCase = true)
        } else {
            val keywordPattern = "(?i)\\b(placement|internship|cdc|tpo|campus drive|hiring|batch)\\b"
            java.util.regex.Pattern.compile(keywordPattern).matcher("$title $subText").find()
        }

        if (!isTargetGroup) {
            Log.d(TAG, "Ignoring message from non-target chat: '$title'")
            return
        }

        Log.d(TAG, "Placement message intercepted from '$title': $fullContent")

        // Analyze and process in background coroutine
        scope.launch {
            try {
                val combinedText = "From: $title\nMessage:\n$fullContent"
                val result = PlacementAnalyzer.analyzeAndProcess(applicationContext, combinedText)
                Log.d(TAG, "Processed result: $result")
            } catch (e: Exception) {
                Log.e(TAG, "Error analyzing WhatsApp notification", e)
            }
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        Log.i(TAG, "WhatsApp Notification Listener connected and actively monitoring!")
    }

    override fun onListenerDisconnected() {
        super.onListenerDisconnected()
        Log.w(TAG, "WhatsApp Notification Listener disconnected.")
    }

    override fun onDestroy() {
        try {
            scope.cancel()
        } catch (e: Exception) {}
        super.onDestroy()
    }
}
