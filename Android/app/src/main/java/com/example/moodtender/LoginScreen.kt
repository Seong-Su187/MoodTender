package com.example.moodtender

import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.google.android.exoplayer2.ExoPlayer
import com.google.android.exoplayer2.MediaItem
import com.google.android.exoplayer2.Player
import com.google.android.exoplayer2.ui.AspectRatioFrameLayout
import com.google.android.exoplayer2.ui.PlayerView

@Composable
fun LoginScreen(onLoginClick: (String, String) -> Unit) { // 🚀 로그인 정보 전달 파라미터 추가
    val context = LocalContext.current
    var idText by remember { mutableStateOf("") }
    var pwText by remember { mutableStateOf("") }

    // 🚀 배경 영상 설정
    val exoPlayer = remember {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(Uri.parse("android.resource://${context.packageName}/${R.raw.background_video}")))
            repeatMode = Player.REPEAT_MODE_ALL
            playWhenReady = true
            prepare()
        }
    }
    DisposableEffect(Unit) { onDispose { exoPlayer.release() } }

    Box(modifier = Modifier.fillMaxSize()) {
        // 1. 배경 영상 레이어
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = false
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                    player = exoPlayer
                }
            },
            modifier = Modifier.fillMaxSize()
        )

        // 2. 웹 스타일 반투명 로그인 카드
        Card(
            modifier = Modifier
                .align(Alignment.Center)
                .fillMaxWidth(0.85f)
                .padding(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xCC1A1A1A)), // 80% 투명도
            shape = RoundedCornerShape(20.dp)
        ) {
            Column(
                modifier = Modifier.padding(28.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("MoodTender", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Color(0xFFD4AF37)) // 골드 포인트
                Text("당신의 마음을 위한 바텐더", fontSize = 14.sp, color = Color.Gray)

                Spacer(modifier = Modifier.height(32.dp))

                // 아이디 입력
                OutlinedTextField(
                    value = idText,
                    onValueChange = { idText = it },
                    label = { Text("아이디", color = Color.Gray) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFFD4AF37), unfocusedBorderColor = Color.DarkGray, focusedTextColor = Color.White, unfocusedTextColor = Color.White)
                )

                Spacer(modifier = Modifier.height(12.dp))

                // 비밀번호 입력
                OutlinedTextField(
                    value = pwText,
                    onValueChange = { pwText = it },
                    label = { Text("비밀번호", color = Color.Gray) },
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFFD4AF37), unfocusedBorderColor = Color.DarkGray, focusedTextColor = Color.White, unfocusedTextColor = Color.White)
                )

                Spacer(modifier = Modifier.height(32.dp))

                // 로그인 버튼
                Button(
                    onClick = { onLoginClick(idText, pwText) }, // 🚀 입력값을 LoginActivity로 전달
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFD4AF37))
                ) {
                    Text("로그인", fontWeight = FontWeight.Bold, color = Color.Black)
                }
            }
        }
    }
}