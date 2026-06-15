// =============================================
// ui.js — 토스트, 사이드바, 대시보드 모달
// =============================================

function showToast(message, icon = '✓', duration = 3000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<span class="toast-icon">${icon}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('sidebar-overlay').classList.toggle('show');
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('show');
}

function openDashboardModal() {
  const modal = document.getElementById('dashboard-modal');
  const frame = document.getElementById('dashboard-frame');
  if (!frame.src) {
    frame.src = frame.dataset.src;
  }
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  closeSidebar();
}

function closeDashboardModal() {
  const modal = document.getElementById('dashboard-modal');
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
}

function openMonthlyModal() {
  const modal = document.getElementById('monthly-modal');
  const frame = document.getElementById('monthly-frame');
  frame.src = frame.dataset.src;
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
}

function closeMonthlyModal() {
  const modal = document.getElementById('monthly-modal');
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  openDashboardModal();
}

window.addEventListener('message', function (e) {
  if (e.data && e.data.type === 'openMonthly') {
    closeDashboardModal();
    openMonthlyModal();
  }
});
