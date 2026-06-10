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
import androidx.activity.compose.setContent // 🚀 [추가] 화면을 그리기 위한 필수 import
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

    // 헬스 커넥트에서 읽어올 필수 권한 목록 셋업
    private val healthPermissions = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class)
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 🚀 [추가] 앱이 켜지면 가장 먼저 핀 번호 입력 화면을 화면에 띄웁니다!
        setContent {
            PairingScreen()
        }

        // [기존 유지] 그 뒤에서 조용히 건강 데이터 권한을 체크하고 전송을 시작합니다.
        if (hasUsageStatsPermission()) {
            checkHealthConnectAndProcess()
        } else {
            requestUsageStatsPermission()
        }
    }

    // 📱 [기존 1단계 기능] 사용 통계 권한 체크 및 요청
    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), packageName)
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun requestUsageStatsPermission() {
        Log.d("통신테스트", "📢 사용 통계 권한이 없어 설정 화면으로 이동합니다.")
        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
    }

    // 🏥 [2단계 추가] 헬스 커넥트 연동 가능 여부 체크
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
                    Log.d("통신테스트", "📢 헬스 커넥트 읽기 권한이 필요합니다. 에뮬레이터 내 Health Connect 앱에서 권한을 켜주세요.")
                    extractAllRealData(healthConnectClient)
                }
            }
        } else {
            Log.e("통신테스트", "❌ 이 기기는 헬스 커넥트를 지원하지 않거나 설치되지 않았습니다. 임시 데이터로 진행합니다.")
            extractAllRealData(null)
        }
    }

    // 📊 [핵심 통합 함수] 앱 사용량 + 실제 걸음수 + 실제 수면 시간 추출
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
                    Log.e("통신테스트", "⚠️ 건강 데이터 조회 중 오류 발생 (기본값 대체): ${e.message}")
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

            Log.d("통신테스트", "🚀 [2보 완수] 서버로 보낼 최종 융합 데이터: $finalData")

            // RetrofitClient의 인스턴스가 호출될 때 HealthDataRequest의 형식이 맞아야 합니다.
            // (이전에 작성하신 ApiService.kt가 잘 저장되어 있어야 합니다.)
            RetrofitClient.instance.sendHealthData(finalData).enqueue(object : Callback<Any> {
                override fun onResponse(call: Call<Any>, response: Response<Any>) {
                    if (response.isSuccessful) {
                        Log.d("통신테스트", "✅ [2보 완수] 실제 건강+앱 데이터 전송 대성공!")
                    } else {
                        Log.e("통신테스트", "❌ 서버 거절 (에러코드: ${response.code()})")
                    }
                }
                override fun onFailure(call: Call<Any>, t: Throwable) {
                    Log.e("통신테스트", "💥 서버 접속 실패: ${t.message}")
                }
            })
        }
    }
}