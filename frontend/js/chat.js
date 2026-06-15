// =============================================
// chat.js — 채팅 패널, 메뉴/음악 선택, 대화 종료
// =============================================

let selectedCocktail = null;
let activeMusicPlayback = null;

function switchPanelTab(btn, tabName) {
  document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
  btn.classList.add('active');
  document.getElementById('tab-' + tabName).style.display = 'flex';
}

function toggleOrderPanel() {
  const panel = document.querySelector('.chat-panel');
  const isOpen = panel.classList.contains('open');
  if (isOpen) {
    closeOrderPanel();
  } else {
    panel.classList.add('open');
    document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.panel-tab')[1].classList.add('active');
    document.getElementById('tab-menu').style.display = 'flex';
  }
}

function closeOrderPanel() {
  document.querySelector('.chat-panel').classList.remove('open');
}

function selectCocktail(el) {
  const cocktail = el.dataset.cocktail;
  const emotion = el.dataset.emotion;
  selectedCocktail = { name: cocktail, emotion: emotion };
  const chatTab = document.querySelector('.panel-tab:first-child');
  switchPanelTab(chatTab, 'chat');
  const input = document.getElementById('text-input');
  input.value = `오늘은 ${cocktail}을 주세요!`;
  generateChat();
}

function selectMusic(el) {
  const music = {
    title: el.dataset.title,
    meta: el.dataset.meta,
    src: el.dataset.src,
    message: el.dataset.message.split('\\n').join('\n')
  };
  const chatTab = document.querySelector('.panel-tab:first-child');
  switchPanelTab(chatTab, 'chat');
  appendMusicSelection(music);
}

function getMusicDuration(meta) {
  const match = meta.match(/(\d+):(\d+)$/);
  if (!match) return 180;
  return Number(match[1]) * 60 + Number(match[2]);
}

function formatMusicTime(seconds) {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  return `${minutes}:${String(safeSeconds % 60).padStart(2, '0')}`;
}

function stopMusicPlayback() {
  if (!activeMusicPlayback) return;
  activeMusicPlayback.audio.pause();
  activeMusicPlayback.audio.currentTime = 0;
  activeMusicPlayback.button.classList.remove('playing');
  activeMusicPlayback.button.textContent = '▶';
  activeMusicPlayback.button.setAttribute('aria-label', '음악 재생');
  activeMusicPlayback.progress.style.width = '0%';
  activeMusicPlayback.currentTime.textContent = '0:00';
  activeMusicPlayback = null;
}

async function toggleMusicPlayback(button, music, progress, currentTime) {
  if (activeMusicPlayback?.button === button) {
    if (activeMusicPlayback.audio.paused) {
      await activeMusicPlayback.audio.play();
      button.classList.add('playing');
      button.textContent = 'Ⅱ';
      button.setAttribute('aria-label', '음악 일시정지');
    } else {
      activeMusicPlayback.audio.pause();
      button.classList.remove('playing');
      button.textContent = '▶';
      button.setAttribute('aria-label', '음악 계속 재생');
    }
    return;
  }

  stopMusicPlayback();

  const audio = new Audio(music.src);
  audio.preload = 'metadata';
  audio.addEventListener('timeupdate', () => {
    const duration = Number.isFinite(audio.duration)
      ? audio.duration
      : getMusicDuration(music.meta);
    progress.style.width = `${(audio.currentTime / duration) * 100}%`;
    currentTime.textContent = formatMusicTime(audio.currentTime);
  });
  audio.addEventListener('ended', () => {
    if (activeMusicPlayback?.audio === audio) stopMusicPlayback();
  });
  audio.addEventListener('error', () => {
    if (activeMusicPlayback?.audio === audio) stopMusicPlayback();
    showToast('음악 파일을 재생하지 못했습니다.', '!');
  });

  button.classList.add('playing');
  button.textContent = 'Ⅱ';
  button.setAttribute('aria-label', '음악 일시정지');
  activeMusicPlayback = { audio, button, progress, currentTime };
  try {
    await audio.play();
  } catch (_) {
    stopMusicPlayback();
    showToast('음악 재생을 시작하지 못했습니다.', '!');
  }
}

