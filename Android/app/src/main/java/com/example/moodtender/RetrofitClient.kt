package com.example.moodtender

import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object RetrofitClient {

    // LLM 응답(감정/요약 체인 등)이 길어질 수 있어 기본 10초 타임아웃을 넉넉히 늘림
    private val okHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    // 🚀 수정: BuildConfig.BASE_URL 대신 실제 서버 주소를 명시적으로 선언합니다.
    // 주의: 백엔드 서버가 8000번 포트가 아니라면 포트 번호를 맞춰주세요!
    // - 에뮬레이터 사용 시: "http://10.0.2.2:8000/"
    // - 실제 스마트폰 기기 사용 시: PC의 내부 IP 주소 (예: "http://192.168.0.15:8000/")
    private const val BASE_URL = "http://10.0.2.2:7862/"

    val instance: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}