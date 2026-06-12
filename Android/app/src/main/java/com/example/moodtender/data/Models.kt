package com.example.moodtender.data

// 서버 조회용
data class HealthResponse(
    val data: List<HealthData>
)

data class HealthData(
    val recordDate: String,
    val stepCount: Int,
    val sleepMinutes: Int,
    val screenTimeMinutes: Int
)

// 채팅 요청용 (기존 ChatScreen.kt와 호환되도록 필드명 유지)
data class ChatRequest(
    val user_id: Int,
    val text: String
)

// 채팅 응답용 (emotion 포함 버전)
data class LLMResponse(
    val reply: String,
    val emotion: String = ""
)