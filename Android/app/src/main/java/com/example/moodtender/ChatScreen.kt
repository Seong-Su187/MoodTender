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
import com.airbnb.lottie.compose.* // 🚀 Lottie 임포트 추가
import kotlinx.coroutines.launch

// 이미지 속 글씨와 어울리는 짙은 갈색
val InkBrown = Color(0xFF4E342E)

@Composable
fun ChatScreen(userId: Int) {
    var text by remember { mutableStateOf("") }
    // 🚀 로딩 상태 추가
    var isLoading by remember { mutableStateOf(false) }
    val messages = remember { mutableStateListOf("어서오세요. 오늘 마음은 어떤 잔에 담아드릴까요?") }
    val scope = rememberCoroutineScope()

    // 🚀 Lottie 애니메이션 설정 (로딩 시 무한 반복)
    val composition by rememberLottieComposition(LottieCompositionSpec.RawRes(R.raw.loading_animation))
    val progress by animateLottieCompositionAsState(
        composition,
        iterations = LottieConstants.IterateForever
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .paint(
                painter = painterResource(id = R.drawable.paper_background),
                contentScale = ContentScale.Crop
            )
            .padding(horizontal = 24.dp, vertical = 32.dp)
    ) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(top = 100.dp)
        ) {
            items(messages) { msg ->
                Text(
                    text = msg,
                    color = InkBrown,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(vertical = 8.dp)
                )
            }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Color(0xE6FFF3E0), RoundedCornerShape(30.dp))
                .padding(horizontal = 16.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            TextField(
                value = text,
                onValueChange = { text = it },
                modifier = Modifier.weight(1f),
                enabled = !isLoading, // 🚀 로딩 중에는 입력 불가
                placeholder = { Text("메시지를 입력해 주세요.", color = InkBrown.copy(alpha = 0.5f)) },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    cursorColor = InkBrown
                )
            )

            // 🚀 로딩 상태에 따른 UI 분기
            if (isLoading) {
                LottieAnimation(
                    composition = composition,
                    progress = { progress },
                    modifier = Modifier.size(50.dp).padding(4.dp)
                )
            } else {
                IconButton(onClick = {
                    if (text.isNotBlank()) {
                        isLoading = true // 로딩 시작
                        scope.launch {
                            messages.add("나: $text")
                            text = ""
                            // 여기서 서버 통신이 완료되면 isLoading = false 처리
                            isLoading = false
                        }
                    }
                }) {
                    Text("➔", fontSize = 24.sp, color = InkBrown)
                }
            }
        }
    }
}