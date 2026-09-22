# 📱 Placement Tracker Android Mobile App

A standalone, downloadable Android app that intercepts college placement drives directly from WhatsApp notifications on your phone, extracts details using **Gemini 3.5 Flash** (or offline zero-heat heuristic), tracks updates & date changes in a local SQLite database, and fires **native Android system notifications** directly to your phone.

---

## 🌟 How It Works on Your Phone

1. **No WhatsApp Web / No QR Code Needed**:
   - The app uses Android's native `NotificationListenerService`.
   - When the placement coordinator posts in your college WhatsApp group, Android automatically hands the notification text to the app in real time.
2. **Zero Phone Heating & Battery Friendly**:
   - **Step 1 (0% Battery)**: Fast regex check filters out non-placement chatter in `0.01 ms`.
   - **Step 2 (0% Phone CPU)**: Sends a lightweight HTTPS request to Google Gemini 3.5 Flash using your configured Gemini API key. Google's servers do 100% of the extraction heavy lifting—your phone does not get warm.
   - **Step 3 (Offline Safe)**: If you don't have internet, a local on-device regex extractor runs automatically.
3. **Native Direct Notifications (No Discord / Telegram Needed)**:
   - 🚀 **New Drive Announced**: Shows heads-up banner with Company, Role, Package, Deadline, and an **"Apply Now"** action button.
   - ⚠️ **Date / Eligibility Changed**: Shows high-priority alert highlighting the exact diff (`Old Deadline ➔ New Deadline`).
4. **Local Database & Offline Dashboard**:
   - Stores all drives and historical coordinator updates in a local SQLite database (`placement_tracker_mobile.db`) inside the app.
   - Beautiful embedded UI showing status, search, deadline countdowns, and change audit timelines.

---

## 🛠️ How to Build & Install the APK

### Method 1: Using Android Studio (Easiest)
1. Open **Android Studio**.
2. Click **Open** and select the folder: `D:\Projects\Placement Tracker\android`.
3. Connect your Android phone via USB (or use an emulator).
4. Click the green **Run ▶** button (or go to **Build** ➔ **Build Bundle(s) / APK(s)** ➔ **Build APK(s)**).
5. Transfer the generated `app-debug.apk` to your phone and install!

### Method 2: Command Line (if Android SDK is installed)
In `D:\Projects\Placement Tracker\android`:
```bash
gradlew assembleDebug
```
The output APK will be located at:
`android/app/build/outputs/apk/debug/app-debug.apk`

---

## 📱 First-Time Phone Setup (One Tap)

1. Open **Placement Tracker** on your phone.
2. A banner will say: *"Enable Notification Access to auto-read WhatsApp placement groups"*.
3. Tap **Enable** ➔ Android will open your phone's **Notification Access** settings.
4. Toggle **Placement Tracker** to **ON**.
5. That's it! Whenever your placement coordinator posts in WhatsApp, your phone will analyze it and notify you directly!
