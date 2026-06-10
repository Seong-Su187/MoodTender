package com.example.moodtender

import com.example.moodtender.data.HealthDataRequest
import retrofit2.Call
import retrofit2.http.Body
import retrofit2.http.POST

// 1. PIN 번호 전송을 위한 요청 데이터 상자
data class VerifyRequest(
    val pin: String,
    val user_id: Int
)

// 2. 서버의 응답을 받을 데이터 상자
data class VerifyResponse(
    val status: String,
    val message: String
)

interface ApiService {
    // 기존 로직: 백그라운드에서 15분마다 건강 데이터를 보내는 통로
    @POST("/api/mobile/health-data")
    fun sendHealthData(@Body request: HealthDataRequest): Call<Any>

    // 🚀 새롭게 추가된 로직: 웹 화면의 PIN 번호를 인증하는 통로
    @POST("/api/mobile/pairing/verify")
    fun verifyPairing(@Body request: VerifyRequest): Call<VerifyResponse>
}