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
            // 🚀 아까 만든 그 예쁜 LoginScreen을 여기에 배치합니다.
            LoginScreen { username, password ->
                // 로그인 버튼 클릭 시 동작할 로직
                val request = UserCreate(username, password)

                RetrofitClient.instance.login(request).enqueue(object : Callback<LoginResponse> {
                    override fun onResponse(call: Call<LoginResponse>, response: Response<LoginResponse>) {
                        if (response.isSuccessful) {
                            val userId = response.body()!!.id

                            // ID 저장
                            val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
                            sharedPref.edit().putInt("USER_ID", userId).apply()

                            // 로그인 성공 -> MainActivity로 이동
                            startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                            finish()
                        } else {
                            Toast.makeText(this@LoginActivity, "로그인 실패", Toast.LENGTH_SHORT).show()
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