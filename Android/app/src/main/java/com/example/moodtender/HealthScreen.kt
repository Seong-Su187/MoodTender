package com.example.moodtender

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun HealthScreen(token: String, onNavigateBack: () -> Unit) {
    var allHealthData by remember { mutableStateOf<List<HealthData>>(emptyList()) }
    var selectedDate by remember { mutableStateOf<String?>(null) }
    val currentData = allHealthData.find { it.recordDate == selectedDate }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            try {
                val response = RetrofitClient.instance.getWebData("Bearer $token").execute()
                if (response.isSuccessful) {
                    allHealthData = response.body()?.data ?: emptyList()
                    selectedDate = allHealthData.lastOrNull()?.recordDate
                }
            } catch (e: Exception) { e.printStackTrace() }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        IconButton(onClick = onNavigateBack) { Text("← 뒤로가기", fontWeight = FontWeight.Bold) }

        Text("내 건강 리포트", fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp))

        DateSelector(allHealthData, selectedDate) { selectedDate = it }

        if (currentData != null) {
            HealthStatusCard(currentData)
        } else {
            Text("데이터를 불러오는 중입니다...", modifier = Modifier.padding(16.dp))
        }
    }
}

@Composable
fun DateSelector(allData: List<HealthData>, selectedDate: String?, onDateSelected: (String) -> Unit) {
    LazyRow(modifier = Modifier.fillMaxWidth().padding(8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(allData.reversed()) { data ->
            val isSelected = (data.recordDate == selectedDate)
            Surface(
                onClick = { onDateSelected(data.recordDate) },
                color = if (isSelected) Color(0xFF6D4C41) else Color(0xFFD7CCC8),
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier.height(40.dp)
            ) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(horizontal = 16.dp)) {
                    Text(text = data.recordDate.substring(5), color = if (isSelected) Color.White else Color.Black, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
fun HealthStatusCard(data: HealthData) {
    Card(modifier = Modifier.fillMaxWidth().padding(8.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E1))) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("📊 최신 기록", fontWeight = FontWeight.Bold)
            Text("날짜: ${data.recordDate}")
            Text("걸음수: ${data.stepCount}보")
            Text("수면시간: ${data.sleepMinutes}분")
            Text("화면사용: ${data.screenTimeMinutes}분")
        }
    }
}