function appendMusicSelection(music) {
  const log = document.getElementById('chat-log');
  if (!log) return;

  const row = document.createElement('div');
  row.className = 'message-row assistant music-selection-message';

  const time = document.createElement('div');
  time.className = 'message-time';
  time.textContent = '방금 전';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble music-selection-bubble';

  const card = document.createElement('div');
  card.className = 'selected-music-card';

  const cardInfo = document.createElement('div');
  cardInfo.className = 'selected-music-info';

  const title = document.createElement('strong');
  title.textContent = music.title;

  const meta = document.createElement('span');
  meta.textContent = music.meta;

  const actions = document.createElement('div');
  actions.className = 'selected-music-player';

  const playButton = document.createElement('button');
  playButton.type = 'button';
  playButton.className = 'music-play-btn';
  playButton.setAttribute('aria-label', '음악 재생');
  playButton.title = '음악 재생';
  playButton.textContent = '▶';

  const progressTrack = document.createElement('div');
  progressTrack.className = 'music-progress-track';

  const progress = document.createElement('span');
  progress.className = 'music-progress-value';
  progressTrack.appendChild(progress);

  const playbackTime = document.createElement('div');
  playbackTime.className = 'music-playback-time';

  const currentTime = document.createElement('span');
  currentTime.textContent = '0:00';

  const totalTime = document.createElement('span');
  totalTime.textContent = formatMusicTime(getMusicDuration(music.meta));

  playbackTime.appendChild(currentTime);
  playbackTime.appendChild(totalTime);
  playButton.addEventListener('click', () => {
    toggleMusicPlayback(playButton, music, progress, currentTime);
  });

  const copyButton = document.createElement('button');
  copyButton.type = 'button';
  copyButton.className = 'music-copy-btn';
  copyButton.setAttribute('aria-label', '음악 정보 복사');
  copyButton.title = '음악 정보 복사';
  copyButton.innerHTML = '<span></span>';
  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(`${music.title}\n${music.meta}`);
      showToast('음악 정보가 복사되었습니다.', '♪');
    } catch (_) {
      showToast('음악 정보를 복사하지 못했습니다.', '!');
    }
  });

  cardInfo.appendChild(title);
  cardInfo.appendChild(meta);
  actions.appendChild(playButton);
  actions.appendChild(progressTrack);
  actions.appendChild(playbackTime);
  cardInfo.appendChild(actions);
  card.appendChild(cardInfo);
  card.appendChild(copyButton);
  bubble.appendChild(card);
  row.appendChild(time);
  row.appendChild(bubble);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
  appendChatMessage('assistant', music.message);
}

async function endConversation() {
  const btn = document.querySelector('.end-chat-btn');
  if (btn) { btn.disabled = true; btn.textContent = '처리 중…'; }

  try {
    const token = localStorage.getItem('access_token');

    if (selectedCocktail) {
      await fetch('/api/emotion/receipts/select-cocktail', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          emotion: selectedCocktail.emotion,
          cocktail_name: selectedCocktail.name
        })
      });
      selectedCocktail = null;
    } else {
      await fetch('/api/llm/receipt', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        }
      });
    }
  } catch (e) {
    console.error('영수증 발급 실패:', e);
  }

  if (btn) { btn.disabled = false; btn.textContent = '대화 종료 · 영수증 발급'; }

  closeOrderPanel();
  if (typeof closeSidebar === 'function') closeSidebar();
  document.getElementById('receipt-modal').style.display = 'flex';

  await loadReceiptData();

  const today = new Date();
  receiptYear = today.getFullYear();
  receiptMonth = today.getMonth();
  renderReceiptCalendar();

  const pad = n => String(n).padStart(2, '0');
  const todayStr = `${today.getFullYear()}-${pad(today.getMonth()+1)}-${pad(today.getDate())}`;

  if (receiptData[todayStr]) {
    const cells = document.querySelectorAll('#receipt-cal-days .cal-day');
    cells.forEach(cell => {
      const num = parseInt(cell.querySelector('span')?.textContent);
      if (num === today.getDate() && cell.classList.contains('has-receipt')) {
        cell.classList.add('selected');
        cell.style.background = `${cell.dataset.emotionColor}55`;
        cell.style.color = '#fff3da';
      }
    });
    openReceiptCard(todayStr, receiptData[todayStr]);
  }
}
