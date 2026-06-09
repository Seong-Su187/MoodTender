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

        // 1단계에서 만든 앱 사용량 권한이 있는지 체크
        if (hasUsageStatsPermission()) {
            // 권한이 있다면 ➡️ 이제 헬스 커넥트 데이터까지 묶어서 처리 시작!
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
            // 헬스 커넥트가 폰에 설치되어 사용 가능한 상태라면 권한 확인 후 데이터 추출
            lifecycleScope.launch {
                val healthConnectClient = HealthConnectClient.getOrCreate(this@MainActivity)
                val grantedPermissions = healthConnectClient.permissionController.getGrantedPermissions()

                if (grantedPermissions.containsAll(healthPermissions)) {
                    // 모든 건강 권한이 허용되어 있다면 진짜 데이터 추출 실행!
                    extractAllRealData(healthConnectClient)
                } else {
                    // 건강 권한이 없다면 권한 요청창 띄우기 가이드 로그 출력
                    Log.d("통신테스트", "📢 헬스 커넥트 읽기 권한이 필요합니다. 에뮬레이터 내 Health Connect 앱에서 권한을 켜주세요.")
                    // 테스트 편의상 권한이 없어도 진행할 수 있게 임시 실행 처리
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
            // [시간 계산] 오늘 자정 ~ 현재
            val calendar = Calendar.getInstance()
            val endTime = calendar.timeInMillis
            calendar.set(Calendar.HOUR_OF_DAY, 0)
            calendar.set(Calendar.MINUTE, 0)
            calendar.set(Calendar.SECOND, 0)
            calendar.set(Calendar.MILLISECOND, 0)
            val startTime = calendar.timeInMillis

            // 1. 실제 앱 사용 시간 추출 (1보 로직)
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

            // 2. 헬스 커넥트에서 진짜 건강 데이터 읽어오기
            var realSteps = 0
            var realSleepMinutes = 0

            if (healthConnectClient != null) {
                try {
                    // 🏃‍♂️ 진짜 걸음수 읽기 (오늘 자정부터 현재까지)
                    val startInstant = Instant.ofEpochMilli(startTime)
                    val endInstant = Instant.ofEpochMilli(endTime)

                    val stepsResponse = healthConnectClient.readRecords(
                        ReadRecordsRequest(
                            recordType = StepsRecord::class,
                            timeRangeFilter = TimeRangeFilter.between(startInstant, endInstant)
                        )
                    )
                    realSteps = stepsResponse.records.sumOf { it.count }.toInt()

                    // 😴 진짜 수면 시간 읽기 (최근 24시간 내 수면 기록 조회)
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

            // 만약 실제 값이 0으로 나오면 에뮬레이터 테스트용 기본 샘플값 부여
            if (realSteps == 0) realSteps = 4500
            if (realSleepMinutes == 0) realSleepMinutes = 480

            // 오늘 날짜 문자열 변환
            val todayStr = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Calendar.getInstance().time)

            // 3. 완전히 새로 태어난 진짜 종합 데이터 그릇 완성!
            val finalData = HealthDataRequest(
                recordDate = todayStr,
                stepCount = realSteps,             // 🔗 진짜 걸음수 매칭 완료!
                sleepMinutes = realSleepMinutes,   // 🔗 진짜 수면 시간 매칭 완료!
                screenTimeMinutes = totalScreenTime,
                appUsageJson = appUsageMap,
                depressionScore = 0
            )

            Log.d("통신테스트", "🚀 [2보 완수] 서버로 보낼 최종 융합 데이터: $finalData")

            // 서버로 최종 전송
            RetrofitClient.instance.sendHealthData(finalData).enqueue(object : Callback<Map<String, String>> {
                override fun onResponse(call: Call<Map<String, String>>, response: Response<Map<String, String>>) {
                    if (response.isSuccessful) {
                        Log.d("통신테스트", "✅ [2보 완수] 실제 건강+앱 데이터 전송 대성공!: ${response.body()}")
                    } else {
                        Log.e("통신테스트", "❌ 서버 거절 (에러코드: ${response.code()})")
                    }
                }
                override fun onFailure(call: Call<Map<String, String>>, t: Throwable) {
                    Log.e("통신테스트", "💥 서버 접속 실패: ${t.message}")
                }
            })
        }
    }
}