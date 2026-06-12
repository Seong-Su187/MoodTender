package com.example.moodtender

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.work.*
import com.example.moodtender.workers.DataSyncWorker
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
        val loggedInUserId = sharedPref.getInt("USER_ID", -1)
        val accessToken = sharedPref.getString("ACCESS_TOKEN", "") ?: ""
        val isPaired = sharedPref.getBoolean("IS_PAIRED", false)

        setContent {
            if (isPaired) {
                // 이미 연동됨 -> 바로 채팅 화면으로
                val intent = Intent(this@MainActivity, ChatActivity::class.java).apply {
                    putExtra("USER_ID", loggedInUserId)
                    putExtra("ACCESS_TOKEN", accessToken)
                }
                startActivity(intent)
                finish()
            } else {
                // 연동 필요 -> 페어링 화면으로
                PairingScreen(currentUserId = loggedInUserId) {
                    val intent = Intent(this@MainActivity, ChatActivity::class.java).apply {
                        putExtra("USER_ID", loggedInUserId)
                        putExtra("ACCESS_TOKEN", accessToken)
                    }
                    startActivity(intent)
                    finish()
                }
            }
        }
        scheduleSyncWork()
    }

    private fun scheduleSyncWork() {
        val workRequest = PeriodicWorkRequestBuilder<DataSyncWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("MoodTenderSync", ExistingPeriodicWorkPolicy.KEEP, workRequest)
    }
}