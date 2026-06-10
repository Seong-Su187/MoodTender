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

// ── 영상 상태 관리 ────────────────────────────────────────────
const VIDEO_IDLE    = '/assets/loop_bg.webm';
const VIDEO_LOADING = '/assets/loading.mp4';

function playIdle(url = VIDEO_IDLE) {
  const videoEl     = document.getElementById('video-output');
  const loadingEl   = document.getElementById('loading-video');
  const placeholder = document.getElementById('video-placeholder');

  if (loadingEl) { loadingEl.pause(); loadingEl.style.display = 'none'; }

  videoEl.classList.remove('luma-key');
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
  loadingEl.src           = VIDEO_LOADING;
  loadingEl.style.display = 'block';
  loadingEl.play().catch(() => {});
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

  await Promise.all([loadVoices(), loadAvatars()]);
  pollStatus();
  playIdle();
});

// ── 아바타 영상 목록 ─────────────────────────────────────────
async function loadAvatars() {
  const sel = document.getElementById('avatar-select');
  if (!sel) return;
  try {
    const res = await fetch('/api/avatars');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const avatars = await res.json();
    avatars.forEach(({ name, label }) => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = label;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error('아바타 목록 로드 실패:', e);
  }

  sel.addEventListener('change', () => {
    const statusEl = document.getElementById('avatar-status');

    if (!sel.value) {
      if (statusEl) statusEl.textContent = '';
      return;
    }

    if (statusEl) statusEl.textContent = '아바타 준비 중...';
    const form = new FormData();
    form.append('avatar_name', sel.value);
    readSSE('/api/prepare_avatar', form, ({ status, error }) => {
      if (status && statusEl) statusEl.textContent = status;
      if (error && statusEl)  statusEl.textContent = `오류: ${error}`;
    }).catch(() => {});
  });
}

// ── 목소리 목록 ──────────────────────────────────────────────
async function loadVoices() {
  const sel = document.getElementById('voice-select');
  try {
    const token = localStorage.getItem('access_token');
    const res = await fetch('/api/voices', {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const voices = await res.json();
    if (!Array.isArray(voices) || voices.length === 0) throw new Error('빈 응답');
    voices.forEach(({ id, name }) => {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error('목소리 목록 로드 실패:', e);
    // 폴백: 기본 목소리 하드코딩
    [
      { id: 'ko-KR-SunHiNeural',  name: '한국어 여성 (SunHi)' },
      { id: 'ko-KR-InJoonNeural', name: '한국어 남성 (InJoon)' },
      { id: 'en-US-JennyNeural',  name: '영어 여성 (Jenny)' },
      { id: 'en-US-GuyNeural',    name: '영어 남성 (Guy)' },
    ].forEach(({ id, name }) => {
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = name;
      sel.appendChild(opt);
    });
  }
}

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
  form.append('voice', document.getElementById('voice-select').value);

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
    const speedSel = document.getElementById('speed-select');
    const speed = speedSel ? speedSel.value : '1.0';
    const reply = await generateLLMReply(userText, speed);
    appendChatMessage('assistant', reply);

    statusEl.textContent = '아바타 영상 생성 중...';
    const form = new FormData();
    form.append('text', reply);
    form.append('voice', document.getElementById('voice-select').value);
    form.append('speed', speed);
    const avatarSel = document.getElementById('avatar-select');
    if (avatarSel && avatarSel.value) form.append('avatar_name', avatarSel.value);

    // MP4 (H264) 스트리밍: 배경이 베이크된 아바타 영상을 컨트롤과 함께 재생
    videoEl.muted = false;
    videoEl.loop  = false;
    videoEl.setAttribute('controls', '');

    const MIME   = 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"';
    const useMSE = 'MediaSource' in window && MediaSource.isTypeSupported(MIME);

    if (useMSE) {
      await _generateStream(form, MIME, videoEl, placeholder, statusEl, () => playIdle());
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
          videoEl.addEventListener('ended', () => playIdle(), { once: true });
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
  bubble.textContent = text;

  row.appendChild(time);
  row.appendChild(bubble);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

async function _generateStream(form, mime, videoEl, placeholder, statusEl, onEnded) {
  const mediaSource = new MediaSource();
  const objectURL   = URL.createObjectURL(mediaSource);

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

  // 영상 종료 시 모니터 정리 후 idle로 복귀
  videoEl.addEventListener('ended', () => {
    clearTimeout(monitorId);
    if (onEnded) onEnded();
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

// ── 아바타 탭 전환 ───────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-photo').style.display = tab === 'photo' ? 'flex' : 'none';
  document.getElementById('tab-video').style.display = tab === 'video' ? 'flex' : 'none';
}

// ── 아바타 초기화 (영상 직접) ────────────────────────────────
async function initAvatarVideo() {
  const fileInput = document.getElementById('avatar-video-file');
  if (!fileInput.files.length) { alert('영상을 선택해주세요.'); return; }

  const btn      = document.getElementById('init-avatar-video-btn');
  const statusEl = document.getElementById('avatar-status');

  btn.disabled = true;

  const form = new FormData();
  form.append('file',       fileInput.files[0]);
  form.append('bbox_shift', document.getElementById('bbox-shift-v').value);

  await readSSE('/api/init_avatar_video', form, ({ status, error }) => {
    if (status) statusEl.textContent = status;
    if (error)  statusEl.textContent = `오류: ${error}`;
  });

  btn.disabled = false;
}

// ── 아바타 초기화 ────────────────────────────────────────────
async function initAvatar() {
  const fileInput = document.getElementById('avatar-file');
  if (!fileInput.files.length) { alert('사진을 선택해주세요.'); return; }

  const btn      = document.getElementById('init-avatar-btn');
  const statusEl = document.getElementById('avatar-status');
  const preview  = document.getElementById('lp-preview');

  btn.disabled = true;

  const form = new FormData();
  form.append('file',          fileInput.files[0]);
  form.append('driving_style', document.getElementById('driving-style').value);
  form.append('motion',        document.getElementById('motion').value);
  form.append('region',        document.getElementById('region').value);
  form.append('bbox_shift',    document.getElementById('bbox-shift').value);

  await readSSE('/api/init_avatar', form, ({ status, error, preview_path }) => {
    if (status)       statusEl.textContent = status;
    if (error)        statusEl.textContent = `오류: ${error}`;
    if (preview_path) {
      preview.src    = `/api/video?path=${encodeURIComponent(preview_path)}`;
      preview.hidden = false;
    }
  });

  btn.disabled = false;
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
