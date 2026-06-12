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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// 말풍선 컴포넌트
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
fun ChatScreen(userId: Int, token: String) {
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var text by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    val messages = remember { mutableStateListOf("어서오세요. 어떤 마음을 담아드릴까요?") }

    val composition by rememberLottieComposition(LottieCompositionSpec.RawRes(R.raw.loading_animation))

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Spacer(Modifier.height(12.dp))
                Text("설정", modifier = Modifier.padding(16.dp), style = MaterialTheme.typography.titleLarge)
                HorizontalDivider()
                NavigationDrawerItem(
                    label = { Text("사용 기록 권한 설정하기") },
                    selected = false,
                    onClick = {
                        context.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
                        scope.launch { drawerState.close() }
                    }
                )
            }
        }
    ) {
        Scaffold(
            topBar = {
                // 🚀 수정: title을 비우고 배경을 투명하게 하여 아이콘만 강조
                TopAppBar(
                    title = { },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Text("☰", fontSize = 24.sp, fontWeight = FontWeight.Bold)
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.Transparent)
                )
            }
        ) { padding ->
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {

                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .paint(painter = painterResource(id = R.drawable.paper_background), contentScale = ContentScale.Crop)
                        .padding(24.dp)
                ) {
                    Text(
                        text = "Order Menu",
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF4E342E),
                        modifier = Modifier.padding(bottom = 16.dp)
                    )

                    LazyColumn(modifier = Modifier.weight(1f)) {
                        items(messages) { msg ->
                            ChatBubble(msg = msg)
                        }
                    }

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(Color(0xE6FFF3E0), RoundedCornerShape(30.dp))
                            .padding(horizontal = 16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TextField(
                            value = text,
                            onValueChange = { text = it },
                            modifier = Modifier.weight(1f),
                            enabled = !isLoading,
                            colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent)
                        )
                        IconButton(onClick = {
                            if (text.isNotBlank()) {
                                isLoading = true
                                val msg = text
                                text = ""
                                messages.add("나: $msg")
                                scope.launch {
                                    try {
                                        val response = withContext(Dispatchers.IO) { RetrofitClient.instance.postChat("Bearer $token", ChatRequest(userId, msg)).execute() }
                                        response.body()?.let { messages.add(it.reply) }
                                    } catch (e: Exception) { messages.add("서버 연결 실패") }
                                    isLoading = false
                                }
                            }
                        }, enabled = !isLoading) { Text("➔", fontSize = 24.sp) }
                    }
                }

                if (isLoading) {
                    Box(
                        modifier = Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.2f)),
                        contentAlignment = Alignment.Center
                    ) {
                        LottieAnimation(
                            composition = composition,
                            iterations = LottieConstants.IterateForever,
                            modifier = Modifier.size(150.dp)
                        )
                    }
                }
            }
        }
    }
}