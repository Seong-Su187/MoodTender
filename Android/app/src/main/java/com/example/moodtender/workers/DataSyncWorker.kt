package com.example.moodtender.workers

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
import com.example.moodtender.RetrofitClient
import com.example.moodtender.data.HealthDataRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.*

class DataSyncWorker(
    context: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(context, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        try {
            Log.d("DataSync", "백그라운드 데이터 수집 시작")

            // 1. 데이터 수집 로직 (MainActivity에서 가져옴)
            val calendar = Calendar.getInstance()
            val endTime = calendar.timeInMillis
            calendar.set(Calendar.HOUR_OF_DAY, 0); calendar.set(Calendar.MINUTE, 0)
            val startTime = calendar.timeInMillis

            // 앱 사용 시간
            val usageStatsManager = applicationContext.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val queryUsageStats = usageStatsManager.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, startTime, endTime)
            val appUsageMap = mutableMapOf("kakao" to 0, "youtube" to 0)
            var totalScreenTime = 0

            queryUsageStats?.forEach { stats ->
                if (stats.packageName.contains("kakao.talk") || stats.packageName.contains("android.youtube")) {
                    val minutes = (stats.totalTimeInForeground / 1000 / 60).toInt()
                    if (minutes > 0) {
                        val key = if (stats.packageName.contains("kakao")) "kakao" else "youtube"
                        appUsageMap[key] = (appUsageMap[key] ?: 0) + minutes
                        totalScreenTime += minutes
                    }
                }
            }

            // 헬스 데이터
            var realSteps = 4500 // 기본값
            var realSleepMinutes = 480

            try {
                val healthClient = HealthConnectClient.getOrCreate(applicationContext)
                val startInstant = Instant.ofEpochMilli(startTime)
                val endInstant = Instant.now()

                realSteps = healthClient.readRecords(ReadRecordsRequest(StepsRecord::class, TimeRangeFilter.between(startInstant, endInstant)))
                    .records.sumOf { it.count }.toInt()

                var sleep = 0
                healthClient.readRecords(ReadRecordsRequest(SleepSessionRecord::class, TimeRangeFilter.between(Instant.now().minus(1, ChronoUnit.DAYS), Instant.now())))
                    .records.forEach { sleep += ChronoUnit.MINUTES.between(it.startTime, it.endTime).toInt() }
                if(sleep > 0) realSleepMinutes = sleep
            } catch (e: Exception) { Log.e("DataSync", "헬스 데이터 접근 실패: ${e.message}") }

            // 2. 서버 전송
            val finalData = HealthDataRequest(
                recordDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date()),
                stepCount = realSteps,
                sleepMinutes = realSleepMinutes,
                screenTimeMinutes = totalScreenTime,
                appUsageJson = appUsageMap,
            )

            val response = RetrofitClient.instance.sendHealthData(finalData).execute()

            if (response.isSuccessful) {
                Log.d("DataSync", "성공적으로 전송됨")
                Result.success()
            } else {
                Result.retry()
            }
        } catch (e: Exception) {
            Log.e("DataSync", "실패: ${e.message}")
            Result.failure()
        }
    }
}