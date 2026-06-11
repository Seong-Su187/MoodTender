package com.example.moodtender

import com.example.moodtender.data.HealthDataRequest
import com.example.moodtender.data.UserCreate // UserCreate 모델이 위치한 패키지 경로를 확인해주세요
import retrofit2.Call
import retrofit2.http.Body
import retrofit2.http.POST

// 🚀 1. 로그인 응답 데이터 상자 (서버가 주는 access_token과 id를 받음)
data class LoginResponse(
    val access_token: String,
    val token_type: String,
    val id: Int
)

// 2. PIN 번호 전송을 위한 요청 데이터 상자
data class VerifyRequest(
    val pin: String,
    val user_id: Int
)

// 3. 서버의 응답을 받을 데이터 상자
data class VerifyResponse(
    val status: String,
    val message: String
)

interface ApiService {
    // 🚀 로그인 요청 통로 (이제 서버에서 id를 받아와서 기기에 저장 가능!)
    @POST("/api/login")
    fun login(@Body request: UserCreate): Call<LoginResponse>

    // 기존 로직: 백그라운드에서 15분마다 건강 데이터를 보내는 통로
    @POST("/api/mobile/health-data")
    fun sendHealthData(@Body request: HealthDataRequest): Call<Any>

    // 웹 화면의 PIN 번호를 인증하는 통로
    @POST("/api/mobile/pairing/verify")
    fun verifyPairing(@Body request: VerifyRequest): Call<VerifyResponse>
}