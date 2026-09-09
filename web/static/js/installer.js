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
    this.init();
    await this.checkLockState();
    await this.loadJavaRuntimes();
    await this.selectType(this.selectedType);
  },

  init() {
    if (this._langListener) return;
    this._langListener = true;
    window.addEventListener('dockraft:language_changed', () => {
      if (typeof App === 'undefined' || App.activeTab !== 'installer') return;
      this.refreshLanguage();
    });
  },

  // Re-applies translations to currently visible installer sections (no toasts).
  refreshLanguage() {
    const installSelect = document.getElementById('installer-version-select');
    if (installSelect && installSelect.options.length <= 1) {
      installSelect.innerHTML = '<option value="">' + I18n.t('t_install_loading_versions') + '</option>';
    }
    const stableSel = document.getElementById('update-version-select-stable');
    if (stableSel && stableSel.options.length === 1 && !stableSel.value) {
      stableSel.options[0].textContent = I18n.t('t_install_update_loading_stable');
    }
    const betaSel = document.getElementById('update-version-select-beta');
    if (betaSel && betaSel.options.length === 1 && !betaSel.value) {
      betaSel.options[0].textContent = I18n.t('t_install_update_loading_beta');
    }

    if (!this.isLocked) {
      this.updateRecommendedJava();
    } else {
      // Installed server: re-render locked banner, update card and plugin notices.
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard && window.__INITIAL_STATS__) {
        this.loadUpdateInfo(window.__INITIAL_STATS__);
      }
    }
  },

  applyLockState(stats, cfg) {
    if (!stats) return;
    const banner = document.getElementById('installer-locked-banner');
    const info = document.getElementById('installer-current-server-info');
    const btn = document.getElementById('btn-install-server');
    const mainCard = document.getElementById('installer-main-card');
    const btnDelete = document.getElementById('btn-delete-server');
    const nameInput = document.getElementById('installer-server-name');
    if (nameInput && cfg && cfg.server_name) {
      nameInput.value = cfg.server_name;
    }

    if (stats.is_installed) {
      this.isLocked = true;
      this.allowForce = false;
      if (banner) banner.style.display = 'flex';
      if (mainCard) mainCard.style.display = 'none';
      if (btnDelete) btnDelete.style.display = 'none';
      if (info && cfg) {
        const typeName = (cfg.server_type || 'Minecraft').toUpperCase();
        const ver = cfg.server_version || '';
        info.innerHTML = `${I18n.t('t_install_banner_locked_installed_a')} <strong>${escapeHtml(typeName)} ${escapeHtml(ver)}</strong> (<code>${escapeHtml(cfg.server_file || 'server.jar')}</code>)${I18n.t('t_install_banner_locked_installed_b')}`;
      }
      if (btn) {
        btn.disabled = true;
        btn.textContent = I18n.t('t_install_btn_installed_locked');
        btn.className = "btn btn-outline";
      }
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard) updateCard.style.display = 'block';
      const isBedrock = (cfg && cfg.server_type || '').toLowerCase() === 'bedrock';
      const pluginsSub = document.getElementById('update-plugins-subsection');
      if (pluginsSub) {
        pluginsSub.style.display = isBedrock ? 'none' : 'block';
      }
    } else {
      this.isLocked = false;
      this.allowForce = true;
      if (banner) banner.style.display = 'none';
      if (mainCard) mainCard.style.display = 'block';
      if (btnDelete) btnDelete.style.display = 'none';
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard) updateCard.style.display = 'none';
      const sub = document.getElementById('update-plugins-subsection');
      if (sub) sub.style.display = 'none';
      if (btn) {
        btn.disabled = false;
        btn.textContent = I18n.t('t_install_btn_install');
        btn.className = "btn btn-primary";
      }
    }
  },

  async checkLockState() {
    // Apply immediate local hydrated state if available
    if (window.__INITIAL_STATS__ && window.__INITIAL_CONFIG__) {
      this.applyLockState(window.__INITIAL_STATS__, window.__INITIAL_CONFIG__);
    }

    try {
      const [sRes, cRes] = await Promise.all([
        fetch('/api/server/status'),
        fetch('/api/config')
      ]);
      const stats = await sRes.json();
      const cfg = await cRes.json();
      
      this.applyLockState(stats, cfg);

      if (stats.is_installed) {
        const isBedrock = (cfg.server_type || '').toLowerCase() === 'bedrock';
        if (!isBedrock) {
          this.loadConsolePluginUpdates();
        }
        await this.loadUpdateInfo(stats);
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
        title: I18n.t('t_install_btn_unlock'),
        message: I18n.t('t_install_unlock_confirm_msg'),
        confirmText: I18n.t('t_install_unlock_confirm_btn'),
        warning: true
      });
      if (ok) {
        this.isLocked = false;
        this.allowForce = true;
        if (mainCard) mainCard.style.display = 'block'; // Mostrar selector al desbloquear
        if (btnDelete) btnDelete.style.display = 'inline-flex'; // Mostrar botón eliminar al desbloquear
        if (badge) badge.style.display = 'inline-block';
        if (btnUnlock) btnUnlock.textContent = I18n.t('t_install_btn_lock');
        if (btnInstall) {
          btnInstall.disabled = false;
          btnInstall.textContent = I18n.t('t_install_btn_overwrite');
          btnInstall.className = "btn btn-danger";
        }
        App.showToast(I18n.t('t_install_unlock_toast'), 'warning');
      }
    } else {
      this.isLocked = true;
      this.allowForce = false;
      if (mainCard) mainCard.style.display = 'none'; // Ocultar nuevamente al bloquear
      if (btnDelete) btnDelete.style.display = 'none'; // Ocultar botón eliminar
      if (badge) badge.style.display = 'none';
      if (btnUnlock) btnUnlock.textContent = I18n.t('t_install_btn_unlock');
      if (btnInstall) {
        btnInstall.disabled = true;
        btnInstall.textContent = I18n.t('t_install_btn_installed_locked');
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

    select.innerHTML = '<option value="">' + I18n.t('t_install_loading_versions') + '</option>';
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
      select.innerHTML = '<option value="">' + I18n.t('t_install_err_loading_versions') + '</option>';
      App.showToast(I18n.fmt('t_install_err_load_versions_for', [type]), 'danger');
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
            select.innerHTML = '<option value="java">' + I18n.t('t_install_java_default') + '</option>';
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

    badge.textContent = I18n.fmt('t_install_recommended_java', [rec]);

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
      App.showToast(I18n.t('t_install_err_blocked'), 'danger');
      return;
    }

    if (this.isInstalling) return;
    this.isInstalling = true;

    if (!selectVer || !selectVer.value) {
      App.showToast(I18n.t('t_install_err_select_version'), 'danger');
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
    btn.textContent = I18n.t('t_install_btn_downloading');

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
        throw new Error(data.detail || I18n.t('t_install_err_install_failed'));
      }

      App.showToast(I18n.t('t_install_toast_download_bg'), 'success');

      // Poll progress
      this.pollingInterval = setInterval(async () => {
        try {
          const pRes = await fetch('/api/installer/progress');
          const pData = await pRes.json();
          if (progressBar) progressBar.style.width = `${pData.percent || 0}%`;
          const st = pData.status || 'Downloading';
          const stText = this.mapStatusText(st);
          if (progressText) progressText.textContent = `${stText} (${pData.percent || 0}%)`;

          if (pData.status === 'completed') {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            App.showToast(I18n.t('t_install_toast_installed_ok'), 'success');
            await this.checkLockState();
            setTimeout(() => {
              App.switchTab('console');
            }, 1200);
          } else if (pData.status && pData.status.startsWith('error')) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            btn.disabled = false;
            btn.textContent = I18n.t('t_install_btn_install');
            App.showToast(I18n.fmt('t_install_err_download', [pData.status]), 'danger');
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
      btn.textContent = I18n.t('t_install_btn_install');
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

      const chName = data.current_channel === 'stable' ? I18n.t('t_install_channel_stable') :
                     data.current_channel === 'pre' ? 'Pre-Release' :
                     data.current_channel === 'preview' ? 'Preview / Beta' : 'Snapshot';

      if (curBadge) {
        if (data.current_version === 'importado') {
          curBadge.innerHTML = I18n.fmt('t_install_current_imported_html', [escapeHtml((data.server_type || 'Paper').toUpperCase())]);
        } else {
          curBadge.innerHTML = I18n.fmt('t_install_current_version_html', [escapeHtml(data.current_version || I18n.t('t_install_unknown'))]);
          const chSpan = document.createElement('span');
          chSpan.style.cssText = 'font-size:0.75rem; opacity:0.85; margin-left:4px;';
          chSpan.textContent = `(${chName})`;
          curBadge.appendChild(chSpan);
        }
      }

      if (statusBadge) {
        statusBadge.style.cursor = 'pointer';
        if (data.current_version === 'importado') {
          statusBadge.textContent = I18n.fmt('t_install_status_update_available', [data.latest_stable || I18n.t('t_install_see_versions')]);
          statusBadge.style.background = 'rgba(56, 139, 253, 0.15)';
          statusBadge.style.borderColor = '#388bfd';
          statusBadge.style.color = '#58a6ff';
          statusBadge.title = I18n.t('t_install_click_select_version');
          statusBadge.onclick = () => {
            this.switchUpdateChannel('stable');
            if (selectStable && data.latest_stable) {
              selectStable.value = data.latest_stable;
              this.onVersionSelectChange('stable');
              App.showToast(I18n.fmt('t_install_toast_version_selected', [data.latest_stable]), 'info');
            }
          };
        } else if (data.update_available) {
          statusBadge.innerHTML = I18n.fmt('t_install_status_new_version_html', [escapeHtml(data.latest_stable)]);
          statusBadge.style.background = 'rgba(56, 139, 253, 0.15)';
          statusBadge.style.borderColor = '#388bfd';
          statusBadge.style.color = '#58a6ff';
          statusBadge.title = I18n.fmt('t_install_click_select_ver', [data.latest_stable]);
          statusBadge.onclick = () => {
            this.switchUpdateChannel('stable');
            if (selectStable && data.latest_stable) {
              selectStable.value = data.latest_stable;
              this.onVersionSelectChange('stable');
              App.showToast(I18n.fmt('t_install_toast_version_selected', [data.latest_stable]), 'info');
            }
          };
        } else {
          statusBadge.textContent = I18n.fmt('t_install_status_up_to_date', [data.latest_stable || data.current_version]);
          statusBadge.style.background = 'rgba(46, 160, 67, 0.15)';
          statusBadge.style.borderColor = '#2ea043';
          statusBadge.style.color = '#3fb950';
          statusBadge.title = I18n.t('t_install_status_latest_title');
          statusBadge.onclick = null;
        }
      }

      if (previewBadge) {
        if (data.preview_available && data.latest_preview) {
          previewBadge.style.display = 'inline-flex';
          previewBadge.style.alignItems = 'center';
          previewBadge.style.cursor = 'pointer';
          previewBadge.title = I18n.fmt('t_install_click_select_beta', [data.latest_preview]);
          previewBadge.innerHTML = I18n.fmt('t_install_beta_available_html', [escapeHtml(data.latest_preview)]);
          previewBadge.onclick = () => {
            this.switchUpdateChannel('beta');
            if (selectBeta) {
              selectBeta.value = data.latest_preview;
              this.onVersionSelectChange('beta');
              App.showToast(I18n.fmt('t_install_toast_beta_selected', [data.latest_preview]), 'warning');
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
          selectStable.innerHTML = `<option value="">${I18n.t('t_install_no_stable_versions')}</option>`;
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
          selectBeta.innerHTML = `<option value="">${I18n.t('t_install_no_beta_versions')}</option>`;
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
      App.showToast(I18n.t('t_install_err_update_version'), 'danger');
      return;
    }

    if (select) select.value = targetVer;

    const isBetaTarget = (this.currentUpdateChannel === 'beta');
    const betaNotice = isBetaTarget ? '\n\n⚠️ ' + I18n.t('t_install_beta_notice') : '';
    const confirmMessage = isRunning
      ? I18n.fmt('t_install_update_confirm_running', [targetVer]) + betaNotice
      : I18n.fmt('t_install_update_confirm_stopped', [targetVer]) + betaNotice;

    const ok = await App.confirm({
      title: I18n.t('t_install_btn_update'),
      message: confirmMessage,
      confirmText: I18n.t('t_install_btn_update'),
      type: isBetaTarget ? 'warning' : 'info'
    });
    if (!ok) return;

    this.isInstalling = true;
    const btn = document.getElementById('btn-apply-update');
    const updateIconSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> ' + I18n.t('t_install_btn_update');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spin-icon" style="display:inline-block;">↻</span> ' + I18n.t('t_install_downloading_ellipsis');
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
        throw new Error(data.detail || I18n.t('t_install_err_update_start'));
      }

      App.showToast(I18n.t('t_install_toast_update_started'), 'info');

      // Poll progress
      if (this.pollingInterval) clearInterval(this.pollingInterval);
      this.pollingInterval = setInterval(async () => {
        try {
          const pRes = await fetch('/api/installer/progress');
          const pData = await pRes.json();
          const pct = pData.percent || 0;
          if (pBar) pBar.style.width = `${pct}%`;
          if (pPct) pPct.textContent = `${pct}%`;
          const st = pData.status || 'Updating';
          const stText = this.mapStatusText(st);
          if (pText) pText.textContent = `${stText} (${pct}%)`;

          if (pData.status === 'completed') {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = updateIconSvg;
            }
            App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
            await this.checkLockState();
          } else if (pData.status && pData.status.startsWith('error')) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            if (btn) {
              btn.disabled = false;
              btn.innerHTML = updateIconSvg;
            }
            App.showToast(I18n.fmt('t_install_err_update_fail', [pData.status]), 'danger');
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

  // Maps server-provided download/install status codes to localized labels.
  mapStatusText(status) {
    if (!status) return '';
    const map = {
      downloading: I18n.t('t_install_status_downloading'),
      verifying: I18n.t('t_install_status_verifying'),
      extracting: I18n.t('t_install_status_extracting'),
      completed: I18n.t('t_install_status_completed'),
      updating: I18n.t('t_install_status_updating'),
      Downloading: I18n.t('t_install_status_downloading'),
      Verifying: I18n.t('t_install_status_verifying'),
      Extracting: I18n.t('t_install_status_extracting'),
      Updating: I18n.t('t_install_status_updating'),
      Completed: I18n.t('t_install_status_completed'),
      'Downloading...': I18n.t('t_install_status_downloading'),
      'Verifying...': I18n.t('t_install_status_verifying'),
      'Extracting...': I18n.t('t_install_status_extracting')
    };
    return map[status] || status;
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
      App.showToast(I18n.t('t_install_err_import_zip'), 'danger');
      return;
    }
    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith('.zip')) {
      App.showToast(I18n.t('t_install_err_import_ext'), 'danger');
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
    if (progText) progText.textContent = I18n.t('t_install_import_uploading');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('accept_eula', acceptEula ? 'true' : 'false');

    try {
      if (progBar) progBar.style.width = '70%';
      if (progText) progText.textContent = I18n.t('t_install_import_extracting');

      const res = await fetch('/api/server/import', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || I18n.t('t_install_err_import_failed'));
      }

      if (progBar) progBar.style.width = '100%';
      if (progText) progText.textContent = I18n.t('t_install_import_done');
      App.showToast(data.message || I18n.t('t_install_toast_imported_ok'), 'success');

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
        App.showToast(I18n.t('t_install_err_delete_running'), 'danger');
        return;
      }

      const ok = await App.confirm({
        title: I18n.t('t_install_delete_title'),
        message: I18n.t('t_install_delete_msg'),
        confirmText: I18n.t('t_install_btn_delete'),
        danger: true
      });
      if (!ok) return;

      App.showToast(I18n.t('t_install_toast_deleting'), 'info');
      const res = await fetch('/api/server/delete', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || I18n.t('t_install_err_delete_failed'));

      App.showToast(data.message || I18n.t('t_install_toast_deleted_ok'), 'success');
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
        container.innerHTML = `<div style="text-align: center; padding: 16px; color: var(--text-muted); font-size: 0.84rem;">${I18n.t('t_install_plugin_load_error')}</div>`;
      }
    }
  },

  renderConsolePluginUpdates(updates) {
    const container = document.getElementById('installer-plugins-list-container');
    const badge = document.getElementById('plugins-update-count-badge');
    const btnNotify = document.getElementById('btn-notify-console-updates');
    const btnClear = document.getElementById('btn-clear-console-updates');
    if (!container) return;

    const count = updates ? updates.length : 0;
    if (badge) {
      badge.textContent = count === 1
        ? I18n.fmt('t_install_plugin_count_one', [count])
        : I18n.fmt('t_install_plugin_count_many', [count]);
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

    if (btnClear) {
      btnClear.style.display = count > 0 ? 'inline-flex' : 'none';
    }

    if (!updates || updates.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 20px 16px; background: rgba(0, 0, 0, 0.25); border-radius: 8px; border: 1px dashed var(--border-color);">
          <div style="font-size: 0.88rem; font-weight: 500; color: #7ee787; margin-bottom: 4px;">
            ✅ ${I18n.t('t_install_plugin_empty_title')}
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted); max-width: 520px; margin: 0 auto;">
            ${I18n.t('t_install_plugin_empty_desc')}
          </div>
        </div>
      `;
      if (btnNotify) btnNotify.style.display = 'none';
      return;
    }

    let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';

    updates.forEach(u => {
      const pluginEsc = escapeHtml(u.plugin);
      const isNamedNew = !u.version || String(u.version).toLowerCase() === 'nueva' || String(u.version).toLowerCase() === 'new';
      const verText = isNamedNew ? I18n.t('t_install_plugin_new_version') : (String(u.version).startsWith('v') ? escapeHtml(u.version) : `v${escapeHtml(u.version)}`);
      const timeBadge = u.time_str ? `<span style="font-size: 0.72rem; color: var(--text-dim); margin-left: auto;">${escapeHtml(u.time_str)}</span>` : '';

      const rawUrl = String(u.url || '');
      const isSafeUrl = /^https?:\/\//i.test(rawUrl);
      const downloadBtn = isSafeUrl ? `
        <a href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="padding: 5px 12px; font-size: 0.78rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          ${I18n.t('t_install_plugin_download')} ↗
        </a>
      ` : `
        <span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-muted); font-size: 0.74rem;">${I18n.t('t_install_plugin_view_console')}</span>
      `;

      const dismissBtn = `
        <button type="button" class="btn btn-outline" data-dismiss-plugin="${escapeHtml(u.plugin)}" style="padding: 5px 8px; font-size: 0.74rem; color: var(--text-muted); border-color: rgba(255,255,255,0.12);" title="${I18n.t('t_install_plugin_dismiss_title')}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      `;

      html += `
        <div class="plugin-item-card has-update" style="padding: 10px 14px;">
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px;">
              <span style="font-weight: 600; font-size: 0.92rem; color: #f0f6fc;">${pluginEsc}</span>
              <span class="badge" style="background: rgba(210, 153, 34, 0.18); border: 1px solid #d29922; color: #e3b341; font-weight: 600; font-size: 0.76rem; display: inline-flex; align-items: center; gap: 4px;">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
                ${verText} ${I18n.t('t_install_plugin_available')}
              </span>
              ${timeBadge}
            </div>
            <div style="font-size: 0.8rem; color: #c9d1d9; font-family: monospace; background: rgba(0,0,0,0.3); padding: 5px 8px; border-radius: 4px; word-break: break-word; line-height: 1.4;">
              ${escapeHtml(u.message)}
            </div>
            ${u.url ? `<div style="font-size: 0.72rem; color: #58a6ff; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"><span style="color: var(--text-dim);">URL:</span> ${escapeHtml(u.url)}</div>` : ''}
          </div>
          <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0; margin-left: 8px;">
            ${downloadBtn}
            ${dismissBtn}
          </div>
        </div>
      `;
    });

    html += '</div>';
    container.innerHTML = html;

    container.querySelectorAll('[data-dismiss-plugin]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.dismissConsoleUpdate(btn.getAttribute('data-dismiss-plugin'));
      });
    });

    if (btnNotify) {
      btnNotify.style.display = 'inline-flex';
    }
  },

  async dismissConsoleUpdate(pluginName) {
    try {
      const res = await fetch(`/api/plugins/console-updates/${encodeURIComponent(pluginName)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        this.consolePluginUpdates = this.consolePluginUpdates.filter(
          u => u.plugin.toLowerCase() !== pluginName.toLowerCase()
        );
        this.renderConsolePluginUpdates(this.consolePluginUpdates);
        if (window.App && App.showToast) {
          App.showToast(I18n.fmt('t_install_toast_plugin_dismissed', [pluginName]), 'info');
        }
      }
    } catch (e) {
      console.error("Error dismissing console update:", e);
    }
  },

  async clearAllConsoleUpdates() {
    if (!confirm(I18n.t('t_install_plugin_clear_confirm'))) {
      return;
    }
    try {
      const res = await fetch('/api/plugins/console-updates', { method: 'DELETE' });
      if (res.ok) {
        this.consolePluginUpdates = [];
        this.renderConsolePluginUpdates(this.consolePluginUpdates);
        if (window.App && App.showToast) {
          App.showToast(I18n.t('t_install_toast_plugin_cleared'), 'success');
        }
      }
    } catch (e) {
      console.error("Error clearing console updates:", e);
    }
  },

  async scanConsolePluginUpdates() {
    const btn = document.getElementById('btn-scan-console-updates');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<svg class="spinner" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10"/></svg> ${I18n.t('t_install_plugin_scanning')}`;
    }

    try {
      const res = await fetch('/api/plugins/scan-console', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        this.consolePluginUpdates = data.updates || [];
        this.renderConsolePluginUpdates(this.consolePluginUpdates);
        if (data.count > 0) {
          App.showToast(I18n.fmt('t_install_toast_plugin_found', [data.count]), 'warning');
        } else {
          App.showToast(I18n.t('t_install_toast_plugin_none'), 'info');
        }
      } else {
        App.showToast(I18n.t('t_install_err_plugin_scan'), 'danger');
      }
    } catch (e) {
      App.showToast(I18n.t('t_install_err_plugin_scan_conn'), 'danger');
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
        App.showToast(I18n.fmt('t_install_toast_plugin_notified', [data.total_outdated || data.total_detected || 0]), 'success');
      } else {
        App.showToast(I18n.t('t_install_err_plugin_notify'), 'danger');
      }
    } catch (e) {
      App.showToast(I18n.t('t_install_err_plugin_notify_dispatch'), 'danger');
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
