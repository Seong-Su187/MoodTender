// =============================================
// receipt.js — 감정 영수증 달력 & 모달
// =============================================

let receiptYear = new Date().getFullYear();
let receiptMonth = new Date().getMonth();
let receiptData = {};
let currentReceiptDate = null;
let currentReceiptIndex = 0;

const emotionColorMap = {
  '기쁨': '#f4923a', '우울': '#4a7fc1', '불안': '#9b59b6',
  '분노': '#e74c3c', '지침': '#d4b800', '외로움': '#a0aabf', '평온': '#27ae60',
  '경사·축하': '#f4923a', '통쾌·후련': '#f4923a', '뿌듯·성취': '#f4923a',
  '설렘·기대': '#f4923a', '소소·만족': '#f4923a', '반가움·재회': '#f4923a',
  '벅참·감동': '#f4923a', '홀가분함': '#f4923a', '활기·에너지': '#f4923a', '낭만·황홀': '#f4923a',
  '가라앉음·무기력': '#4a7fc1', '자책·후회': '#4a7fc1', '서러움·눈물': '#4a7fc1',
  '공허·허전': '#4a7fc1', '실망·좌절': '#4a7fc1', '상실감': '#4a7fc1',
  '비관·절망': '#4a7fc1', '씁쓸함': '#4a7fc1', '미련': '#4a7fc1', '위축·열등감': '#4a7fc1',
  '초조·긴장': '#9b59b6', '막막·답답': '#9b59b6', '걱정·근심': '#9b59b6',
  '혼란·복잡': '#9b59b6', '두려움·공포': '#9b59b6', '조급함': '#9b59b6',
  '과민·예민': '#9b59b6', '강박·집착': '#9b59b6', '의심·불신': '#9b59b6',
  '욱·폭발': '#e74c3c', '답답·울화': '#e74c3c', '짜증·신경질': '#e74c3c',
  '억울·분개': '#e74c3c', '배신감': '#e74c3c', '증오·미움': '#e74c3c',
  '질투·시기': '#e74c3c', '반항·적대': '#e74c3c',
  '탈진·소진': '#d4b800', '압박·짓눌림': '#d4b800', '수면부족·피로': '#d4b800',
  '감정노동·사람에 치임': '#d4b800', '무의미·권태': '#d4b800', '현실도피': '#d4b800',
  '고립·단절': '#a0aabf', '그리움·회상': '#a0aabf', '소외·겉돎': '#a0aabf',
  '쓸쓸·적막': '#a0aabf', '몰이해': '#a0aabf', '향수병': '#a0aabf',
  '버려짐': '#a0aabf', '짝사랑': '#a0aabf', '이별·상실': '#a0aabf', '군중 속 고독': '#a0aabf',
  '담담·무던': '#27ae60', '여유·느긋': '#27ae60', '안도·다행': '#27ae60',
  '홀가분·가벼움': '#27ae60', '위안·포근함': '#27ae60', '감사·충만함': '#27ae60',
  '수용·인정': '#27ae60', '집중·몰입': '#27ae60', '나른함': '#27ae60',
  '비워냄': '#27ae60', '조화·균형': '#27ae60',
};

function getEmotionColor(emotion) {
  if (!emotion) return '#c8902e';
  if (emotionColorMap[emotion]) return emotionColorMap[emotion];
  for (const [key, color] of Object.entries(emotionColorMap)) {
    if (emotion.includes(key) || key.includes(emotion)) return color;
  }
  return '#c8902e';
}

