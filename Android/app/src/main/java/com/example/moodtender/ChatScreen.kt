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
                TopAppBar(
                    title = { Text("오늘의 마음", fontWeight = FontWeight.Bold) },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) { Text("☰") }
                    }
                )
            }
        ) { padding ->
            Column(modifier = Modifier.fillMaxSize().padding(padding).paint(painter = painterResource(id = R.drawable.paper_background), contentScale = ContentScale.Crop).padding(24.dp)) {
                LazyColumn(modifier = Modifier.weight(1f)) {
                    items(messages) { msg -> Text(text = msg, color = Color(0xFF4E342E), fontSize = 18.sp, modifier = Modifier.padding(vertical = 8.dp)) }
                }
                Row(modifier = Modifier.fillMaxWidth().background(Color(0xE6FFF3E0), RoundedCornerShape(30.dp)).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                    TextField(value = text, onValueChange = { text = it }, modifier = Modifier.weight(1f), enabled = !isLoading, colors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent))
                    if (isLoading) LottieAnimation(composition = composition, iterations = LottieConstants.IterateForever, modifier = Modifier.size(50.dp))
                    else IconButton(onClick = {
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
                    }) { Text("➔", fontSize = 24.sp) }
                }
            }
        }
    }
}