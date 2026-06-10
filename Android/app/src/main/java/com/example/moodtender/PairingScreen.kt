package com.example.moodtender

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PairingScreen() {
    // 사용자가 입력할 6자리 핀 번호 상태
    var pinText by remember { mutableStateOf("") }
    // 결과 메시지 (성공/실패)
    var resultMessage by remember { mutableStateOf("") }
    var isError by remember { mutableStateOf(false) }

    val coroutineScope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF121212)) // 다크 테마 배경
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "📱",
            fontSize = 64.sp,
            modifier = Modifier.padding(bottom = 16.dp)
        )

        Text(
            text = "디바이스 연동",
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold,
            color = Color.White
        )

        Spacer(modifier = Modifier.height(12.dp))

        Text(
            text = "PC 웹 화면에 표시된\n6자리 핀 번호를 입력해주세요.",
            color = Color.Gray,
            textAlign = TextAlign.Center,
            fontSize = 16.sp,
            lineHeight = 24.sp
        )

        Spacer(modifier = Modifier.height(40.dp))

        // PIN 입력 칸
        OutlinedTextField(
            value = pinText,
            onValueChange = {
                // 숫자만 최대 6자리까지 입력 가능하도록 제한
                if (it.length <= 6 && it.all { char -> char.isDigit() }) {
                    pinText = it
                }
            },
            label = { Text("PIN 번호 입력", color = Color.Gray) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            textStyle = LocalTextStyle.current.copy(
                fontSize = 24.sp,
                letterSpacing = 8.sp,
                textAlign = TextAlign.Center,
                color = Color.White
            ),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(0.8f),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Color(0xFF7C4DFF), // 보라색 포인트
                unfocusedBorderColor = Color.DarkGray
            )
        )

        Spacer(modifier = Modifier.height(32.dp))

        // 연동 버튼
        Button(
            onClick = {
                // 버튼 누르면 서버로 전송
                coroutineScope.launch {
                    try {
                        // 🚨 임시: 웹 테스트와 맞추기 위해 user_id 1로 고정
                        val request = VerifyRequest(pin = pinText, user_id = 1)

                        // 백그라운드 스레드에서 네트워크 통신
                        val response = withContext(Dispatchers.IO) {
                            RetrofitClient.instance.verifyPairing(request).execute()
                        }

                        if (response.isSuccessful) {
                            resultMessage = "✅ 연동 성공! 웹 화면을 확인하세요."
                            isError = false
                        } else {
                            resultMessage = "❌ 잘못된 핀 번호이거나 계정이 다릅니다."
                            isError = true
                        }
                    } catch (e: Exception) {
                        resultMessage = "⚠️ 네트워크 오류: 서버에 연결할 수 없습니다."
                        isError = true
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth(0.8f)
                .height(56.dp),
            enabled = pinText.length == 6, // 6자리를 다 채워야 버튼 활성화
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Color(0xFF7C4DFF),
                disabledContainerColor = Color.DarkGray
            )
        ) {
            Text("연동하기", fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }

        Spacer(modifier = Modifier.height(24.dp))

        // 결과 메시지 표시
        if (resultMessage.isNotEmpty()) {
            Text(
                text = resultMessage,
                color = if (isError) Color(0xFFFF6B7A) else Color(0xFF61D394),
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium
            )
        }
    }
}