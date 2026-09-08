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
          if (msg.status === 'OFFLINE') {
            this.updateTpsUI(null);
          }
        } else if (msg.type === 'eula_required') {
          App.openEulaModal();
        } else if (msg.type === 'crash_diagnostics') {
          this.showCrashAlert(msg.data);
        } else if (msg.type === 'tps') {
          this.updateTpsUI(msg.data);
        } else if (msg.type === 'stats') {
          this.updateStatsUI(msg.data);
          this.checkInstalled(msg.data);
          if (msg.data && msg.data.tps) {
            this.updateTpsUI(msg.data.tps);
          }
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
    if (btnKill) btnKill.addEventListener('click', async () => {
      const ok = await App.confirm({
        title: 'Forzar Apagado Inmediato (Kill)',
        message: '¿Confirmas forzar el apagado inmediato (Kill) del servidor?\n\nSe terminará cualquier proceso de Minecraft activo inmediatamente y se liberarán los bloqueos de disco.',
        confirmText: 'Forzar Apagado',
        danger: true
      });
      if (ok) {
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

    if (isStarting || isRunning) {
      this.hideCrashAlert();
    }
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
      if (topUptime) {
        if (typeof I18n !== 'undefined' && stats.uptime_seconds !== undefined && stats.uptime_seconds !== null && Number(stats.uptime_seconds) > 0) {
          topUptime.textContent = I18n.formatUptime(Number(stats.uptime_seconds));
        } else {
          topUptime.textContent = stats.uptime_formatted || (typeof I18n !== 'undefined' ? I18n.t('banner_status_offline') : 'Fuera de línea');
        }
      }
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
      if (stats.tps) this.updateTpsUI(stats.tps);
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
  },

  updateTpsUI(tps) {
    const topTps = document.getElementById('top-server-tps');
    const kpiVal = document.getElementById('metric-kpi-tps-val');
    const kpiBadge = document.getElementById('metric-kpi-tps-badge');
    const kpi1m = document.getElementById('metric-kpi-tps-1m');
    const kpi5m = document.getElementById('metric-kpi-tps-5m');
    const kpi15m = document.getElementById('metric-kpi-tps-15m');

    if (!tps || tps.status === 'offline' || tps['1m'] === null || tps['1m'] === undefined) {
      if (topTps) {
        topTps.textContent = '--';
        topTps.style.color = 'var(--text-dim)';
      }
      if (kpiVal) kpiVal.textContent = '--';
      if (kpiBadge) {
        kpiBadge.textContent = 'Fuera de línea';
        kpiBadge.style.color = '#8b949e';
        kpiBadge.style.background = 'rgba(139, 148, 158, 0.15)';
      }
      return;
    }

    const val1m = Number(tps['1m']);
    const val5m = Number(tps['5m'] !== undefined ? tps['5m'] : val1m);
    const val15m = Number(tps['15m'] !== undefined ? tps['15m'] : val1m);

    let color = '#3fb950'; // green
    let label = 'Óptimo';
    let bg = 'rgba(46, 160, 67, 0.15)';

    if (val1m < 16.0) {
      color = '#f85149'; // red lag
      label = 'Lag Severo';
      bg = 'rgba(248, 81, 73, 0.15)';
    } else if (val1m < 19.5) {
      color = '#d29922'; // amber moderate
      label = 'Carga Moderada';
      bg = 'rgba(210, 153, 34, 0.15)';
    }

    if (topTps) {
      topTps.textContent = `${val1m.toFixed(1)} TPS`;
      topTps.style.color = color;
    }

    if (kpiVal) {
      kpiVal.textContent = val1m.toFixed(1);
      kpiVal.style.color = color;
    }
    if (kpiBadge) {
      kpiBadge.textContent = label;
      kpiBadge.style.color = color;
      kpiBadge.style.background = bg;
    }
    if (kpi1m) {
      kpi1m.textContent = val1m.toFixed(1);
      kpi1m.style.color = color;
    }
    if (kpi5m) {
      kpi5m.textContent = val5m.toFixed(1);
    }
    if (kpi15m) {
      kpi15m.textContent = val15m.toFixed(1);
    }
  },

  showCrashAlert(diag) {
    const alertBox = document.getElementById('console-crash-alert');
    const alertText = document.getElementById('console-crash-text');
    if (alertBox && alertText) {
      alertBox.style.display = 'flex';
      alertText.innerHTML = `<strong>¡Alerta de Caída!</strong> ${diag.title || 'Error no controlado'}: ${diag.cause || ''}`;
    }
    App.showToast(`El servidor se detuvo: ${diag.title || 'Caída inesperada'}`, 'danger');
  },

  hideCrashAlert() {
    const alertBox = document.getElementById('console-crash-alert');
    if (alertBox) {
      alertBox.style.display = 'none';
    }
  },

  openDiagnosticsModal() {
    const modal = document.getElementById('modal-diagnostics');
    if (modal) {
      modal.classList.add('open');
      this.switchDiagTab('analysis');
      this.loadDiagnostics();
    }
  },

  closeDiagnosticsModal() {
    const modal = document.getElementById('modal-diagnostics');
    if (modal) modal.classList.remove('open');
  },

  switchDiagTab(tab) {
    const btnAnalysis = document.getElementById('diag-tab-analysis-btn');
    const btnShare = document.getElementById('diag-tab-share-btn');
    const paneAnalysis = document.getElementById('diag-pane-analysis');
    const paneShare = document.getElementById('diag-pane-share');

    if (tab === 'analysis') {
      if (btnAnalysis) btnAnalysis.classList.add('active');
      if (btnShare) btnShare.classList.remove('active');
      if (paneAnalysis) paneAnalysis.style.display = 'block';
      if (paneShare) paneShare.style.display = 'none';
    } else {
      if (btnAnalysis) btnAnalysis.classList.remove('active');
      if (btnShare) btnShare.classList.add('active');
      if (paneAnalysis) paneAnalysis.style.display = 'none';
      if (paneShare) paneShare.style.display = 'block';
    }
  },

  async loadDiagnostics() {
    const loading = document.getElementById('diag-loading');
    const results = document.getElementById('diag-results');
    const alertBox = document.getElementById('diag-alert-box');
    const title = document.getElementById('diag-title');
    const cause = document.getElementById('diag-cause');
    const reco = document.getElementById('diag-recommendation');
    const excerptContainer = document.getElementById('diag-excerpt-container');
    const excerpt = document.getElementById('diag-excerpt');
    const source = document.getElementById('diag-source');

    if (loading) loading.style.display = 'block';
    if (results) results.style.display = 'none';

    try {
      const res = await fetch('/api/diagnostics/analyze');
      const data = await res.json();

      if (loading) loading.style.display = 'none';
      if (results) results.style.display = 'block';

      if (data.has_issue) {
        if (alertBox) {
          alertBox.style.borderLeftColor = data.severity === 'critical' ? '#f85149' : '#d29922';
          alertBox.style.background = data.severity === 'critical' ? 'rgba(248, 81, 73, 0.1)' : 'rgba(210, 153, 34, 0.1)';
        }
        if (title) {
          title.textContent = data.title;
          title.style.color = data.severity === 'critical' ? '#f85149' : '#e3b341';
        }
        if (cause) cause.textContent = data.cause;
        if (reco) reco.textContent = data.recommendation;

        if (data.excerpt && data.excerpt.trim()) {
          if (excerptContainer) excerptContainer.style.display = 'block';
          if (excerpt) excerpt.textContent = data.excerpt;
          if (source) source.textContent = data.source || 'latest.log';
        } else {
          if (excerptContainer) excerptContainer.style.display = 'none';
        }
      } else {
        if (alertBox) {
          alertBox.style.borderLeftColor = '#3fb950';
          alertBox.style.background = 'rgba(46, 160, 67, 0.1)';
        }
        if (title) {
          title.textContent = data.title || 'Sin problemas detectados';
          title.style.color = '#3fb950';
        }
        if (cause) cause.textContent = data.message || 'El servidor opera con normalidad.';
        if (reco) reco.textContent = data.recommendation || 'Todo en orden.';
        if (excerptContainer) excerptContainer.style.display = 'none';
      }
    } catch (err) {
      if (loading) loading.style.display = 'none';
      if (results) results.style.display = 'block';
      if (title) title.textContent = "Error al ejecutar análisis";
      if (cause) cause.textContent = err.message || "No se pudo consultar el endpoint de diagnósticos.";
    }
  },

  async shareLogToMclogs() {
    const btn = document.getElementById('btn-do-share-log');
    const resultBox = document.getElementById('diag-share-result');
    const urlInput = document.getElementById('diag-share-url');
    const linkBtn = document.getElementById('diag-share-link');

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spin-icon" style="display:inline-block;">↻</span> Subiendo y anonimizando registro...';
    }

    try {
      const res = await fetch('/api/diagnostics/share', { method: 'POST' });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Error al subir log a mclo.gs");
      }

      if (resultBox) resultBox.style.display = 'block';
      if (urlInput) urlInput.value = data.url;
      if (linkBtn) linkBtn.href = data.url;

      App.showToast("Log subido a mclo.gs con éxito", 'success');
    } catch (err) {
      App.showToast(err.message || "Error al compartir log", 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Subir y Generar Enlace Seguro (mclo.gs)';
      }
    }
  },

  copyShareUrl() {
    const input = document.getElementById('diag-share-url');
    if (input && input.value) {
      navigator.clipboard.writeText(input.value).then(() => {
        App.showToast("Enlace de mclo.gs copiado al portapapeles", 'success');
      }).catch(() => {
        input.select();
        document.execCommand('copy');
        App.showToast("Enlace copiado", 'success');
      });
    }
  }
};

