package com.example.moodtender.data

// 서버와 데이터를 주고받을 때 사용할 '데이터 상자'입니다.
data class UserCreate(
    val username: String,
    val password: String
)