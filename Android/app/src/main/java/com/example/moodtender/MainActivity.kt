package com.example.moodtender

import android.content.Context
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
        val token = sharedPref.getString("TOKEN", "") ?: "" // 토큰도 저장되어 있다고 가정

        setContent {
            var hasPermission by remember { mutableStateOf(hasUsageStatsPermission()) }
            val navController = rememberNavController()

            if (!hasPermission) {
                PermissionScreen(onPermissionGranted = {
                    hasPermission = hasUsageStatsPermission()
                })
            } else {
                // 권한이 있을 때만 내비게이션 실행
                NavHost(navController = navController, startDestination = "chat") {
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