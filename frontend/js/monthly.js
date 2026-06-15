// =============================================
// monthly.js — 감정 월간 분석 (monthly.html iframe 내부)
// =============================================

(function () {
  var _charts = {};

  function avg(arr, key) {
    return Math.round(arr.reduce(function (s, r) { return s + r[key]; }, 0) / arr.length);
  }

  function animateCount(el, endVal, format, delay) {
    var duration = 900;
    var startTime = null;
    setTimeout(function () {
      function step(timestamp) {
        if (!startTime) startTime = timestamp;
        var progress = Math.min((timestamp - startTime) / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        var cur = Math.round(eased * endVal);
        el.textContent = format(cur);
        if (progress < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }, delay || 0);
  }

  function showMsg(msg, color) {
    var el = document.getElementById('mc-report-text');
    if (el) el.innerHTML = '<span style="color:' + (color || '#a89060') + ';">' + msg + '</span>';
  }

  async function loadMonthlyAnalysis() {
    var token = localStorage.getItem('access_token');
    if (!token) { showMsg('로그인이 필요합니다.', '#e98b82'); return; }

    try {
      var res = await fetch('/api/web/data', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (!res.ok) throw new Error(res.status);

      var result = await res.json();
      var allRecords = result.data || [];

      if (allRecords.length === 0) { showMsg('아직 수집된 데이터가 없습니다.'); return; }

      var monthMap = {};
      for (var i = 0; i < allRecords.length; i++) {
        var r = allRecords[i];
        var m = r.recordDate.slice(0, 7);
        if (!monthMap[m]) monthMap[m] = [];
        monthMap[m].push(r);
      }

      var allMonths = Object.keys(monthMap).sort();
      var months = allMonths.slice(-12);

      var labels  = months.map(function (m) { var p = m.split('-'); return p[0] + '.' + p[1]; });
      var steps   = months.map(function (m) { return avg(monthMap[m], 'stepCount'); });
      var sleep   = months.map(function (m) { return avg(monthMap[m], 'sleepMinutes'); });
      var screen  = months.map(function (m) { return avg(monthMap[m], 'screenTimeMinutes'); });
      renderCards(labels, steps, sleep, screen);
      renderCharts(labels, steps, sleep, screen);
      renderReport(months, labels, steps, sleep, screen);

    } catch (e) {
      console.error('월간 데이터 로드 실패:', e);
      showMsg('데이터를 불러오지 못했습니다.', '#e98b82');
    }
  }

  function deltaSpan(cur, prev, isLowerBetter, formatDiff) {
    var diff = cur - prev;
    if (diff === 0) return '<span class="delta-same">변화 없음</span>';
    var absDiff = Math.abs(diff);
    var pct = Math.round(absDiff / Math.max(prev, 1) * 100);
    var increased = diff > 0;
    var good = increased !== isLowerBetter;
    var cls = good ? 'delta-up' : 'delta-down';
    var sign = increased ? '▲' : '▼';
    var pctStr = increased ? '(+' + pct + '%)' : '(-' + pct + '%)';
    var diffStr = formatDiff ? formatDiff(absDiff) : absDiff.toLocaleString();
    return '<span class="' + cls + '">' + sign + ' ' + diffStr + ' ' + pctStr + '</span>';
  }

  function renderCards(labels, steps, sleep, screen) {
    var n = labels.length;
    if (n === 0) return;
    var last = n - 1;

    animateCount(
      document.getElementById('mval-steps'),
      steps[last],
      function (v) { return v.toLocaleString() + '보'; },
      80
    );
    document.getElementById('mdelta-steps').innerHTML = n >= 2 ? deltaSpan(steps[last], steps[last - 1], false, function(d) { return d.toLocaleString() + '보'; }) : '';

    animateCount(
      document.getElementById('mval-sleep'),
      sleep[last],
      function (v) { return Math.floor(v / 60) + '시간 ' + (v % 60) + '분'; },
      160
    );
    document.getElementById('mdelta-sleep').innerHTML = n >= 2 ? deltaSpan(sleep[last], sleep[last - 1], false, function(d) { return d >= 60 ? Math.floor(d/60) + '시간 ' + (d%60) + '분' : d + '분'; }) : '';

    animateCount(
      document.getElementById('mval-screen'),
      screen[last],
      function (v) { return v + '분'; },
      240
    );
    document.getElementById('mdelta-screen').innerHTML = n >= 2 ? deltaSpan(screen[last], screen[last - 1], true, function(d) { return d + '분'; }) : '';
  }

  function chartOptions(yTitle) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      color: '#b3a48c',
      scales: {
        x: {
          grid: { color: 'rgba(200,160,90,0.08)' },
          ticks: { color: '#b3a48c', maxRotation: 45 }
        },
        y: {
          beginAtZero: false,
          grid: { color: 'rgba(200,160,90,0.08)' },
          ticks: { color: '#b3a48c' },
          title: { display: true, text: yTitle, color: '#b3a48c' }
        }
      },
      plugins: { legend: { labels: { color: '#f4ecd9' } } }
    };
  }

  function renderCharts(labels, steps, sleep, screen) {
    Object.values(_charts).forEach(function (c) { if (c) c.destroy(); });
    _charts = {};

    var stepsCtx = document.getElementById('mc-steps').getContext('2d');
    _charts.steps = new Chart(stepsCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: '평균 걸음수 (보)',
          data: steps,
          borderColor: '#c8902e',
          backgroundColor: 'rgba(200,144,46,0.15)',
          pointBackgroundColor: '#e8c884',
          pointRadius: 3,
          pointHoverRadius: 5,
          fill: true,
          tension: 0.35
        }]
      },
      options: chartOptions('걸음수 (보)')
    });

    var sleepCtx = document.getElementById('mc-sleep').getContext('2d');
    _charts.sleep = new Chart(sleepCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: '평균 수면 (분)',
          data: sleep,
          borderColor: '#7dc4e8',
          backgroundColor: 'rgba(125,196,232,0.12)',
          pointBackgroundColor: '#b8e0f4',
          pointRadius: 3,
          pointHoverRadius: 5,
          fill: true,
          tension: 0.35
        }]
      },
      options: chartOptions('수면 (분)')
    });

    var screenCtx = document.getElementById('mc-screen').getContext('2d');
    _charts.screen = new Chart(screenCtx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: '평균 스크린타임 (분)',
          data: screen,
          borderColor: '#e0746b',
          backgroundColor: 'rgba(224,116,107,0.12)',
          pointBackgroundColor: '#f4d4d0',
          pointRadius: 3,
          pointHoverRadius: 5,
          fill: true,
          tension: 0.35
        }]
      },
      options: chartOptions('스크린타임 (분)')
    });

  }

  function renderReport(months, labels, steps, sleep, screen) {
    var el = document.getElementById('mc-report-text');
    var n = months.length;

    if (n < 2) {
      el.innerHTML = '<p>아직 비교할 수 있는 월별 데이터가 부족해요. 데이터가 더 쌓이면 분석이 시작됩니다.</p>';
      return;
    }

    var lines = [];
    var last = n - 1;

    function pct(a, b) { return Math.round(Math.abs(a - b) / Math.max(b, 1) * 100); }
    function sleepStr(m) { return Math.floor(m / 60) + '시간 ' + (m % 60) + '분'; }

    var sdiff = steps[last] - steps[last - 1];
    if (sdiff > 0)      lines.push('지난 달보다 걸음수가 ' + pct(steps[last], steps[last - 1]) + '% 늘었어요. 신체 활동이 활발해지고 있네요.');
    else if (sdiff < 0) lines.push('지난 달보다 걸음수가 ' + pct(steps[last], steps[last - 1]) + '% 줄었어요. 활동량이 조금 줄어들었군요.');
    else                lines.push('지난 달과 걸음수가 비슷하게 유지되고 있어요.');

    var sldiff = sleep[last] - sleep[last - 1];
    if (sldiff > 0)      lines.push('수면 시간이 ' + pct(sleep[last], sleep[last - 1]) + '% 늘어 평균 ' + sleepStr(sleep[last]) + ' 자고 있어요.');
    else if (sldiff < 0) lines.push('수면 시간이 ' + pct(sleep[last], sleep[last - 1]) + '% 줄어 평균 ' + sleepStr(sleep[last]) + ' 자고 있어요. 충분한 휴식이 필요할 것 같아요.');
    else                 lines.push('수면 패턴이 안정적으로 유지되고 있어요.');

    var scdiff = screen[last] - screen[last - 1];
    if (scdiff > 0)      lines.push('스마트폰 사용이 ' + pct(screen[last], screen[last - 1]) + '% 늘어 일 평균 ' + screen[last] + '분이에요. 디지털 피로도를 주의해 보세요.');
    else if (scdiff < 0) lines.push('스마트폰 사용이 ' + pct(screen[last], screen[last - 1]) + '% 줄어 일 평균 ' + screen[last] + '분이에요. 건강한 디지털 습관이 자리잡고 있어요.');
    else                 lines.push('스마트폰 사용 패턴이 일정하게 유지되고 있어요.');

    if (n >= 3) {
      var stepTrend  = steps[last]  > steps[0]  ? '증가' : steps[last]  < steps[0]  ? '감소' : '유지';
      var sleepTrend = sleep[last]  > sleep[0]  ? '증가' : sleep[last]  < sleep[0]  ? '감소' : '유지';
      lines.push(
        labels[0] + ' → ' + labels[last] + ' 전체 ' + n + '개월 흐름을 보면, ' +
        '신체 활동은 ' + stepTrend + ' 추세이고 수면량은 ' + sleepTrend + ' 추세예요.'
      );
    }

    el.innerHTML = lines.map(function (l) {
      return '<p style="margin-bottom:8px;">' + l + '</p>';
    }).join('');
  }

  document.addEventListener('DOMContentLoaded', loadMonthlyAnalysis);
})();
