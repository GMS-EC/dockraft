// Dockraft Ultra-Lightweight Canvas Metrics Controller
const Metrics = {
  history: [],
  summary: null,
  pollTimer: null,
  isLive: true,
  hoverPoint: null,
  canvas: null,
  ctx: null,

  init() {
    this.canvas = document.getElementById('metrics-chart-canvas');
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');

    // Setup mouse hover for interactive tooltips
    this.canvas.addEventListener('mousemove', (e) => this.handleMouseMove(e));
    this.canvas.addEventListener('mouseleave', () => this.handleMouseLeave());

    // Window / container resize observer for crisp DPI rendering
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => this.redraw());
      ro.observe(this.canvas.parentElement);
    } else {
      window.addEventListener('resize', () => this.redraw());
    }
  },

  async loadMetrics() {
    if (!this.canvas) this.init();
    await this.fetchData();
    this.startLivePolling();
  },

  startLivePolling() {
    this.stopLivePolling();
    if (!this.isLive) return;
    this.pollTimer = setInterval(() => {
      if (typeof App !== 'undefined' && App.activeTab === 'metrics') {
        this.fetchData();
      }
    }, 10000);
  },

  stopLivePolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  },

  toggleLivePolling() {
    this.isLive = !this.isLive;
    const dot = document.getElementById('metrics-live-dot');
    const label = document.getElementById('metrics-live-label');
    if (this.isLive) {
      if (dot) dot.style.backgroundColor = '#34d399';
      if (dot) dot.style.boxShadow = '0 0 6px #34d399';
      if (label) label.textContent = 'En Vivo (10s)';
      this.startLivePolling();
      this.fetchData();
    } else {
      if (dot) dot.style.backgroundColor = '#8b949e';
      if (dot) dot.style.boxShadow = 'none';
      if (label) label.textContent = 'Pausado';
      this.stopLivePolling();
    }
  },

  async fetchData() {
    try {
      const res = await fetch('/api/metrics/history');
      if (!res.ok) return;
      const data = await res.json();
      this.history = data.history || [];
      this.summary = data.summary || null;
      this.updateKPIs();
      this.redraw();
    } catch (e) {
      console.debug("Metrics fetch error:", e);
    }
  },

  async resetMetrics() {
    const ok = await App.confirm({
      title: 'Vaciar Historial de Métricas',
      message: '¿Deseas vaciar el historial de métricas y reiniciar los contadores de picos?',
      confirmText: 'Vaciar Historial',
      danger: true
    });
    if (!ok) return;
    try {
      const res = await fetch('/api/metrics/reset', { method: 'POST' });
      if (res.ok) {
        this.history = [];
        await this.fetchData();
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast("Historial de métricas reiniciado correctamente", "success");
        }
      }
    } catch (e) {
      console.warn("Reset error:", e);
    }
  },

  updateKPIs() {
    if (!this.summary) return;
    const s = this.summary;

    const cpuVal = document.getElementById('metric-kpi-cpu-val');
    const cpuPeak = document.getElementById('metric-kpi-cpu-peak');
    const cpuAvg = document.getElementById('metric-kpi-cpu-avg');
    if (cpuVal) cpuVal.textContent = `${s.current_cpu || 0.0}%`;
    if (cpuPeak) cpuPeak.textContent = `${s.peak_cpu || 0.0}%`;
    if (cpuAvg) cpuAvg.textContent = `${s.avg_cpu || 0.0}%`;

    const ramVal = document.getElementById('metric-kpi-ram-val');
    const ramPct = document.getElementById('metric-kpi-ram-pct');
    const ramPeak = document.getElementById('metric-kpi-ram-peak');
    const ramAssigned = document.getElementById('metric-kpi-ram-assigned');
    if (ramVal) ramVal.textContent = `${Math.round(s.current_ram_mb || 0)} MB`;
    if (ramPct) ramPct.textContent = `(${s.current_ram_percent || 0}%)`;
    if (ramPeak) ramPeak.textContent = `${Math.round(s.peak_ram_mb || 0)} MB`;
    if (ramAssigned) ramAssigned.textContent = `${Math.round(s.assigned_ram_mb || 2048)} MB`;

    const plVal = document.getElementById('metric-kpi-players-val');
    const plPeak = document.getElementById('metric-kpi-players-peak');
    if (plVal) plVal.textContent = s.current_players || 0;
    if (plPeak) plPeak.textContent = `${s.peak_players || 0} jugadores`;

    const upVal = document.getElementById('metric-kpi-uptime-val');
    const stBadge = document.getElementById('metric-kpi-status-badge');
    const isOnline = s.current_status === 'RUNNING' || s.current_status === 'ONLINE' || s.current_status === 'STARTING';
    if (upVal) {
      if (!isOnline) {
        upVal.textContent = '--';
        upVal.removeAttribute('title');
      } else if (s.uptime_clock && s.uptime_clock !== '--') {
        upVal.textContent = s.uptime_clock;
        if (s.uptime_formatted) upVal.title = s.uptime_formatted;
      } else if (s.uptime_seconds !== undefined && s.uptime_seconds !== null && Number(s.uptime_seconds) > 0) {
        const secs = Number(s.uptime_seconds);
        const d = Math.floor(secs / 86400);
        const h = Math.floor((secs % 86400) / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const sc = secs % 60;
        const pad = (n) => String(n).padStart(2, '0');
        upVal.textContent = d > 0 ? `${d}d ${pad(h)}:${pad(m)}:${pad(sc)}` : `${pad(h)}:${pad(m)}:${pad(sc)}`;
        if (s.uptime_formatted) upVal.title = s.uptime_formatted;
      } else {
        upVal.textContent = s.uptime_str || '--';
      }
    }
    if (stBadge) {
      stBadge.textContent = s.current_status || 'OFFLINE';
      stBadge.style.background = isOnline ? 'rgba(46, 160, 67, 0.15)' : 'rgba(218, 54, 51, 0.15)';
      stBadge.style.color = isOnline ? '#3fb950' : '#f85149';
    }

    const countEl = document.getElementById('metrics-sample-count');
    if (countEl) countEl.textContent = `${this.history.length} muestras`;

    const overlay = document.getElementById('metrics-empty-overlay');
    if (overlay) {
      overlay.style.display = (this.history.length === 0) ? 'flex' : 'none';
    }
  },

  redraw() {
    if (!this.canvas || !this.ctx) return;
    const parent = this.canvas.parentElement;
    if (!parent) return;

    const dpr = window.devicePixelRatio || 1;
    const w = parent.clientWidth;
    const h = parent.clientHeight;
    if (w === 0 || h === 0) return;

    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.ctx.resetTransform ? this.ctx.resetTransform() : this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(dpr, dpr);

    const ctx = this.ctx;
    ctx.clearRect(0, 0, w, h);

    const padding = { top: 20, right: 24, bottom: 30, left: 45 };
    const chartW = w - padding.left - padding.right;
    const chartH = h - padding.top - padding.bottom;

    if (chartW <= 0 || chartH <= 0) return;

    // Draw Grid & Y Axis (0% to 100%)
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(48, 54, 61, 0.45)';
    ctx.fillStyle = '#8b949e';
    ctx.font = '10px Inter, -apple-system, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
      const val = Math.round((100 / ySteps) * i);
      const y = padding.top + chartH - (chartH * (i / ySteps));

      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();

      ctx.fillText(`${val}%`, padding.left - 8, y);
    }

    if (this.history.length < 2) return;

    // Calculate step width along X
    const dataLen = this.history.length;
    const stepX = chartW / (dataLen - 1);

    // Draw X Axis Timestamps (e.g. 5 ticks)
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const xTicks = Math.min(5, dataLen);
    for (let i = 0; i < xTicks; i++) {
      const idx = Math.floor((dataLen - 1) * (i / (xTicks - 1)));
      const sample = this.history[idx];
      if (!sample) continue;
      const x = padding.left + (idx * stepX);
      ctx.fillText(sample.time_str || '', x, padding.top + chartH + 8);
    }

    // Series visibility
    const showCpu = document.getElementById('metric-series-cpu')?.checked !== false;
    const showRamPct = document.getElementById('metric-series-ram-pct')?.checked !== false;
    const showRamMb = document.getElementById('metric-series-ram-mb')?.checked === true;
    const showPlayers = document.getElementById('metric-series-players')?.checked !== false;

    // Draw Series: RAM % (Cyan)
    if (showRamPct) {
      this.drawSeries(ctx, this.history, s => s.memory_percent || 0, 100, '#38bdf8', 'rgba(56, 189, 248, 0.12)', padding, chartH, stepX);
    }

    // Draw Series: RAM MB (Scaled relative to assigned RAM)
    if (showRamMb) {
      const assigned = this.summary?.assigned_ram_mb || 2048;
      this.drawSeries(ctx, this.history, s => ((s.memory_mb || 0) / assigned) * 100, 100, '#60a5fa', 'rgba(96, 165, 250, 0.08)', padding, chartH, stepX);
    }

    // Draw Series: CPU % (Amber)
    if (showCpu) {
      this.drawSeries(ctx, this.history, s => s.cpu_percent || 0, 100, '#f59e0b', 'rgba(245, 158, 11, 0.15)', padding, chartH, stepX);
    }

    // Draw Series: Players (Purple, scaled e.g. 0 to 20 or peak)
    if (showPlayers) {
      const maxPl = Math.max(10, (this.summary?.peak_players || 0) + 2);
      this.drawSeries(ctx, this.history, s => ((s.players_online || 0) / maxPl) * 100, 100, '#a855f7', 'rgba(168, 85, 247, 0.15)', padding, chartH, stepX);
    }

    // Draw hover cursor guide line
    if (this.hoverPoint && this.hoverPoint.index >= 0 && this.hoverPoint.index < dataLen) {
      const hx = padding.left + (this.hoverPoint.index * stepX);
      ctx.beginPath();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = '#58a6ff';
      ctx.lineWidth = 1.5;
      ctx.moveTo(hx, padding.top);
      ctx.lineTo(hx, padding.top + chartH);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  },

  drawSeries(ctx, data, valExtractor, maxVal, strokeColor, fillColor, padding, chartH, stepX) {
    if (data.length === 0) return;

    ctx.beginPath();
    const points = [];
    for (let i = 0; i < data.length; i++) {
      const rawVal = valExtractor(data[i]);
      const normVal = Math.max(0, Math.min(100, (rawVal / maxVal) * 100));
      const x = padding.left + (i * stepX);
      const y = padding.top + chartH - (chartH * (normVal / 100));
      points.push({ x, y });
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }

    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Area fill
    if (fillColor && points.length > 1) {
      ctx.beginPath();
      ctx.moveTo(points[0].x, padding.top + chartH);
      for (let pt of points) ctx.lineTo(pt.x, pt.y);
      ctx.lineTo(points[points.length - 1].x, padding.top + chartH);
      ctx.closePath();
      ctx.fillStyle = fillColor;
      ctx.fill();
    }
  },

  handleMouseMove(e) {
    if (this.history.length === 0 || !this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const padding = { top: 20, right: 24, bottom: 30, left: 45 };
    const chartW = rect.width - padding.left - padding.right;

    if (x < padding.left || x > rect.width - padding.right) {
      this.handleMouseLeave();
      return;
    }

    const relX = x - padding.left;
    const idx = Math.round((relX / chartW) * (this.history.length - 1));
    const safeIdx = Math.max(0, Math.min(this.history.length - 1, idx));

    this.hoverPoint = { index: safeIdx, x, y };
    this.redraw();
    this.showTooltip(this.history[safeIdx], x, y, rect);
  },

  showTooltip(sample, x, y, rect) {
    const tooltip = document.getElementById('metrics-tooltip');
    const tTime = document.getElementById('metrics-tooltip-time');
    const tBody = document.getElementById('metrics-tooltip-body');
    if (!tooltip || !tTime || !tBody || !sample) return;

    tTime.textContent = sample.time_str || '--:--:--';
    tBody.innerHTML = `
      <div style="display: flex; justify-content: space-between; gap: 14px; color: #cbd5e1;">
        <span style="color: #f59e0b; font-weight: 600;">CPU:</span>
        <span style="font-family: var(--font-mono);">${sample.cpu_percent || 0.0}%</span>
      </div>
      <div style="display: flex; justify-content: space-between; gap: 14px; color: #cbd5e1;">
        <span style="color: #38bdf8; font-weight: 600;">RAM:</span>
        <span style="font-family: var(--font-mono);">${Math.round(sample.memory_mb || 0)} MB (${sample.memory_percent || 0}%)</span>
      </div>
      <div style="display: flex; justify-content: space-between; gap: 14px; color: #cbd5e1;">
        <span style="color: #a855f7; font-weight: 600;">Jugadores:</span>
        <span style="font-family: var(--font-mono);">${sample.players_online || 0}</span>
      </div>
    `;

    tooltip.style.display = 'block';

    // Prevent tooltip overflow
    const tooltipW = 160;
    let posX = x + 15;
    if (posX + tooltipW > rect.width) {
      posX = x - tooltipW - 15;
    }
    tooltip.style.left = `${posX}px`;
    tooltip.style.top = `${Math.max(10, y - 40)}px`;
  },

  handleMouseLeave() {
    this.hoverPoint = null;
    const tooltip = document.getElementById('metrics-tooltip');
    if (tooltip) tooltip.style.display = 'none';
    this.redraw();
  }
};
