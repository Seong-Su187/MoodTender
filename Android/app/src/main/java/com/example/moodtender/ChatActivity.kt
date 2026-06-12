package com.example.moodtender

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.example.moodtender.ui.theme.MoodTenderTheme

class ChatActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val userId = intent.getIntExtra("USER_ID", -1)
        val accessToken = intent.getStringExtra("ACCESS_TOKEN") ?: ""

        setContent {
            MoodTenderTheme {
                ChatScreen(userId = userId, token = accessToken)
            }
        }
    }
}