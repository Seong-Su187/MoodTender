package com.example.moodtender

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.paint
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.airbnb.lottie.compose.*
import com.example.moodtender.data.ChatRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun ChatScreen(userId: Int, token: String) {
    var text by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    val messages = remember { mutableStateListOf("어서오세요. 어떤 마음을 담아드릴까요?") }
    val scope = rememberCoroutineScope()
    val composition by rememberLottieComposition(LottieCompositionSpec.RawRes(R.raw.loading_animation))

    Column(modifier = Modifier.fillMaxSize().paint(painter = painterResource(id = R.drawable.paper_background), contentScale = ContentScale.Crop).padding(24.dp)) {
        LazyColumn(modifier = Modifier.weight(1f), contentPadding = PaddingValues(top = 100.dp)) {
            items(messages) { msg ->
                Text(text = msg, color = Color(0xFF4E342E), fontSize = 18.sp, modifier = Modifier.padding(vertical = 8.dp))
            }
        }

        Row(modifier = Modifier.fillMaxWidth().background(Color(0xE6FFF3E0), RoundedCornerShape(30.dp)).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
            TextField(value = text, onValueChange = { text = it }, modifier = Modifier.weight(1f), enabled = !isLoading, colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent))
            
            if (isLoading) {
                LottieAnimation(composition = composition, iterations = LottieConstants.IterateForever, modifier = Modifier.size(50.dp))
            } else {
                IconButton(onClick = {
                    if (text.isNotBlank()) {
                        isLoading = true
                        scope.launch {
                            val userMsg = text
                            text = ""
                            messages.add("나: $userMsg")
                            try {
                                val response = withContext(Dispatchers.IO) { RetrofitClient.instance.postChat("Bearer $token", ChatRequest(user_id = userId, text = userMsg)).execute() }
                                response.body()?.let { messages.add(it.reply) }
                            } catch (e: Exception) { messages.add("서버 연결 실패") }
                            isLoading = false
                        }
                    }
                }) { Text("➔", fontSize = 24.sp) }
            }
        }
    }
}