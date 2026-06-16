package com.example.moodtender

import android.app.AppOpsManager
import android.content.Context
import android.os.Bundle
import android.os.Process
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.work.*
import com.example.moodtender.workers.DataSyncWorker
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
        val loggedInUserId = sharedPref.getInt("USER_ID", -1)
        val token = sharedPref.getString("ACCESS_TOKEN", "") ?: ""

        // 🚀 LoginActivity에서 저장한 연동 상태 불러오기
        val isPaired = sharedPref.getBoolean("IS_PAIRED", false)

        setContent {
            var hasPermission by remember { mutableStateOf(hasUsageStatsPermission()) }
            val navController = rememberNavController()

            if (!hasPermission) {
                PermissionScreen(onPermissionGranted = {
                    hasPermission = hasUsageStatsPermission()
                })
            } else {
                // 🚀 연동 여부에 따라 첫 화면(startDestination)을 다르게 띄웁니다!
                val startDest = if (isPaired) "chat" else "pairing"

                NavHost(navController = navController, startDestination = startDest) {

                    // 🔒 연동 안 된 유저용: 핀 번호 입력 화면
                    composable("pairing") {
                        PairingScreen(
                            currentUserId = loggedInUserId, // 👈 준비물 1: 유저 ID 전달
                            onPairingSuccess = {            // 👈 준비물 2: 성공 시 작동할 스위치 전달
                                // ✅ 인증 성공 시 메인 채팅창으로 부드럽게 이동!
                                navController.navigate("chat") {
                                    // 사용자가 '뒤로 가기'를 눌렀을 때 핀 번호 창으로 다시 안 돌아가도록 방어
                                    popUpTo("pairing") { inclusive = true }
                                }
                            }
                        )
                    }

                    // ✅ 연동 완료된 유저용: 메인 채팅 화면
                    composable("chat") {
                        ChatScreen(
                            userId = loggedInUserId,
                            token = token,
                            onNavigateToHealth = { navController.navigate("health") }
                        )
                    }

                    composable("health") {
                        HealthScreen(
                            token = token,
                            onNavigateBack = { navController.popBackStack() }
                        )
                    }
                }
            }
        }
        scheduleSyncWork()
    }

    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), packageName)
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun scheduleSyncWork() {
        val workRequest = PeriodicWorkRequestBuilder<DataSyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("MoodTenderSync", ExistingPeriodicWorkPolicy.KEEP, workRequest)
    }
}