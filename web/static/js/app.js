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

    this.initBannerToggle();

    // Register Service Worker for PWA if supported
    if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
      navigator.serviceWorker.register('/static/sw.js').then((reg) => {
        reg.update().catch(() => {});
        console.log('[Dockraft PWA] Service Worker registrado con éxito:', reg.scope);
      }).catch((err) => {
        console.debug('[Dockraft PWA] Service Worker registration skipped:', err);
      });
    }
  },

  initBannerToggle() {
    const banner = document.getElementById('server-overview-banner');
    const bar = document.getElementById('banner-mobile-bar');
    if (!banner) return;

    if (bar && !bar._toggleBound) {
      bar._toggleBound = true;
      bar.setAttribute('role', 'button');
      bar.setAttribute('tabindex', '0');
      bar.setAttribute('aria-expanded', 'false');

      const onToggle = (e) => {
        if (e) {
          e.preventDefault();
          e.stopPropagation();
        }
        this.toggleBannerDetails();
      };

      bar.addEventListener('click', onToggle);
      bar.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.toggleBannerDetails();
        }
      });
    }

    try {
      const saved = localStorage.getItem('dockraft_banner_expanded');
      if (saved === '1') {
        banner.classList.add('expanded');
        if (bar) bar.setAttribute('aria-expanded', 'true');
        const hint = document.getElementById('banner-toggle-hint');
        if (hint) hint.textContent = typeof I18n !== 'undefined' ? I18n.t('banner_collapse', 'Ocultar') : 'Ocultar';
      }
    } catch(e) {}
  },

  toggleBannerDetails() {
    const banner = document.getElementById('server-overview-banner');
    const bar = document.getElementById('banner-mobile-bar');
    const hint = document.getElementById('banner-toggle-hint');
    if (!banner) return;
    const isExpanded = banner.classList.toggle('expanded');
    if (bar) {
      bar.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
    }
    if (hint) {
      hint.textContent = isExpanded 
        ? (typeof I18n !== 'undefined' ? I18n.t('banner_collapse', 'Ocultar') : 'Ocultar')
        : (typeof I18n !== 'undefined' ? I18n.t('banner_expand', 'Expandir') : 'Expandir');
    }
    try {
      localStorage.setItem('dockraft_banner_expanded', isExpanded ? '1' : '0');
    } catch(e) {}
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

    // Auto-scroll active tab into view in mobile nav rail
    const activeBtn = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
    if (activeBtn && activeBtn.scrollIntoView) {
      activeBtn.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }

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
    } else if (tabId === 'logs') {
      if (typeof Logs !== 'undefined') {
        Logs.loadLogs();
        Logs.startPolling();
      }
    }

    if (tabId !== 'logs' && typeof Logs !== 'undefined') {
      Logs.stopPolling();
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
  },

  ensureConfirmModal() {
    let modal = document.getElementById('modal-app-confirm');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.className = 'modal-backdrop modal-dialog-backdrop';
    modal.id = 'modal-app-confirm';
    modal.style.zIndex = '1200';
    modal.innerHTML = `
      <div class="modal-box modal-dialog-box" style="max-width: 480px;">
        <div class="modal-header" style="padding: 16px 20px; border-bottom: 1px solid #30363d;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <div id="modal-confirm-icon" style="width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;"></div>
            <h3 id="modal-confirm-title-text" style="font-size: 1.05rem; font-weight: 600; color: #f0f6fc; margin: 0;">Confirmación</h3>
          </div>
          <button class="action-icon-btn" id="modal-confirm-btn-close" type="button" aria-label="Cerrar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body" style="padding: 20px;">
          <div id="modal-confirm-message" style="font-size: 0.92rem; line-height: 1.6; color: #cbd5e1; white-space: pre-line; word-break: break-word;"></div>
        </div>
        <div class="modal-footer" style="padding: 14px 20px; border-top: 1px solid #30363d; display: flex; justify-content: flex-end; gap: 10px;">
          <button type="button" class="btn btn-outline" id="modal-confirm-btn-cancel">Cancelar</button>
          <button type="button" class="btn btn-danger" id="modal-confirm-btn-ok">Confirmar</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  },

  ensurePromptModal() {
    let modal = document.getElementById('modal-app-prompt');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.className = 'modal-backdrop modal-dialog-backdrop';
    modal.id = 'modal-app-prompt';
    modal.style.zIndex = '1200';
    modal.innerHTML = `
      <div class="modal-box modal-dialog-box" style="max-width: 480px;">
        <div class="modal-header" style="padding: 16px 20px; border-bottom: 1px solid #30363d;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <div id="modal-prompt-icon" style="width: 36px; height: 36px; border-radius: 8px; background: rgba(56, 139, 253, 0.15); border: 1px solid rgba(56, 139, 253, 0.3); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </div>
            <h3 id="modal-prompt-title-text" style="font-size: 1.05rem; font-weight: 600; color: #f0f6fc; margin: 0;">Entrada Requerida</h3>
          </div>
          <button class="action-icon-btn" id="modal-prompt-btn-close" type="button" aria-label="Cerrar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body" style="padding: 20px;">
          <div id="modal-prompt-message" style="font-size: 0.92rem; line-height: 1.5; color: #cbd5e1; margin-bottom: 14px; white-space: pre-line; word-break: break-word;"></div>
          <div class="form-group" style="margin-bottom: 0;">
            <input type="text" class="form-input" id="modal-prompt-input" autocomplete="off" spellcheck="false" style="font-size: 0.95rem; padding: 9px 12px;">
          </div>
        </div>
        <div class="modal-footer" style="padding: 14px 20px; border-top: 1px solid #30363d; display: flex; justify-content: flex-end; gap: 10px;">
          <button type="button" class="btn btn-outline" id="modal-prompt-btn-cancel">Cancelar</button>
          <button type="button" class="btn btn-primary" id="modal-prompt-btn-ok">Aceptar</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  },

  confirm(options) {
    return new Promise((resolve) => {
      const modal = this.ensureConfirmModal();

      const opts = typeof options === 'string' ? { message: options } : (options || {});
      const isDanger = Boolean(opts.danger || opts.type === 'danger');
      const isWarning = Boolean(opts.warning || opts.type === 'warning');

      const titleEl = document.getElementById('modal-confirm-title-text');
      const iconEl = document.getElementById('modal-confirm-icon');
      const msgEl = document.getElementById('modal-confirm-message');
      const btnOk = document.getElementById('modal-confirm-btn-ok');
      const btnCancel = document.getElementById('modal-confirm-btn-cancel');
      const btnClose = document.getElementById('modal-confirm-btn-close');

      if (titleEl) titleEl.textContent = opts.title || (isDanger ? 'Confirmación requerida' : 'Confirmar Acción');
      if (msgEl) msgEl.textContent = opts.message || '¿Estás seguro de continuar con esta acción?';

      if (btnOk) {
        btnOk.textContent = opts.confirmText || (isDanger ? 'Eliminar' : 'Confirmar');
        btnOk.className = isDanger ? 'btn btn-danger' : (isWarning ? 'btn btn-warning' : 'btn btn-primary');
      }
      if (btnCancel) {
        btnCancel.textContent = opts.cancelText || 'Cancelar';
      }

      if (iconEl) {
        if (isDanger) {
          iconEl.style.background = 'rgba(248, 81, 73, 0.15)';
          iconEl.style.border = '1px solid rgba(248, 81, 73, 0.3)';
          iconEl.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
        } else if (isWarning) {
          iconEl.style.background = 'rgba(210, 153, 34, 0.15)';
          iconEl.style.border = '1px solid rgba(210, 153, 34, 0.3)';
          iconEl.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#d29922" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
        } else {
          iconEl.style.background = 'rgba(56, 139, 253, 0.15)';
          iconEl.style.border = '1px solid rgba(56, 139, 253, 0.3)';
          iconEl.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
        }
      }

      let resolved = false;
      const finish = (result) => {
        if (resolved) return;
        resolved = true;
        modal.classList.remove('open');
        window.removeEventListener('keydown', onKeyDown);
        resolve(result);
      };

      const onKeyDown = (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          finish(false);
        } else if (e.key === 'Enter') {
          if (document.activeElement === btnCancel) {
            e.preventDefault();
            finish(false);
          } else {
            e.preventDefault();
            finish(true);
          }
        }
      };

      if (btnOk) btnOk.onclick = () => finish(true);
      if (btnCancel) btnCancel.onclick = () => finish(false);
      if (btnClose) btnClose.onclick = () => finish(false);
      modal.onclick = (e) => {
        if (e.target === modal) finish(false);
      };

      window.addEventListener('keydown', onKeyDown);
      modal.classList.add('open');

      if (isDanger && btnCancel) {
        btnCancel.focus();
      } else if (btnOk) {
        btnOk.focus();
      }
    });
  },

  prompt(options) {
    return new Promise((resolve) => {
      const modal = this.ensurePromptModal();

      const opts = typeof options === 'string' ? { message: options } : (options || {});
      const titleEl = document.getElementById('modal-prompt-title-text');
      const msgEl = document.getElementById('modal-prompt-message');
      const inputEl = document.getElementById('modal-prompt-input');
      const btnOk = document.getElementById('modal-prompt-btn-ok');
      const btnCancel = document.getElementById('modal-prompt-btn-cancel');
      const btnClose = document.getElementById('modal-prompt-btn-close');

      if (titleEl) titleEl.textContent = opts.title || 'Entrada Requerida';
      if (msgEl) msgEl.textContent = opts.message || '';
      if (inputEl) {
        inputEl.placeholder = opts.placeholder || '';
        inputEl.value = opts.defaultValue || '';
      }
      if (btnOk) btnOk.textContent = opts.confirmText || 'Aceptar';
      if (btnCancel) btnCancel.textContent = opts.cancelText || 'Cancelar';

      let resolved = false;
      const finish = (result) => {
        if (resolved) return;
        resolved = true;
        modal.classList.remove('open');
        window.removeEventListener('keydown', onKeyDown);
        resolve(result);
      };

      const onKeyDown = (e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          finish(null);
        } else if (e.key === 'Enter') {
          e.preventDefault();
          finish(inputEl ? inputEl.value : '');
        }
      };

      if (btnOk) btnOk.onclick = () => finish(inputEl ? inputEl.value : '');
      if (btnCancel) btnCancel.onclick = () => finish(null);
      if (btnClose) btnClose.onclick = () => finish(null);
      modal.onclick = (e) => {
        if (e.target === modal) finish(null);
      };

      window.addEventListener('keydown', onKeyDown);
      modal.classList.add('open');

      if (inputEl) {
        setTimeout(() => {
          inputEl.focus();
          inputEl.select();
        }, 50);
      }
    });
  }
};

window.App = App;
window.toggleBannerDetails = () => App.toggleBannerDetails();

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