const subToMainMap = {
  '경사·축하':'기쁨','통쾌·후련':'기쁨','뿌듯·성취':'기쁨','설렘·기대':'기쁨',
  '소소·만족':'기쁨','반가움·재회':'기쁨','벅참·감동':'기쁨','홀가분함':'기쁨',
  '활기·에너지':'기쁨','낭만·황홀':'기쁨',
  '가라앉음·무기력':'우울','자책·후회':'우울','서러움·눈물':'우울','공허·허전':'우울',
  '실망·좌절':'우울','상실감':'우울','비관·절망':'우울','씁쓸함':'우울',
  '미련':'우울','위축·열등감':'우울',
  '초조·긴장':'불안','막막·답답':'불안','걱정·근심':'불안','혼란·복잡':'불안',
  '두려움·공포':'full_anxiety','조급함':'불안','과민·예민':'불안','강박·집착':'불안','의심·불신':'불안',
  '욱·폭발':'분노','답답·울화':'분노','짜증·신경질':'분노','억울·분개':'분노',
  '배신감':'분노','증오·미움':'분노','질투·시기':'분노','반항·적대':'분노',
  '탈진·소진':'지침','압박·짓눌림':'지침','수면부족·피로':'지침',
  '감정노동·사람에 치임':'지침','무의미·권태':'지침','현실도피':'지침',
  '고립·단절':'외로움','그리움·회상':'외로움','소외·겉돎':'외로움','쓸쓸·적막':'외로움',
  '몰이해':'외로움','향수병':'외로움','버려짐':'외로움','짝사랑':'외로움',
  '이별·상실':'외로움','군중 속 고독':'외로움',
  '담담·무던':'평온','여유·느긋':'평온','안도·다행':'평온','홀가분·가벼움':'평온',
  '위안·포근함':'평온','감사·충만함':'평온','수용·인정':'평온','집중·몰입':'평온',
  '나른함':'평온','비워냄':'평온','조화·균형':'평온',
};

function getMainCategory(sub) {
  return subToMainMap[sub] || null;
}

function getWeatherEmoji(weather) {
  if (!weather) return '';
  if (weather.includes('맑')) return '☀️';
  if (weather.includes('흐')) return '☁️';
  if (weather.includes('구름')) return '⛅';
  if (weather.includes('비')) return '🌧️';
  if (weather.includes('눈')) return '❄️';
  if (weather.includes('바람')) return '💨';
  if (weather.includes('안개')) return '🌫️';
  return '🌤️';
}

function formatReceiptDate(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  const days = ['일', '월', '화', '수', '목', '금', '토'];
  return `${y}년 ${m}월 ${d}일 (${days[date.getDay()]})`;
}

function renderMonthSummary() {
  const el = document.getElementById('receipt-month-summary');
  if (!el) return;
  const pad = n => String(n).padStart(2, '0');
  const prefix = `${receiptYear}-${pad(receiptMonth + 1)}`;
  const counts = {};
  Object.entries(receiptData).forEach(([dateStr, list]) => {
    if (!dateStr.startsWith(prefix)) return;
    const data = list[0];
    const main = getMainCategory(data.dominant_sub_category) || data.dominant_sub_category;
    if (main) counts[main] = (counts[main] || 0) + 1;
  });
  if (Object.keys(counts).length === 0) {
    el.innerHTML = '<span class="summary-empty">이번 달 감정 기록이 없어요</span>';
    return;
  }
  const rows = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, cnt]) => {
      const color = getEmotionColor(cat);
      return `<div class="summary-item">
        <span class="summary-dot" style="background:${color}"></span>
        <span class="summary-label">${cat}</span>
        <span class="summary-count">${cnt}일</span>
      </div>`;
    }).join('');
  el.innerHTML = `<div class="summary-title">이번 달 감정</div>${rows}`;
}

async function openReceiptModal() {
  document.getElementById('receipt-modal').style.display = 'flex';
  closeSidebar();
  await loadReceiptData();
  renderReceiptCalendar();
}

function closeReceiptModal() {
  document.getElementById('receipt-modal').style.display = 'none';
  closeReceiptCard();
}

async function loadReceiptData() {
  try {
    const token = localStorage.getItem('access_token');
    const res = await fetch('/api/emotion/receipts', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const data = await res.json();
      receiptData = {};
      (data.receipts || []).forEach(r => {
        if (!receiptData[r.receipt_date]) receiptData[r.receipt_date] = [];
        receiptData[r.receipt_date].push(r);
      });
    }
  } catch (e) {
    receiptData = {};
  }
}

