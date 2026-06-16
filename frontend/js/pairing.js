// =============================================
// pairing.js — 기기 연동 (WebSocket)
// =============================================

let pairingSocket = null;
let currentWebUserId = null;

async function checkDevicePairingStatus() {
  try {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const response = await fetch(`/api/users/me/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });

    if (response.ok) {
      const data = await response.json();
      currentWebUserId = data.user_id;

      if (data.is_device_paired === true) {
        const overlay = document.getElementById('pairing-overlay');
        if (overlay) {
          overlay.style.display = 'none';
        }
        showToast('로그인 완료!', '✓');
        showToast('디바이스가 이미 연동되어 있어요.', '🔗');
        console.log("✅ 이미 연동된 유저입니다. 자동 잠금 해제 완료!");
      } else {
        console.log("🔒 디바이스 연동이 필요합니다.");
      }
    }
  } catch (error) {
    console.error("연동 상태 확인 중 오류 발생:", error);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  checkDevicePairingStatus();
});

function startPairing() {
  if (!currentWebUserId) {
    alert("유저 정보를 불러오는 중입니다. 잠시 후 다시 시도해주세요.");
    return;
  }

  document.getElementById('locked-state').style.display = 'none';
  document.getElementById('pin-state').style.display = 'block';
  closeSidebar();

  pairingSocket = new WebSocket(`ws://${window.location.host}/api/pairing/ws/${currentWebUserId}`);

  pairingSocket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'pin_generated') {
      document.getElementById('pin-display').innerText = data.pin;
    } else if (data.type === 'pairing_success') {
      unlockScreen();
    }
  };

  pairingSocket.onclose = function() {
    console.log('페어링 소켓 연결이 종료되었습니다.');
  };
}

function unlockScreen() {
  const overlay = document.getElementById('pairing-overlay');
  overlay.style.opacity = '0';
  setTimeout(() => {
    overlay.style.display = 'none';
    console.log("✅ 기기 연결 완료! 이제 원할 때 언제든 과거 대화를 열람할 수 있습니다.");
  }, 500);
}
