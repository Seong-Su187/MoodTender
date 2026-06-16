// =============================================
// history.js — 대화 기록 모달 (정렬 해결)
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
      // 날짜 구분선 생성
      const dateDivider = `<div style="text-align: center; margin: 20px 0; color: #cbb5ff; font-weight: bold;">${new Date(dateStr).toLocaleDateString()}</div>`;
      contentDiv.innerHTML += dateDivider;

      data.history[dateStr].forEach(msg => {
        // 🚀 role 판별: 정확하게 'user'만 오른쪽, 나머지는 왼쪽(AI)
        const role = (msg.role || "").toLowerCase();
        const isUser = (role === 'user');

        const alignSelf = isUser ? 'flex-end' : 'flex-start';
        const bgColor = isUser ? 'rgba(88, 44, 6, 0.84)' : 'rgba(252, 241, 210, 0.9)';
        const textColor = isUser ? '#f5e8c5' : '#3a1c05';
        const senderName = isUser ? '나' : 'AI 바텐더';

        contentDiv.innerHTML += `
          <div style="align-self: ${alignSelf}; max-width: 80%; margin-bottom: 12px; display: flex; flex-direction: column; align-items: ${isUser ? 'flex-end' : 'flex-start'};">
            <div style="font-size: 0.75rem; color: #a8a1b3; margin-bottom: 4px; font-weight: 600;">${senderName}</div>
            <div style="background: ${bgColor}; color: ${textColor}; padding: 12px 16px; border-radius: 16px; font-size: 0.9rem; box-shadow: 0 2px 8px rgba(0,0,0,0.2);">
              ${msg.content}
            </div>
          </div>
        `;
      });
    });
    contentDiv.scrollTop = contentDiv.scrollHeight;
  } catch (error) {
    contentDiv.innerHTML = '<div style="text-align: center; color: #ff6b7a;">불러오기 실패</div>';
  }
}

function closeHistoryModal() {
  document.getElementById('history-modal').style.display = 'none';
}