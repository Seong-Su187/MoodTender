package com.example.moodtender

import com.example.moodtender.data.*
import retrofit2.Call
import retrofit2.http.*

// 1. 로그인/연동 관련 데이터 상자
data class LoginResponse(
    val access_token: String,
    val token_type: String,
    val id: Int
)

data class VerifyRequest(
    val pin: String,
    val user_id: Int
)

data class VerifyResponse(
    val status: String,
    val message: String
)

interface ApiService {
    // 🚀 로그인 및 연동
    @POST("/api/login")
    fun login(@Body request: UserCreate): Call<LoginResponse>

    @POST("/api/mobile/health-data")
    fun sendHealthData(@Body request: HealthDataRequest): Call<Any>

    @POST("/api/mobile/pairing/verify")
    fun verifyPairing(@Body request: VerifyRequest): Call<VerifyResponse>

    // 🚀 채팅 기능 (새로 추가)
    @POST("/api/chat")
    fun postChat(@Body request: ChatRequest): Call<LLMResponse>

    @GET("/api/chat/history")
    fun getChatHistory(@Header("Authorization") token: String): Call<Map<String, Any>>
}