// ── 인증 체크 ────────────────────────────────────────────────
(function checkAuth() {
  if (!localStorage.getItem('access_token')) {
    window.location.href = '/login';
  }
  const username = localStorage.getItem('username');
  if (username) {
    const badge = document.getElementById('username-badge');
    if (badge) badge.textContent = username + ' 님';
  }
})();

// Redis 블랙리스트 연동 로그아웃
let isModelReady = false;
const DEFAULT_VOICE = 'onyx';

// ── 영상 상태 관리 ────────────────────────────────────────────
const VIDEO_IDLE           = '/assets/loop_bg.mp4?v=3';
const VIDEO_LOADING_START  = '/assets/loading_start.mp4?v=3';
const VIDEO_LOADING_FINISH = '/assets/loading_finish.mp4?v=3';
const IDLE_RETURN_DELAY_MS = 700; // 응답 영상 종료 후 idle 루프 전환까지 여백

function playIdle(url = VIDEO_IDLE) {
  const videoEl     = document.getElementById('video-output');
  const loadingEl   = document.getElementById('loading-video');
  const placeholder = document.getElementById('video-placeholder');

  // 이전 응답 영상의 MediaSource blob URL 해제 (버퍼 누적 방지)
  if (videoEl.src && videoEl.src.startsWith('blob:')) {
    URL.revokeObjectURL(videoEl.src);
  }

  if (loadingEl) { loadingEl.pause(); loadingEl.style.display = 'none'; }

  videoEl.classList.remove('luma-key');
  videoEl.classList.add('idle');
  videoEl.removeAttribute('controls');
  videoEl.muted         = true;
  videoEl.loop          = true;
  videoEl.src           = url;
  videoEl.style.display = 'block';
  if (placeholder) placeholder.style.display = 'none';
  videoEl.play().catch(() => {});
}

function playLoading() {
  const loadingEl = document.getElementById('loading-video');
  if (!loadingEl) return;
  loadingEl.loop          = true;
  loadingEl.src           = VIDEO_LOADING_START;
  loadingEl.style.display = 'block';
  loadingEl.currentTime   = 0;
  loadingEl.play().catch(() => {});
}

// 응답 영상 종료 → 마무리 영상 재생 → idle 루프로 복귀
function playFinishThenIdle() {
  const loadingEl = document.getElementById('loading-video');
  if (!loadingEl) { playIdle(); return; }

  loadingEl.loop          = false;
  loadingEl.src           = VIDEO_LOADING_FINISH;
  loadingEl.style.display = 'block';
  loadingEl.currentTime   = 0;

  const goIdle = () => playIdle();
  loadingEl.addEventListener('ended', goIdle, { once: true });
  loadingEl.addEventListener('error', goIdle, { once: true });
  loadingEl.play().catch(goIdle);
}

async function logout() {
  const token = localStorage.getItem('access_token');
  if (token) {
    try {
      await fetch('/api/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
    } catch (e) { console.error("로그아웃 통신 에러:", e); }
  }
  localStorage.removeItem('access_token');
  localStorage.removeItem('username');
  window.location.href = '/login';
}

// ── 초기화 ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) logoutBtn.addEventListener('click', logout);

  pollStatus();
  playIdle();
});

// ── 모델 상태 폴링 (2초) ─────────────────────────────────────
async function pollStatus() {
  try {
    const data = await fetch('/api/status').then(r => r.json());
    applyModelState(data);
  } catch (_) {}
  setTimeout(pollStatus, 2000);
}

function applyModelState({ ready, status, error, loading }) {
  const statusEl = document.getElementById('model-status-text');
  const loadBtn  = document.getElementById('load-model-btn');
  const genBtn   = document.getElementById('generate-btn');

  isModelReady = Boolean(ready);
  statusEl.textContent = status;

  if (ready) {
    statusEl.className = 'ready';
    loadBtn.style.display = 'none';
    genBtn.disabled  = false;
  } else if (error) {
    statusEl.className  = 'error';
    loadBtn.disabled    = false;
    genBtn.disabled     = true;
    loadBtn.textContent = '재시도';
  } else if (loading) {
    statusEl.className  = '';
    loadBtn.disabled    = true;
    genBtn.disabled     = true;
    loadBtn.textContent = '로딩 중...';
  }
}

