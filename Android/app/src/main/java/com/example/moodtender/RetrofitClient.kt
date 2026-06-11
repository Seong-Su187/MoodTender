package com.example.moodtender // ui.theme가 사라진 정상적인 상태

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object RetrofitClient {
<<<<<<< Updated upstream
    private const val BASE_URL = "http://59.22.23.224:7862/"
=======
    private const val BASE_URL = "http://172.30.1.40:7862/"
>>>>>>> Stashed changes

    val instance: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}