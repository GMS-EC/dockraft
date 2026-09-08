// Dockraft Secure Login Controller
const LoginApp = {
  countdownInterval: null,
  remainingSeconds: 0,

  init() {
    if (window.SERVER_LOCKOUT_REMAINING && window.SERVER_LOCKOUT_REMAINING > 0) {
      this.startLockoutCountdown(window.SERVER_LOCKOUT_REMAINING);
    }

    // Check if arrived with expired session
    const urlParams = new URLSearchParams(window.location.search);
    const isExpired = window.SESSION_EXPIRED_INIT || urlParams.get('expired') === '1';
    const expiredEl = document.getElementById('login-expired-msg');
    if (expiredEl && isExpired) {
      expiredEl.style.display = 'flex';
    }

    const userInput = document.getElementById('login-username');
    const passInput = document.getElementById('login-password');
    if (userInput && !userInput.value) {
      userInput.focus();
    } else if (passInput) {
      passInput.focus();
    }
  },

  async submitLogin(event) {
    if (event) event.preventDefault();

    if (this.remainingSeconds > 0) {
      return;
    }

    const userInput = document.getElementById('login-username');
    const passInput = document.getElementById('login-password');
    const submitBtn = document.getElementById('btn-login-submit');
    const btnIcon = document.getElementById('btn-login-icon');
    const btnText = document.getElementById('btn-login-text');
    const errorAlert = document.getElementById('login-error-msg');

    const username = userInput ? userInput.value.trim() : '';
    const password = passInput ? passInput.value : '';

    if (!username) {
      this.showError("Por favor ingresa el nombre de usuario.");
      if (userInput) userInput.focus();
      return;
    }

    if (!password) {
      this.showError("Por favor ingresa la contraseña de administrador.");
      if (passInput) passInput.focus();
      return;
    }

    // Set UI loading state
    if (submitBtn) submitBtn.disabled = true;
    if (btnIcon) btnIcon.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="spin-icon"><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></svg>';
    if (btnText) btnText.textContent = 'Verificando...';
    if (errorAlert) errorAlert.style.display = 'none';

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      const data = await res.json().catch(() => ({}));

      if (res.status === 200 && data.status === 'success') {
        if (btnIcon) btnIcon.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
        if (btnText) btnText.textContent = 'Acceso concedido';
        if (submitBtn) submitBtn.style.backgroundColor = '#238636';

        // Redirect to authenticated dashboard
        setTimeout(() => {
          window.location.href = '/';
        }, 300);
        return;
      }

      if (res.status === 429) {
        // Rate limited / Locked out
        const retryAfter = parseInt(res.headers.get('Retry-After') || '600', 10);
        this.startLockoutCountdown(retryAfter);
        return;
      }

      // 401 or other error
      const detail = data.detail || 'Usuario o contraseña incorrectos.';
      this.showError(detail);
      this.shakeCard();
      if (passInput) {
        passInput.value = '';
        passInput.focus();
      }

    } catch (err) {
      this.showError("Error de conexión con el servidor: " + err.message);
    } finally {
      if (this.remainingSeconds <= 0 && submitBtn) {
        submitBtn.disabled = false;
        if (btnIcon) btnIcon.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>';
        if (btnText) btnText.textContent = 'Iniciar Sesión';
      }
    }
  },

  startLockoutCountdown(seconds) {
    if (this.countdownInterval) {
      clearInterval(this.countdownInterval);
      this.countdownInterval = null;
    }

    this.remainingSeconds = seconds;
    const userInput = document.getElementById('login-username');
    const passInput = document.getElementById('login-password');
    const submitBtn = document.getElementById('btn-login-submit');
    const btnIcon = document.getElementById('btn-login-icon');
    const btnText = document.getElementById('btn-login-text');
    const errorAlert = document.getElementById('login-error-msg');

    if (userInput) userInput.disabled = true;
    if (passInput) passInput.disabled = true;
    if (submitBtn) {
      submitBtn.disabled = true;
      if (btnIcon) btnIcon.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
      if (btnText) btnText.textContent = 'Bloqueado';
    }

    const updateUI = () => {
      if (this.remainingSeconds <= 0) {
        clearInterval(this.countdownInterval);
        this.countdownInterval = null;
        this.remainingSeconds = 0;

        if (userInput) userInput.disabled = false;
        if (passInput) passInput.disabled = false;
        if (submitBtn) {
          submitBtn.disabled = false;
          if (btnIcon) btnIcon.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>';
          if (btnText) btnText.textContent = 'Iniciar Sesión';
        }

        if (errorAlert) {
          errorAlert.style.display = 'block';
          errorAlert.style.backgroundColor = 'rgba(56, 139, 253, 0.1)';
          errorAlert.style.borderColor = '#388bfd';
          errorAlert.style.color = '#79c0ff';
          errorAlert.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:text-bottom; margin-right:4px;"><polyline points="20 6 9 17 4 12"/></svg> El periodo de bloqueo ha finalizado. Ya puedes intentar acceder nuevamente.';
        }
        return;
      }

      const m = Math.floor(this.remainingSeconds / 60);
      const s = this.remainingSeconds % 60;
      const fmt = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;

      if (errorAlert) {
        errorAlert.style.display = 'block';
        errorAlert.style.backgroundColor = 'rgba(248, 81, 73, 0.12)';
        errorAlert.style.borderColor = '#f85149';
        errorAlert.style.color = '#ff7b72';
        errorAlert.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:text-bottom; margin-right:4px;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <strong>Acceso bloqueado por seguridad</strong> debido a demasiados intentos fallidos.<br>
          Podrás intentar de nuevo en: <span style="font-weight: 700; font-family: var(--font-mono); color: #f85149;">${fmt}</span>
        `;
      }

      this.remainingSeconds--;
    };

    updateUI();
    this.countdownInterval = setInterval(updateUI, 1000);
  },

  togglePasswordVisibility() {
    const passInput = document.getElementById('login-password');
    const toggleBtn = document.getElementById('login-password-toggle');
    if (!passInput) return;

    if (passInput.type === 'password') {
      passInput.type = 'text';
      if (toggleBtn) toggleBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    } else {
      passInput.type = 'password';
      if (toggleBtn) toggleBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    }
  },

  showError(message) {
    const errorAlert = document.getElementById('login-error-msg');
    if (errorAlert) {
      errorAlert.style.display = 'block';
      errorAlert.style.backgroundColor = 'rgba(248, 81, 73, 0.12)';
      errorAlert.style.borderColor = '#f85149';
      errorAlert.style.color = '#f85149';
      errorAlert.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:text-bottom; margin-right:4px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${this.escapeHtml(message)}`;
    }
  },

  shakeCard() {
    const card = document.getElementById('login-card');
    if (card) {
      card.classList.remove('shake-anim');
      // Trigger reflow
      void card.offsetWidth;
      card.classList.add('shake-anim');
    }
  },

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  LoginApp.init();
});
