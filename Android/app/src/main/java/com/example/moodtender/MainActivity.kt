package com.example.moodtender

import android.app.AppOpsManager
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.lifecycle.lifecycleScope
import com.example.moodtender.data.HealthDataRequest
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.Calendar
import java.util.Locale
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class MainActivity : ComponentActivity() {

    private val healthPermissions = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class)
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 🚀 로그인 시 저장해둔 유저 ID를 SharedPreferences에서 불러옵니다.
        // (로그인 성공 시 "USER_ID"라는 키로 값을 저장해두었어야 합니다.)
        val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
        val loggedInUserId = sharedPref.getInt("USER_ID", -1)

        // 🚀 PairingScreen에 진짜 유저 ID를 전달합니다.
        setContent {
            PairingScreen(currentUserId = loggedInUserId)
        }

        if (hasUsageStatsPermission()) {
            checkHealthConnectAndProcess()
        } else {
            requestUsageStatsPermission()
        }
    }

    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), packageName)
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun requestUsageStatsPermission() {
        Log.d("통신테스트", "📢 사용 통계 권한이 없어 설정 화면으로 이동합니다.")
        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
    }

    private fun checkHealthConnectAndProcess() {
        val providerPackageName = "com.google.android.apps.healthdata"
        val status = HealthConnectClient.getSdkStatus(this, providerPackageName)

        if (status == HealthConnectClient.SDK_AVAILABLE) {
            lifecycleScope.launch {
                val healthConnectClient = HealthConnectClient.getOrCreate(this@MainActivity)
                val grantedPermissions = healthConnectClient.permissionController.getGrantedPermissions()

                if (grantedPermissions.containsAll(healthPermissions)) {
                    extractAllRealData(healthConnectClient)
                } else {
                    Log.d("통신테스트", "📢 헬스 커넥트 권한이 필요합니다.")
                    extractAllRealData(healthConnectClient)
                }
            }
        } else {
            Log.e("통신테스트", "❌ 헬스 커넥트 지원 불가. 임시 데이터로 진행합니다.")
            extractAllRealData(null)
        }
    }

    private fun extractAllRealData(healthConnectClient: HealthConnectClient?) {
        lifecycleScope.launch {
            val calendar = Calendar.getInstance()
            val endTime = calendar.timeInMillis
            calendar.set(Calendar.HOUR_OF_DAY, 0)
            calendar.set(Calendar.MINUTE, 0)
            calendar.set(Calendar.SECOND, 0)
            calendar.set(Calendar.MILLISECOND, 0)
            val startTime = calendar.timeInMillis

            val usageStatsManager = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val queryUsageStats = usageStatsManager.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, startTime, endTime)
            val appUsageMap = mutableMapOf("kakao" to 0, "youtube" to 0)

            queryUsageStats?.forEach { stats ->
                if (stats.packageName.contains("kakao.talk") || stats.packageName.contains("android.youtube")) {
                    val minutes = (stats.totalTimeInForeground / 1000 / 60).toInt()
                    if (minutes > 0) {
                        val key = if (stats.packageName.contains("kakao")) "kakao" else "youtube"
                        appUsageMap[key] = (appUsageMap[key] ?: 0) + minutes
                    }
                }
            }
            val totalScreenTime = (appUsageMap["kakao"] ?: 0) + (appUsageMap["youtube"] ?: 0)

            var realSteps = 0
            var realSleepMinutes = 0

            if (healthConnectClient != null) {
                try {
                    val startInstant = Instant.ofEpochMilli(startTime)
                    val endInstant = Instant.ofEpochMilli(endTime)

                    val stepsResponse = healthConnectClient.readRecords(
                        ReadRecordsRequest(
                            recordType = StepsRecord::class,
                            timeRangeFilter = TimeRangeFilter.between(startInstant, endInstant)
                        )
                    )
                    realSteps = stepsResponse.records.sumOf { it.count }.toInt()

                    val sleepResponse = healthConnectClient.readRecords(
                        ReadRecordsRequest(
                            recordType = SleepSessionRecord::class,
                            timeRangeFilter = TimeRangeFilter.between(Instant.now().minus(1, ChronoUnit.DAYS), Instant.now())
                        )
                    )
                    sleepResponse.records.forEach { session ->
                        val durationMinutes = ChronoUnit.MINUTES.between(session.startTime, session.endTime).toInt()
                        realSleepMinutes += durationMinutes
                    }
                } catch (e: Exception) {
                    Log.e("통신테스트", "⚠️ 데이터 조회 중 오류: ${e.message}")
                }
            }

            if (realSteps == 0) realSteps = 4500
            if (realSleepMinutes == 0) realSleepMinutes = 480

            val todayStr = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Calendar.getInstance().time)

            val finalData = HealthDataRequest(
                recordDate = todayStr,
                stepCount = realSteps,
                sleepMinutes = realSleepMinutes,
                screenTimeMinutes = totalScreenTime,
                appUsageJson = appUsageMap,
                depressionScore = 0
            )

            RetrofitClient.instance.sendHealthData(finalData).enqueue(object : Callback<Any> {
                override fun onResponse(call: Call<Any>, response: Response<Any>) {
                    if (response.isSuccessful) {
                        Log.d("통신테스트", "✅ 데이터 전송 성공!")
                    } else {
                        Log.e("통신테스트", "❌ 서버 거절 (${response.code()})")
                    }
                }
                override fun onFailure(call: Call<Any>, t: Throwable) {
                    Log.e("통신테스트", "💥 서버 접속 실패: ${t.message}")
                }
            })
        }
    }
}