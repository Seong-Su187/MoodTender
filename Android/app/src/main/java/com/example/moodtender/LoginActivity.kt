package com.example.moodtender

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.example.moodtender.data.UserCreate
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

class LoginActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var username by remember { mutableStateOf("") }
            var password by remember { mutableStateOf("") }

            Column(Modifier.padding(16.dp).fillMaxSize(), Arrangement.Center) {
                TextField(value = username, onValueChange = { username = it }, label = { Text("아이디") })
                TextField(value = password, onValueChange = { password = it }, label = { Text("비밀번호") })
                Button(onClick = {
                    val request = UserCreate(username, password)
                    RetrofitClient.instance.login(request).enqueue(object : Callback<LoginResponse> {
                        override fun onResponse(call: Call<LoginResponse>, response: Response<LoginResponse>) {
                            if (response.isSuccessful) {
                                val userId = response.body()!!.id
                                // 🚀 ID 저장!
                                val sharedPref = getSharedPreferences("AppPrefs", Context.MODE_PRIVATE)
                                sharedPref.edit().putInt("USER_ID", userId).apply()
                                
                                // 메인 화면(기기 연동 화면)으로 이동
                                startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                                finish()
                            } else {
                                Toast.makeText(this@LoginActivity, "로그인 실패", Toast.LENGTH_SHORT).show()
                            }
                        }
                        override fun onFailure(call: Call<LoginResponse>, t: Throwable) { }
                    })
                }) { Text("로그인") }
            }
        }
    }
}