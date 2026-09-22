package com.placementtracker.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import org.json.JSONObject

object PlacementNotifier {

    private const val CHANNEL_NEW_DRIVES = "placement_new_drives"
    private const val CHANNEL_UPDATES = "placement_updates"
    private const val CHANNEL_SHORTLISTS = "placement_shortlists"
    private const val CHANNEL_REGISTRATION = "placement_registration"

    fun initChannels(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

            val newDrivesChannel = NotificationChannel(
                CHANNEL_NEW_DRIVES,
                "New Placement Drives",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications for newly announced campus placement drives & internships"
                enableVibration(true)
                enableLights(true)
            }

            val updatesChannel = NotificationChannel(
                CHANNEL_UPDATES,
                "Drive Changes & Deadlines",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Urgent alerts when test dates, eligibility, or deadlines are modified"
                enableVibration(true)
                enableLights(true)
            }

            val shortlistChannel = NotificationChannel(
                CHANNEL_SHORTLISTS,
                "Interview & OA Shortlists",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Urgent high-priority alerts when your USN is found in interview shortlists"
                enableVibration(true)
                enableLights(true)
            }

            val regChannel = NotificationChannel(
                CHANNEL_REGISTRATION,
                "Registration Confirmations",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "Confirmation notifications when your registration is verified by placement cell"
            }

            manager.createNotificationChannel(newDrivesChannel)
            manager.createNotificationChannel(updatesChannel)
            manager.createNotificationChannel(shortlistChannel)
            manager.createNotificationChannel(regChannel)
        }
    }

    fun showNewDriveNotification(context: Context, drive: JSONObject) {
        initChannels(context)
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val company = drive.optString("company_name", "New Placement")
        val role = drive.optString("role", "Opportunity")
        val ctc = drive.optString("ctc_or_stipend", "Not disclosed")
        val deadline = drive.optString("deadline", "TBD")
        val applyLink = drive.optString("apply_link", "")

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            System.currentTimeMillis().toInt(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_NEW_DRIVES)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("🚀 $company is Hiring: $role")
            .setContentText("💰 $ctc • ⏳ Deadline: $deadline")
            .setStyle(NotificationCompat.BigTextStyle().bigText(
                "Role: $role\nCompensation: $ctc\nDeadline: $deadline\nEligibility: ${drive.optString("eligibility_criteria")}"
            ))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)

        // Action button to apply directly if link exists
        if (applyLink.isNotEmpty()) {
            val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse(applyLink))
            val browserPending = PendingIntent.getActivity(
                context,
                (System.currentTimeMillis() + 1).toInt(),
                browserIntent,
                PendingIntent.FLAG_IMMUTABLE
            )
            builder.addAction(android.R.drawable.ic_menu_send, "Apply Now", browserPending)
        }

        manager.notify(company.hashCode(), builder.build())
    }

    fun showUpdateNotification(context: Context, company: String, summary: String, changesText: String) {
        initChannels(context)
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            System.currentTimeMillis().toInt(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_UPDATES)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("⚠️ UPDATE: $company Placement Drive")
            .setContentText(summary)
            .setStyle(NotificationCompat.BigTextStyle().bigText(
                "Coordinator update for $company:\n\n$summary\n\n$changesText"
            ))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)

        manager.notify((company + "_update").hashCode(), builder.build())
    }

    fun showShortlistNotification(context: Context, company: String, summary: String, details: String) {
        initChannels(context)
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            System.currentTimeMillis().toInt(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_SHORTLISTS)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("🎉 SHORTLISTED: $company Round 2!")
            .setContentText(summary)
            .setStyle(NotificationCompat.BigTextStyle().bigText("Congratulations!\n\n$summary\n\n$details"))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)

        manager.notify((company + "_shortlist").hashCode(), builder.build())
    }

    fun showRegistrationConfirmedNotification(context: Context, company: String, summary: String) {
        initChannels(context)
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            System.currentTimeMillis().toInt(),
            intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_REGISTRATION)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("✅ Registration Verified: $company")
            .setContentText(summary)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)

        manager.notify((company + "_reg_confirm").hashCode(), builder.build())
    }
}

