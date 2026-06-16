package com.example.moodtender

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.moodtender.data.HealthData
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun HealthScreen(token: String, onNavigateBack: () -> Unit) {
    var allHealthData by remember { mutableStateOf<List<HealthData>>(emptyList()) }
    var selectedDate by remember { mutableStateOf<String?>(null) }
    val scrollState = rememberScrollState() // 🚀 내용이 많아져 스크롤 추가

    val currentData = allHealthData.find { it.recordDate == selectedDate }

    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            try {
                val response = RetrofitClient.instance.getHealthData("Bearer $token").execute()
                if (response.isSuccessful) {
                    val body = response.body()
                    allHealthData = body?.data?.sortedBy { it.recordDate } ?: emptyList()
                    selectedDate = allHealthData.lastOrNull()?.recordDate
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .padding(horizontal = 16.dp, vertical = 8.dp)
    ) {
        TextButton(onClick = onNavigateBack, contentPadding = PaddingValues(0.dp)) {
            Text("← 뒤로가기", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color.Black)
        }

        Text("내 건강 리포트", fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 12.dp))

        if (allHealthData.isNotEmpty()) {
            DateSelector(allHealthData, selectedDate) { selectedDate = it }

            // 🚀 스크롤 가능한 영역 (아이디어 1, 2, 3이 모두 들어갑니다)
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(scrollState)
                    .padding(bottom = 20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                if (currentData != null) {
                    // 아이디어 3: 시각화된 목표 달성률 (원형 프로그래스)
                    DailyGoalCard(currentData)

                    // 아이디어 2: 주간 트렌드 막대 그래프
                    WeeklyTrendCard(allHealthData)

                    // 아이디어 1: AI 바텐더의 따뜻한 코멘트
                    AIBartenderCommentCard(currentData)
                }
            }
        } else {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("데이터를 불러오는 중입니다...", color = Color.Gray)
            }
        }
    }
}

@Composable
fun DateSelector(allData: List<HealthData>, selectedDate: String?, onDateSelected: (String) -> Unit) {
    LazyRow(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
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

// 🍩 [아이디어 3] 시각화된 목표 달성률 카드
@Composable
fun DailyGoalCard(data: HealthData) {
    val targetSteps = 10000f
    val currentProgress = (data.stepCount / targetSteps).coerceIn(0f, 1f)

    // 부드럽게 차오르는 애니메이션 효과
    val animatedProgress by animateFloatAsState(
        targetValue = currentProgress,
        animationSpec = tween(durationMillis = 1000),
        label = "progress"
    )

    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E1))) {
        Row(modifier = Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            // 원형 프로그래스 바
            Box(contentAlignment = Alignment.Center, modifier = Modifier.size(100.dp)) {
                CircularProgressIndicator(progress = 1f, color = Color(0xFFE0E0E0), strokeWidth = 8.dp)
                CircularProgressIndicator(
                    progress = animatedProgress,
                    color = Color(0xFFf4923a),
                    strokeWidth = 8.dp,
                    strokeCap = StrokeCap.Round
                )
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("👟", fontSize = 24.sp)
                    Text("${(animatedProgress * 100).toInt()}%", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                }
            }

            Spacer(modifier = Modifier.width(24.dp))

            // 텍스트 요약
            Column {
                Text(data.recordDate, color = Color.Gray, fontSize = 12.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Text("${data.stepCount} 걸음", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = Color(0xFF3E2723))
                Spacer(modifier = Modifier.height(8.dp))
                Text("🌙 수면: ${data.sleepMinutes / 60}시간 ${data.sleepMinutes % 60}분", fontSize = 14.sp, color = Color.DarkGray)
                Text("📱 화면: ${data.screenTimeMinutes / 60}시간 ${data.screenTimeMinutes % 60}분", fontSize = 14.sp, color = Color.DarkGray)
            }
        }
    }
}

// 📊 [아이디어 2] 주간 트렌드 요약 (미니 막대 그래프)
@Composable
fun WeeklyTrendCard(allData: List<HealthData>) {
    val weeklyData = allData.takeLast(7) // 최근 7일 데이터만 추출
    val maxSteps = weeklyData.maxOfOrNull { it.stepCount }?.toFloat() ?: 10000f

    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color.White), elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("📈 최근 7일 걸음 수 트렌드", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color(0xFF3E2723))
            Spacer(modifier = Modifier.height(16.dp))

            Row(modifier = Modifier.fillMaxWidth().height(100.dp), horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.Bottom) {
                weeklyData.forEach { data ->
                    val barHeight = (data.stepCount / maxSteps).coerceIn(0.1f, 1f) // 최소 높이 보장

                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Bottom) {
                        Box(
                            modifier = Modifier
                                .width(16.dp)
                                .fillMaxHeight(barHeight)
                                .clip(RoundedCornerShape(topStart = 8.dp, topEnd = 8.dp))
                                .background(Color(0xFF8D6E63))
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        // 날짜 끝자리 (예: 11-30 -> 30)
                        Text(data.recordDate.takeLast(2), fontSize = 10.sp, color = Color.Gray)
                    }
                }
            }
        }
    }
}

// 🤖 [아이디어 1] AI 바텐더의 '오늘의 건강 코멘트'
@Composable
fun AIBartenderCommentCard(data: HealthData) {
    val comment = when {
        data.sleepMinutes < 300 -> "수면이 많이 부족해 보여요. 오늘은 폰을 잠시 내려놓고 따뜻한 차와 함께 일찍 눈을 붙여볼까요?"
        data.stepCount > 10000 -> "오늘 하루 정말 열심히 걸으셨네요! 푹 쉬면서 다리 근육을 부드럽게 풀어주세요."
        data.screenTimeMinutes > 300 -> "화면을 본 시간이 꽤 길어요. 피로한 눈을 위해 잠시 창밖을 보며 휴식하는 걸 추천해 드려요."
        else -> "오늘도 무사히 하루를 보내셨군요. 수고 많으셨어요. 당신의 내일도 제가 응원할게요."
    }

    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFFF5E6D3))) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("🍸", fontSize = 42.sp, modifier = Modifier.padding(end = 16.dp))
            Column {
                Text("MoodTender의 한마디", fontWeight = FontWeight.Bold, color = Color(0xFF6D4C41), fontSize = 15.sp)
                Spacer(modifier = Modifier.height(6.dp))
                Text(comment, color = Color(0xFF4E342E), fontSize = 14.sp, lineHeight = 20.sp)
            }
        }
    }
}