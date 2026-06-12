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
// 🚀 아래 두 import가 빨간 줄을 해결해 줄 핵심입니다!
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
        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp),
        horizontalAlignment = if (isUser) Alignment.End else Alignment.Start
    ) {
        Surface(
            color = bubbleColor,
            shape = RoundedCornerShape(16.dp),
            shadowElevation = 2.dp,
            modifier = Modifier.widthIn(max = 280.dp)
        ) {
            Text(text = cleanMsg, color = textColor, fontSize = 16.sp, modifier = Modifier.padding(12.dp))
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

    // 로딩 애니메이션
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
            topBar = {
                TopAppBar(
                    title = { },
                    navigationIcon = { IconButton(onClick = { scope.launch { drawerState.open() } }) { Text("☰", fontSize = 24.sp, fontWeight = FontWeight.Bold) } },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent)
                )
            }
        ) { padding ->
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .paint(painter = painterResource(id = R.drawable.paper_background), contentScale = ContentScale.Crop)
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    LazyColumn(
                        modifier = Modifier.weight(1f).fillMaxWidth(),
                        contentPadding = PaddingValues(vertical = 8.dp)
                    ) {
                        items(messages) { msg -> ChatBubble(msg = msg) }
                    }

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
                            enabled = !isLoading,
                            colors = TextFieldDefaults.colors(
                                focusedContainerColor = Color.Transparent,
                                unfocusedContainerColor = Color.Transparent,
                                focusedIndicatorColor = Color.Transparent,
                                unfocusedIndicatorColor = Color.Transparent
                            )
                        )

                        if (isLoading) {
                            LottieAnimation(composition = composition, iterations = LottieConstants.IterateForever, modifier = Modifier.size(50.dp).padding(4.dp))
                        } else {
                            IconButton(
                                onClick = {
                                    if (text.isNotBlank()) {
                                        isLoading = true
                                        val msg = text
                                        text = ""
                                        messages.add("나: $msg")
                                        scope.launch {
                                            try {
                                                val response = withContext(Dispatchers.IO) { RetrofitClient.instance.postChat(ChatRequest(userId, msg)).execute() }
                                                response.body()?.let { messages.add(it.reply) }
                                            } catch (e: Exception) { messages.add("서버 연결 실패") }
                                            isLoading = false
                                        }
                                    }
                                },
                                enabled = !isLoading,
                                modifier = Modifier.padding(end = 8.dp)
                            ) {
                                Text("➔", fontSize = 24.sp, color = Color(0xFF6D4C41))
                            }
                        }
                    }
                }
            }
        }
    }
}