// ── 모델 로드 ────────────────────────────────────────────────
async function loadModel() {
  const loadBtn = document.getElementById('load-model-btn');
  loadBtn.disabled    = true;
  loadBtn.textContent = '로딩 중...';

  await fetch('/api/load_model', { method: 'POST' });

  const es = new EventSource('/api/load_model/stream');
  es.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    document.getElementById('model-status-text').textContent = msg.status;
    if (msg.ready || msg.error) {
      es.close();
      applyModelState(msg);
    }
  };
  es.onerror = () => es.close();
}

// ── 영상 생성 (스트리밍 MSE) ─────────────────────────────────
async function generate() {
  let text = document.getElementById('text-input').value.trim();
  if (!text) return;

  const genBtn      = document.getElementById('generate-btn');
  const statusEl    = document.getElementById('gen-status');
  const videoEl     = document.getElementById('video-output');
  const placeholder = document.getElementById('video-placeholder');

  genBtn.disabled      = true;
  statusEl.textContent = '생성 중...';

  try {
    statusEl.textContent = 'AI 답변 생성 중...';
    text = await generateLLMReply(text);
  } catch (e) {
    statusEl.textContent = `OpenAI 오류: ${e.message}`;
    genBtn.disabled = !isModelReady;
    return;
  }

  const form = new FormData();
  form.append('text',  text);
  form.append('voice', DEFAULT_VOICE);

  const MIME   = 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"';
  const useMSE = 'MediaSource' in window && MediaSource.isTypeSupported(MIME);

  if (useMSE) {
    await _generateStream(form, MIME, videoEl, placeholder, statusEl);
  } else {
    await readSSE('/api/generate', form, ({ status, error, video_path }) => {
      if (status)     statusEl.textContent = status;
      if (error)      statusEl.textContent = `오류: ${error}`;
      if (video_path) {
        videoEl.src               = `/api/video?path=${encodeURIComponent(video_path)}`;
        videoEl.style.display     = 'block';
        placeholder.style.display = 'none';
        videoEl.play();
      }
    });
  }

  genBtn.disabled = false;
}

async function generateLLMReply(text, speed = '1.0') {
  const response = await fetch('/api/llm/respond', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ text, speed: Number(speed) })
  });

  let data = {};
  try {
    data = await response.json();
  } catch (_) {}

  if (!response.ok) {
    throw new Error(data.detail || '답변 생성에 실패했습니다.');
  }

  return data.reply;
}

async function generateChat() {
  const input       = document.getElementById('text-input');
  const genBtn      = document.getElementById('generate-btn');
  const statusEl    = document.getElementById('gen-status');
  const videoEl     = document.getElementById('video-output');
  const placeholder = document.getElementById('video-placeholder');
  const userText    = input.value.trim();

  if (!userText || genBtn.disabled) return;

  appendChatMessage('user', userText);
  input.value = '';
  genBtn.disabled = true;
  playLoading();

  try {
    statusEl.textContent = 'AI 답변 생성 중...';
    const speed = '1.0';
    const reply = await generateLLMReply(userText, speed);
    appendChatMessage('assistant', reply);

    statusEl.textContent = '아바타 영상 생성 중...';
    const form = new FormData();
    form.append('text', reply);
    form.append('voice', DEFAULT_VOICE);
    form.append('speed', speed);

    // MP4 (H264) 스트리밍: 배경이 베이크된 아바타 영상 재생
    videoEl.muted = false;
    videoEl.loop  = false;

    const MIME   = 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"';
    const useMSE = 'MediaSource' in window && MediaSource.isTypeSupported(MIME);

    if (useMSE) {
      await _generateStream(form, MIME, videoEl, placeholder, statusEl, () => playFinishThenIdle());
    } else {
      await readSSE('/api/generate', form, ({ status, error, video_path }) => {
        if (status) statusEl.textContent = status;
        if (error) {
          statusEl.textContent = `오류: ${error}`;
          appendChatMessage('system', error);
          return;
        }
        if (video_path) {
          videoEl.src               = `/api/video?path=${encodeURIComponent(video_path)}`;
          videoEl.style.display     = 'block';
          placeholder.style.display = 'none';
          videoEl.play().catch(() => {});
          videoEl.addEventListener('play', () => {
            const loadingEl = document.getElementById('loading-video');
            if (loadingEl) { loadingEl.pause(); loadingEl.style.display = 'none'; }
          }, { once: true });
          videoEl.addEventListener('ended', () => setTimeout(playFinishThenIdle, IDLE_RETURN_DELAY_MS), { once: true });
        }
      });
    }
  } catch (e) {
    statusEl.textContent = `오류: ${e.message}`;
    appendChatMessage('system', e.message);
    playIdle();
  } finally {
    genBtn.disabled = !isModelReady;
    input.focus();
  }
}

