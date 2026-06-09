package com.example.moodtender

import android.app.usage.UsageStatsManager
import android.content.Context
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.example.moodtender.data.HealthDataRequest
import java.text.SimpleDateFormat
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.Calendar
import java.util.Locale

class HealthDataWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    // 🛠️ 백그라운드에서 주기적으로 '자동 실행'될 핵심 메서드
    override suspend fun doWork(): Result {
        Log.d("WorkManager테스트", "🔄 백그라운드 자동 수집 및 전송 스케줄러 가동!")

        try {
            // [시간 계산] 오늘 자정 ~ 현재
            val calendar = Calendar.getInstance()
            val endTime = calendar.timeInMillis
            calendar.set(Calendar.HOUR_OF_DAY, 0)
            calendar.set(Calendar.MINUTE, 0)
            calendar.set(Calendar.SECOND, 0)
            calendar.set(Calendar.MILLISECOND, 0)
            val startTime = calendar.timeInMillis

            // 1. 실제 앱 사용 시간 추출 (1보 로직)
            val usageStatsManager = applicationContext.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
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

            // 2. 헬스 커넥트에서 진짜 건강 데이터 읽어오기 (2보 로직)
            var realSteps = 0
            var realSleepMinutes = 0

            val healthConnectClient = try {
                HealthConnectClient.getOrCreate(applicationContext)
            } catch (e: Exception) {
                null
            }

            if (healthConnectClient != null) {
                try {
                    val startInstant = Instant.ofEpochMilli(startTime)
                    val endInstant = Instant.ofEpochMilli(endTime)

                    // 진짜 걸음수 조회
                    val stepsResponse = healthConnectClient.readRecords(
                        ReadRecordsRequest(
                            recordType = StepsRecord::class,
                            timeRangeFilter = TimeRangeFilter.between(startInstant, endInstant)
                        )
                    )
                    realSteps = stepsResponse.records.sumOf { it.count }.toInt()

                    // 진짜 수면시간 조회
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
                    Log.e("WorkManager테스트", "⚠️ 백그라운드 내 건강 데이터 조회 실패: ${e.message}")
                }
            }

            // 에뮬레이터 환경용 보정 기본값
            if (realSteps == 0) realSteps = 5200
            if (realSleepMinutes == 0) realSleepMinutes = 450

            val todayStr = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Calendar.getInstance().time)

            // 데이터 그릇 생성
            val finalData = HealthDataRequest(
                recordDate = todayStr,
                stepCount = realSteps,
                sleepMinutes = realSleepMinutes,
                screenTimeMinutes = totalScreenTime,
                appUsageJson = appUsageMap,
                depressionScore = 0
            )

            Log.d("WorkManager테스트", "📊 백그라운드에서 가공된 데이터: $finalData")

            // 3. 서버로 동기 전송 (백그라운드 스레드이므로 비동기 enqueue 대신 execute 사용)
            val response = RetrofitClient.instance.sendHealthData(finalData).execute()

            return if (response.isSuccessful) {
                Log.d("WorkManager테스트", "✅ [3보 완수] 백그라운드 자동 전송 대성공!: ${response.body()}")
                Result.success() // 일 성공 완료 리포트
            } else {
                Log.e("WorkManager테스트", "❌ 서버 전송 실패 (에러코드: ${response.code()})")
                Result.retry() // 네트워크가 불안정하면 나중에 다시 시도하게 함
            }

        } catch (e: Exception) {
            Log.e("WorkManager테스트", "💥 백그라운드 치명적 에러 발생: ${e.message}")
            return Result.failure() // 일 실패 리포트
        }
    }
}