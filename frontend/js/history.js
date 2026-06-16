// =============================================
// history.js — 대화 기록 모달 (전체 코드)
// =============================================

async function openHistoryModal() {
  document.getElementById('history-modal').style.display = 'flex';
  const contentDiv = document.getElementById('history-content');
  contentDiv.innerHTML = '<div style="text-align: center; color: #a8a1b3; margin-top: 50px;">데이터를 불러오는 중입니다...</div>';

  try {
    const response = await fetch('/api/chat/history', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
    });
    const data = await response.json();
    contentDiv.innerHTML = '';

    if (!data.history || Object.keys(data.history).length === 0) {
      contentDiv.innerHTML = '<div style="text-align: center; color: #a8a1b3; margin-top: 50px;">대화 기록이 없습니다.</div>';
      return;
    }

    Object.keys(data.history).sort().forEach(dateStr => {
      // 날짜 구분선
      const dateObj = new Date(dateStr);
      const formattedDate = dateObj.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' });
      const dateDividerHtml = `
        <div style="display: flex; align-items: center; justify-content: center; margin: 24px 0 12px 0; width: 100%;">
          <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.08);"></div>
          <div style="background: rgba(124, 77, 255, 0.15); color: #cbb5ff; border: 1px solid rgba(124, 77, 255, 0.3); padding: 4px 16px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; margin: 0 16px;">
            📅 ${formattedDate}
          </div>
          <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.08);"></div>
        </div>
      `;
      contentDiv.innerHTML += dateDividerHtml;

      data.history[dateStr].forEach(msg => {
        const role = (msg.role || "").toLowerCase();
        const isUser = (role === 'user');

        const alignSelf = isUser ? 'flex-end' : 'flex-start';
        const bgColor = isUser ? 'rgba(88, 44, 6, 0.84)' : 'rgba(252, 241, 210, 0.9)';
        const textColor = isUser ? '#f5e8c5' : '#3a1c05';
        const borderRadius = isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px';
        const senderName = isUser ? '나' : 'AI 바텐더';

        const bubbleHtml = `
          <div style="align-self: ${alignSelf}; max-width: 80%; margin-bottom: 12px; display: flex; flex-direction: column; align-items: ${isUser ? 'flex-end' : 'flex-start'};">
            <div style="font-size: 0.75rem; color: #a8a1b3; margin-bottom: 4px; font-weight: 600;">${senderName}</div>
            <div style="background: ${bgColor}; color: ${textColor}; padding: 12px 16px; border-radius: ${borderRadius}; font-size: 0.9rem; line-height: 1.5; box-shadow: 0 2px 8px rgba(0,0,0,0.2);">
              ${msg.content}
            </div>
          </div>
        `;
        contentDiv.innerHTML += bubbleHtml;
      });
    });
    contentDiv.scrollTop = contentDiv.scrollHeight;
  } catch (error) {
    contentDiv.innerHTML = '<div style="text-align: center; color: #ff6b7a; margin-top: 50px;">불러오기 실패</div>';
  }
}

// 🚀 [버그 해결] 전역 객체(window)에 명시적으로 닫기 함수를 등록하여 어디서든 실행되도록 강제합니다.
window.closeHistoryModal = function() {
  const modal = document.getElementById('history-modal');
  if (modal) {
    modal.style.display = 'none';
  }
};

// 🚀 [추가 개선] 모달창 바깥의 어두운 배경을 클릭해도 창이 닫히도록 만듭니다.
window.addEventListener('click', function(event) {
  const modal = document.getElementById('history-modal');
  if (event.target === modal) {
    modal.style.display = 'none';
  }
});