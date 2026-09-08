// Dockraft Console & Controls Script
const Console = {
  socket: null,
  history: [],
  historyIndex: -1,
  maxLogs: 1500,

  init() {
    this.setupWebSocket();
    this.setupEvents();
    this.pollStatus();

    window.addEventListener('dockraft:language_changed', () => {
      if (this.lastStats) this.updateStats(this.lastStats);
    });
  },

  setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/console`;

    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      this.appendTerminalLine("[Dockraft] Connected to live server console stream.");
    };

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'init') {
          this.updateStatusUI(msg.status);
          const body = document.getElementById('terminal-content');
          if (body) body.innerHTML = '';
          (msg.history || []).forEach(line => this.appendTerminalLine(line));
        } else if (msg.type === 'log') {
          this.appendTerminalLine(msg.data);
        } else if (msg.type === 'status') {
          this.updateStatusUI(msg.status);
        } else if (msg.type === 'eula_required') {
          App.openEulaModal();
        } else if (msg.type === 'stats') {
          this.updateStatsUI(msg.data);
          this.checkInstalled(msg.data);
        }
      } catch (e) {
        console.error("Error parsing WS message:", e);
      }
    };

    this.socket.onclose = (event) => {
      if (event && (event.code === 4001 || event.code === 4003)) {
        if (typeof App !== 'undefined' && App.handleSessionExpired) {
          App.handleSessionExpired();
        } else {
          window.location.href = '/login?expired=1';
        }
        return;
      }
      this.appendTerminalLine("[Dockraft] Connection to console lost. Reconnecting in 3s...");
      setTimeout(() => this.setupWebSocket(), 3000);
    };
  },

  setupEvents() {
    const input = document.getElementById('terminal-cmd-input');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          this.sendCurrentCommand();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (this.history.length > 0) {
            if (this.historyIndex === -1) this.historyIndex = this.history.length - 1;
            else if (this.historyIndex > 0) this.historyIndex--;
            input.value = this.history[this.historyIndex] || '';
          }
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (this.historyIndex !== -1) {
            if (this.historyIndex < this.history.length - 1) {
              this.historyIndex++;
              input.value = this.history[this.historyIndex];
            } else {
              this.historyIndex = -1;
              input.value = '';
            }
          }
        }
      });
    }

    // Button controls
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const btnRestart = document.getElementById('btn-restart');
    const btnKill = document.getElementById('btn-kill');

    if (btnStart) btnStart.addEventListener('click', () => this.serverAction('start'));
    if (btnStop) btnStop.addEventListener('click', () => this.serverAction('stop'));
    if (btnRestart) btnRestart.addEventListener('click', () => this.serverAction('restart'));
    if (btnKill) btnKill.addEventListener('click', () => {
      if (confirm("¿Confirmas forzar el apagado inmediato (Kill) del servidor? Se terminará cualquier proceso de Minecraft activo y se liberarán los bloqueos de disco.")) {
        this.serverAction('kill');
      }
    });

    // Clear console button
    const btnClear = document.getElementById('btn-clear-console');
    if (btnClear) {
      btnClear.addEventListener('click', () => {
        const body = document.getElementById('terminal-content');
        if (body) body.innerHTML = '';
      });
    }
  },

  sendCurrentCommand() {
    const input = document.getElementById('terminal-cmd-input');
    if (!input) return;
    const cmd = input.value.trim();
    if (!cmd) return;

    this.sendCommand(cmd);
    this.history.push(cmd);
    this.historyIndex = -1;
    input.value = '';
  },

  sendCommand(cmd) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'command', command: cmd }));
    } else {
      // Fallback via HTTP REST
      fetch('/api/server/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd })
      });
    }
  },

  async serverAction(action) {
    if (action === 'start') {
      try {
        const eRes = await fetch('/api/server/eula');
        if (eRes.ok) {
          const eData = await eRes.json();
          if (!eData.accepted) {
            App.openEulaModal();
            return;
          }
        }
      } catch (e) {}
    }

    try {
      const res = await fetch(`/api/server/${action}`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'error') {
        App.showToast(data.message, 'danger');
      } else {
        const labels = {
          start: typeof I18n !== 'undefined' ? I18n.t('toast_server_started') : 'Servidor iniciado',
          stop: typeof I18n !== 'undefined' ? I18n.t('toast_server_stopped') : 'Detención solicitada',
          restart: typeof I18n !== 'undefined' ? I18n.t('toast_server_restarted') : 'Reinicio solicitado',
          kill: typeof I18n !== 'undefined' ? I18n.t('toast_server_killed') : 'Servidor finalizado forzadamente (Kill)'
        };
        App.showToast(labels[action] || `Acción ${action} ejecutada`, 'success');
      }
    } catch (e) {
      App.showToast(`Error al ejecutar acción ${action}`, 'danger');
    }
  },

  checkedInitialInstall: false,

  checkInstalled(stats) {
    if (!stats) return;
    const banner = document.getElementById('console-uninstalled-banner');
    if (stats.is_installed === false) {
      if (banner) banner.style.display = 'flex';
      if (!this.checkedInitialInstall) {
        this.checkedInitialInstall = true;
        // Automatically switch to installer tab on first load if no server is installed
        setTimeout(() => {
          App.switchTab('installer');
          App.showToast("Bienvenido: Selecciona una versión para instalar tu servidor", 'info');
        }, 300);
      }
    } else {
      if (banner) banner.style.display = 'none';
      this.checkedInitialInstall = true;
    }
  },

  async pollStatus() {
    try {
      const res = await fetch('/api/server/status');
      if (res.ok) {
        const stats = await res.json();
        this.updateStatusUI(stats.status);
        this.updateStatsUI(stats);
        this.checkInstalled(stats);
      }
    } catch (e) {}
  },

  updateStatusUI(status) {
    const pill = document.getElementById('status-pill');
    const text = document.getElementById('status-text');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    const btnRestart = document.getElementById('btn-restart');
    const btnKill = document.getElementById('btn-kill');

    if (pill) {
      pill.className = `status-pill ${status.toLowerCase()}`;
    }
    if (text) {
      text.textContent = status;
    }

    const isOffline = status === 'OFFLINE';
    const isRunning = status === 'RUNNING';
    const isStarting = status === 'STARTING';
    const isStopping = status === 'STOPPING';

    if (btnStart) btnStart.disabled = !isOffline;
    if (btnStop) btnStop.disabled = isOffline || isStopping;
    if (btnRestart) btnRestart.disabled = isOffline || isStopping;
    // Botón Kill siempre disponible como mecanismo de emergencia contra bloqueos o procesos huérfanos
    if (btnKill) btnKill.disabled = false;
  },

  updateStatsUI(stats) {
    if (!stats) return;

    // CPU (normalized to process usage)
    const cpuVal = document.getElementById('stat-cpu-val');
    const cpuBar = document.getElementById('stat-cpu-bar');
    const cpuPct = stats.cpu_percent !== undefined ? Number(stats.cpu_percent) : 0;
    if (cpuVal) cpuVal.textContent = `${cpuPct.toFixed(1)}%`;
    if (cpuBar) {
      cpuBar.style.width = `${Math.min(cpuPct, 100)}%`;
      cpuBar.className = cpuPct > 80 ? 'progress-bar-fill danger' : (cpuPct > 50 ? 'progress-bar-fill warning' : 'progress-bar-fill');
    }

    // Memory (relative to allocated server memory)
    const memVal = document.getElementById('stat-mem-val');
    const memBar = document.getElementById('stat-mem-bar');
    const assignedMem = stats.assigned_memory_mb || 2048;
    const currentMem = stats.memory_mb || 0;
    const memPct = stats.memory_percent !== undefined ? Number(stats.memory_percent) : Math.round((currentMem / assignedMem) * 100);

    if (memVal) {
      memVal.textContent = `${Math.round(currentMem)} MB / ${Math.round(assignedMem)} MB (${memPct}%)`;
    }
    if (memBar) {
      memBar.style.width = `${Math.min(memPct, 100)}%`;
      memBar.className = memPct > 85 ? 'progress-bar-fill danger' : (memPct > 65 ? 'progress-bar-fill warning' : 'progress-bar-fill');
    }

    // Disk Usage
    const diskVal = document.getElementById('stat-disk-val');
    const diskBar = document.getElementById('stat-disk-bar');
    if (diskVal) {
      const usedGb = ((stats.disk_used_mb || 0) / 1024).toFixed(2);
      const limitGb = ((stats.disk_limit_mb || 10240) / 1024).toFixed(1);
      const diskPct = stats.disk_percent !== undefined ? Number(stats.disk_percent) : 0;
      diskVal.textContent = `${usedGb} GB / ${limitGb} GB (${diskPct}%)`;
      if (diskBar) {
        diskBar.style.width = `${Math.min(diskPct, 100)}%`;
        diskBar.className = diskPct > 85 ? 'progress-bar-fill danger' : (diskPct > 65 ? 'progress-bar-fill warning' : 'progress-bar-fill');
      }
    }

    // Server ID / PID Badge
    const pidBadge = document.getElementById('stat-pid-badge');
    if (pidBadge) {
      if (stats.pid) {
        pidBadge.textContent = `ID: #${stats.pid}`;
        pidBadge.style.color = '#79c0ff';
        pidBadge.style.borderColor = 'rgba(56, 139, 253, 0.4)';
      } else {
        pidBadge.textContent = 'ID: --';
        pidBadge.style.color = 'var(--text-muted)';
        pidBadge.style.borderColor = 'var(--border-color)';
      }
    }

    // Top Overview 3-Column Banner (Reference Image Metrics)
    const topStatus = document.getElementById('top-server-status');
    const topStarted = document.getElementById('top-server-started');
    const topUptime = document.getElementById('top-server-uptime');
    const topTz = document.getElementById('top-server-timezone');
    const topCpu = document.getElementById('top-server-cpu');
    const topMem = document.getElementById('top-server-memory');
    const topPlayers = document.getElementById('top-server-players');
    const topName = document.getElementById('top-server-name');
    const topVersion = document.getElementById('top-server-version');
    const topMotd = document.getElementById('top-server-motd');
    const topType = document.getElementById('top-server-type');

    this.lastStats = stats;
    if (topTz) topTz.textContent = stats.timezone || 'America/Guayaquil';

    if (!stats.is_installed) {
      if (topStatus) {
        topStatus.textContent = typeof I18n !== 'undefined' ? I18n.t('banner_none_installed', 'Sin instalar') : 'Sin instalar';
        topStatus.className = 'overview-val status-text-inline offline';
      }
      if (topName) topName.textContent = '--';
      if (topStarted) topStarted.textContent = '--';
      if (topUptime) topUptime.textContent = '--';
      if (topCpu) topCpu.textContent = '0 %';
      if (topMem) topMem.textContent = '0 MB / --';
      if (topPlayers) topPlayers.textContent = '--';
      if (topVersion) topVersion.textContent = typeof I18n !== 'undefined' ? I18n.t('banner_none_installed', 'Sin instalar') : 'Sin instalar';
      if (topMotd) topMotd.textContent = typeof I18n !== 'undefined' ? I18n.t('banner_none_installed', 'Ningún servidor instalado') : 'Ningún servidor instalado';
      if (topType) topType.textContent = '--';
    } else {
      if (topStatus) {
        const isOnline = stats.status === 'RUNNING';
        const isStarting = stats.status === 'STARTING';
        const isStopping = stats.status === 'STOPPING';
        let label = 'Apagado';
        if (isOnline) label = typeof I18n !== 'undefined' ? I18n.t('banner_status_running') : 'En línea';
        else if (isStarting) label = typeof I18n !== 'undefined' ? I18n.t('banner_status_starting') : 'Iniciando...';
        else if (isStopping) label = typeof I18n !== 'undefined' ? I18n.t('banner_status_stopping') : 'Deteniendo...';
        else label = typeof I18n !== 'undefined' ? I18n.t('banner_status_offline') : 'Apagado';
        topStatus.textContent = label;
        topStatus.className = `overview-val status-text-inline ${stats.status ? stats.status.toLowerCase() : 'offline'}`;
      }
      if (topName) topName.textContent = stats.server_name || 'Mi Servidor Dockraft';
      if (topStarted) topStarted.textContent = stats.started_at_str || (typeof I18n !== 'undefined' ? I18n.t('banner_status_offline') : 'No iniciado');
      if (topUptime) topUptime.textContent = stats.uptime_formatted || (typeof I18n !== 'undefined' ? I18n.t('banner_status_offline') : 'Fuera de línea');
      if (topCpu) topCpu.textContent = `${cpuPct.toFixed(1)} %`;
      if (topMem) {
        const curGb = (currentMem / 1024).toFixed(1);
        const maxGb = assignedMem > 0 ? (assignedMem / 1024).toFixed(1) : '2.0';
        topMem.textContent = `${curGb}GB / ${maxGb}GB`;
      }
      if (topPlayers) {
        topPlayers.textContent = `${stats.online_players || 0}/${stats.max_players || 20}`;
      }
      if (topVersion) {
        const typeLabel = stats.server_type ? (stats.server_type.charAt(0).toUpperCase() + stats.server_type.slice(1)) : 'Servidor';
        topVersion.textContent = `${typeLabel} ${stats.server_version || ''}`;
      }
      if (topMotd) topMotd.textContent = stats.motd || 'A Dockraft Minecraft Server';
      if (topType) topType.textContent = stats.server_type_display || 'minecraft-java';
    }
  },

  escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  },

  convertAnsiToHtml(text) {
    let html = this.escapeHtml(text);
    // Simple ANSI regex replacement
    html = html
      .replace(/\u001b\[0;31;1m/g, '<span style="color:#ef4444;font-weight:bold;">')
      .replace(/\u001b\[0;32;1m/g, '<span style="color:#10b981;font-weight:bold;">')
      .replace(/\u001b\[0;33;1m/g, '<span style="color:#f59e0b;font-weight:bold;">')
      .replace(/\u001b\[0;34;1m/g, '<span style="color:#3b82f6;font-weight:bold;">')
      .replace(/\u001b\[0;35;1m/g, '<span style="color:#a855f7;font-weight:bold;">')
      .replace(/\u001b\[0;36;1m/g, '<span style="color:#06b6d4;font-weight:bold;">')
      .replace(/\u001b\[0;37;1m/g, '<span style="color:#f3f4f6;font-weight:bold;">')
      .replace(/\u001b\[m/g, '</span>')
      .replace(/\u001b\[0m/g, '</span>')
      .replace(/\u001b\[.*?m/g, ''); // strip remaining ansi codes

    return html;
  },

  appendTerminalLine(rawLine) {
    const container = document.getElementById('terminal-content');
    if (!container) return;

    const lineElem = document.createElement('div');
    lineElem.innerHTML = this.convertAnsiToHtml(rawLine);
    container.appendChild(lineElem);

    // Limit elements to prevent memory leak in long running tabs
    while (container.childNodes.length > this.maxLogs) {
      container.removeChild(container.firstChild);
    }

    container.scrollTop = container.scrollHeight;
  }
};