function appendChatMessage(role, text) {
  const log = document.getElementById('chat-log');
  if (!log) return;

  const row = document.createElement('div');
  row.className = `message-row ${role}`;

  const time = document.createElement('div');
  time.className = 'message-time';
  time.textContent = '방금 전';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  row.appendChild(time);
  row.appendChild(bubble);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;

  // AI 응답은 한 글자씩 타이핑, 나머지는 즉시 표시
  if (role === 'assistant') {
    typeText(bubble, text, log);
  } else {
    bubble.textContent = text;
    log.scrollTop = log.scrollHeight;
  }
}

// ── AI 타이핑 효과 ───────────────────────────────────────────
function typeText(el, text, log) {
  el.classList.add('typing');
  let i = 0;
  const speed = 26; // 글자당 ms

  (function step() {
    if (i <= text.length) {
      el.textContent = text.slice(0, i);
      log.scrollTop = log.scrollHeight;
      i += 1;
      setTimeout(step, speed);
    } else {
      el.classList.remove('typing');
    }
  })();
}

async function _generateStream(form, mime, videoEl, placeholder, statusEl, onEnded) {
  const mediaSource = new MediaSource();
  const objectURL   = URL.createObjectURL(mediaSource);

  videoEl.classList.remove('idle');
  videoEl.src               = objectURL;
  videoEl.style.display     = 'block';
  placeholder.style.display = 'none';

  await new Promise(resolve =>
    mediaSource.addEventListener('sourceopen', resolve, { once: true })
  );

  const sb          = mediaSource.addSourceBuffer(mime);
  const appendQueue = [];
  let   appending   = false;
  let   streamDone  = false;

  function flushQueue() {
    if (appending || appendQueue.length === 0 || mediaSource.readyState !== 'open') return;
    appending = true;
    sb.appendBuffer(appendQueue.shift());
  }

  sb.addEventListener('updateend', () => {
    appending = false;
    if (streamDone && appendQueue.length === 0) {
      try { mediaSource.endOfStream(); statusEl.textContent = '완료!'; } catch (_) {}
    } else {
      flushQueue();
    }
  });
  sb.addEventListener('error', e => console.error('[MSE]', e));

  videoEl.addEventListener('play', () => {
    const loadingEl = document.getElementById('loading-video');
    if (loadingEl) { loadingEl.pause(); loadingEl.style.display = 'none'; }
  }, { once: true });

  // 영상 종료 시 모니터 정리 후 여백을 두고 idle로 복귀
  videoEl.addEventListener('ended', () => {
    clearTimeout(monitorId);
    setTimeout(() => { if (onEnded) onEnded(); }, IDLE_RETURN_DELAY_MS);
  }, { once: true });

  // 버퍼 직접 모니터링
  const PAUSE_THRESHOLD  = 0.05;
  const RESUME_THRESHOLD = 1.0;
  let monitorId  = null;
  let started    = false;
  let playAllowed = false;

  function monitorBuffer() {
    if (!started || videoEl.ended) return;
    const buf = videoEl.buffered;
    if (buf.length > 0) {
      const ahead = buf.end(buf.length - 1) - videoEl.currentTime;
      if (!streamDone) {
        // 스트리밍 중: 임계값으로 일시정지/재개
        if (!videoEl.paused && ahead < PAUSE_THRESHOLD) {
          videoEl.pause();
          statusEl.textContent = '버퍼링 중...';
        } else if (videoEl.paused && playAllowed && ahead >= RESUME_THRESHOLD) {
          videoEl.play().catch(() => {});
          statusEl.textContent = '재생 중...';
        }
      } else if (videoEl.paused && playAllowed) {
        // 스트림 완료 후: paused 상태면 무조건 재생해서 ended 이벤트 발생시킴
        videoEl.play().catch(() => {});
        statusEl.textContent = '완료!';
      }
    }
    monitorId = setTimeout(monitorBuffer, 200);
  }

  const response = await fetch('/api/generate_stream', {
    method:  'POST',
    body:    form,
    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
  });

  if (!response.ok) {
    let message = '영상 생성에 실패했습니다.';
    try {
      const data = await response.json();
      if (data.error) message = data.error;
    } catch (_) {}
    statusEl.textContent = `오류: ${message}`;
    appendChatMessage('system', message);
    playIdle();
    return;
  }

  const reader = response.body.getReader();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    appendQueue.push(value);
    flushQueue();

    if (!started) {
      started = true;
      statusEl.textContent = '버퍼링 중...';
      monitorBuffer();
      playAllowed = true;
    }
  }

  streamDone = true;
  if (!appending && appendQueue.length === 0 && mediaSource.readyState === 'open') {
    try { mediaSource.endOfStream(); statusEl.textContent = '완료!'; } catch (_) {}
  }
  // 스트림 완료 즉시: 끝부분에서 멈춰있으면 바로 재개
  if (videoEl.paused && playAllowed) {
    const buf = videoEl.buffered;
    if (buf.length > 0 && buf.end(buf.length - 1) - videoEl.currentTime > 0) {
      videoEl.play().catch(() => {});
      statusEl.textContent = '완료!';
    }
  }
}

