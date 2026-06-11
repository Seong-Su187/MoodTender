package com.example.moodtender.data

data class LLMResponse(
    val reply: String,
    val emotion: String = "" // 감정 정보가 있으면 UI에서 효과를 줄 수 있습니다.
)