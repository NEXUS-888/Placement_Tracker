# Proguard rules for Placement Tracker
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keep class com.placementtracker.app.** { *; }
