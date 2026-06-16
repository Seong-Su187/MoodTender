// =============================================
// monthly.js — 감정 월간 분석 (monthly.html)
// =============================================

(function () {
  var currentYear, currentMonth;

  var EMOTION_EMOJI = {
    '기쁨':   '☀️',
    '우울':   '🌧️',
    '불안':   '⛈️',
    '분노':   '🌪️',
    '지침':   '🌫️',
    '외로움': '🌙',
    '평온':   '🌤️'
  };

  var EMOTION_COLOR = {
    '기쁨':   '#e8874a',
    '우울':   '#7dc4e8',
    '불안':   '#b89de0',
    '분노':   '#e0746b',
    '지침':   '#c8c050',
    '외로움': '#7a7a8e',
    '평온':   '#7dcea0'
  };

  function getEmoji(main) { return EMOTION_EMOJI[main] || '💭'; }
  function getColor(main) { return EMOTION_COLOR[main] || '#b3a48c'; }

  function hexToRgba(hex, alpha) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
  }

  function setMonthTitle(year, month) {
    var el = document.getElementById('month-title');
    if (el) el.textContent = year + '년 ' + month + '월';
  }

  function setNextBtnState(year, month) {
    var now = new Date();
    var isCurrentOrFuture = year > now.getFullYear() ||
      (year === now.getFullYear() && month >= now.getMonth() + 1);
    var btn = document.getElementById('btn-next');
    if (btn) {
      btn.disabled = isCurrentOrFuture;
    }
  }

  function renderEmotionFlow(weeks) {
    var container = document.getElementById('emotion-flow');
    if (!container) return;

    var weekMap = {};
    (weeks || []).forEach(function (w) {
      var num = parseInt(w.label.replace('주차', ''));
      weekMap[num] = w;
    });

    var html = '';
    for (var i = 1; i <= 4; i++) {
      var delay = ((i - 1) * 0.1).toFixed(2);
      var w = weekMap[i];

      if (w) {
        var main = w.main_emotion || '평온';
        var color = getColor(main);
        var vars =
          '--ec:' + color + ';' +
          '--ec28:' + hexToRgba(color, 0.28) + ';' +
          '--ec14:' + hexToRgba(color, 0.14) + ';' +
          '--ec06:' + hexToRgba(color, 0.06) + ';' +
          '--ecb:' + hexToRgba(color, 0.35) + ';';
        var dominantCnt = w.main_emotion_count || w.count;
        var pct = Math.round(dominantCnt / w.count * 100);

        html += '<div class="week-card" style="animation-delay:' + delay + 's;' + vars + '">';
        html += '<div class="week-label">' + i + '주차</div>';
        html += '<div class="week-emoji">' + getEmoji(main) + '</div>';
        html += '<div class="week-emotion-name">' + main + '</div>';
        html += '<div class="week-pct-wrap">';
        html += '<div class="week-pct-bar"><div class="week-pct-fill" style="width:' + pct + '%;background:' + color + ';box-shadow:0 0 8px ' + hexToRgba(color, 0.5) + '"></div></div>';
        html += '<span class="week-pct-label" style="color:' + color + '">' + pct + '%</span>';
        html += '</div>';
        html += '</div>';
      } else {
        html += '<div class="week-card week-card--empty" style="animation-delay:' + delay + 's">';
        html += '<div class="week-label">' + i + '주차</div>';
        html += '<div class="week-emoji" style="opacity:0.18; font-size:2rem">—</div>';
        html += '<div class="week-emotion-name week-no-data">기록 없음</div>';
        html += '<div class="week-pct-wrap">';
        html += '<div class="week-pct-bar"></div>';
        html += '<span class="week-pct-label" style="color:rgba(180,160,120,0.25)">—</span>';
        html += '</div>';
        html += '</div>';
      }

      if (i < 4) {
        html += '<div class="flow-arrow">›</div>';
      }
    }

    container.innerHTML = html;
  }

  function showReport(text) {
    var el = document.getElementById('mc-report-text');
    if (!el) return;
    el.innerHTML = text;
  }

  function showError(msg) {
    var flow = document.getElementById('emotion-flow');
    if (flow) flow.innerHTML = '<div class="flow-empty">' + msg + '</div>';
    showReport(msg);
  }

  function renderYearlyFlow(months) {
    var container = document.getElementById('yearly-flow');
    if (!container) return;

    var html = '';
    months.forEach(function (m, i) {
      var delay = (i * 0.035).toFixed(2);
      if (m.main_emotion) {
        var color = getColor(m.main_emotion);
        var bg = hexToRgba(color, 0.18);
        var border = hexToRgba(color, 0.35);
        html += '<div class="month-card" style="animation-delay:' + delay + 's;background:' + bg + ';border-color:' + border + ';--ec:' + color + ';--ec28:' + hexToRgba(color, 0.35) + ';--ec14:' + hexToRgba(color, 0.18) + '">';
        html += '<div class="month-label">' + m.label + '</div>';
        html += '<div class="month-emoji">' + getEmoji(m.main_emotion) + '</div>';
        html += '<div class="month-emotion" style="color:' + color + '">' + m.main_emotion + '</div>';
      } else {
        html += '<div class="month-card month-card--empty" style="animation-delay:' + delay + 's">';
        html += '<div class="month-label">' + m.label + '</div>';
        html += '<div class="month-emoji-empty">—</div>';
        html += '<div class="month-emotion month-no-data"></div>';
      }
      html += '</div>';
    });

    container.innerHTML = html;
  }

  async function loadYearlyAnalysis(year) {
    var token = localStorage.getItem('access_token');
    if (!token) return;

    var titleEl = document.getElementById('yearly-title');
    if (titleEl) titleEl.textContent = year + '년 월별 대표 감정';

    try {
      var res = await fetch('/api/web/yearly-analysis?year=' + year, {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (!res.ok) return;
      var data = await res.json();
      renderYearlyFlow(data.months || []);
    } catch (e) {
      console.error('연간 분석 로드 실패:', e);
    }
  }

  async function loadMonthlyAnalysis(year, month) {
    var token = localStorage.getItem('access_token');
    if (!token) { showError('로그인이 필요합니다.'); return; }

    var flow = document.getElementById('emotion-flow');
    if (flow) flow.innerHTML = '<div class="flow-loading">데이터를 불러오는 중입니다...</div>';
    showReport('데이터를 불러오는 중입니다...');

    try {
      var res = await fetch('/api/web/monthly-analysis?year=' + year + '&month=' + month, {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (!res.ok) throw new Error(res.status);

      var data = await res.json();
      renderEmotionFlow(data.weeks || []);
      showReport(data.report || '이번 달 분석 내용이 없습니다.');

    } catch (e) {
      console.error('월간 분석 로드 실패:', e);
      showError('데이터를 불러오지 못했습니다.');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var now = new Date();
    currentYear  = now.getFullYear();
    currentMonth = now.getMonth() + 1;

    setMonthTitle(currentYear, currentMonth);
    setNextBtnState(currentYear, currentMonth);
    loadMonthlyAnalysis(currentYear, currentMonth);
    loadYearlyAnalysis(currentYear);

    document.getElementById('btn-prev').addEventListener('click', function () {
      currentMonth--;
      if (currentMonth < 1) { currentMonth = 12; currentYear--; }
      setMonthTitle(currentYear, currentMonth);
      setNextBtnState(currentYear, currentMonth);
      loadMonthlyAnalysis(currentYear, currentMonth);
    });

    document.getElementById('btn-next').addEventListener('click', function () {
      var now = new Date();
      if (currentYear < now.getFullYear() ||
          (currentYear === now.getFullYear() && currentMonth < now.getMonth() + 1)) {
        currentMonth++;
        if (currentMonth > 12) { currentMonth = 1; currentYear++; }
        setMonthTitle(currentYear, currentMonth);
        setNextBtnState(currentYear, currentMonth);
        loadMonthlyAnalysis(currentYear, currentMonth);
      }
    });
  });
})();
