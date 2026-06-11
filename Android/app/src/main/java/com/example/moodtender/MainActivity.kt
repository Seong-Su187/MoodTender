package com.example.moodtender

import android.app.AppOpsManager
import android.content.Context
import android.os.Bundle
import android.os.Process
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.work.*
import com.example.moodtender.workers.DataSyncWorker
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 🚀 로그인 시 저장해둔 유저 ID
        val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
        val loggedInUserId = sharedPref.getInt("USER_ID", -1)

        setContent {
            // 🚀 사용 통계 권한이 있는지 체크 (상태 관리)
            var hasPermission by remember { mutableStateOf(hasUsageStatsPermission()) }

            if (hasPermission) {
                // 권한이 있다면 기존 화면으로
                PairingScreen(currentUserId = loggedInUserId)
            } else {
                // 권한이 없다면 안내 화면으로
                PermissionScreen(onPermissionGranted = {
                    // 사용자가 "이미 허용했어요" 버튼을 눌렀을 때 다시 체크
                    hasPermission = hasUsageStatsPermission()
                })
            }
        }

        // 백그라운드 작업 예약
        scheduleSyncWork()
    }

    // 🚀 권한 확인용 헬퍼 함수 추가
    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), packageName)
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun scheduleSyncWork() {
        val workRequest = PeriodicWorkRequestBuilder<DataSyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .build()

        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "MoodTenderSync",
            ExistingPeriodicWorkPolicy.KEEP,
            workRequest
        )
    }

    // 💡 팁: 사용자가 설정 화면에서 돌아왔을 때 권한 상태를 갱신하려면 이 함수를 추가하세요.
    override fun onResume() {
        super.onResume()
        // 앱으로 다시 돌아올 때마다 권한 상태를 최신으로 체크하여 화면을 새로고침
        // (상태가 변경되면 화면이 리컴포지션됩니다)
    }
}