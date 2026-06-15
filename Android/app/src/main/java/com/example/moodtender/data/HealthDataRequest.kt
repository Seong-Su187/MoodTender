package com.example.moodtender.data

import com.google.gson.annotations.SerializedName

data class HealthDataRequest(
    @SerializedName("record_date")
    val recordDate: String,

    @SerializedName("step_count")
    val stepCount: Int,

    @SerializedName("sleep_minutes")
    val sleepMinutes: Int,

    @SerializedName("screen_time_minutes")
    val screenTimeMinutes: Int,

    @SerializedName("app_usage_json")
    val appUsageJson: Map<String, Int>,
)