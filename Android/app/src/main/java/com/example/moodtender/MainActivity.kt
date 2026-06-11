package com.example.moodtender

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
        val loggedInUserId = sharedPref.getInt("USER_ID", -1)
        val accessToken = sharedPref.getString("ACCESS_TOKEN", "") ?: ""

        setContent {
            var hasPermission by remember { mutableStateOf(hasUsageStatsPermission()) }

            if (hasPermission) {
                PairingScreen(currentUserId = loggedInUserId) {
                    // 성공 시 인텐트에 USER_ID와 토큰을 담아 ChatActivity로 전송
                    val intent = Intent(this@MainActivity, ChatActivity::class.java)
                    intent.putExtra("USER_ID", loggedInUserId)
                    intent.putExtra("ACCESS_TOKEN", accessToken)
                    startActivity(intent)
                    finish()
                }
            } else {
                PermissionScreen(onPermissionGranted = { hasPermission = hasUsageStatsPermission() })
            }
        }
    }

    private fun hasUsageStatsPermission(): Boolean {
        // (기존 권한 체크 로직 유지)
        return true // 예시로 true 반환
    }
}