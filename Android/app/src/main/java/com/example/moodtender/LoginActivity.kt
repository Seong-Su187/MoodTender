// LoginActivity.kt
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

                RetrofitClient.instance.login(request).enqueue(object : Callback<LoginResponse> {
                    override fun onResponse(call: Call<LoginResponse>, response: Response<LoginResponse>) {
                        if (response.isSuccessful) {
                            val loginResponse = response.body() ?: return

                            // 🚀 로그인 한 번으로 아이디, 토큰, 연동 상태를 다 받아서 저장!
                            val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
                            sharedPref.edit()
                                .putInt("USER_ID", loginResponse.id)
                                .putString("ACCESS_TOKEN", loginResponse.access_token)
                                .putBoolean("IS_PAIRED", loginResponse.is_device_paired) // 연동 상태 저장
                                .apply()

                            // 군더더기 없이 바로 메인으로 이동
                            startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                            finish()
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