function changeReceiptMonth(dir) {
  receiptMonth += dir;
  if (receiptMonth > 11) { receiptMonth = 0; receiptYear++; }
  if (receiptMonth < 0)  { receiptMonth = 11; receiptYear--; }
  hideReceiptContent();
  renderReceiptCalendar();
}

function renderReceiptCalendar() {
  const label = document.getElementById('receipt-month-label');
  label.textContent = `${receiptYear}년 ${receiptMonth + 1}월`;

  const container = document.getElementById('receipt-cal-days');
  container.innerHTML = '';

  const firstDay = new Date(receiptYear, receiptMonth, 1).getDay();
  const daysInMonth = new Date(receiptYear, receiptMonth + 1, 0).getDate();

  for (let i = 0; i < firstDay; i++) {
    const blank = document.createElement('div');
    blank.className = 'cal-day empty';
    container.appendChild(blank);
  }

  const today = new Date();
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${receiptYear}-${String(receiptMonth + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const isToday = d === today.getDate() && receiptMonth === today.getMonth() && receiptYear === today.getFullYear();
    const hasReceipt = !!receiptData[dateStr];
    const cell = document.createElement('div');
    cell.className = 'cal-day' + (hasReceipt ? ' has-receipt' : '') + (isToday ? ' is-today' : '');

    if (hasReceipt) {
      const color = getEmotionColor(receiptData[dateStr][0].dominant_sub_category);
      cell.dataset.emotionColor = color;
      cell.style.background = `${color}25`;
      cell.style.border = `1px solid ${color}66`;
      cell.style.color = color;
    }

    const numSpan = document.createElement('span');
    numSpan.textContent = d;
    cell.appendChild(numSpan);

    if (hasReceipt) {
      const dot = document.createElement('span');
      dot.className = 'receipt-dot';
      dot.style.background = cell.dataset.emotionColor;
      cell.appendChild(dot);
    }

    cell.style.cursor = 'pointer';
    cell.onclick = () => {
      if (cell.classList.contains('selected')) {
        cell.classList.remove('selected');
        if (hasReceipt) {
          const c = cell.dataset.emotionColor;
          cell.style.background = `${c}25`;
          cell.style.color = c;
        }
        hideReceiptContent();
      } else {
        document.querySelectorAll('.cal-day.selected').forEach(el => {
          el.classList.remove('selected');
          if (el.dataset.emotionColor) {
            el.style.background = `${el.dataset.emotionColor}25`;
            el.style.color = el.dataset.emotionColor;
          }
        });
        cell.classList.add('selected');
        if (hasReceipt) {
          const c = cell.dataset.emotionColor;
          cell.style.background = `${c}55`;
          cell.style.color = '#fff3da';
        }
        openReceiptCard(dateStr, receiptData[dateStr] || null);
      }
    };
    container.appendChild(cell);
  }
  renderMonthSummary();
}

function hideReceiptContent() {
  document.getElementById('receipt-empty-state').style.display = 'flex';
  document.getElementById('receipt-detail').style.display = 'none';
  document.getElementById('receipt-no-data').style.display = 'none';
}

function closeReceiptCard() {
  hideReceiptContent();
  document.querySelectorAll('.cal-day.selected').forEach(el => {
    el.classList.remove('selected');
    if (el.dataset.emotionColor) {
      el.style.background = `${el.dataset.emotionColor}25`;
      el.style.color = el.dataset.emotionColor;
    }
  });
}

const cocktailColorNameMap = {
  '기쁨': '주황 칵테일', '우울': '파랑 칵테일', '불안': '보라 칵테일',
  '분노': '빨강 칵테일', '지침': '노랑 칵테일', '외로움': '검정 칵테일', '평온': '초록 칵테일'
};

function navigateReceipt(dir) {
  const list = receiptData[currentReceiptDate];
  if (!list) return;
  currentReceiptIndex = Math.max(0, Math.min(list.length - 1, currentReceiptIndex + dir));
  _renderReceiptCard(currentReceiptDate, list[currentReceiptIndex], list.length);
}

function openReceiptCard(dateStr, data) {
  currentReceiptDate = dateStr;
  currentReceiptIndex = 0;

  document.getElementById('receipt-empty-state').style.display = 'none';
  document.getElementById('receipt-no-data').style.display = 'none';
  document.getElementById('receipt-detail').style.display = 'none';

  const list = Array.isArray(data) ? data : (data ? [data] : null);

  if (!list || list.length === 0) {
    document.getElementById('rnd-date').textContent = dateStr;
    document.getElementById('receipt-no-data').style.display = 'flex';
    document.getElementById('rc-cocktail-badge').style.display = 'none';
    document.getElementById('rc-emotion-dot').style.background = 'transparent';
    return;
  }

  _renderReceiptCard(dateStr, list[0], list.length);
}

function _renderReceiptCard(dateStr, data, total) {
  const nav = document.getElementById('rc-nav');
  const navLabel = document.getElementById('rc-nav-label');
  if (total > 1) {
    nav.style.display = 'flex';
    navLabel.textContent = `${currentReceiptIndex + 1} / ${total}`;
  } else {
    nav.style.display = 'none';
  }

  const isDirect = data.summary_note && data.summary_note.includes('직접 선택하셨어요');
  const emotion = data.dominant_sub_category || null;
  const color = getEmotionColor(emotion);
  const main = getMainCategory(emotion);
  const sub = document.getElementById('rc-emotion-sub');

  document.getElementById('receipt-card-date').textContent = formatReceiptDate(dateStr);

  const badge = document.getElementById('rc-cocktail-badge');
  const dot   = document.getElementById('rc-emotion-dot');
  badge.style.color   = color;
  badge.style.filter  = `drop-shadow(0 0 6px ${color}bb)`;
  badge.style.display = 'flex';
  dot.style.background  = color;
  dot.style.boxShadow   = `0 0 6px ${color}88`;

  if (isDirect) {
    document.getElementById('rc-title').textContent = '감정 영수증';
    document.getElementById('rc-section-label').textContent = '선택한 칵테일';
    document.getElementById('rc-label-emotion').textContent = '주문';
    document.getElementById('rc-label-weather').textContent = '감정';
    document.getElementById('rc-label-cocktail').textContent = '칵테일';

    document.getElementById('rc-emotion').textContent = main ? (cocktailColorNameMap[main] || main) : (emotion || '-');
    sub.textContent = emotion || '';
    sub.style.display = emotion ? 'block' : 'none';
    document.getElementById('rc-weather').textContent = main || '-';
    document.getElementById('rc-cocktail').textContent = data.recommended_cocktail || '-';
    document.getElementById('rc-summary').textContent = data.summary_note || '';
  } else {
    document.getElementById('rc-title').textContent = '감정 영수증';
    document.getElementById('rc-section-label').textContent = '오늘의 감정';
    document.getElementById('rc-label-emotion').textContent = '감정';
    document.getElementById('rc-label-weather').textContent = '날씨';
    document.getElementById('rc-label-cocktail').textContent = '추천 칵테일';

    if (main) {
      document.getElementById('rc-emotion').textContent = main;
      sub.textContent = emotion;
      sub.style.display = 'block';
    } else {
      document.getElementById('rc-emotion').textContent = emotion || '-';
      sub.style.display = 'none';
    }
    document.getElementById('rc-weather').textContent = data.weather ? `${getWeatherEmoji(data.weather)} ${data.weather}` : '-';
    document.getElementById('rc-cocktail').textContent = data.recommended_cocktail || '-';
    document.getElementById('rc-summary').textContent = data.summary_note || '아직 감정 영수증이 없어요.';
  }

  document.getElementById('receipt-detail').style.display = 'flex';
}
