async function openHistoryModal() {
  document.getElementById('history-modal').style.display = 'flex';
  const contentDiv = document.getElementById('history-content');
  contentDiv.innerHTML = '불러오는 중...';

  try {
    const response = await fetch('/api/chat/history', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
    });
    const data = await response.json();
    contentDiv.innerHTML = '';

    Object.keys(data.history).sort().forEach(dateStr => {
      data.history[dateStr].forEach(msg => {
        // 🚀 role 값을 소문자로 강제 변환 후 비교 (대문자 user/User 대응)
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
  } catch (error) {
    contentDiv.innerHTML = '불러오기 실패';
  }
}