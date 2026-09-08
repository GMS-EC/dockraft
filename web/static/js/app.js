// Global fetch interceptor to handle 401 Unauthorized / Session Expiration immediately
(function() {
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const res = await originalFetch.apply(this, args);
    const url = (typeof args[0] === 'string') ? args[0] : (args[0] && args[0].url ? args[0].url : '');
    if (res && res.status === 401 && !url.includes('/api/auth/login')) {
      if (typeof App !== 'undefined' && App.handleSessionExpired) {
        App.handleSessionExpired();
      } else {
        window.location.href = '/login?expired=1';
      }
    }
    return res;
  };
})();

// Dockraft Core App Script
const App = {
  activeTab: 'console',
  authRequired: false,
  authenticated: true,
  sessionTimeoutMinutes: 60,
  lastActivityTime: Date.now(),
  sessionTimer: null,
  refreshTimer: null,
  hasRecentActivity: false,

  init() {
    this.setupTabs();
    this.checkAuth();
    
    // Global keyboard shortcuts
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        const editorModal = document.getElementById('file-editor-modal');
        if (editorModal && editorModal.classList.contains('open')) {
          e.preventDefault();
          Files.saveCurrentFile();
        }
      }
    });

    if (typeof Files !== 'undefined' && Files.init) {
      Files.init();
    }

    // Register Service Worker for PWA if supported
    if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
      navigator.serviceWorker.register('/static/sw.js').then((reg) => {
        console.log('[Dockraft PWA] Service Worker registrado con éxito:', reg.scope);
      }).catch((err) => {
        console.debug('[Dockraft PWA] Service Worker registration skipped:', err);
      });
    }
  },

  setupTabs() {
    const tabs = document.querySelectorAll('.nav-btn');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.getAttribute('data-tab');
        this.switchTab(target);
      });
    });
  },

  switchTab(tabId) {
    this.activeTab = tabId;
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
      pane.classList.toggle('active', pane.id === `tab-${tabId}`);
    });

    // Refresh content for selected tab
    if (tabId === 'metrics') {
      if (typeof Metrics !== 'undefined') Metrics.loadMetrics();
    } else {
      if (typeof Metrics !== 'undefined') Metrics.stopLivePolling();
    }

    if (tabId === 'players') {
      if (typeof Players !== 'undefined') Players.loadPlayers();
    } else {
      if (typeof Players !== 'undefined') Players.stopPolling();
    }

    if (tabId === 'files') {
      Files.loadDirectory();
    } else {
      if (typeof Files !== 'undefined' && Files.hideContextMenu) Files.hideContextMenu();
    }
    
    if (tabId === 'installer') {
      Installer.loadInstaller();
    } else if (tabId === 'settings') {
      Settings.loadSettings();
    } else if (tabId === 'backups') {
      Backups.loadBackups();
    } else if (tabId === 'tasks') {
      Tasks.loadTasks();
    } else if (tabId === 'webhooks') {
      Webhooks.loadConfig();
    }
  },

  async checkAuth() {
    try {
      const res = await fetch('/api/auth/status');
      if (res.status === 401) {
        this.handleSessionExpired();
        return;
      }
      const data = await res.json();
      this.authRequired = data.auth_required;
      if (data.session_timeout_minutes) {
        this.sessionTimeoutMinutes = data.session_timeout_minutes;
      }
      if (this.authRequired) {
        this.setupSessionMonitoring(this.sessionTimeoutMinutes);
      }
      Console.init();
      if (typeof Tasks !== 'undefined') Tasks.init();
    } catch (e) {
      console.warn("Auth check error:", e);
      Console.init();
      if (typeof Tasks !== 'undefined') Tasks.init();
    }
  },

  setupSessionMonitoring(timeoutMinutes) {
    if (timeoutMinutes && timeoutMinutes > 0) {
      this.sessionTimeoutMinutes = timeoutMinutes;
    }
    this.lastActivityTime = Date.now();
    this.hasRecentActivity = false;

    // Track user interactions
    const onActivity = () => {
      this.lastActivityTime = Date.now();
      this.hasRecentActivity = true;
    };

    ['mousedown', 'keydown', 'scroll', 'touchstart'].forEach(evt => {
      window.addEventListener(evt, onActivity, { passive: true });
    });

    // Periodic watchdog checks for user inactivity
    if (this.sessionTimer) clearInterval(this.sessionTimer);
    this.sessionTimer = setInterval(() => {
      this.checkSessionInactivity();
    }, 10000);

    // Sliding refresh: refresh token periodically only if user has been active
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    const refreshIntervalMs = Math.max(60000, Math.min(300000, (this.sessionTimeoutMinutes * 60 * 1000) / 4));
    this.refreshTimer = setInterval(() => {
      if (this.hasRecentActivity && this.authRequired) {
        this.refreshSession();
        this.hasRecentActivity = false;
      }
    }, refreshIntervalMs);

    // Immediate check on tab focus / wake
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        this.checkSessionInactivity();
      }
    });
  },

  checkSessionInactivity() {
    if (!this.authRequired) return;
    const idleSeconds = (Date.now() - this.lastActivityTime) / 1000;
    const maxSeconds = this.sessionTimeoutMinutes * 60;
    if (idleSeconds >= maxSeconds) {
      this.handleSessionExpired();
    }
  },

  async refreshSession() {
    try {
      await fetch('/api/auth/refresh', { method: 'POST' });
    } catch (_) {}
  },

  async handleSessionExpired() {
    if (this.sessionTimer) clearInterval(this.sessionTimer);
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (_) {}
    window.location.href = '/login?expired=1';
  },

  async logout() {
    if (this.sessionTimer) clearInterval(this.sessionTimer);
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
      console.warn("Logout error:", e);
    }
    window.location.href = '/login';
  },

  showLoginModal() {
    this.handleSessionExpired();
  },

  openEulaModal() {
    const modal = document.getElementById('eula-modal');
    if (modal) modal.classList.add('open');
  },

  closeEulaModal() {
    const modal = document.getElementById('eula-modal');
    if (modal) modal.classList.remove('open');
  },

  async acceptEula() {
    try {
      const res = await fetch('/api/server/eula', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accepted: true })
      });
      if (res.ok) {
        this.closeEulaModal();
        this.showToast('EULA aceptado correctamente', 'success');
        // Auto start server if on console tab
        if (typeof Console !== 'undefined' && Console.serverAction) {
          Console.serverAction('start');
        }
      }
    } catch (e) {
      this.showToast('Error al aceptar el EULA', 'danger');
    }
  },

  async rejectEula() {
    try {
      await fetch('/api/server/eula', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accepted: false })
      });
      this.closeEulaModal();
      this.showToast('EULA rechazado. Minecraft no se iniciará.', 'warning');
    } catch (e) {
      this.closeEulaModal();
    }
  },

  togglePasswordVisibility() {
    const input = document.getElementById('login-password-input');
    const btn = document.getElementById('login-password-toggle');
    if (!input) return;
    if (input.type === 'password') {
      input.type = 'text';
      if (btn) btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    } else {
      input.type = 'password';
      if (btn) btn.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    }
  },

  async login(password) {
    const btn = document.getElementById('btn-login-submit');
    const input = document.getElementById('login-password-input');
    const errorEl = document.getElementById('login-error-msg');
    const card = document.getElementById('login-card');

    if (!password) {
      if (errorEl) {
        errorEl.textContent = 'Por favor ingresa la contraseña de administrador.';
        errorEl.style.display = 'block';
      }
      return;
    }

    if (errorEl) errorEl.style.display = 'none';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spin-icon">↻</span> Verificando...';
    }

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      });
      if (res.ok) {
        const modal = document.getElementById('login-modal');
        if (modal) modal.classList.remove('open');
        this.showToast('¡Bienvenido a Dockraft!', 'success');
        if (input) input.value = '';
        Console.init();
      } else {
        if (card) {
          card.classList.remove('shake');
          void card.offsetWidth;
          card.classList.add('shake');
        }
        if (errorEl) {
          errorEl.textContent = 'Contraseña incorrecta. Inténtalo de nuevo.';
          errorEl.style.display = 'block';
        }
        if (input) {
          input.focus();
          input.select();
        }
      }
    } catch (e) {
      if (errorEl) {
        errorEl.textContent = 'Error de conexión con el servidor Dockraft.';
        errorEl.style.display = 'block';
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Ingresar a Dockraft →';
      }
    }
  },

  showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      // Fallback: create the container if somehow missing
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    // Do not spam identical messages
    const existing = Array.from(container.children).find(el => el.textContent === message);
    if (existing) return;

    // Limit maximum toasts to 3
    while (container.children.length >= 3) {
      container.removeChild(container.firstChild);
    }

    const typeStyles = {
      success: { bg: '#238636', border: '#2ea043' },
      danger:  { bg: '#da3633', border: '#f85149' },
      warning: { bg: '#9e6a03', border: '#d29922' },
      info:    { bg: '#1f6feb', border: '#388bfd' },
    };
    const style = typeStyles[type] || typeStyles.info;

    const toast = document.createElement('div');
    toast.style.cssText = `
      background: ${style.bg};
      border: 1px solid ${style.border};
      color: white;
      padding: 10px 16px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      animation: fadeIn 0.15s ease-out;
      max-width: 320px;
      word-break: break-word;
    `;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3500);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();

  // Wire up logout button hover effect (inline style can't do :hover)
  const logoutBtn = document.getElementById('btn-logout');
  if (logoutBtn) {
    logoutBtn.addEventListener('mouseenter', () => {
      logoutBtn.style.color = '#f85149';
      logoutBtn.style.borderColor = '#da3633';
      logoutBtn.style.backgroundColor = 'rgba(218,54,51,0.1)';
    });
    logoutBtn.addEventListener('mouseleave', () => {
      logoutBtn.style.color = '#8b949e';
      logoutBtn.style.borderColor = '#30363d';
      logoutBtn.style.backgroundColor = 'transparent';
    });
    // Intercept to call POST /api/auth/logout before navigating
    logoutBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (_) {}
      window.location.href = '/login';
    });
  }
});
