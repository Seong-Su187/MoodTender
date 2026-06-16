package com.example.moodtender

import com.example.moodtender.data.*
import retrofit2.Call
import retrofit2.http.*

// 1. 로그인/연동 관련 데이터 상자
// ApiService.kt 안의 로그인 응답 데이터 상자
data class LoginResponse(
    val access_token: String,
    val token_type: String,
    val id: Int,
    val is_device_paired: Boolean // 🚀 서버에서 주는 이 값 하나면 끝납니다!
)

// 🚀 추가됨: 서버에서 유저의 연동 상태를 받아올 데이터 상자
data class UserStatusResponse(
    val user_id: Int,
    val is_device_paired: Boolean
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

    // 🚀 내 기기 연동 상태 확인 API
    @GET("/api/users/me/status")
    fun getUserStatus(@Header("Authorization") token: String): Call<UserStatusResponse>

    @GET("/api/web/data")
    fun getHealthData(@Header("Authorization") token: String): Call<HealthResponse>

    @POST("/api/mobile/health-data")
    fun sendHealthData(@Body request: HealthDataRequest): Call<Any>

    @POST("/api/mobile/pairing/verify")
    fun verifyPairing(@Body request: VerifyRequest): Call<VerifyResponse>

    // 🚀 채팅 기능 (새로 추가)
    @POST("/api/llm/respond")
    fun postChat(@Header("Authorization") token: String, @Body request: ChatRequest): Call<LLMResponse>

    @GET("/api/chat/history")
    fun getChatHistory(@Header("Authorization") token: String): Call<Map<String, Any>>
}