// =============================================
// history.js — 대화 기록 모달
// =============================================

async function openHistoryModal() {
  if (!currentWebUserId) {
    alert("유저 정보를 불러오는 중입니다. 잠시 후 다시 시도해주세요.");
    return;
  }

  document.getElementById('history-modal').style.display = 'flex';
  closeSidebar();

  const contentDiv = document.getElementById('history-content');
  contentDiv.innerHTML = '<div style="text-align: center; color: #a8a1b3; margin-top: 50px;">데이터를 불러오는 중입니다...</div>';

  try {
    const response = await fetch('/api/chat/history', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
    });
    const data = await response.json();

    contentDiv.innerHTML = '';

    if (!data.history || Object.keys(data.history).length === 0) {
      contentDiv.innerHTML = '<div style="text-align: center; color: #a8a1b3; margin-top: 50px;">과거 대화 기록이 없습니다.</div>';
      return;
    }

    const sortedDates = Object.keys(data.history).sort();

    sortedDates.forEach(dateStr => {
      const dateObj = new Date(dateStr);
      const options = { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' };
      const formattedDate = dateObj.toLocaleDateString('ko-KR', options);

      const dateDividerHtml = `
        <div style="display: flex; align-items: center; justify-content: center; margin: 24px 0 12px 0; width: 100%;">
          <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.08);"></div>
          <div style="background: rgba(124, 77, 255, 0.15); color: #cbb5ff; border: 1px solid rgba(124, 77, 255, 0.3); padding: 4px 16px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; margin: 0 16px;">
            📅 ${formattedDate}
          </div>
          <div style="flex: 1; height: 1px; background: rgba(255,255,255,0.08);"></div>
        </div>
      `;
      contentDiv.innerHTML += dateDividerHtml;

      const messages = data.history[dateStr];
      messages.forEach(msg => {
        const isUser = msg.role === 'user';
        const alignSelf = isUser ? 'flex-end' : 'flex-start';
        const bgColor = isUser ? 'rgba(88, 44, 6, 0.84)' : 'rgba(252, 241, 210, 0.9)';
        const textColor = isUser ? '#f5e8c5' : '#3a1c05';
        const borderRadius = isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px';

        const bubbleHtml = `
          <div style="align-self: ${alignSelf}; max-width: 80%; margin-bottom: 6px;">
            <div style="font-size: 0.75rem; color: #a8a1b3; margin-bottom: 3px; text-align: ${isUser ? 'right' : 'left'}; font-weight: 600;">
              ${isUser ? '나' : 'AI 바텐더'}
            </div>
            <div style="display: flex; align-items: flex-end; gap: 6px; flex-direction: ${isUser ? 'row-reverse' : 'row'};">
              <div style="background: ${bgColor}; color: ${textColor}; padding: 12px 16px; border-radius: ${borderRadius}; font-size: 0.9rem; line-height: 1.5; box-shadow: 0 2px 8px rgba(0,0,0,0.2); word-break: keep-all;">
                ${msg.content}
              </div>
              <span style="font-size: 0.68rem; color: rgba(244, 241, 247, 0.4); min-width: max-content; margin-bottom: 2px;">
                ${msg.time || ""}
              </span>
            </div>
          </div>
        `;
        contentDiv.innerHTML += bubbleHtml;
      });
    });

    contentDiv.scrollTop = contentDiv.scrollHeight;

  } catch (error) {
    console.error("하루 단위 기록 불러오기 실패:", error);
    contentDiv.innerHTML = '<div style="text-align: center; color: #ff6b7a; margin-top: 50px;">기록을 불러오는데 실패했습니다.</div>';
  }
}

function closeHistoryModal() {
  document.getElementById('history-modal').style.display = 'none';
}
