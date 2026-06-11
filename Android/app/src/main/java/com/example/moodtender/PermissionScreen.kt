package com.example.moodtender

import android.app.Activity
import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.paint
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val InkBrown = Color(0xFF4E342E)

@Composable
fun PermissionScreen(onPermissionGranted: () -> Unit) {
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .paint(
                painter = painterResource(id = R.drawable.paper_background),
                contentScale = ContentScale.Crop
            )
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "당신의 마음을 읽기 위해",
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            color = InkBrown
        )
        Text(
            text = "다음 권한들이 필요해요.",
            fontSize = 18.sp,
            color = InkBrown.copy(alpha = 0.8f),
            modifier = Modifier.padding(bottom = 40.dp)
        )

        // 권한 설명 카드
        Card(
            colors = CardDefaults.cardColors(containerColor = Color(0xCCFFF3E0)),
            modifier = Modifier.fillMaxWidth().padding(bottom = 30.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text("• 건강 데이터 (걸음/수면): 오늘의 활력을 확인합니다.", color = InkBrown)
                Text("• 앱 사용 시간: 마음의 휴식 시간을 측정합니다.", color = InkBrown)
            }
        }

        // 설정으로 이동 버튼
        Button(
            onClick = {
                // 앱 설정 화면으로 이동
                val intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
                context.startActivity(intent)
            },
            colors = ButtonDefaults.buttonColors(containerColor = InkBrown),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth().height(50.dp)
        ) {
            Text("권한 설정하러 가기", color = Color.White, fontSize = 16.sp)
        }

        Spacer(modifier = Modifier.height(16.dp))

        TextButton(onClick = onPermissionGranted) {
            Text("이미 허용했어요", color = InkBrown.copy(alpha = 0.6f))
        }
    }
}