package com.example.moodtender

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.example.moodtender.data.UserCreate
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class LoginActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            LoginScreen { username, password ->
                val request = UserCreate(username, password)

                // 1단계: 로그인하여 토큰과 ID 받기
                RetrofitClient.instance.login(request).enqueue(object : Callback<LoginResponse> {
                    override fun onResponse(call: Call<LoginResponse>, response: Response<LoginResponse>) {
                        if (response.isSuccessful) {
                            val loginResponse = response.body() ?: return
                            val userId = loginResponse.id
                            val token = loginResponse.access_token

                            // 2단계: 발급받은 토큰으로 서버에 '진짜 연동 상태' 물어보기
                            RetrofitClient.instance.getUserStatus("Bearer $token").enqueue(object : Callback<UserStatusResponse> {
                                override fun onResponse(call: Call<UserStatusResponse>, statusResponse: Response<UserStatusResponse>) {
                                    if (statusResponse.isSuccessful) {
                                        // 🚀 여기서 서버 DB에 저장된 확실한 true/false 값을 가져옵니다!
                                        val realPairedStatus = statusResponse.body()?.is_device_paired ?: false

                                        // 3단계: 확인된 진짜 상태를 메모장에 안전하게 저장
                                        val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
                                        sharedPref.edit()
                                            .putInt("USER_ID", userId)
                                            .putString("ACCESS_TOKEN", token)
                                            .putBoolean("IS_PAIRED", realPairedStatus) // 더 이상 리셋되지 않습니다!
                                            .apply()

                                        // 모든 준비 끝, 메인 화면으로 이동
                                        startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                                        finish()
                                    } else {
                                        Toast.makeText(this@LoginActivity, "연동 상태 확인 실패", Toast.LENGTH_SHORT).show()
                                    }
                                }

                                override fun onFailure(call: Call<UserStatusResponse>, t: Throwable) {
                                    Toast.makeText(this@LoginActivity, "상태 확인 통신 오류", Toast.LENGTH_SHORT).show()
                                }
                            })

                        } else {
                            Toast.makeText(this@LoginActivity, "로그인 실패: 아이디나 비밀번호를 확인해주세요.", Toast.LENGTH_SHORT).show()
                        }
                    }
                    override fun onFailure(call: Call<LoginResponse>, t: Throwable) {
                        Toast.makeText(this@LoginActivity, "서버 접속 실패", Toast.LENGTH_SHORT).show()
                    }
                })
            }
        }
    }
}