// ── 마이크 STT ───────────────────────────────────────────────
(function setupMic() {
  const btn    = document.getElementById('mic-btn');
  const icon   = btn ? btn.querySelector('.icon-mic') : null;
  if (!btn) return;

  let mediaRecorder = null;
  let chunks        = [];
  let recording     = false;

  btn.addEventListener('click', async () => {
    if (!recording) {
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        alert('마이크 접근 권한이 필요합니다.');
        return;
      }

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      chunks        = [];
      mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        btn.disabled      = true;
        btn.title         = '처리 중...';
        if (icon) icon.textContent = '⏳';

        const blob     = new Blob(chunks, { type: mimeType });
        const formData = new FormData();
        formData.append('audio', blob, 'audio.webm');

        try {
          const res  = await fetch('/api/stt', {
            method:  'POST',
            headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` },
            body:    formData,
          });
          const data = await res.json();
          if (res.ok && data.text) {
            document.getElementById('text-input').value = data.text;
            generateChat();
          } else {
            alert(data.detail || 'STT 오류가 발생했습니다.');
          }
        } catch {
          alert('서버와 통신 중 오류가 발생했습니다.');
        } finally {
          btn.disabled      = false;
          btn.title         = '음성 입력';
          if (icon) icon.textContent = '';
          btn.classList.remove('recording');
        }
      };

      mediaRecorder.start();
      recording = true;
      btn.classList.add('recording');
      btn.title = '클릭하여 녹음 중지';
    } else {
      mediaRecorder.stop();
      recording = false;
    }
  });
})();

// ── 세로 영상 비율 자동 감지 ─────────────────────────────────
(function setupVideoAspect() {
  const videoEl = document.getElementById('video-output');
  if (!videoEl) return;
  videoEl.addEventListener('loadedmetadata', () => {
    if (videoEl.videoHeight > videoEl.videoWidth) {
      videoEl.classList.add('portrait');
    } else {
      videoEl.classList.remove('portrait');
    }
  });
})();

// ── SSE 유틸 ─────────────────────────────────────────────────
async function readSSE(url, formData, onMessage) {
  const res    = await fetch(url, {
    method: 'POST',
    body:   formData,
    headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
  });
  const reader = res.body.getReader();
  const dec    = new TextDecoder();
  let   buf    = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const msg = JSON.parse(line.slice(6));
      onMessage(msg);
      if (msg.done || msg.error) return;
    }
  }
}
