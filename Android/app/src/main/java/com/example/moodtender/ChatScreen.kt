package com.example.moodtender

import android.content.Intent
import android.provider.Settings
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.airbnb.lottie.compose.*
import com.example.moodtender.data.ChatRequest
import com.example.moodtender.data.LLMResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun ChatBubble(msg: String) {
    val isUser = msg.startsWith("나: ")
    val cleanMsg = msg.removePrefix("나: ")
    val bubbleColor = if (isUser) Color(0xFF6D4C41) else Color(0xFFD7CCC8)
    val textColor = if (isUser) Color.White else Color.Black

    Column(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start
    ) {
        Surface(
            color = bubbleColor,
            shape = RoundedCornerShape(16.dp),
            shadowElevation = 2.dp,
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Text(
                text = cleanMsg,
                color = textColor,
                fontSize = 16.sp,
                modifier = Modifier.padding(12.dp)
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(userId: Int, token: String, onNavigateToHealth: () -> Unit) {
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var text by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }

    val messages = remember { mutableStateListOf("어서오세요. 오늘 마음은 어떤 잔에 담아드릴까요?") }

    // 로딩 애니메이션 준비
    val composition by rememberLottieComposition(LottieCompositionSpec.RawRes(R.raw.loading_animation))

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Spacer(Modifier.height(12.dp))
                Text("설정", modifier = Modifier.padding(16.dp), style = MaterialTheme.typography.titleLarge)
                HorizontalDivider()
                NavigationDrawerItem(label = { Text("사용 기록 권한 설정") }, selected = false, onClick = { context.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)); scope.launch { drawerState.close() } })
                NavigationDrawerItem(label = { Text("내 건강 데이터 확인") }, selected = false, onClick = { scope.launch { drawerState.close() }; onNavigateToHealth() })
            }
        }
    ) {
        Scaffold(
            containerColor = Color.Transparent,
            modifier = Modifier.paint(
                painter = painterResource(id = R.drawable.paper_background),
                contentScale = ContentScale.Crop
            ),
            topBar = {
                TopAppBar(
                    title = { },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Text("☰", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = Color(0xFF3E2723))
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent)
                )
            }
        ) { padding ->
            // 🚀 최상단 Box: 이곳이 화면 전체를 덮는 레이어입니다.
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {

                // --- 1. 채팅 내용과 입력창 (기본 레이어) ---
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    LazyColumn(
                        modifier = Modifier.weight(1f).fillMaxWidth(),
                        reverseLayout = true,
                        contentPadding = PaddingValues(vertical = 8.dp)
                    ) {
                        items(messages) { msg -> ChatBubble(msg = msg) }
                    }

                    // 하단 입력창 Row
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 16.dp)
                            .height(56.dp)
                            .background(Color(0xE6FFF3E0), RoundedCornerShape(30.dp)),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextField(
                            value = text,
                            onValueChange = { newValue: String -> text = newValue },
                            modifier = Modifier.weight(1f).height(56.dp),
                            enabled = !isLoading, // 로딩 중에는 입력 불가
                            colors = TextFieldDefaults.colors(
                                focusedContainerColor = Color.Transparent,
                                unfocusedContainerColor = Color.Transparent,
                                focusedIndicatorColor = Color.Transparent,
                                unfocusedIndicatorColor = Color.Transparent
                            )
                        )

                        // 🚀 수정: 로딩 중이어도 버튼을 없애지 않고 클릭만 막아서 레이아웃 깨짐 방지
                        IconButton(
                            onClick = {
                                if (text.isNotBlank() && !isLoading) {
                                    isLoading = true
                                    val msg = text
                                    text = ""

                                    messages.add(0, "나: $msg")

                                    scope.launch {
                                        try {
                                            val response = withContext(Dispatchers.IO) {
                                                RetrofitClient.instance.postChat(
                                                    "Bearer $token",
                                                    ChatRequest(user_id = userId, text = msg)
                                                ).execute()
                                            }
                                            response.body()?.let { messages.add(0, it.reply) }
                                        } catch (e: Exception) {
                                            messages.add(0, "서버 연결 실패")
                                        }
                                        isLoading = false
                                    }
                                }
                            },
                            enabled = !isLoading && text.isNotBlank(),
                            modifier = Modifier.padding(end = 8.dp)
                        ) {
                            // 로딩 중일 때는 버튼 색상을 흐리게 처리
                            Text(
                                text = "➔",
                                fontSize = 24.sp,
                                color = if (isLoading) Color.Gray else Color(0xFF6D4C41)
                            )
                        }
                    }
                }

                // --- 2. 🚀 화면 정중앙 로딩 애니메이션 오버레이 ---
                if (isLoading) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(Color(0x33000000)), // 약간 어두운 반투명 배경 (옵션)
                        contentAlignment = Alignment.Center
                    ) {
                        LottieAnimation(
                            composition = composition,
                            iterations = LottieConstants.IterateForever,
                            modifier = Modifier.size(100.dp) // 필요시 크기 조절 가능
                        )
                    }
                }
            }
        }
    }
}