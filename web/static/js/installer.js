// Dockraft Server Software & Version Installer Script
const Installer = {
  selectedType: 'paper',
  versionsCache: {},
  runtimes: [],
  pollingInterval: null,
  isInstalling: false,
  eventsSetup: false,
  isLocked: false,
  allowForce: false,

  async loadInstaller() {
    if (!this.eventsSetup) {
      this.setupEvents();
      this.eventsSetup = true;
    }
    await this.checkLockState();
    await this.loadJavaRuntimes();
    await this.selectType(this.selectedType);
  },

  async checkLockState() {
    try {
      const [sRes, cRes] = await Promise.all([
        fetch('/api/server/status'),
        fetch('/api/config')
      ]);
      const stats = await sRes.json();
      const cfg = await cRes.json();
      
      const banner = document.getElementById('installer-locked-banner');
      const info = document.getElementById('installer-current-server-info');
      const btn = document.getElementById('btn-install-server');
      const mainCard = document.getElementById('installer-main-card');
      const btnDelete = document.getElementById('btn-delete-server');
      const nameInput = document.getElementById('installer-server-name');
      if (nameInput && cfg.server_name) {
        nameInput.value = cfg.server_name;
      }

      if (stats.is_installed) {
        this.isLocked = true;
        this.allowForce = false;
        if (banner) banner.style.display = 'flex';
        if (mainCard) mainCard.style.display = 'none'; // Ocultar software selector si ya está instalado
        if (btnDelete) btnDelete.style.display = 'none'; // Oculto hasta que se desbloquee
        if (info) {
          const typeName = (cfg.server_type || 'Minecraft').toUpperCase();
          const ver = cfg.server_version || '';
          info.innerHTML = `Tienes instalado un servidor <strong>${typeName} ${ver}</strong> (<code>${cfg.server_file || 'server.jar'}</code>). La instalación de otro software está bloqueada para evitar sobrescribir mundos, plugins y configuraciones.`;
        }
        if (btn) {
          btn.disabled = true;
          btn.textContent = "Servidor ya Instalado (Bloqueado)";
          btn.className = "btn btn-outline";
        }
        const updateCard = document.getElementById('installer-update-card');
        if (updateCard) updateCard.style.display = 'block';
        const isBedrock = (cfg.server_type || '').toLowerCase() === 'bedrock';
        const pluginsSub = document.getElementById('update-plugins-subsection');
        if (pluginsSub) {
          pluginsSub.style.display = isBedrock ? 'none' : 'block';
          if (!isBedrock) {
            this.loadConsolePluginUpdates();
          }
        }
        await this.loadUpdateInfo(stats);
      } else {
        this.isLocked = false;
        this.allowForce = true;
        if (banner) banner.style.display = 'none';
        if (mainCard) mainCard.style.display = 'block'; // Mostrar si no hay servidor
        if (btnDelete) btnDelete.style.display = 'none';
        const updateCard = document.getElementById('installer-update-card');
        if (updateCard) updateCard.style.display = 'none';
        const sub = document.getElementById('update-plugins-subsection');
        if (sub) sub.style.display = 'none';
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Instalar y Configurar Servidor";
          btn.className = "btn btn-primary";
        }
      }
    } catch (e) {
      console.warn("Could not check server install state", e);
    }
  },

  async toggleUnlockReinstall() {
    const btnUnlock = document.getElementById('btn-unlock-reinstall');
    const badge = document.getElementById('reinstall-warning-badge');
    const btnInstall = document.getElementById('btn-install-server');
    const mainCard = document.getElementById('installer-main-card');
    const btnDelete = document.getElementById('btn-delete-server');

    if (this.isLocked) {
      const ok = await App.confirm({
        title: 'Desbloquear Reinstalación',
        message: '¿Deseas desbloquear la reinstalación y opciones avanzadas?\n\nADVERTENCIA: Se desbloqueará la selección de software y la opción de eliminar el servidor actual.',
        confirmText: 'Desbloquear',
        warning: true
      });
      if (ok) {
        this.isLocked = false;
        this.allowForce = true;
        if (mainCard) mainCard.style.display = 'block'; // Mostrar selector al desbloquear
        if (btnDelete) btnDelete.style.display = 'inline-flex'; // Mostrar botón eliminar al desbloquear
        if (badge) badge.style.display = 'inline-block';
        if (btnUnlock) btnUnlock.textContent = 'Bloquear / Ocultar opciones';
        if (btnInstall) {
          btnInstall.disabled = false;
          btnInstall.textContent = "Sobrescribir e Instalar";
          btnInstall.className = "btn btn-danger";
        }
        App.showToast("Opciones de reinstalación y eliminación desbloqueadas", 'warning');
      }
    } else {
      this.isLocked = true;
      this.allowForce = false;
      if (mainCard) mainCard.style.display = 'none'; // Ocultar nuevamente al bloquear
      if (btnDelete) btnDelete.style.display = 'none'; // Ocultar botón eliminar
      if (badge) badge.style.display = 'none';
      if (btnUnlock) btnUnlock.textContent = 'Desbloquear Reinstalación';
      if (btnInstall) {
        btnInstall.disabled = true;
        btnInstall.textContent = "Servidor ya Instalado (Bloqueado)";
        btnInstall.className = "btn btn-outline";
      }
    }
  },

  setupEvents() {
    const cards = document.querySelectorAll('.type-card');
    cards.forEach(card => {
      card.addEventListener('click', () => {
        const type = card.getAttribute('data-type');
        this.selectType(type);
      });
    });

    const versionSelect = document.getElementById('installer-version-select');
    if (versionSelect) {
      versionSelect.addEventListener('change', () => {
        this.updateRecommendedJava();
      });
    }

    const btnInstall = document.getElementById('btn-install-server');
    if (btnInstall) {
      btnInstall.addEventListener('click', () => this.startInstallation());
    }

    // Quick RAM buttons
    document.querySelectorAll('.ram-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const ram = chip.getAttribute('data-ram');
        const maxInput = document.getElementById('install-max-ram');
        if (maxInput) maxInput.value = ram;
      });
    });

    // Console plugin updates buttons
    const btnScan = document.getElementById('btn-scan-console-updates');
    if (btnScan) {
      btnScan.addEventListener('click', () => this.scanConsolePluginUpdates());
    }
    const btnNotify = document.getElementById('btn-notify-console-updates');
    if (btnNotify) {
      btnNotify.addEventListener('click', () => this.notifyConsolePluginUpdates());
    }
  },

  async selectType(type) {
    this.selectedType = type;
    document.querySelectorAll('.type-card').forEach(card => {
      card.classList.toggle('selected', card.getAttribute('data-type') === type);
    });

    const javaGroup = document.getElementById('java-runtime-group');
    const aikarGroup = document.getElementById('aikar-flags-group');

    if (type === 'bedrock') {
      if (javaGroup) javaGroup.style.display = 'none';
      if (aikarGroup) aikarGroup.style.display = 'none';
    } else {
      if (javaGroup) javaGroup.style.display = 'flex';
      if (aikarGroup) aikarGroup.style.display = 'flex';
    }

    await this.fetchVersions(type);
  },

  async fetchVersions(type) {
    const select = document.getElementById('installer-version-select');
    if (!select) return;

    select.innerHTML = '<option value="">Loading versions...</option>';
    select.disabled = true;

    try {
      const res = await fetch(`/api/installer/versions?type=${type}`);
      const data = await res.json();
      this.versionsCache[type] = data.versions || [];

      select.innerHTML = '';
      this.versionsCache[type].forEach(ver => {
        const opt = document.createElement('option');
        if (typeof ver === 'object' && ver !== null) {
          opt.value = ver.id || ver.mc_version;
          opt.textContent = ver.label || ver.id;
        } else {
          opt.value = ver;
          opt.textContent = ver;
        }
        select.appendChild(opt);
      });
      select.disabled = false;
      this.updateRecommendedJava();
    } catch (e) {
      select.innerHTML = '<option value="">Error loading versions</option>';
      App.showToast(`Failed to load versions for ${type}`, 'danger');
    }
  },

  async loadJavaRuntimes() {
    try {
      const res = await fetch('/api/java/runtimes');
      if (res.ok) {
        this.runtimes = await res.json();
        const select = document.getElementById('installer-java-select');
        if (select) {
          select.innerHTML = '';
          if (this.runtimes.length === 0) {
            select.innerHTML = '<option value="java">Default System Java (java)</option>';
          } else {
            this.runtimes.forEach(rt => {
              const opt = document.createElement('option');
              opt.value = rt.path;
              opt.textContent = `${rt.name} [${rt.path}]`;
              select.appendChild(opt);
            });
          }
        }
      }
    } catch (e) {
      console.warn("Could not fetch Java runtimes:", e);
    }
  },

  updateRecommendedJava() {
    if (this.selectedType === 'bedrock') return;
    const selectVer = document.getElementById('installer-version-select');
    const badge = document.getElementById('recommended-java-badge');
    if (!selectVer || !badge) return;

    const ver = selectVer.value;
    let rec = 25;
    if (ver.startsWith('26.') || ver.startsWith('25.') || ver.includes('1.25') || ver.includes('1.26')) {
      rec = 25;
    } else if (ver.includes('1.16') || ver.includes('1.12') || ver.includes('1.8')) {
      rec = 8;
    } else if (ver.includes('1.17') || ver.includes('1.18') || ver.includes('1.19') || ver.includes('1.20.4')) {
      rec = 17;
    } else if (ver.includes('1.21') || ver.includes('1.22') || ver.includes('1.23') || ver.includes('1.24')) {
      rec = 21;
    } else {
      rec = 25;
    }

    badge.textContent = `Recommended: Java ${rec}`;

    // Auto-select runtime if found
    const selectJava = document.getElementById('installer-java-select');
    if (selectJava && this.runtimes.length > 0) {
      const match = this.runtimes.find(r => r.version === rec);
      if (match) {
        selectJava.value = match.path;
      }
    }
  },

  async startInstallation() {
    const selectVer = document.getElementById('installer-version-select');
    const minRam = document.getElementById('install-min-ram')?.value.trim() || '1G';
    const maxRam = document.getElementById('install-max-ram')?.value.trim() || '2G';
    const aikar = document.getElementById('install-aikar-flags')?.checked ?? true;
    const serverName = document.getElementById('installer-server-name')?.value.trim() || 'Mi Servidor Dockraft';
    const cpuCores = parseInt(document.getElementById('install-cpu-cores')?.value || '2', 10);
    const diskLimit = parseFloat(document.getElementById('install-disk-limit')?.value || '10');

    if (this.isLocked) {
      App.showToast("La instalación está bloqueada para proteger tu servidor actual. Desbloquea la reinstalación si deseas continuar.", 'danger');
      return;
    }

    if (this.isInstalling) return;
    this.isInstalling = true;

    if (!selectVer || !selectVer.value) {
      App.showToast("Please select a valid version first", 'danger');
      this.isInstalling = false;
      return;
    }

    const payload = {
      server_type: this.selectedType,
      version: selectVer.value,
      server_name: serverName,
      min_ram: minRam,
      max_ram: maxRam,
      aikar_flags: aikar,
      cpu_cores: cpuCores,
      disk_limit_gb: diskLimit,
      force: this.allowForce || false
    };

    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }

    const btn = document.getElementById('btn-install-server');
    btn.disabled = true;
    btn.textContent = "Downloading & Preparing...";

    const progressBox = document.getElementById('install-progress-box');
    const progressBar = document.getElementById('install-progress-bar');
    const progressText = document.getElementById('install-progress-text');
    if (progressBox) progressBox.style.display = 'block';

    try {
      const res = await fetch('/api/installer/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Installation failed");
      }

      App.showToast("Download started in background", 'success');

      // Poll progress
      this.pollingInterval = setInterval(async () => {
        try {
          const pRes = await fetch('/api/installer/progress');
          const pData = await pRes.json();
          if (progressBar) progressBar.style.width = `${pData.percent || 0}%`;
          if (progressText) progressText.textContent = `${pData.status || 'Downloading'} (${pData.percent || 0}%)`;

          if (pData.status === 'completed') {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            App.showToast("Servidor instalado y configurado correctamente.", 'success');
            await this.checkLockState();
            setTimeout(() => {
              App.switchTab('console');
            }, 1200);
          } else if (pData.status && pData.status.startsWith('error')) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            btn.disabled = false;
            btn.textContent = "Install & Setup Server";
            App.showToast(`Download error: ${pData.status}`, 'danger');
          }
        } catch (err) {
          clearInterval(this.pollingInterval);
          this.pollingInterval = null;
          this.isInstalling = false;
          btn.disabled = false;
        }
      }, 800);

    } catch (e) {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
      this.isInstalling = false;
      App.showToast(e.message, 'danger');
      btn.disabled = false;
      btn.textContent = "Install & Setup Server";
      if (progressBox) progressBox.style.display = 'none';
    }
  },

  async loadUpdateInfo(stats) {
    const card = document.getElementById('installer-update-card');
    if (!card) return;

    try {
      const res = await fetch('/api/installer/update-info');
      if (!res.ok) return;
      const data = await res.json();

      if (!data.is_installed) {
        card.style.display = 'none';
        const sub = document.getElementById('update-plugins-subsection');
        if (sub) sub.style.display = 'none';
        return;
      }

      card.style.display = 'block';
      const isBedrock = (data.server_type || '').toLowerCase() === 'bedrock';
      const pluginsSub = document.getElementById('update-plugins-subsection');
      if (pluginsSub) {
        pluginsSub.style.display = isBedrock ? 'none' : 'block';
        if (!isBedrock) {
          this.loadConsolePluginUpdates();
        }
      }
      const typeBadge = document.getElementById('update-server-type-badge');
      const curBadge = document.getElementById('update-current-version-badge');
      const statusBadge = document.getElementById('update-status-badge');
      const previewBadge = document.getElementById('update-preview-badge');
      const selectStable = document.getElementById('update-version-select-stable');
      const selectBeta = document.getElementById('update-version-select-beta');
      const select = document.getElementById('update-version-select');
      const warningBadge = document.getElementById('update-warning-badge');

      if (typeBadge) typeBadge.textContent = (data.server_type || '').toUpperCase();

      const chName = data.current_channel === 'stable' ? 'Estable' :
                     data.current_channel === 'pre' ? 'Pre-Release' :
                     data.current_channel === 'preview' ? 'Preview / Beta' : 'Snapshot';

      if (curBadge) {
        if (data.current_version === 'importado') {
          curBadge.innerHTML = `Versión Actual: <strong>Importada (${(data.server_type || 'Paper').toUpperCase()})</strong>`;
        } else {
          curBadge.innerHTML = `Versión Actual: <strong>${data.current_version || 'Desconocida'}</strong> <span style="font-size:0.75rem; opacity:0.85; margin-left:4px;">(${chName})</span>`;
        }
      }

      if (statusBadge) {
        statusBadge.style.cursor = 'pointer';
        if (data.current_version === 'importado') {
          statusBadge.textContent = `Actualización disponible (${data.latest_stable || 'Ver versiones'})`;
          statusBadge.style.background = 'rgba(56, 139, 253, 0.15)';
          statusBadge.style.borderColor = '#388bfd';
          statusBadge.style.color = '#58a6ff';
          statusBadge.title = "Haz clic para seleccionar esta versión";
          statusBadge.onclick = () => {
            this.switchUpdateChannel('stable');
            if (selectStable && data.latest_stable) {
              selectStable.value = data.latest_stable;
              this.onVersionSelectChange('stable');
              App.showToast(`Versión seleccionada: ${data.latest_stable}`, 'info');
            }
          };
        } else if (data.update_available) {
          statusBadge.innerHTML = `Nueva versión disponible: <strong>${data.latest_stable}</strong> <span style="font-size:0.75rem; margin-left:4px; opacity:0.85;">(clic para elegir)</span>`;
          statusBadge.style.background = 'rgba(56, 139, 253, 0.15)';
          statusBadge.style.borderColor = '#388bfd';
          statusBadge.style.color = '#58a6ff';
          statusBadge.title = `Haz clic para seleccionar ${data.latest_stable}`;
          statusBadge.onclick = () => {
            this.switchUpdateChannel('stable');
            if (selectStable && data.latest_stable) {
              selectStable.value = data.latest_stable;
              this.onVersionSelectChange('stable');
              App.showToast(`Versión seleccionada: ${data.latest_stable}`, 'info');
            }
          };
        } else {
          statusBadge.textContent = `Servidor actualizado (Estable: ${data.latest_stable || data.current_version})`;
          statusBadge.style.background = 'rgba(46, 160, 67, 0.15)';
          statusBadge.style.borderColor = '#2ea043';
          statusBadge.style.color = '#3fb950';
          statusBadge.title = "Servidor en la última versión estable";
          statusBadge.onclick = null;
        }
      }

      if (previewBadge) {
        if (data.preview_available && data.latest_preview) {
          previewBadge.style.display = 'inline-flex';
          previewBadge.style.alignItems = 'center';
          previewBadge.style.cursor = 'pointer';
          previewBadge.title = `Haz clic para seleccionar la beta ${data.latest_preview}`;
          previewBadge.innerHTML = `Beta disponible: <strong>${data.latest_preview}</strong> <span style="font-size:0.75rem; margin-left:4px; opacity:0.85;">(clic para elegir)</span>`;
          previewBadge.onclick = () => {
            this.switchUpdateChannel('beta');
            if (selectBeta) {
              selectBeta.value = data.latest_preview;
              this.onVersionSelectChange('beta');
              App.showToast(`Versión beta seleccionada: ${data.latest_preview}`, 'warning');
            }
          };
        } else {
          previewBadge.style.display = 'none';
        }
      }

      const items = data.versions || [];
      const stables = items.filter(v => v.channel === 'stable');
      const previews = items.filter(v => v.channel !== 'stable');

      // Populate Stable Select
      if (selectStable) {
        selectStable.innerHTML = '';
        stables.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.id;
          opt.textContent = v.label || v.id;
          opt.setAttribute('data-channel', 'stable');
          selectStable.appendChild(opt);
        });
        if (stables.length === 0) {
          selectStable.innerHTML = `<option value="">No hay versiones estables disponibles</option>`;
        }
      }

      // Populate Beta Select
      if (selectBeta) {
        selectBeta.innerHTML = '';
        previews.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.id;
          opt.textContent = `🔥 ${v.label || v.id}`;
          opt.setAttribute('data-channel', v.channel || 'pre');
          selectBeta.appendChild(opt);
        });
        if (previews.length === 0) {
          selectBeta.innerHTML = `<option value="">No hay versiones beta disponibles</option>`;
        }
      }

      // Populate hidden compatibility select
      if (select) {
        select.innerHTML = '';
        items.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.id;
          opt.textContent = v.label || v.id;
          select.appendChild(opt);
        });
        if (items.length === 0) {
          select.innerHTML = `<option value="${data.current_version}">${data.current_version}</option>`;
        }
      }

      this.switchUpdateChannel(this.currentUpdateChannel || 'stable');

    } catch (err) {
      console.warn("Could not load update info:", err);
    }
  },

  currentUpdateChannel: 'stable',

  switchUpdateChannel(channel) {
    this.currentUpdateChannel = channel;
    const btnStable = document.getElementById('btn-channel-stable');
    const btnBeta = document.getElementById('btn-channel-beta');
    const groupStable = document.getElementById('update-group-stable');
    const groupBeta = document.getElementById('update-group-beta');
    const alertBeta = document.getElementById('beta-instability-alert');
    const selectStable = document.getElementById('update-version-select-stable');
    const selectBeta = document.getElementById('update-version-select-beta');
    const selectComp = document.getElementById('update-version-select');

    if (channel === 'stable') {
      if (btnStable) {
        btnStable.style.background = 'var(--accent-primary)';
        btnStable.style.color = '#fff';
        btnStable.classList.add('active');
      }
      if (btnBeta) {
        btnBeta.style.background = 'transparent';
        btnBeta.style.color = 'var(--text-muted)';
        btnBeta.style.border = 'none';
        btnBeta.classList.remove('active');
      }
      if (groupStable) groupStable.style.display = 'block';
      if (groupBeta) groupBeta.style.display = 'none';
      if (alertBeta) alertBeta.style.display = 'none';

      if (selectComp && selectStable) {
        selectComp.value = selectStable.value;
      }
    } else {
      if (btnBeta) {
        btnBeta.style.background = 'rgba(210, 153, 34, 0.25)';
        btnBeta.style.color = '#f2cc60';
        btnBeta.style.border = '1px solid #d29922';
        btnBeta.classList.add('active');
      }
      if (btnStable) {
        btnStable.style.background = 'transparent';
        btnStable.style.color = 'var(--text-muted)';
        btnStable.classList.remove('active');
      }
      if (groupStable) groupStable.style.display = 'none';
      if (groupBeta) groupBeta.style.display = 'block';
      if (alertBeta) alertBeta.style.display = 'block';

      if (selectComp && selectBeta) {
        selectComp.value = selectBeta.value;
      }
    }
  },

  onVersionSelectChange(channel) {
    const selectStable = document.getElementById('update-version-select-stable');
    const selectBeta = document.getElementById('update-version-select-beta');
    const selectComp = document.getElementById('update-version-select');
    if (channel === 'stable' && selectStable && selectComp) {
      selectComp.value = selectStable.value;
    } else if (channel === 'beta' && selectBeta && selectComp) {
      selectComp.value = selectBeta.value;
    }
  },

  async startUpdate() {
    if (this.isInstalling) return;

    let isRunning = false;
    try {
      const sRes = await fetch('/api/server/status');
      const stats = await sRes.json();
      isRunning = (stats.status && stats.status !== 'OFFLINE');
    } catch (e) {}

    let targetVer = null;
    const selectStable = document.getElementById('update-version-select-stable');
    const selectBeta = document.getElementById('update-version-select-beta');
    const select = document.getElementById('update-version-select');

    if (this.currentUpdateChannel === 'beta' && selectBeta && selectBeta.value) {
      targetVer = selectBeta.value;
    } else if (selectStable && selectStable.value) {
      targetVer = selectStable.value;
    } else if (select && select.value) {
      targetVer = select.value;
    }

    if (!targetVer) {
      App.showToast("Por favor selecciona una versión válida para actualizar.", 'danger');
      return;
    }

    if (select) select.value = targetVer;

    const isBetaTarget = (this.currentUpdateChannel === 'beta');
    const betaNotice = isBetaTarget ? '\n\n⚠️ NOTA: Estás instalando una versión Beta/Snapshot experimental.' : '';
    const confirmMessage = isRunning
      ? `¿Deseas actualizar tu servidor a la versión "${targetVer}"?${betaNotice}\n\n• El servidor se detendrá de forma segura (guardando mundos con save-all).\n• Se creará un respaldo de seguridad automático (pre-update-${targetVer}).\n• Se verificará la integridad del archivo para evitar corrupciones.\n• El servidor se reiniciará automáticamente al finalizar la actualización.`
      : `¿Deseas actualizar tu servidor a la versión "${targetVer}"?${betaNotice}\n\n• Se creará un respaldo de seguridad automático (pre-update-${targetVer}).\n• Se verificará la integridad del paquete descargado contra corrupciones.\n• Tus mundos, plugins y configuraciones se mantendrán intactos.`;

    const ok = await App.confirm({
      title: 'Actualizar Servidor',
      message: confirmMessage,
      confirmText: 'Actualizar Servidor',
      type: isBetaTarget ? 'warning' : 'info'
    });
    if (!ok) return;

    this.isInstalling = true;
    const btn = document.getElementById('btn-apply-update');
    const updateIconSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Actualizar Servidor';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spin-icon" style="display:inline-block;">↻</span> Descargando...';
    }

    const pBox = document.getElementById('update-progress-box');
    const pBar = document.getElementById('update-progress-bar');
    const pText = document.getElementById('update-progress-text');
    const pPct = document.getElementById('update-progress-percent');
    if (pBox) pBox.style.display = 'block';

    try {
      const res = await fetch('/api/installer/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version: targetVer })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Error al iniciar actualización");
      }

      App.showToast("Descarga de actualización iniciada...", 'info');

      // Poll progress
      if (this.pollingInterval) clearInterval(this.pollingInterval);
      this.pollingInterval = setInterval(async () => {
        try {
          const pRes = await fetch('/api/installer/progress');
          const pData = await pRes.json();
          const pct = pData.percent || 0;
          if (pBar) pBar.style.width = `${pct}%`;
          if (pPct) pPct.textContent = `${pct}%`;
          if (pText) pText.textContent = `${pData.status || 'Actualizando'} (${pct}%)`;

          if (pData.status === 'completed') {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = updateIconSvg;
            }
            App.showToast("¡Servidor actualizado correctamente!", 'success');
            await this.checkLockState();
          } else if (pData.status && pData.status.startsWith('error')) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = updateIconSvg;
            }
            App.showToast(`Error al actualizar: ${pData.status}`, 'danger');
          }
        } catch (err) {
          clearInterval(this.pollingInterval);
          this.pollingInterval = null;
          this.isInstalling = false;
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = updateIconSvg;
          }
        }
      }, 800);

    } catch (e) {
      this.isInstalling = false;
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = updateIconSvg;
      }
      if (pBox) pBox.style.display = 'none';
      App.showToast(e.message, 'danger');
    }
  },

  openImportModal() {
    const modal = document.getElementById('import-server-modal');
    if (modal) {
      modal.classList.add('open');
      const prog = document.getElementById('import-progress-box');
      if (prog) prog.style.display = 'none';
      const fileInput = document.getElementById('import-server-file');
      if (fileInput) fileInput.value = '';
    }
  },

  closeImportModal() {
    const modal = document.getElementById('import-server-modal');
    if (modal) modal.classList.remove('open');
  },

  async uploadServerZip() {
    const fileInput = document.getElementById('import-server-file');
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      App.showToast("Por favor selecciona un archivo .zip para importar", 'danger');
      return;
    }
    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.zip')) {
      App.showToast("El archivo debe tener extensión .zip", 'danger');
      return;
    }

    const btn = document.getElementById('btn-start-import');
    const progBox = document.getElementById('import-progress-box');
    const progBar = document.getElementById('import-progress-bar');
    const progText = document.getElementById('import-progress-text');
    const acceptEula = document.getElementById('import-accept-eula')?.checked ?? true;

    if (btn) btn.disabled = true;
    if (progBox) progBox.style.display = 'block';
    if (progBar) progBar.style.width = '30%';
    if (progText) progText.textContent = "Subiendo archivo del servidor...";

    const formData = new FormData();
    formData.append('file', file);
    formData.append('accept_eula', acceptEula ? 'true' : 'false');

    try {
      if (progBar) progBar.style.width = '70%';
      if (progText) progText.textContent = "Extrayendo y configurando servidor...";

      const res = await fetch('/api/server/import', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Error al importar el servidor");
      }

      if (progBar) progBar.style.width = '100%';
      if (progText) progText.textContent = "¡Importación completada!";
      App.showToast(data.message || "Servidor importado correctamente", 'success');

      setTimeout(() => {
        this.closeImportModal();
        this.checkLockState();
        App.switchTab('console');
      }, 1000);
    } catch (err) {
      App.showToast(err.message, 'danger');
      if (progBox) progBox.style.display = 'none';
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  async deleteServer() {
    try {
      const sRes = await fetch('/api/server/status');
      const stats = await sRes.json();
      if (stats.status !== 'OFFLINE') {
        App.showToast("Debes detener el servidor antes de poder eliminarlo", 'danger');
        return;
      }

      const ok = await App.confirm({
        title: 'Eliminar Servidor Definitivamente',
        message: 'ATENCIÓN: ¿Estás completamente seguro de que deseas ELIMINAR el servidor actual?\n\nEsta acción borrará permanentemente los ejecutables, mundos, plugins, mods y archivos de configuración actuales.\n\n(Las copias de seguridad en la pestaña "Copias de Seguridad" permanecerán intactas y a salvo).\n\n¿Confirmas la eliminación definitiva?',
        confirmText: 'Eliminar Servidor',
        danger: true
      });
      if (!ok) return;

      App.showToast("Eliminando servidor y limpiando archivos...", 'info');
      const res = await fetch('/api/server/delete', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Error al eliminar el servidor");

      App.showToast(data.message || "Servidor eliminado con éxito", 'success');
      await this.checkLockState();
      App.switchTab('installer');
    } catch (err) {
      App.showToast(err.message, 'danger');
    }
  },

  consolePluginUpdates: [],

  async loadConsolePluginUpdates() {
    const subsection = document.getElementById('update-plugins-subsection');
    if (!subsection) return;

    try {
      const res = await fetch('/api/plugins/console-updates');
      if (res.ok) {
        const data = await res.json();
        this.consolePluginUpdates = data.updates || [];
        this.renderConsolePluginUpdates(this.consolePluginUpdates);
      }
    } catch (e) {
      console.warn("Could not load console plugin updates:", e);
      const container = document.getElementById('installer-plugins-list-container');
      if (container) {
        container.innerHTML = `<div style="text-align: center; padding: 16px; color: var(--text-muted); font-size: 0.84rem;">No se pudieron cargar los avisos de actualización.</div>`;
      }
    }
  },

  renderConsolePluginUpdates(updates) {
    const container = document.getElementById('installer-plugins-list-container');
    const badge = document.getElementById('plugins-update-count-badge');
    const btnNotify = document.getElementById('btn-notify-console-updates');
    if (!container) return;

    const count = updates ? updates.length : 0;
    if (badge) {
      badge.textContent = `${count} ${count === 1 ? 'detectada' : 'detectadas'}`;
      if (count > 0) {
        badge.style.background = 'rgba(210, 153, 34, 0.18)';
        badge.style.borderColor = '#d29922';
        badge.style.color = '#e3b341';
      } else {
        badge.style.background = 'rgba(46, 160, 67, 0.15)';
        badge.style.borderColor = '#2ea043';
        badge.style.color = '#3fb950';
      }
    }

    if (!updates || updates.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 20px 16px; background: rgba(0, 0, 0, 0.25); border-radius: 8px; border: 1px dashed var(--border-color);">
          <div style="font-size: 0.88rem; font-weight: 500; color: #7ee787; margin-bottom: 4px;">
            ✅ Ningún plugin ha reportado actualizaciones pendientes en la consola
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted); max-width: 520px; margin: 0 auto;">
            Cuando un plugin instalado detecte una nueva versión oficial (en GitHub, Hangar, Spigot o su web oficial), el aviso y su enlace de descarga aparecerán automáticamente aquí.
          </div>
        </div>
      `;
      if (btnNotify) btnNotify.style.display = 'none';
      return;
    }

    let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';

    updates.forEach(u => {
      const verText = u.version ? `v${u.version}` : 'Nueva versión';
      const timeBadge = u.time_str ? `<span style="font-size: 0.72rem; color: var(--text-dim); margin-left: auto;">${u.time_str}</span>` : '';

      const downloadBtn = u.url ? `
        <a href="${u.url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="padding: 5px 12px; font-size: 0.78rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          Descargar ↗
        </a>
      ` : `
        <span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-muted); font-size: 0.74rem;">Ver en consola</span>
      `;

      html += `
        <div class="plugin-item-card has-update" style="padding: 10px 14px;">
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px;">
              <span style="font-weight: 600; font-size: 0.92rem; color: #f0f6fc;">${u.plugin}</span>
              <span class="badge" style="background: rgba(210, 153, 34, 0.18); border: 1px solid #d29922; color: #e3b341; font-weight: 600; font-size: 0.76rem; display: inline-flex; align-items: center; gap: 4px;">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
                ${verText} disponible
              </span>
              ${timeBadge}
            </div>
            <div style="font-size: 0.8rem; color: #c9d1d9; font-family: monospace; background: rgba(0,0,0,0.3); padding: 5px 8px; border-radius: 4px; word-break: break-word; line-height: 1.4;">
              ${u.message}
            </div>
            ${u.url ? `<div style="font-size: 0.72rem; color: #58a6ff; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"><span style="color: var(--text-dim);">URL:</span> ${u.url}</div>` : ''}
          </div>
          <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0; margin-left: 8px;">
            ${downloadBtn}
          </div>
        </div>
      `;
    });

    html += '</div>';
    container.innerHTML = html;

    if (btnNotify) {
      btnNotify.style.display = 'inline-flex';
    }
  },

  async scanConsolePluginUpdates() {
    const btn = document.getElementById('btn-scan-console-updates');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<svg class="spinner" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10"/></svg> Escaneando...`;
    }

    try {
      const res = await fetch('/api/plugins/scan-console', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        this.consolePluginUpdates = data.updates || [];
        this.renderConsolePluginUpdates(this.consolePluginUpdates);
        if (data.count > 0) {
          App.showToast(`Se detectaron ${data.count} avisos de actualización de plugins en la consola`, 'warning');
        } else {
          App.showToast("No se encontraron avisos de actualización en el log de la consola.", 'info');
        }
      } else {
        App.showToast("Error al escanear los logs de la consola.", 'danger');
      }
    } catch (e) {
      App.showToast("Error de conexión al escanear logs.", 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }
  },

  async notifyConsolePluginUpdates() {
    const btn = document.getElementById('btn-notify-console-updates');
    if (btn) btn.disabled = true;

    try {
      const res = await fetch('/api/plugins/notify-updates', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        App.showToast(`Alerta despachada a Webhooks para ${data.total_outdated || data.total_detected || 0} plugins`, 'success');
      } else {
        App.showToast("Error al notificar por Webhook.", 'danger');
      }
    } catch (e) {
      App.showToast("Error al despachar alerta de plugins.", 'danger');
    } finally {
      if (btn) btn.disabled = false;
    }
  },

  // Compatibility helpers
  async loadInstalledPlugins(stats) {
    return this.loadConsolePluginUpdates();
  },
  async checkPluginUpdates() {
    return this.scanConsolePluginUpdates();
  },
  async notifyPluginUpdates() {
    return this.notifyConsolePluginUpdates();
  }
};

window.Installer = Installer;
