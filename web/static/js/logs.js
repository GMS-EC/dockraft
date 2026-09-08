// Dockraft Activity & Console Audit Logs Script
const Logs = {
  logs: [],
  currentCategory: 'all',
  searchQuery: '',
  pollingTimer: null,
  autoRefresh: true,
  isFetching: false,

  async init() {
    this.setupEvents();
  },

  setupEvents() {
    // Search input listener is attached via HTML oninput
  },

  async loadLogs(showToast = false) {
    if (this.isFetching) return;
    this.isFetching = true;

    try {
      const res = await fetch('/api/activity/logs?limit=1000');
      if (!res.ok) throw new Error("Error al consultar registros de actividad");
      const data = await res.json();
      this.logs = data.logs || [];

      // Update counters
      const totalEl = document.getElementById('logs-total-count');
      const cmdsEl = document.getElementById('logs-commands-count');
      const sysEl = document.getElementById('logs-system-count');

      const total = this.logs.length;
      const cmds = this.logs.filter(l => l.category === 'console').length;
      const sys = this.logs.filter(l => l.category !== 'console').length;

      if (totalEl) totalEl.textContent = `${total} registros`;
      if (cmdsEl) cmdsEl.textContent = `${cmds} comandos`;
      if (sysEl) sysEl.textContent = `${sys} eventos`;

      this.render();

      if (showToast) {
        App.showToast("Registros actualizados correctamente", 'info');
      }
    } catch (err) {
      console.warn("Could not load activity logs:", err);
      if (showToast) {
        App.showToast(err.message, 'danger');
      }
    } finally {
      this.isFetching = false;
    }
  },

  render() {
    const tbody = document.getElementById('logs-table-body');
    const emptyState = document.getElementById('logs-empty-state');
    const pageInfo = document.getElementById('logs-pagination-info');
    if (!tbody) return;

    const q = (this.searchQuery || '').trim().toLowerCase();
    const cat = this.currentCategory;

    const filtered = this.logs.filter(item => {
      // Category filter
      if (cat !== 'all' && item.category !== cat) return false;

      // Text search filter
      if (q) {
        const strAction = (item.action || '').toLowerCase();
        const strMsg = (item.message || '').toLowerCase();
        const strDetail = (item.details || item.detail || '').toLowerCase();
        const strUser = (item.user || '').toLowerCase();
        if (!strAction.includes(q) && !strMsg.includes(q) && !strDetail.includes(q) && !strUser.includes(q)) {
          return false;
        }
      }
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = '';
      if (emptyState) emptyState.style.display = 'block';
      if (pageInfo) pageInfo.textContent = 'Mostrando 0 registros';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (pageInfo) {
      pageInfo.textContent = `Mostrando ${filtered.length} de ${this.logs.length} registros`;
    }

    tbody.innerHTML = filtered.map(item => {
      const catBadge = this.formatCategoryBadge(item.category);
      const statusBadge = this.formatStatusBadge(item.status || item.level);
      const timeStr = this.formatTimestamp(item.timestamp);
      const detailHtml = this.formatDetail(item);
      const userStr = escapeHtml(item.user || 'admin');
      const actionStr = escapeHtml(this.formatAction(item.action));

      return `
        <tr style="border-bottom: 1px solid rgba(48, 54, 61, 0.5); font-size: 0.83rem;">
          <td style="color: var(--text-dim); white-space: nowrap; font-family: var(--font-mono); font-size: 0.78rem;">
            ${timeStr}
          </td>
          <td>${catBadge}</td>
          <td style="font-weight: 500; color: #c9d1d9;">${actionStr}</td>
          <td style="word-break: break-word;">${detailHtml}</td>
          <td>
            <span style="font-size: 0.76rem; color: #8b949e; background: rgba(110, 118, 129, 0.1); padding: 2px 6px; border-radius: 4px;">
              ${userStr}
            </span>
          </td>
          <td style="text-align: center;">${statusBadge}</td>
        </tr>
      `;
    }).join('');
  },

  formatCategoryBadge(cat) {
    switch (cat) {
      case 'console':
        return `<span class="badge" style="background: rgba(163, 113, 247, 0.15); border: 1px solid #8957e5; color: #d2a8ff; font-size: 0.74rem;">⌨️ Consola</span>`;
      case 'server':
        return `<span class="badge" style="background: rgba(46, 160, 67, 0.15); border: 1px solid #2ea043; color: #3fb950; font-size: 0.74rem;">⚡ Servidor</span>`;
      case 'backup':
        return `<span class="badge" style="background: rgba(56, 139, 253, 0.15); border: 1px solid #388bfd; color: #58a6ff; font-size: 0.74rem;">💾 Respaldo</span>`;
      case 'update':
        return `<span class="badge" style="background: rgba(45, 212, 191, 0.15); border: 1px solid #2dd4bf; color: #5eead4; font-size: 0.74rem;">🔄 Actualización</span>`;
      case 'security':
        return `<span class="badge" style="background: rgba(248, 81, 73, 0.15); border: 1px solid #f85149; color: #ff7b72; font-size: 0.74rem;">🛡️ Seguridad</span>`;
      case 'tasks':
        return `<span class="badge" style="background: rgba(227, 179, 65, 0.15); border: 1px solid #d29922; color: #f2cc60; font-size: 0.74rem;">⏱️ Tarea</span>`;
      default:
        return `<span class="badge" style="font-size: 0.74rem;">${escapeHtml(cat || 'general')}</span>`;
    }
  },

  formatStatusBadge(level) {
    switch (level) {
      case 'success':
        return `<span class="badge badge-success" style="font-size: 0.72rem;">Éxito</span>`;
      case 'error':
        return `<span class="badge badge-danger" style="font-size: 0.72rem;">Error</span>`;
      case 'warning':
        return `<span class="badge badge-warning" style="font-size: 0.72rem;">Aviso</span>`;
      default:
        return `<span class="badge" style="background: rgba(110, 118, 129, 0.2); border: 1px solid #30363d; color: #8b949e; font-size: 0.72rem;">Info</span>`;
    }
  },

  formatTimestamp(ts) {
    if (!ts) return '--';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return escapeHtml(ts);
      return d.toLocaleString('es-ES', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    } catch (e) {
      return escapeHtml(ts);
    }
  },

  formatAction(act) {
    if (!act) return 'Evento';
    const dict = {
      'command_executed': 'Comando ejecutado',
      'server_start': 'Inicio de servidor',
      'server_stop': 'Parada de servidor',
      'server_kill': 'Forzar apagado (Kill)',
      'backup_created': 'Copia creada',
      'backup_restored': 'Copia restaurada',
      'backup_deleted': 'Copia eliminada',
      'server_update': 'Actualización aplicada',
      'login_success': 'Inicio de sesión',
      'login_failed': 'Fallo de autenticación',
      'logout': 'Cierre de sesión',
      'task_run': 'Tarea programada'
    };
    return dict[act] || act;
  },

  formatDetail(item) {
    const rawDetail = item.details || item.detail || item.message || '';
    if (item.category === 'console') {
      const cleanCmd = String(rawDetail).replace(/^>\s*/, '');
      const cmd = escapeHtml(cleanCmd);
      return `
        <div style="display: inline-flex; align-items: center; gap: 6px; background: rgba(0, 0, 0, 0.35); padding: 3px 8px; border-radius: 4px; border: 1px solid rgba(163, 113, 247, 0.25);">
          <span style="color: #d2a8ff; font-family: var(--font-mono); font-size: 0.82rem;">&gt;</span>
          <code style="font-family: var(--font-mono); color: #79c0ff; font-size: 0.83rem; font-weight: 500;">${cmd}</code>
          <button onclick="Logs.copyCommand('${cmd.replace(/'/g, "\\'")}')" title="Copiar comando" style="background: none; border: none; color: #8b949e; cursor: pointer; padding: 2px 4px; display: inline-flex; align-items: center; font-size: 0.75rem;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          </button>
        </div>
      `;
    }

    const msg = escapeHtml(item.message || '');
    const detail = rawDetail && rawDetail !== item.message ? `<div style="font-size: 0.76rem; color: var(--text-dim); margin-top: 2px;">${escapeHtml(rawDetail)}</div>` : (item.message ? '' : escapeHtml(rawDetail));
    return `<div>${msg}${detail}</div>`;
  },

  copyCommand(cmd) {
    navigator.clipboard.writeText(cmd).then(() => {
      App.showToast(`Comando copiado: "${cmd}"`, 'info');
    }).catch(() => {
      App.showToast("No se pudo copiar al portapapeles", 'warning');
    });
  },

  setCategory(cat) {
    this.currentCategory = cat;
    document.querySelectorAll('.log-chip').forEach(chip => {
      chip.classList.toggle('active', chip.getAttribute('data-category') === cat);
    });
    this.render();
  },

  handleSearch(query) {
    this.searchQuery = query;
    this.render();
  },

  toggleAutoRefresh(enabled) {
    this.autoRefresh = enabled;
    if (enabled) {
      this.startPolling();
    } else {
      this.stopPolling();
    }
  },

  startPolling() {
    this.stopPolling();
    if (this.autoRefresh) {
      this.pollingTimer = setInterval(() => {
        if (App.activeTab === 'logs') {
          this.loadLogs(false);
        }
      }, 5000);
    }
  },

  stopPolling() {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  },

  async clearLogs() {
    const ok = await App.confirm({
      title: 'Vaciar Historial de Registros',
      message: '¿Estás seguro de que deseas eliminar todo el historial de auditoría y comandos de consola?\n\nEsta acción no se puede deshacer.',
      confirmText: 'Limpiar Todo',
      danger: true
    });
    if (!ok) return;

    try {
      const res = await fetch('/api/activity/clear', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error al limpiar registros");
      App.showToast("Historial de registros vaciado", 'success');
      await this.loadLogs();
    } catch (err) {
      App.showToast(err.message, 'danger');
    }
  },

  exportLogs(format = 'csv') {
    const link = document.createElement('a');
    link.href = `/api/activity/export?format=${format}`;
    link.download = `dockraft_audit_logs_${Date.now()}.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    App.showToast(`Descargando registros en formato ${format.toUpperCase()}...`, 'info');
  }
};
