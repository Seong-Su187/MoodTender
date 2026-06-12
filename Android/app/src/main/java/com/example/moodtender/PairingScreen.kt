package com.example.moodtender

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
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
fun PairingScreen(currentUserId: Int, onPairingSuccess: () -> Unit) {
    var pinText by remember { mutableStateOf("") }
    var resultMessage by remember { mutableStateOf("") }
    var isError by remember { mutableStateOf(false) }
    val coroutineScope = rememberCoroutineScope()
    val context = LocalContext.current

    Column(modifier = Modifier.fillMaxSize().background(Color(0xFF121212)).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Text(text = "📱", fontSize = 64.sp, modifier = Modifier.padding(bottom = 16.dp))
        Text(text = "디바이스 연동", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Color.White)
        Spacer(modifier = Modifier.height(40.dp))

        OutlinedTextField(
            value = pinText,
            onValueChange = { if (it.length <= 6 && it.all { char -> char.isDigit() }) pinText = it },
            label = { Text("PIN 번호 입력", color = Color.Gray) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            textStyle = LocalTextStyle.current.copy(fontSize = 24.sp, letterSpacing = 8.sp, textAlign = TextAlign.Center, color = Color.White),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(0.8f),
            colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFF7C4DFF), unfocusedBorderColor = Color.DarkGray)
        )
        Spacer(modifier = Modifier.height(32.dp))

        Button(
            onClick = {
                coroutineScope.launch {
                    try {
                        val response = withContext(Dispatchers.IO) { RetrofitClient.instance.verifyPairing(VerifyRequest(pinText, currentUserId)).execute() }
                        if (response.isSuccessful) {
                            context.getSharedPreferences("AppPrefs", Context.MODE_PRIVATE).edit().putBoolean("IS_PAIRED", true).apply()
                            onPairingSuccess()
                        } else {
                            resultMessage = "❌ 잘못된 핀 번호입니다."
                            isError = true
                        }
                    } catch (e: Exception) {
                        resultMessage = "⚠️ 네트워크 오류"
                        isError = true
                    }
                }
            },
            modifier = Modifier.fillMaxWidth(0.8f).height(56.dp),
            enabled = pinText.length == 6,
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF7C4DFF))
        ) { Text("연동하기", fontSize = 18.sp, fontWeight = FontWeight.Bold) }

        if (resultMessage.isNotEmpty()) {
            Spacer(modifier = Modifier.height(16.dp))
            Text(text = resultMessage, color = if (isError) Color(0xFFFF6B7A) else Color(0xFF61D394))
        }
    }
}