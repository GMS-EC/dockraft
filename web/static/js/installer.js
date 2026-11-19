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
  modpackType: 'modpack',
  modpackResults: [],
  selectedModpack: null,
  selectedModpackVersions: [],
  selectedModpackRequirements: null,
  pendingMrpackFile: null,
  selectedModStack: [],
  resolvedModStack: null,
  modpackUpdateData: null,
  installedModsData: null,

  _setInstallButtonText(text) {
    const labelEl = document.getElementById('btn-install-server-text');
    if (labelEl) {
      labelEl.textContent = text;
      return;
    }
    const btn = document.getElementById('btn-install-server');
    if (btn) btn.textContent = text;
  },

  async loadInstaller() {
    if (!this.eventsSetup) {
      this.setupEvents();
      this.eventsSetup = true;
    }
    this.init();
    if (this.isInstalling) {
      if (this._activeUpdateMode === 'install') {
        const btn = document.getElementById('btn-install-server');
        if (btn) {
          btn.disabled = true;
          this._setInstallButtonText(I18n.t('t_install_btn_downloading'));
        }
      } else if (this._activeUpdateMode) {
        this._setUpdateBusy(true, this._activeUpdateMode);
      }
      return;
    }
    await this.checkLockState();
    await this.loadJavaRuntimes();
    await this.selectType(this.selectedType);
  },

  init() {
    this._initialized = true;
    if (this._langListener) return;
    this._langListener = true;
    window.addEventListener('dockraft:language_changed', () => {
      this.refreshLanguage();
    });

    // Ensure build modal trigger button is always actively bound
    const btnBuildModal = document.getElementById('btn-open-build-modal');
    if (btnBuildModal && !btnBuildModal._bound) {
      btnBuildModal._bound = true;
      btnBuildModal.addEventListener('click', (e) => {
        if (e && e.preventDefault) e.preventDefault();
        this.openBuildModal();
      });
    }
  },

  _translateVersionLabel(raw) {
    const s = String(raw || '');
    if (typeof I18n === 'undefined' || I18n.currentLang !== 'en') return s;
    return s
      .replace(/\(Última Versión Estable\)/g, `(${I18n.t('t_install_channel_latest_stable') || 'Latest Stable'})`)
      .replace(/\(Estable\)/g, `(${I18n.t('t_install_channel_stable') || 'Stable'})`);
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
      if (this.selectedType === 'modpack') {
        if (!this.isInstalling && !this.allowForce) {
          this._setInstallButtonText(I18n.t('t_install_btn_install_modpack') || 'Instalar Modpack y Dependencias');
        }
        if (this.modpackResults.length > 0) {
          this.renderModpackResults();
        }
        if (this.selectedModpack) {
          this.loadModpackRequirements();
        }
        if (this.modpackType === 'mod') {
          this.renderModStackPanel();
        }
        this._refreshModpackRamHintState();
      }
    } else {
      // Installed server: re-render locked banner, update card, modpack/mods cards and plugin notices.
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard) {
        if (this.updateData) {
          this._renderUpdateInfo(this.updateData, { skipPluginsFetch: true });
        } else {
          this.loadUpdateInfo(window.__INITIAL_STATS__);
        }
        this.updateApplyButtonText();
      }
      if (this.modpackUpdateData && this.modpackUpdateData.has_modpack) {
        this.renderModpackUpdateCard(this.modpackUpdateData);
      }
      if (this.installedModsData) {
        this.renderInstalledMods(this.installedModsData);
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
      if (banner) {
        banner.classList.remove('d-none');
        banner.style.display = 'flex';
      }
      if (mainCard) {
        mainCard.classList.add('d-none');
        mainCard.style.display = 'none';
      }
      if (btnDelete) btnDelete.style.display = 'none';
      if (info && cfg) {
        const typeName = (cfg.server_type || 'Minecraft').toUpperCase();
        const ver = cfg.server_version || '';
        const mpBadge = cfg.modpack_name ? ` · <strong>${escapeHtml(cfg.modpack_name)}</strong>` : '';
        info.innerHTML = `<span data-i18n="t_install_banner_locked_installed_a">${I18n.t('t_install_banner_locked_installed_a')}</span> <strong>${escapeHtml(typeName)} ${escapeHtml(ver)}</strong>${mpBadge} (<code>${escapeHtml(cfg.server_file || 'server.jar')}</code>)<span data-i18n="t_install_banner_locked_installed_b">${I18n.t('t_install_banner_locked_installed_b')}</span>`;
      }
      if (btn) {
        btn.disabled = true;
        this._setInstallButtonText(I18n.t('t_install_btn_installed_locked'));
        btn.className = "btn btn-outline";
      }
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard) {
        updateCard.classList.remove('d-none');
        updateCard.style.display = 'block';
      }
      const sTypeLow = (cfg && cfg.server_type || '').toLowerCase();
      const isModdedLoader = ['fabric', 'neoforge', 'forge', 'quilt'].includes(sTypeLow);
      const isBedrock = sTypeLow === 'bedrock';
      const pluginsSub = document.getElementById('update-plugins-subsection');
      if (pluginsSub) {
        if (isBedrock || isModdedLoader) {
          pluginsSub.classList.add('d-none');
          pluginsSub.style.display = 'none';
        } else {
          pluginsSub.classList.remove('d-none');
          pluginsSub.style.display = 'block';
        }
      }
      const modsCard = document.getElementById('installer-mods-manager-card');
      if (modsCard) {
        modsCard.classList.toggle('d-none', !isModdedLoader);
        modsCard.style.display = isModdedLoader ? 'block' : 'none';
      }
      const mpUpdCard = document.getElementById('installer-modpack-update-card');
      if (mpUpdCard) {
        const showMp = Boolean(cfg && cfg.modpack_type === 'modpack' && cfg.modpack_id);
        mpUpdCard.classList.toggle('d-none', !showMp);
        mpUpdCard.style.display = showMp ? 'block' : 'none';
      }
    } else {
      this.isLocked = false;
      this.allowForce = true;
      if (banner) {
        banner.classList.add('d-none');
        banner.style.display = 'none';
      }
      if (mainCard) {
        mainCard.classList.remove('d-none');
        mainCard.style.display = 'block';
      }
      if (btnDelete) btnDelete.style.display = 'none';
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard) {
        updateCard.classList.add('d-none');
        updateCard.style.display = 'none';
      }
      const modsCard = document.getElementById('installer-mods-manager-card');
      if (modsCard) {
        modsCard.classList.add('d-none');
        modsCard.style.display = 'none';
      }
      const mpUpdCard = document.getElementById('installer-modpack-update-card');
      if (mpUpdCard) {
        mpUpdCard.classList.add('d-none');
        mpUpdCard.style.display = 'none';
      }
      const sub = document.getElementById('update-plugins-subsection');
      if (sub) {
        sub.classList.add('d-none');
        sub.style.display = 'none';
      }
      if (btn) {
        if (this.isInstalling) {
          btn.disabled = true;
          this._setInstallButtonText(I18n.t('t_install_btn_downloading'));
        } else {
          btn.disabled = false;
          this._setInstallButtonText(
            this.selectedType === 'modpack'
              ? (I18n.t('t_install_btn_install_modpack') || 'Instalar Modpack y Dependencias')
              : I18n.t('t_install_btn_install')
          );
          btn.className = "btn btn-primary";
        }
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
        const sTypeLow = (cfg.server_type || '').toLowerCase();
        const isModdedLoader = ['fabric', 'neoforge', 'forge', 'quilt'].includes(sTypeLow);
        if (sTypeLow !== 'bedrock' && !isModdedLoader) {
          this.loadConsolePluginUpdates();
        }
        await this.loadUpdateInfo(stats);
        if (cfg.modpack_type === 'modpack' && cfg.modpack_id) {
          this.loadModpackUpdateStatus();
        }
        if (isModdedLoader) {
          this.loadInstalledMods(true);
        }
      }
      await this.resumeActiveProgressIfAny(Boolean(stats.is_installed));
    } catch (e) {
      console.warn("Could not check server install state", e);
    }
  },

  async resumeActiveProgressIfAny(isInstalled) {
    if (this.pollingInterval || this.isInstalling) return;
    try {
      const pRes = await fetch('/api/installer/progress');
      if (!pRes.ok) return;
      const pData = await pRes.json();
      const active = Boolean(pData.is_active || pData.is_downloading);
      if (!active) return;

      this.isInstalling = true;
      if (isInstalled) {
        this._setUpdateBusy(true, 'build');
        const pBox = document.getElementById('update-progress-box');
        const pBar = document.getElementById('update-progress-bar');
        const pText = document.getElementById('update-progress-text');
        const pPct = document.getElementById('update-progress-percent');
        if (pBox) pBox.style.display = 'block';
        this._pollInstallerProgress({
          barEl: pBar,
          pctEl: pPct,
          textEl: pText,
          defaultStatus: pData.status || 'updating',
          onComplete: async () => {
            if (pBox) pBox.style.display = 'none';
            this.isInstalling = false;
            this._setUpdateBusy(false);
            App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
            await this.checkLockState();
          },
          onError: (statusMsg) => {
            if (pBox) pBox.style.display = 'none';
            this.isInstalling = false;
            this._setUpdateBusy(false);
            if (statusMsg) {
              App.showToast(I18n.fmt('t_install_err_update_fail', [statusMsg]), 'danger');
            }
          }
        });
      } else {
        this._activeUpdateMode = 'install';
        const btn = document.getElementById('btn-install-server');
        if (btn) {
          btn.disabled = true;
          this._setInstallButtonText(I18n.t('t_install_btn_downloading'));
        }
        const progressBox = document.getElementById('install-progress-box');
        const progressBar = document.getElementById('install-progress-bar');
        const progressText = document.getElementById('install-progress-text');
        if (progressBox) progressBox.style.display = 'block';
        this._pollInstallerProgress({
          barEl: progressBar,
          textEl: progressText,
          defaultStatus: pData.status || 'downloading',
          onComplete: async () => {
            this.isInstalling = false;
            this._activeUpdateMode = null;
            App.showToast(I18n.t('t_install_toast_installed_ok'), 'success');
            await this.checkLockState();
          },
          onError: (statusMsg) => {
            this.isInstalling = false;
            this._activeUpdateMode = null;
            if (btn) {
              btn.disabled = false;
              this._setInstallButtonText(
                this.selectedType === 'modpack'
                  ? (I18n.t('t_install_btn_install_modpack') || 'Instalar Modpack y Dependencias')
                  : I18n.t('t_install_btn_install')
              );
            }
            if (statusMsg) {
              App.showToast(I18n.fmt('t_install_err_download', [statusMsg]), 'danger');
            }
          }
        });
      }
    } catch (e) {
      // Non-fatal resume check
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
        if (mainCard) {
          mainCard.classList.remove('d-none');
          mainCard.style.display = 'block'; // Mostrar selector al desbloquear
        }
        if (btnDelete) btnDelete.style.display = 'inline-flex'; // Mostrar botón eliminar al desbloquear
        if (badge) badge.style.display = 'inline-block';
        if (btnUnlock) btnUnlock.textContent = I18n.t('t_install_btn_lock');
        if (btnInstall) {
          btnInstall.disabled = false;
          this._setInstallButtonText(I18n.t('t_install_btn_overwrite'));
          btnInstall.className = "btn btn-danger";
        }
        App.showToast(I18n.t('t_install_unlock_toast'), 'warning');
      }
    } else {
      this.isLocked = true;
      this.allowForce = false;
      if (mainCard) {
        mainCard.classList.add('d-none');
        mainCard.style.display = 'none'; // Ocultar nuevamente al bloquear
      }
      if (btnDelete) btnDelete.style.display = 'none'; // Ocultar botón eliminar
      if (badge) badge.style.display = 'none';
      if (btnUnlock) btnUnlock.textContent = I18n.t('t_install_btn_unlock');
      if (btnInstall) {
        btnInstall.disabled = true;
        this._setInstallButtonText(I18n.t('t_install_btn_installed_locked'));
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
        if (maxInput) {
          maxInput.value = ram;
          this._refreshModpackRamHintState();
        }
      });
    });

    const maxRamInp = document.getElementById('install-max-ram');
    if (maxRamInp) {
      maxRamInp.addEventListener('input', () => this._refreshModpackRamHintState());
    }
    const btnApplyRecRam = document.getElementById('btn-apply-recommended-ram');
    if (btnApplyRecRam) {
      btnApplyRecRam.addEventListener('click', () => this.applyRecommendedModpackRam());
    }

    // Console plugin updates buttons
    const btnScan = document.getElementById('btn-scan-console-updates');
    if (btnScan) {
      btnScan.addEventListener('click', () => this.scanConsolePluginUpdates());
    }
    const btnNotify = document.getElementById('btn-notify-console-updates');
    if (btnNotify) {
      btnNotify.addEventListener('click', () => this.notifyConsolePluginUpdates());
    }

    this.setupModpackEvents();
  },

  async selectType(type) {
    this.selectedType = type;
    document.querySelectorAll('.type-card').forEach(card => {
      card.classList.toggle('selected', card.getAttribute('data-type') === type);
    });

    const javaGroup = document.getElementById('java-runtime-group');
    const aikarGroup = document.getElementById('aikar-flags-group');
    const stdVersionGroup = document.getElementById('standard-version-group');
    const modpackPanel = document.getElementById('modpack-selector-panel');

    if (type === 'bedrock') {
      if (javaGroup) javaGroup.style.display = 'none';
      if (aikarGroup) aikarGroup.style.display = 'none';
    } else {
      if (javaGroup) javaGroup.style.display = 'flex';
      if (aikarGroup) aikarGroup.style.display = 'flex';
    }

    if (type === 'modpack') {
      if (stdVersionGroup) stdVersionGroup.style.display = 'none';
      if (modpackPanel) modpackPanel.style.display = 'block';

      if (!this.isLocked && !this.isInstalling) {
        const badge = document.getElementById('reinstall-warning-badge');
        const isReinstallMode = this.allowForce && badge && badge.style.display !== 'none';
        this._setInstallButtonText(
          isReinstallMode
            ? I18n.t('t_install_btn_overwrite')
            : (I18n.t('t_install_btn_install_modpack') || 'Instalar Modpack y Dependencias')
        );
      }

      const minRamEl = document.getElementById('install-min-ram');
      const maxRamEl = document.getElementById('install-max-ram');
      if (maxRamEl && (maxRamEl.value || '').trim().toUpperCase() === '2G') {
        maxRamEl.value = '4G';
      }
      if (minRamEl && (minRamEl.value || '').trim().toUpperCase() === '1G') {
        minRamEl.value = '2G';
      }
      this.updateModpackRamHint(
        this.currentRecommendedRam || { min_ram: '2G', max_ram: '4G', min_recommended_gb: 4, recommended_gb: 4 }
      );

      if (this.modpackResults.length === 0) {
        await this.searchModpacks();
      }
      return;
    }

    this.updateModpackRamHint(null);
    if (stdVersionGroup) stdVersionGroup.style.display = 'block';
    if (modpackPanel) modpackPanel.style.display = 'none';
    if (!this.isLocked && !this.isInstalling) {
      const badge = document.getElementById('reinstall-warning-badge');
      const isReinstallMode = this.allowForce && badge && badge.style.display !== 'none';
      this._setInstallButtonText(
        isReinstallMode ? I18n.t('t_install_btn_overwrite') : I18n.t('t_install_btn_install')
      );
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
      const data = await window.readApiJson(res, I18n.fmt('t_install_err_load_versions_for', [type]));
      this.versionsCache[type] = data.versions || [];

      select.innerHTML = '';
      this.versionsCache[type].forEach(ver => {
        const opt = document.createElement('option');
        if (typeof ver === 'object' && ver !== null) {
          opt.value = ver.id || ver.mc_version;
          opt.textContent = this._translateVersionLabel(ver.label || ver.id);
        } else {
          opt.value = ver;
          opt.textContent = this._translateVersionLabel(ver);
        }
        select.appendChild(opt);
      });
      select.disabled = false;
      this.updateRecommendedJava();
      this.onInstallVersionChange();
    } catch (e) {
      select.innerHTML = '<option value="">' + I18n.t('t_install_err_loading_versions') + '</option>';
      App.showToast(I18n.fmt('t_install_err_load_versions_for', [type]), 'danger');
    }
  },

  async loadJavaRuntimes() {
    const select = document.getElementById('installer-java-select');
    if (!select) return;

    try {
      const res = await fetch('/api/java/runtimes');
      if (!res.ok) return;
      this.runtimes = await res.json();
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
    if (this.selectedType === 'modpack') {
      return await this.startModpackInstallation();
    }

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

    this._activeUpdateMode = 'install';
    const btn = document.getElementById('btn-install-server');
    btn.disabled = true;
    this._setInstallButtonText(I18n.t('t_install_btn_downloading'));

    const progressBox = document.getElementById('install-progress-box');
    const progressBar = document.getElementById('install-progress-bar');
    const progressText = document.getElementById('install-progress-text');
    if (progressBox) progressBox.style.display = 'block';
    if (progressBar) progressBar.style.width = '0%';
    if (progressText) progressText.textContent = I18n.t('t_install_status_preparing');

    try {
      const res = await fetch('/api/installer/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      await window.readApiJson(res, I18n.t('t_install_err_install_failed'));

      App.showToast(I18n.t('t_install_toast_download_bg'), 'success');

      this._pollInstallerProgress({
        barEl: progressBar,
        textEl: progressText,
        defaultStatus: 'Downloading',
        onComplete: async () => {
          this.isInstalling = false;
          this._activeUpdateMode = null;
          App.showToast(I18n.t('t_install_toast_installed_ok'), 'success');
          await this.checkLockState();
          setTimeout(() => {
            App.switchTab('console');
          }, 1200);
        },
        onError: (statusMsg) => {
          this.isInstalling = false;
          this._activeUpdateMode = null;
          btn.disabled = false;
          this._setInstallButtonText(I18n.t('t_install_btn_install'));
          if (statusMsg) {
            App.showToast(I18n.fmt('t_install_err_download', [statusMsg]), 'danger');
          }
        }
      });

    } catch (e) {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
      this.isInstalling = false;
      this._activeUpdateMode = null;
      App.showToast(e.message, 'danger');
      btn.disabled = false;
      this._setInstallButtonText(I18n.t('t_install_btn_install'));
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
      this.updateData = data;
      window.__LAST_UPDATE_DATA__ = data;
      this._renderUpdateInfo(data, { skipPluginsFetch: false });
    } catch (err) {
      console.warn("Could not load update info:", err);
    }
  },

  _renderUpdateInfo(data, opts = {}) {
    const card = document.getElementById('installer-update-card');
    if (!card || !data) return;

    if (!data.is_installed) {
      card.style.display = 'none';
      const sub = document.getElementById('update-plugins-subsection');
      if (sub) sub.style.display = 'none';
      return;
    }

    card.style.display = 'block';
    const sTypeLow = (data.server_type || '').toLowerCase();
    const isModdedLoader = ['fabric', 'neoforge', 'forge', 'quilt'].includes(sTypeLow);
    const isBedrock = sTypeLow === 'bedrock';
    const pluginsSub = document.getElementById('update-plugins-subsection');
    if (pluginsSub) {
      pluginsSub.style.display = (isBedrock || isModdedLoader) ? 'none' : 'block';
      if (!isBedrock && !isModdedLoader && !opts.skipPluginsFetch) {
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
          let verDisplay = escapeHtml(data.current_version || I18n.t('t_install_unknown'));
          if (data.current_build) {
            verDisplay += ` (Build #${escapeHtml(String(data.current_build))})`;
          }
          curBadge.innerHTML = I18n.fmt('t_install_current_version_html', [verDisplay]);
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
        } else if (data.build_update_available && (data.current_version === data.latest_stable || !data.latest_stable)) {
          const zapSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px; vertical-align: -1px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`;
          statusBadge.innerHTML = zapSvg + I18n.fmt('t_install_new_build_available_html', [escapeHtml(String(data.latest_build || ''))]);
          statusBadge.style.background = 'rgba(56, 189, 248, 0.15)';
          statusBadge.style.borderColor = '#38bdf8';
          statusBadge.style.color = '#38bdf8';
          statusBadge.title = I18n.t('t_install_build_btn_change') || 'Cambiar / Actualizar Build';
          statusBadge.onclick = () => {
            this.openBuildModal();
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
          let upToDateText = data.latest_stable || data.current_version;
          if (data.current_build) {
            upToDateText += ` (Build #${data.current_build})`;
          }
          statusBadge.textContent = I18n.fmt('t_install_status_up_to_date', [upToDateText]);
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

      if (warningBadge) {
        // Dedicated build notice banner is handled inside Block 1 (#installer-build-card)
        warningBadge.style.display = 'none';
        warningBadge.onclick = null;
      }

      // Update Dedicated Build Card
      const buildCard = document.getElementById('installer-build-card');
      const sType = String(data.server_type || '').toLowerCase();
      const supportsBuilds = ['paper', 'purpur', 'folia', 'velocity'].includes(sType);
      if (buildCard) {
        if (supportsBuilds && data.is_installed) {
          buildCard.classList.remove('d-none');
          buildCard.style.display = 'block';

          const bVer = document.getElementById('build-card-mc-ver');
          if (bVer) bVer.textContent = data.current_version || data.latest_stable || '26.3';

          const bCur = document.getElementById('build-current-display');
          if (bCur) {
            bCur.textContent = data.current_build ? `#${data.current_build}` : (I18n.t('t_install_unknown') || 'No detectada');
          }

          const bBadge = document.getElementById('build-server-type-badge');
          if (bBadge) bBadge.textContent = sType.toUpperCase();

          const bNotice = document.getElementById('build-new-notice-banner');
          const bNoticeNum = document.getElementById('build-new-notice-num');
          const bNoticeVer = document.getElementById('build-new-notice-ver');
          const bBtnText = document.getElementById('btn-open-build-modal-text');
          const lockBuildBtnText = this.isInstalling && this._activeUpdateMode === 'build';

          if (data.build_update_available && data.latest_build) {
            if (bNotice) bNotice.style.display = 'block';
            if (bNoticeNum) bNoticeNum.textContent = `#${data.latest_build}`;
            if (bNoticeVer) bNoticeVer.textContent = data.current_version || data.latest_stable || '26.3';
            if (bBtnText && !lockBuildBtnText) {
              bBtnText.textContent = I18n.fmt('t_install_btn_update_to_build', [data.latest_build]) || `Actualizar a Build #${data.latest_build}`;
            }
          } else {
            if (bNotice) bNotice.style.display = 'none';
            if (bBtnText && !lockBuildBtnText) {
              bBtnText.textContent = I18n.t('t_install_build_btn_change') || 'Cambiar / Actualizar Build';
            }
          }

          const bBtn = document.getElementById('btn-open-build-modal');
          if (bBtn && !bBtn._bound) {
            bBtn._bound = true;
            bBtn.addEventListener('click', (e) => {
              if (e && e.preventDefault) e.preventDefault();
              this.openBuildModal();
            });
          }
        } else {
          buildCard.classList.add('d-none');
          buildCard.style.display = 'none';
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
          opt.textContent = this._translateVersionLabel(v.label || v.id);
          opt.setAttribute('data-channel', 'stable');
          selectStable.appendChild(opt);
        });
        if (stables.length === 0) {
          selectStable.innerHTML = `<option value="">${I18n.t('t_install_no_stable_versions')}</option>`;
        } else if (data.latest_stable) {
          selectStable.value = data.latest_stable;
        }
      }

      // Populate Beta Select
      if (selectBeta) {
        selectBeta.innerHTML = '';
        previews.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.id;
          opt.textContent = this._translateVersionLabel(v.label || v.id);
          opt.setAttribute('data-channel', v.channel || 'pre');
          selectBeta.appendChild(opt);
        });
        if (previews.length === 0) {
          selectBeta.innerHTML = `<option value="">${I18n.t('t_install_no_beta_versions')}</option>`;
        } else if (data.latest_preview) {
          selectBeta.value = data.latest_preview;
        }
      }

      // Populate hidden compatibility select
      if (select) {
        select.innerHTML = '';
        items.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.id;
          opt.textContent = this._translateVersionLabel(v.label || v.id);
          select.appendChild(opt);
        });
        if (items.length === 0) {
          const opt = document.createElement('option');
          opt.value = data.current_version || '';
          opt.textContent = data.current_version || '';
          select.appendChild(opt);
        }
      }

      this.switchUpdateChannel(this.currentUpdateChannel || 'stable');
      this.updateApplyButtonText();
  },

  currentUpdateChannel: 'stable',

  switchUpdateChannel(channel) {
    this.currentUpdateChannel = channel;
    const btnStable = document.getElementById('btn-channel-stable');
    const btnBeta = document.getElementById('btn-channel-beta');
    const groupStable = document.getElementById('update-group-stable');
    const groupBeta = document.getElementById('update-group-beta');
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

      if (selectComp && selectBeta) {
        selectComp.value = selectBeta.value;
      }
    }

    const activeSelect = channel === 'stable' ? selectStable : selectBeta;
    let selVal = activeSelect ? activeSelect.value : null;
    if (!selVal && activeSelect && activeSelect.options && activeSelect.options.length > 0) {
      selVal = activeSelect.options[0].value;
      activeSelect.value = selVal;
    }
    this.updateVersionChangelogCard(selVal, channel);
    this.updateApplyButtonText();
    this.checkMcUpgradeModCompatibility(selVal);
  },

  onVersionSelectChange(channel) {
    const selectStable = document.getElementById('update-version-select-stable');
    const selectBeta = document.getElementById('update-version-select-beta');
    const selectComp = document.getElementById('update-version-select');
    let selVal = null;
    if (channel === 'stable' && selectStable) {
      selVal = selectStable.value;
      if (selectComp) selectComp.value = selVal;
    } else if (channel === 'beta' && selectBeta) {
      selVal = selectBeta.value;
      if (selectComp) selectComp.value = selVal;
    }
    this.updateVersionChangelogCard(selVal, channel);
    this.updateApplyButtonText();
    this.checkMcUpgradeModCompatibility(selVal);
  },

  updateApplyButtonText() {
    const btn = document.getElementById('btn-apply-update');
    if (!btn || this.isInstalling) return;

    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const selectStable = document.getElementById('update-version-select-stable');
    const selectBeta = document.getElementById('update-version-select-beta');
    const selectedVer = String((this.currentUpdateChannel === 'beta' ? selectBeta?.value : selectStable?.value) || '').trim();
    const curVerClean = String(data.current_version || '').trim();

    const cubeSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>';

    if (selectedVer && curVerClean && selectedVer === curVerClean) {
      const btnText = I18n.fmt('t_install_btn_reinstall_mc_ver', [selectedVer]) || `Reinstalar Minecraft ${selectedVer}`;
      btn.innerHTML = `${cubeSvg} <span>${escapeHtml(btnText)}</span>`;
      btn.style.boxShadow = '';
      btn.style.borderColor = '#388bfd';
      btn.style.color = '#58a6ff';
    } else if (selectedVer) {
      const btnText = I18n.fmt('t_install_btn_change_mc_ver', [selectedVer]) || `Cambiar a Minecraft ${selectedVer}`;
      btn.innerHTML = `${cubeSvg} <span>${escapeHtml(btnText)}</span>`;
      btn.style.boxShadow = '0 0 10px rgba(56, 139, 253, 0.3)';
      btn.style.borderColor = '#388bfd';
      btn.style.color = '#58a6ff';
    } else {
      const btnText = I18n.t('t_install_btn_change_generic') || 'Cambiar Versión de Minecraft';
      btn.innerHTML = `${cubeSvg} <span>${escapeHtml(btnText)}</span>`;
      btn.style.boxShadow = '';
      btn.style.borderColor = '#388bfd';
      btn.style.color = '#58a6ff';
    }
  },

  buildVersionMeta(serverType, versionId, channel) {
    const st = (serverType || 'paper').toLowerCase();
    const vid = String(versionId || '').trim();
    const m = vid.match(/([0-9]+(?:\.[0-9]+)+(?:-[a-zA-Z0-9\.\-]+)?)/);
    const cleanVer = m ? m[1] : vid;
    const isBedrock = st === 'bedrock';

    let isStable = channel === 'stable';
    if (!channel) {
      isStable = !vid.includes('-pre') && !vid.includes('-rc') && !vid.toLowerCase().includes('snapshot') && !vid.toLowerCase().includes('beta') && !vid.toLowerCase().includes('preview');
    }

    let officialUrl = '';
    let officialLabel = '';

    if (st === 'paper') {
      officialUrl = 'https://papermc.io/downloads/paper';
      officialLabel = I18n.t('t_install_official_paper') || 'Página Oficial y Descargas de PaperMC';
    } else if (st === 'folia') {
      officialUrl = 'https://papermc.io/downloads/folia';
      officialLabel = I18n.t('t_install_official_folia') || 'Página Oficial y Descargas de Folia';
    } else if (st === 'velocity') {
      officialUrl = 'https://papermc.io/downloads/velocity';
      officialLabel = I18n.t('t_install_official_velocity') || 'Página Oficial y Descargas de Velocity';
    } else if (st === 'purpur') {
      officialUrl = cleanVer ? `https://purpurmc.org/downloads?version=${cleanVer}` : 'https://purpurmc.org/downloads';
      officialLabel = I18n.t('t_install_official_purpur') || 'Página Oficial y Descargas de Purpur';
    } else if (st === 'fabric') {
      officialUrl = 'https://fabricmc.net/';
      officialLabel = I18n.t('t_install_official_fabric') || 'Portal Oficial de FabricMC';
    } else if (st === 'forge') {
      officialUrl = 'https://files.minecraftforge.net/net/minecraftforge/forge/';
      officialLabel = I18n.t('t_install_official_forge') || 'Portal Oficial de Minecraft Forge';
    } else if (st === 'neoforge') {
      officialUrl = 'https://neoforged.net/';
      officialLabel = I18n.t('t_install_official_neoforge') || 'Portal Oficial de NeoForge';
    } else if (st === 'quilt') {
      officialUrl = 'https://quiltmc.org/';
      officialLabel = I18n.t('t_install_official_quilt') || 'Portal Oficial de QuiltMC';
    } else if (st === 'bedrock') {
      if (!isStable) {
        officialUrl = 'https://feedback.minecraft.net/hc/en-us/sections/360001185332-Beta-and-Preview-Information-and-Changelogs';
        officialLabel = I18n.t('t_install_official_bedrock_beta') || 'Novedades Oficiales de Betas y Previews (Bedrock)';
      } else {
        officialUrl = 'https://feedback.minecraft.net/hc/en-us/sections/360001186971-Release-Changelogs';
        officialLabel = I18n.t('t_install_official_bedrock') || 'Página Oficial y Cambios de Bedrock';
      }
    } else {
      officialUrl = 'https://www.minecraft.net/articles';
      officialLabel = I18n.t('t_install_official_vanilla') || 'Artículos Oficiales de Lanzamiento en Minecraft.net';
    }

    const wikiUrl = isBedrock
      ? `https://minecraft.wiki/w/Bedrock_Edition_${cleanVer}`
      : `https://minecraft.wiki/w/Java_Edition_${cleanVer}`;
    const wikiLabel = (typeof I18n.fmt === 'function')
      ? I18n.fmt('t_install_btn_wiki_ver', [cleanVer])
      : `Wiki de Minecraft (${cleanVer})`;

    let adviceTitle = '';
    let adviceText = '';
    if (isStable) {
      adviceTitle = I18n.t('t_install_advice_stable_title') || 'Compilación Estable (Recomendada para Producción)';
      adviceText = (typeof I18n.fmt === 'function')
        ? I18n.fmt('t_install_advice_stable_text', [cleanVer])
        : `La versión ${cleanVer} es una compilación Estable oficial. Es la opción recomendada si buscas máxima compatibilidad con plugins/mods, estabilidad para tus jugadores y cero riesgos de fallos experimentales.`;
    } else {
      const chLabel = (vid.includes('-rc') ? 'Release Candidate' : (vid.includes('-pre') ? 'Pre-Release' : (isBedrock ? 'Preview / Beta' : 'Beta / Snapshot')));
      adviceTitle = (typeof I18n.fmt === 'function')
        ? I18n.fmt('t_install_advice_beta_title', [chLabel])
        : `Compilación ${chLabel} (Preliminar de Desarrollo)`;
      adviceText = (typeof I18n.fmt === 'function')
        ? I18n.fmt('t_install_advice_beta_text', [cleanVer])
        : `La versión ${cleanVer} incluye mecánicas preliminares antes de su lanzamiento final, pero puede contener bugs o incompatibilidad con plugins. Te conviene quedarte en Estable si tu comunidad está activa, o probar esta versión si tienes un entorno de prueba. Dockraft creará una copia de seguridad preventiva antes de actualizar.`;
    }

    return {
      serverType: st,
      versionId: vid,
      cleanVer,
      isStable,
      officialUrl,
      officialLabel,
      wikiUrl,
      wikiLabel,
      changelogUrl: officialUrl,
      engineUrl: wikiUrl,
      engineLabel: wikiLabel,
      adviceTitle,
      adviceText
    };
  },

  _renderVersionDetailsCard(ids, meta, item = {}) {
    const card = document.getElementById(ids.card);
    if (!card) return;
    card.style.display = 'block';

    const chBadge = document.getElementById(ids.badge);
    const titleEl = document.getElementById(ids.title);
    const btnOfficial = document.getElementById(ids.btnOfficial);
    const btnOfficialText = document.getElementById(ids.btnOfficialText);
    const btnWiki = document.getElementById(ids.btnWiki);
    const btnWikiLabel = document.getElementById(ids.btnWikiLabel);
    const adviceTitle = document.getElementById(ids.adviceTitle);
    const adviceText = document.getElementById(ids.adviceText);

    if (chBadge) {
      if (meta.isStable) {
        chBadge.textContent = I18n.t('t_install_channel_stable') || 'Estable';
        chBadge.style.background = 'rgba(46, 160, 67, 0.15)';
        chBadge.style.border = '1px solid #2ea043';
        chBadge.style.color = '#3fb950';
      } else {
        const chName = (item.channel === 'pre' || meta.versionId.includes('-pre')) ? 'Pre-Release' :
                       (item.channel === 'preview' || meta.versionId.includes('preview') || meta.serverType === 'bedrock') ? 'Preview / Beta' :
                       (meta.versionId.includes('-rc') ? 'Release Candidate' : 'Snapshot');
        chBadge.textContent = chName;
        chBadge.style.background = 'rgba(210, 153, 34, 0.15)';
        chBadge.style.border = '1px solid #d29922';
        chBadge.style.color = '#e3b341';
      }
    }

    if (titleEl) {
      titleEl.textContent = `${(meta.serverType || 'Minecraft').toUpperCase()} ${this._translateVersionLabel(item.label || meta.versionId)}`;
    }

    if (btnOfficial) {
      btnOfficial.href = meta.officialUrl;
      if (btnOfficialText) {
        btnOfficialText.textContent = meta.officialLabel || I18n.t('t_install_btn_view_changelog') || 'Web Oficial y Cambios';
      }
    }

    if (btnWiki) {
      if (meta.wikiUrl) {
        btnWiki.style.display = 'inline-flex';
        btnWiki.href = meta.wikiUrl;
        if (btnWikiLabel) {
          btnWikiLabel.textContent = meta.wikiLabel || I18n.t('t_install_btn_engine_notes') || 'Wiki de Minecraft';
        }
      } else {
        btnWiki.style.display = 'none';
      }
    }

    if (adviceTitle && adviceText) {
      adviceTitle.textContent = meta.adviceTitle;
      adviceText.textContent = meta.adviceText;
    }
  },

  updateVersionChangelogCard(selectedVersionId, channel) {
    const card = document.getElementById('update-version-details-card');
    if (!card) return;

    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const serverType = data.server_type || 'paper';

    if (!selectedVersionId) {
      const activeSelect = (channel === 'beta' || this.currentUpdateChannel === 'beta')
        ? document.getElementById('update-version-select-beta')
        : document.getElementById('update-version-select-stable');
      if (activeSelect && activeSelect.value) {
        selectedVersionId = activeSelect.value;
      }
    }

    if (!selectedVersionId) {
      card.style.display = 'none';
      return;
    }

    const items = data.versions || [];
    let item = items.find(v => String(v.id).trim() === String(selectedVersionId).trim());
    if (!item) {
      item = items.find(v => String(v.clean_version).trim() === String(selectedVersionId).trim()) || {};
    }

    const itemCh = item.channel || channel || 'stable';
    const meta = this.buildVersionMeta(serverType, selectedVersionId, itemCh);

    if (item.official_url) meta.officialUrl = item.official_url;
    if (item.wiki_url) meta.wikiUrl = item.wiki_url;
    if (item.clean_version) meta.cleanVer = item.clean_version;

    this._renderVersionDetailsCard({
      card: 'update-version-details-card',
      badge: 'update-details-channel-badge',
      title: 'update-details-version-title',
      btnOfficial: 'btn-view-changelog',
      btnOfficialText: 'btn-view-changelog-text',
      btnWiki: 'btn-view-engine-notes',
      btnWikiLabel: 'btn-engine-notes-label',
      adviceTitle: 'update-details-advice-title',
      adviceText: 'update-details-advice-text'
    }, meta, item);
  },

  onInstallVersionChange() {
    this.updateRecommendedJava();
    const select = document.getElementById('installer-version-select');
    const card = document.getElementById('install-version-details-card');
    if (!select || !card) return;

    const vid = select.value;
    if (!vid) {
      card.style.display = 'none';
      return;
    }

    const meta = this.buildVersionMeta(this.selectedType, vid, null);
    this._renderVersionDetailsCard({
      card: 'install-version-details-card',
      badge: 'install-details-channel-badge',
      title: 'install-details-version-title',
      btnOfficial: 'btn-install-view-changelog',
      btnOfficialText: 'btn-install-view-changelog-text',
      btnWiki: 'btn-install-view-engine-notes',
      btnWikiLabel: 'btn-install-engine-notes-label',
      adviceTitle: 'install-details-advice-title',
      adviceText: 'install-details-advice-text'
    }, meta);
  },

  async startUpdate() {
    if (this.isInstalling) {
      App.showToast(I18n.t('t_install_toast_already_busy'), 'info');
      return;
    }

    let isRunning = false;
    try {
      const sRes = await fetch('/api/server/status');
      if (sRes.ok) {
        const stats = await sRes.json();
        isRunning = (stats.status && stats.status !== 'OFFLINE');
      }
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

    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const curVerClean = String(data.current_version || '').trim();
    const targetVerClean = String(targetVer || '').trim();
    const isSameVersion = (targetVerClean === curVerClean);
    const isBetaTarget = (this.currentUpdateChannel === 'beta');
    const betaNotice = isBetaTarget ? '\n\n' + I18n.t('t_install_beta_notice') : '';

    const confirmTitle = isSameVersion
      ? (I18n.fmt('t_install_btn_reinstall_mc_ver', [targetVer]) || `Reinstalar Minecraft ${targetVer}`)
      : (I18n.fmt('t_install_btn_change_mc_ver', [targetVer]) || `Cambiar a Minecraft ${targetVer}`);
    const confirmBtnText = confirmTitle;
    const confirmMessage = isRunning
      ? I18n.fmt('t_install_update_confirm_running', [targetVer]) + betaNotice
      : I18n.fmt('t_install_update_confirm_stopped', [targetVer]) + betaNotice;

    const ok = await App.confirm({
      title: confirmTitle,
      message: confirmMessage,
      confirmText: confirmBtnText,
      type: isBetaTarget ? 'warning' : 'info'
    });
    if (!ok) return;

    this.isInstalling = true;
    this._setUpdateBusy(true, 'version');

    const pBox = document.getElementById('update-progress-box');
    const pBar = document.getElementById('update-progress-bar');
    const pText = document.getElementById('update-progress-text');
    const pPct = document.getElementById('update-progress-percent');
    if (pBox) pBox.style.display = 'block';
    if (pBar) pBar.style.width = '0%';
    if (pPct) pPct.textContent = '0%';
    if (pText) pText.textContent = I18n.t(isRunning ? 't_install_status_stopping' : 't_install_status_backing_up');

    try {
      const sTypeLow = String(data.server_type || '').toLowerCase();
      const isModdedLoader = ['fabric', 'neoforge', 'forge', 'quilt'].includes(sTypeLow);
      const updPayload = { version: targetVer };
      if (isModdedLoader) {
        updPayload.update_mods = Boolean(document.getElementById('update-mods-on-mc-upgrade')?.checked);
        updPayload.allow_beta_mods = Boolean(document.getElementById('mods-upd-allow-beta')?.checked);
      }
      const res = await fetch('/api/installer/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updPayload)
      });
      await window.readApiJson(res, I18n.t('t_install_err_update_start'));

      App.showToast(I18n.t('t_install_toast_update_started'), 'info');

      this._pollInstallerProgress({
        barEl: pBar,
        pctEl: pPct,
        textEl: pText,
        defaultStatus: 'updating',
        onComplete: async () => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
          await this.checkLockState();
        },
        onError: (statusMsg) => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          if (statusMsg) {
            App.showToast(I18n.fmt('t_install_err_update_fail', [statusMsg]), 'danger');
          }
        }
      });

    } catch (e) {
      this.isInstalling = false;
      this._setUpdateBusy(false);
      if (pBox) pBox.style.display = 'none';
      App.showToast(e.message, 'danger');
    }
  },

  _restoreBuildModalButton() {
    const bBtn = document.getElementById('btn-open-build-modal');
    if (!bBtn) return;
    bBtn.disabled = false;
    bBtn.style.opacity = '';
    bBtn.style.cursor = '';
    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const labelText = (data.build_update_available && data.latest_build)
      ? (I18n.fmt('t_install_btn_update_to_build', [data.latest_build]) || `Actualizar a Build #${data.latest_build}`)
      : (I18n.t('t_install_build_btn_change') || 'Cambiar / Actualizar Build');
    const refreshSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>';
    bBtn.innerHTML = `${refreshSvg} <span id="btn-open-build-modal-text">${escapeHtml(labelText)}</span>`;
  },

  _setUpdateBusy(isBusy, activeMode = 'version') {
    this._activeUpdateMode = isBusy ? activeMode : null;
    const spinnerSvg = '<svg class="spin-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>';

    const btnBuild = document.getElementById('btn-open-build-modal');
    const btnApply = document.getElementById('btn-apply-update');

    if (isBusy) {
      if (btnBuild) {
        btnBuild.disabled = true;
        btnBuild.style.opacity = '0.7';
        btnBuild.style.cursor = 'not-allowed';
        if (activeMode === 'build') {
          btnBuild.innerHTML = `${spinnerSvg} <span id="btn-open-build-modal-text">${escapeHtml(I18n.t('t_install_updating_ellipsis'))}</span>`;
        }
      }
      if (btnApply) {
        btnApply.disabled = true;
        btnApply.style.opacity = '0.7';
        btnApply.style.cursor = 'not-allowed';
        if (activeMode === 'version') {
          btnApply.innerHTML = `${spinnerSvg} <span>${escapeHtml(I18n.t('t_install_downloading_ellipsis'))}</span>`;
        }
      }
    } else {
      this._restoreBuildModalButton();
      if (btnApply) {
        btnApply.disabled = false;
        btnApply.style.opacity = '';
        btnApply.style.cursor = '';
      }
      this.updateApplyButtonText();
    }

    [
      'update-version-select-stable',
      'update-version-select-beta',
      'btn-channel-stable',
      'btn-channel-beta',
      'btn-unlock-reinstall',
      'btn-delete-server',
      'btn-apply-modpack-update',
      'btn-update-all-mods',
      'btn-open-add-mod-modal',
      'modpack-update-version-select',
      'modpack-upd-allow-beta',
      'mods-upd-allow-beta',
      'btn-refresh-installed-mods'
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.disabled = Boolean(isBusy);
    });
  },

  // Maps server-provided download/install status codes to localized labels.
  mapStatusText(status) {
    if (!status) return '';
    const norm = String(status).trim().toLowerCase().replace(/\.+$/, '');
    const map = {
      idle: I18n.t('t_install_status_idle'),
      preparing: I18n.t('t_install_status_preparing'),
      stopping: I18n.t('t_install_status_stopping'),
      backing_up: I18n.t('t_install_status_backing_up'),
      downloading: I18n.t('t_install_status_downloading'),
      downloading_modpack: I18n.t('t_install_status_downloading_modpack'),
      installing_loader: I18n.t('t_install_status_installing_loader'),
      downloading_mods: I18n.t('t_install_status_downloading_mods'),
      verifying: I18n.t('t_install_status_verifying'),
      extracting: I18n.t('t_install_status_extracting'),
      extracting_overrides: I18n.t('t_install_status_extracting_overrides'),
      installing: I18n.t('t_install_status_installing'),
      updating: I18n.t('t_install_status_updating'),
      restarting: I18n.t('t_install_status_restarting'),
      completed: I18n.t('t_install_status_completed')
    };
    return map[norm] || status;
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
      const data = await window.readApiJson(res, I18n.t('t_install_err_import_failed'));

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
          <div style="font-size: 0.88rem; font-weight: 500; color: #7ee787; margin-bottom: 4px; display: flex; align-items: center; justify-content: center; gap: 6px;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            <span>${I18n.t('t_install_plugin_empty_title')}</span>
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
      const searchUrl = `https://www.google.com/search?q=${encodeURIComponent(u.plugin + ' minecraft plugin download')}`;
      const downloadBtn = isSafeUrl ? `
        <a href="${escapeHtml(rawUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-primary" style="padding: 5px 12px; font-size: 0.78rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          ${I18n.t('t_install_plugin_download')} ↗
        </a>
      ` : `
        <a href="${escapeHtml(searchUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-outline" style="padding: 5px 10px; font-size: 0.76rem; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; color: var(--text-muted); border-color: rgba(255,255,255,0.12);" title="${escapeHtml(u.message)}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          Buscar ↗
        </a>
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
    const ok = await App.confirm({
      title: I18n.t('t_install_btn_clear', 'Limpiar Avisos'),
      message: I18n.t('t_install_plugin_clear_confirm', '¿Deseas descartar todos los avisos de actualización de plugins detectados?'),
      confirmText: I18n.t('t_install_btn_clear', 'Limpiar Avisos'),
      danger: true
    });
    if (!ok) return;
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

  _restoreScanButton(btn) {
    if (!btn) return;
    btn.disabled = false;
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> <span data-i18n="t_install_btn_scan">${I18n.t('t_install_btn_scan')}</span>`;
  },

  async scanConsolePluginUpdates() {
    const btn = document.getElementById('btn-scan-console-updates');
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
        this._restoreScanButton(btn);
        if (data.count > 0) {
          App.showToast(I18n.fmt('t_install_toast_plugin_found', [data.count]), 'warning');
        } else {
          App.showToast(I18n.t('t_install_toast_plugin_none'), 'info');
        }
        return;
      } else {
        App.showToast(I18n.t('t_install_err_plugin_scan'), 'danger');
      }
    } catch (e) {
      App.showToast(I18n.t('t_install_err_plugin_scan_conn'), 'danger');
    } finally {
      this._restoreScanButton(btn);
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

  // --- Modpacks & Mod-based Server Workbench ---
  setupModpackEvents() {
    document.querySelectorAll('.modpack-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.getAttribute('data-mp-type') || 'modpack';
        this.setModpackType(mode);
      });
    });

    const btnSearch = document.getElementById('btn-modpack-search');
    if (btnSearch) {
      btnSearch.addEventListener('click', () => this.searchModpacks());
    }

    const searchInput = document.getElementById('modpack-search-input');
    if (searchInput) {
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.searchModpacks();
        }
      });
    }

    const loaderFilter = document.getElementById('modpack-loader-filter');
    if (loaderFilter) {
      loaderFilter.addEventListener('change', () => this.searchModpacks());
    }

    const allowBetaInstall = document.getElementById('modpack-allow-beta');
    if (allowBetaInstall) {
      allowBetaInstall.addEventListener('change', () => {
        if (this.modpackType === 'mod' && this.selectedModStack.length > 0) {
          this.resolveCurrentModStack();
        }
      });
    }

    const builderLoader = document.getElementById('mod-builder-loader');
    if (builderLoader) {
      builderLoader.addEventListener('change', async () => {
        await this.loadModBuilderVersions();
        if (this.selectedModStack.length > 0) {
          await this.resolveCurrentModStack();
        }
        await this.searchModpacks();
      });
    }

    const builderMc = document.getElementById('mod-builder-mc-version');
    if (builderMc) {
      builderMc.addEventListener('change', async () => {
        if (this.selectedModStack.length > 0) {
          await this.resolveCurrentModStack();
        }
        await this.searchModpacks();
      });
    }

    const mpUpdBeta = document.getElementById('modpack-upd-allow-beta');
    if (mpUpdBeta) {
      mpUpdBeta.addEventListener('change', () => this.loadModpackUpdateStatus());
    }

    const modsUpdBeta = document.getElementById('mods-upd-allow-beta');
    if (modsUpdBeta) {
      modsUpdBeta.addEventListener('change', () => this.loadInstalledMods(true));
    }

    const addModInp = document.getElementById('add-mod-search-input');
    if (addModInp) {
      addModInp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.searchCompatibleModsForServer();
        }
      });
    }

    const addModBeta = document.getElementById('add-mod-allow-beta');
    if (addModBeta) {
      addModBeta.addEventListener('change', () => this.searchCompatibleModsForServer());
    }

    document.querySelectorAll('.modpack-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const q = chip.getAttribute('data-mp-query') || '';
        const inp = document.getElementById('modpack-search-input');
        if (inp) inp.value = q;
        this.searchModpacks(q);
      });
    });

    const btnUpload = document.getElementById('btn-upload-mrpack');
    const fileInput = document.getElementById('modpack-mrpack-file');
    if (btnUpload && fileInput) {
      btnUpload.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files[0]) {
          this.onLocalMrpackSelected(fileInput.files[0]);
        }
      });
    }

    const verSel = document.getElementById('modpack-version-select');
    if (verSel) {
      verSel.addEventListener('change', () => this.onModpackVersionChange());
    }

    const modLdrSel = document.getElementById('modpack-mod-loader-select');
    if (modLdrSel) {
      modLdrSel.addEventListener('change', () => this.loadModpackRequirements());
    }

    const modMcSel = document.getElementById('modpack-mod-mc-select');
    if (modMcSel) {
      modMcSel.addEventListener('change', () => this.loadModpackRequirements());
    }
  },

  _parseRamGb(rawVal) {
    const s = String(rawVal || '').trim().toUpperCase();
    const m = s.match(/^(\d+(?:\.\d+)?)\s*([GM])?B?$/);
    if (!m) return 0;
    const num = parseFloat(m[1]);
    if (m[2] === 'M') return num / 1024;
    return num;
  },

  updateModpackRamHint(ramObj) {
    const bar = document.getElementById('modpack-ram-hint-bar');
    if (!bar) return;
    if (!ramObj || this.selectedType !== 'modpack') {
      bar.style.display = 'none';
      return;
    }
    this.currentRecommendedRam = ramObj;
    bar.style.display = 'inline-flex';
    this._refreshModpackRamHintState();
  },

  _refreshModpackRamHintState() {
    const bar = document.getElementById('modpack-ram-hint-bar');
    const txt = document.getElementById('modpack-ram-hint-text');
    const btn = document.getElementById('btn-apply-recommended-ram');
    const maxInput = document.getElementById('install-max-ram');
    const ramObj = this.currentRecommendedRam;
    if (!bar || !txt || !ramObj || this.selectedType !== 'modpack') return;

    const minRecGb = Number(ramObj.min_recommended_gb || 4);
    const recGb = Number(ramObj.recommended_gb || minRecGb);
    const curGb = this._parseRamGb(maxInput ? maxInput.value : '4G');
    const isLow = curGb > 0 && curGb < minRecGb;
    const labelGb = recGb > minRecGb ? `${minRecGb}–${recGb}` : `${minRecGb}`;

    if (isLow) {
      txt.textContent = I18n.fmt('t_install_mp_ram_low_warn', [minRecGb]);
      bar.style.background = 'rgba(210, 153, 34, 0.14)';
      bar.style.borderColor = 'rgba(210, 153, 34, 0.45)';
      bar.style.color = '#e3b341';
      if (btn) btn.style.display = 'inline';
    } else {
      txt.textContent = I18n.fmt('t_install_mp_ram_min_rec', [labelGb]);
      bar.style.background = 'rgba(60, 163, 116, 0.08)';
      bar.style.borderColor = 'rgba(60, 163, 116, 0.25)';
      bar.style.color = 'var(--text-muted)';
      if (btn) btn.style.display = (curGb === recGb) ? 'none' : 'inline';
    }
  },

  applyRecommendedModpackRam() {
    const ramObj = this.currentRecommendedRam;
    if (!ramObj) return;
    const minEl = document.getElementById('install-min-ram');
    const maxEl = document.getElementById('install-max-ram');
    if (minEl && ramObj.min_ram) minEl.value = ramObj.min_ram;
    if (maxEl && ramObj.max_ram) maxEl.value = ramObj.max_ram;
    this._refreshModpackRamHintState();
  },

  async setModpackType(mode) {
    this.modpackType = mode === 'mod' ? 'mod' : 'modpack';
    document.querySelectorAll('.modpack-pill-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-mp-type') === this.modpackType);
    });
    this.pendingMrpackFile = null;
    this.selectedModpack = null;
    this.selectedModpackRequirements = null;
    const isStackMode = this.modpackType === 'mod';

    const selPanel = document.getElementById('modpack-selected-panel');
    if (selPanel) selPanel.style.display = 'none';
    const envBar = document.getElementById('mod-builder-env-bar');
    if (envBar) envBar.style.display = isStackMode ? 'block' : 'none';
    const stackPanel = document.getElementById('mod-stack-panel');
    if (stackPanel) stackPanel.style.display = isStackMode ? 'block' : 'none';
    const loaderFilter = document.getElementById('modpack-loader-filter');
    if (loaderFilter) loaderFilter.style.display = isStackMode ? 'none' : 'block';

    if (isStackMode) {
      await this.loadModBuilderVersions();
      this.renderModStackPanel();
    } else if (!this.isLocked && !this.isInstalling) {
      this._setInstallButtonText(I18n.t('t_install_btn_install_modpack') || 'Instalar Modpack y Dependencias');
    }
    await this.searchModpacks();
  },

  async loadModBuilderVersions() {
    const loaderSel = document.getElementById('mod-builder-loader');
    const mcSel = document.getElementById('mod-builder-mc-version');
    if (!loaderSel || !mcSel) return;
    const ldr = loaderSel.value || 'fabric';
    const prev = mcSel.value;

    try {
      let vers = this.versionsCache[`mb_${ldr}`];
      if (!vers) {
        const res = await fetch(`/api/installer/versions?type=${encodeURIComponent(ldr)}`);
        if (res.ok) {
          const d = await res.json();
          vers = (d.versions || []).map(v => (typeof v === 'object' && v !== null) ? (v.mc_version || v.id) : String(v));
          this.versionsCache[`mb_${ldr}`] = vers;
        }
      }
      if (vers && vers.length > 0) {
        mcSel.innerHTML = '';
        vers.slice(0, 35).forEach(v => {
          const opt = document.createElement('option');
          opt.value = v;
          opt.textContent = v;
          mcSel.appendChild(opt);
        });
        if (prev && vers.includes(prev)) {
          mcSel.value = prev;
        } else if (vers.includes('1.21.1')) {
          mcSel.value = '1.21.1';
        }
      }
    } catch (e) {
      console.warn('Could not load mod builder MC versions:', e);
    }
  },

  async searchModpacks(queryOverride) {
    const grid = document.getElementById('modpack-results-grid');
    const statusEl = document.getElementById('modpack-search-status');
    const inputEl = document.getElementById('modpack-search-input');
    const loaderEl = document.getElementById('modpack-loader-filter');
    const builderLdrEl = document.getElementById('mod-builder-loader');
    const builderMcEl = document.getElementById('mod-builder-mc-version');
    const q = queryOverride !== undefined ? String(queryOverride) : (inputEl ? inputEl.value.trim() : '');
    const loader = this.modpackType === 'mod'
      ? (builderLdrEl ? builderLdrEl.value.trim() : '')
      : (loaderEl ? loaderEl.value.trim() : '');
    const gameVer = this.modpackType === 'mod' && builderMcEl ? builderMcEl.value.trim() : '';

    if (statusEl) statusEl.textContent = I18n.t('t_install_mp_searching') || 'Buscando proyectos compatibles...';
    if (grid) grid.innerHTML = '';

    try {
      const qs = new URLSearchParams({
        q,
        project_type: this.modpackType,
        limit: '9'
      });
      if (loader) qs.set('loader', loader);
      if (gameVer) qs.set('game_version', gameVer);

      const res = await fetch(`/api/installer/modpacks/search?${qs.toString()}`);
      const data = await window.readApiJson(res, I18n.t('t_install_mp_searching'));
      this.modpackResults = data.hits || [];
      this.renderModpackResults();
    } catch (e) {
      if (statusEl) statusEl.textContent = I18n.fmt('t_install_mp_err_search', [e.message]);
      this.modpackResults = [];
    }
  },

  renderModpackResults() {
    const grid = document.getElementById('modpack-results-grid');
    const statusEl = document.getElementById('modpack-search-status');
    if (!grid) return;

    const hits = this.modpackResults || [];
    if (hits.length === 0) {
      if (statusEl) statusEl.textContent = I18n.t('t_install_mp_empty');
      grid.innerHTML = '';
      return;
    }

    if (statusEl) statusEl.textContent = I18n.fmt('t_install_mp_results_count', [hits.length]);
    grid.innerHTML = '';
    const selectedId = this.selectedModpack ? this.selectedModpack.project_id : null;
    const stackIds = new Set((this.selectedModStack || []).map(m => m.project_id));

    hits.forEach(item => {
      const card = document.createElement('button');
      card.type = 'button';
      const isSelected = this.modpackType === 'mod'
        ? stackIds.has(item.project_id)
        : (selectedId === item.project_id);
      card.className = `modpack-card${isSelected ? ' selected' : ''}`;
      card.setAttribute('data-project-id', item.project_id);

      const iconHtml = item.icon_url
        ? `<img src="${escapeHtml(item.icon_url)}" alt="" class="modpack-card-icon" loading="lazy">`
        : `<div class="modpack-card-icon" style="display:flex;align-items:center;justify-content:center;color:var(--accent-primary);font-weight:700;">M</div>`;
      const loadersHtml = (item.loaders || []).slice(0, 3)
        .map(l => `<span class="modpack-loader-tag">${escapeHtml(l)}</span>`)
        .join('');
      const dlFmt = Number(item.downloads || 0).toLocaleString();

      card.innerHTML = `
        ${iconHtml}
        <div class="modpack-card-body">
          <div class="modpack-card-title">${escapeHtml(item.title)}</div>
          <div class="modpack-card-desc">${escapeHtml(item.description || '')}</div>
          <div class="modpack-card-meta">
            ${loadersHtml}
            <span>${escapeHtml(I18n.fmt('t_install_mp_downloads', [dlFmt]))}</span>
          </div>
        </div>
      `;
      card.addEventListener('click', () => {
        if (this.modpackType === 'mod') {
          this.toggleModInStack(item);
        } else {
          this.selectModpack(item.project_id);
        }
      });
      grid.appendChild(card);
    });
  },

  async toggleModInStack(item) {
    if (!item || !item.project_id) return;
    const idx = this.selectedModStack.findIndex(m => m.project_id === item.project_id);
    if (idx >= 0) {
      this.selectedModStack.splice(idx, 1);
    } else {
      this.selectedModStack.push({
        project_id: item.project_id,
        title: item.title || item.slug || item.project_id
      });
    }
    this.renderModpackResults();
    await this.resolveCurrentModStack();
  },

  async removeModFromStack(projectId) {
    this.selectedModStack = this.selectedModStack.filter(m => m.project_id !== projectId);
    this.renderModpackResults();
    await this.resolveCurrentModStack();
  },

  async resolveCurrentModStack() {
    const loader = document.getElementById('mod-builder-loader')?.value || 'fabric';
    const mcVer = document.getElementById('mod-builder-mc-version')?.value || '1.21.1';
    const allowBeta = Boolean(document.getElementById('modpack-allow-beta')?.checked);

    if (this.selectedModStack.length === 0) {
      this.resolvedModStack = null;
      this.renderModStackPanel();
      return;
    }

    const depsBox = document.getElementById('mod-stack-deps-box');
    if (depsBox) {
      depsBox.textContent = I18n.t('t_install_mp_inspecting') || 'Analizando...';
      depsBox.style.display = 'flex';
    }

    try {
      const res = await fetch('/api/installer/modpacks/resolve-stack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_ids: this.selectedModStack.map(m => m.project_id),
          loader,
          mc_version: mcVer,
          allow_beta: allowBeta
        })
      });
      this.resolvedModStack = await window.readApiJson(res, 'Error');
    } catch (e) {
      this.resolvedModStack = { conflicts: [{ reason: e.message }], missing: [], auto_dependencies: [], can_install: false };
    }
    this.renderModStackPanel();
  },

  renderModStackPanel() {
    const loader = document.getElementById('mod-builder-loader')?.value || 'fabric';
    const mcVer = document.getElementById('mod-builder-mc-version')?.value || '1.21.1';
    const envPill = document.getElementById('mod-stack-env-pill');
    const ramPill = document.getElementById('mod-stack-ram-pill');
    const chipsBox = document.getElementById('mod-stack-chips');
    const warnBox = document.getElementById('mod-stack-warnings');
    const depsBox = document.getElementById('mod-stack-deps-box');

    if (envPill) envPill.textContent = `${loader.toUpperCase()} · ${mcVer}`;
    if (!chipsBox) return;

    if (this.selectedModStack.length === 0) {
      if (ramPill) ramPill.style.display = 'none';
      chipsBox.innerHTML = `<span style="font-size: 0.79rem; color: var(--text-muted);">${escapeHtml(I18n.t('t_install_mp_stack_empty'))}</span>`;
      if (warnBox) warnBox.style.display = 'none';
      if (depsBox) depsBox.style.display = 'none';
      if (!this.isLocked && !this.isInstalling) {
        this._setInstallButtonText(I18n.fmt('t_install_mp_btn_install_stack', [0]));
      }
      return;
    }

    chipsBox.innerHTML = '';
    this.selectedModStack.forEach(m => {
      const pill = document.createElement('span');
      pill.className = 'mod-stack-pill';
      pill.innerHTML = `<span>${escapeHtml(m.title)}</span><button type="button" aria-label="Remove">&times;</button>`;
      pill.querySelector('button').addEventListener('click', () => this.removeModFromStack(m.project_id));
      chipsBox.appendChild(pill);
    });

    const plan = this.resolvedModStack;
    if (warnBox) {
      const issues = [];
      if (plan && plan.conflicts) plan.conflicts.forEach(c => issues.push(c.reason));
      if (plan && plan.missing) plan.missing.forEach(m => issues.push(`${m.title}: ${m.reason}`));
      if (issues.length > 0) {
        warnBox.innerHTML = issues.map(i => `<div>${escapeHtml(i)}</div>`).join('');
        warnBox.style.display = 'block';
      } else {
        warnBox.style.display = 'none';
      }
    }

    if (depsBox) {
      const deps = (plan && plan.auto_dependencies) || [];
      if (deps.length > 0) {
        depsBox.innerHTML = deps
          .map(d => `<span class="modpack-loader-tag">+ ${escapeHtml(d.project_title || d.filename)}</span>`)
          .join('');
        depsBox.style.display = 'flex';
      } else {
        depsBox.style.display = 'none';
      }
    }

    if (ramPill) {
      const rInfo = (plan && plan.recommended_ram) || { min_ram: '2G', max_ram: '4G', min_recommended_gb: 3, recommended_gb: 4 };
      const minG = Number(rInfo.min_recommended_gb || 3);
      const recG = Number(rInfo.recommended_gb || minG);
      const lbl = recG > minG ? `${minG}–${recG}` : `${minG}`;
      ramPill.textContent = I18n.fmt('t_install_mp_ram_min_rec', [lbl]);
      ramPill.style.display = 'inline-block';
      this.updateModpackRamHint(rInfo);
    }

    if (!this.isLocked && !this.isInstalling) {
      const totalFiles = (plan && plan.total_files) || this.selectedModStack.length;
      this._setInstallButtonText(I18n.fmt('t_install_mp_btn_install_stack', [totalFiles]));
    }
  },

  async selectModpack(projectId) {
    this.pendingMrpackFile = null;
    const panel = document.getElementById('modpack-selected-panel');
    const verSel = document.getElementById('modpack-version-select');
    const verCtrls = document.getElementById('modpack-version-controls');
    if (panel) panel.style.display = 'block';
    if (verCtrls) verCtrls.style.display = 'grid';
    if (verSel) {
      verSel.innerHTML = `<option value="">${I18n.t('t_install_loading_versions')}</option>`;
      verSel.disabled = true;
    }

    document.querySelectorAll('.modpack-card').forEach(c => {
      c.classList.toggle('selected', c.getAttribute('data-project-id') === projectId);
    });

    try {
      const res = await fetch(`/api/installer/modpacks/project/${encodeURIComponent(projectId)}`);
      const data = await window.readApiJson(res, 'Error');
      const proj = data.project || {};
      const versions = data.versions || [];

      this.selectedModpack = proj;
      this.selectedModpackVersions = versions;

      const iconEl = document.getElementById('modpack-selected-icon');
      const titleEl = document.getElementById('modpack-selected-title');
      const subEl = document.getElementById('modpack-selected-subtitle');
      const badgeEl = document.getElementById('modpack-selected-source-badge');
      const urlEl = document.getElementById('modpack-selected-url');

      if (iconEl) {
        if (proj.icon_url) {
          iconEl.src = proj.icon_url;
          iconEl.style.display = 'block';
        } else {
          iconEl.style.display = 'none';
        }
      }
      if (titleEl) titleEl.textContent = proj.title || projectId;
      if (subEl) subEl.textContent = proj.description || '';
      if (badgeEl) badgeEl.textContent = proj.project_type === 'mod' ? 'Modrinth Mod' : 'Modrinth Modpack';
      if (urlEl) {
        urlEl.href = proj.url || 'https://modrinth.com';
        urlEl.style.display = 'inline-flex';
      }

      const nameInput = document.getElementById('installer-server-name');
      if (nameInput && (!nameInput.value.trim() || nameInput.value.trim() === 'Mi Servidor Dockraft')) {
        nameInput.value = proj.title || 'Mi Servidor Dockraft';
      }

      if (verSel) {
        verSel.innerHTML = '';
        versions.slice(0, 25).forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.id;
          const mcs = (v.game_versions || []).slice(-2).join(', ');
          const ldrs = (v.loaders || []).join('/');
          opt.textContent = `${v.name || v.version_number} [${ldrs}${mcs ? ' · ' + mcs : ''}]`;
          verSel.appendChild(opt);
        });
        verSel.disabled = versions.length === 0;
      }

      await this.onModpackVersionChange();
    } catch (e) {
      App.showToast(I18n.fmt('t_install_mp_err_search', [e.message]), 'danger');
    }
  },

  async onModpackVersionChange() {
    const verSel = document.getElementById('modpack-version-select');
    const vid = verSel ? verSel.value : '';
    const vObj = (this.selectedModpackVersions || []).find(v => v.id === vid);
    const ldrGroup = document.getElementById('modpack-mod-loader-group');
    const mcGroup = document.getElementById('modpack-mod-mc-group');
    const ldrSel = document.getElementById('modpack-mod-loader-select');
    const mcSel = document.getElementById('modpack-mod-mc-select');

    const isModMode = this.selectedModpack && this.selectedModpack.project_type === 'mod';
    if (isModMode && vObj) {
      if (ldrGroup && ldrSel) {
        ldrSel.innerHTML = '';
        (vObj.loaders || []).forEach(l => {
          const opt = document.createElement('option');
          opt.value = l;
          opt.textContent = l.toUpperCase();
          ldrSel.appendChild(opt);
        });
        ldrGroup.style.display = (vObj.loaders || []).length > 0 ? 'block' : 'none';
      }
      if (mcGroup && mcSel) {
        mcSel.innerHTML = '';
        const gvs = [...(vObj.game_versions || [])].reverse();
        gvs.forEach(gv => {
          const opt = document.createElement('option');
          opt.value = gv;
          opt.textContent = gv;
          mcSel.appendChild(opt);
        });
        mcGroup.style.display = gvs.length > 0 ? 'block' : 'none';
      }
    } else {
      if (ldrGroup) ldrGroup.style.display = 'none';
      if (mcGroup) mcGroup.style.display = 'none';
    }

    await this.loadModpackRequirements();
  },

  async loadModpackRequirements() {
    if (!this.selectedModpack) return;
    const verSel = document.getElementById('modpack-version-select');
    const vid = verSel ? verSel.value : '';
    if (!vid) return;

    const reqMc = document.getElementById('modpack-req-mc');
    const reqLoader = document.getElementById('modpack-req-loader');
    const reqJava = document.getElementById('modpack-req-java');
    const reqRam = document.getElementById('modpack-req-ram');
    const reqDeps = document.getElementById('modpack-req-deps');
    const depsBox = document.getElementById('modpack-req-deps-list');

    if (reqDeps) reqDeps.textContent = I18n.t('t_install_mp_inspecting') || 'Analizando...';
    if (depsBox) depsBox.style.display = 'none';

    try {
      const qs = new URLSearchParams();
      if (this.selectedModpack.project_type === 'mod') {
        const ldrSel = document.getElementById('modpack-mod-loader-select');
        const mcSel = document.getElementById('modpack-mod-mc-select');
        if (ldrSel && ldrSel.value) qs.set('loader', ldrSel.value);
        if (mcSel && mcSel.value) qs.set('mc_version', mcSel.value);
      }

      const url = `/api/installer/modpacks/project/${encodeURIComponent(this.selectedModpack.project_id)}/version/${encodeURIComponent(vid)}/requirements?${qs.toString()}`;
      const res = await fetch(url);
      const reqs = await window.readApiJson(res, 'Error');
      this.selectedModpackRequirements = reqs;

      if (reqMc) reqMc.textContent = reqs.mc_version || '--';
      if (reqLoader) reqLoader.textContent = (reqs.loader || '--').toUpperCase();
      if (reqJava) {
        reqJava.textContent = reqs.recommended_java ? `Java ${reqs.recommended_java}` : '--';
        if (reqs.recommended_java) {
          const selectJava = document.getElementById('installer-java-select');
          if (selectJava && this.runtimes.length > 0) {
            const match = this.runtimes.find(r => r.version === reqs.recommended_java);
            if (match) selectJava.value = match.path;
          }
        }
      }

      const rInfo = reqs.recommended_ram || { min_ram: '2G', max_ram: '4G', min_recommended_gb: 4, recommended_gb: 4 };
      const minG = Number(rInfo.min_recommended_gb || 4);
      const recG = Number(rInfo.recommended_gb || minG);
      if (reqRam) {
        reqRam.textContent = recG > minG ? `${minG}–${recG} GB` : `${minG} GB`;
      }
      this.updateModpackRamHint(rInfo);

      if (reqs.project_type === 'modpack') {
        const mb = reqs.pack_size_bytes ? `${(reqs.pack_size_bytes / (1024 * 1024)).toFixed(1)} MB` : '.mrpack';
        if (reqDeps) reqDeps.textContent = I18n.fmt('t_install_mp_req_mrpack_auto', [mb]);
        if (depsBox) depsBox.style.display = 'none';
      } else {
        const deps = reqs.dependencies || [];
        if (reqDeps) {
          reqDeps.textContent = deps.length > 0
            ? I18n.fmt('t_install_mp_req_deps_count', [deps.length])
            : I18n.t('t_install_mp_req_deps_none');
        }
        if (depsBox) {
          if (deps.length > 0) {
            depsBox.innerHTML = deps
              .map(d => `<span class="modpack-loader-tag">${escapeHtml(d.project_title || d.filename)} (${escapeHtml(d.version_number || '')})</span>`)
              .join('');
            depsBox.style.display = 'flex';
          } else {
            depsBox.style.display = 'none';
          }
        }
      }
    } catch (e) {
      if (reqDeps) reqDeps.textContent = e.message;
    }
  },

  onLocalMrpackSelected(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.mrpack')) {
      App.showToast('El archivo debe tener extensión .mrpack', 'danger');
      return;
    }
    this.pendingMrpackFile = file;
    this.selectedModpack = null;
    this.selectedModpackRequirements = null;
    document.querySelectorAll('.modpack-card').forEach(c => c.classList.remove('selected'));

    const panel = document.getElementById('modpack-selected-panel');
    const verCtrls = document.getElementById('modpack-version-controls');
    const iconEl = document.getElementById('modpack-selected-icon');
    const titleEl = document.getElementById('modpack-selected-title');
    const subEl = document.getElementById('modpack-selected-subtitle');
    const badgeEl = document.getElementById('modpack-selected-source-badge');
    const urlEl = document.getElementById('modpack-selected-url');
    const depsBox = document.getElementById('modpack-req-deps-list');

    if (panel) panel.style.display = 'block';
    if (verCtrls) verCtrls.style.display = 'none';
    if (iconEl) iconEl.style.display = 'none';
    if (urlEl) urlEl.style.display = 'none';
    if (depsBox) depsBox.style.display = 'none';

    if (titleEl) titleEl.textContent = file.name;
    if (subEl) subEl.textContent = I18n.t('t_install_mp_local_mrpack_hint');
    if (badgeEl) badgeEl.textContent = '.mrpack Local';

    const mb = `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
    const setTxt = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };
    setTxt('modpack-req-mc', 'Auto (.mrpack)');
    setTxt('modpack-req-loader', 'Auto (.mrpack)');
    setTxt('modpack-req-java', 'Auto');
    const localRam = file.size >= 35 * 1024 * 1024
      ? { min_ram: '4G', max_ram: '8G', min_recommended_gb: 6, recommended_gb: 8 }
      : (file.size >= 12 * 1024 * 1024
        ? { min_ram: '3G', max_ram: '6G', min_recommended_gb: 4, recommended_gb: 6 }
        : { min_ram: '2G', max_ram: '4G', min_recommended_gb: 4, recommended_gb: 4 });
    setTxt(
      'modpack-req-ram',
      localRam.recommended_gb > localRam.min_recommended_gb
        ? `${localRam.min_recommended_gb}–${localRam.recommended_gb} GB`
        : `${localRam.min_recommended_gb} GB`
    );
    this.updateModpackRamHint(localRam);
    setTxt('modpack-req-deps', mb);
  },

  async startModpackInstallation() {
    if (this.isLocked) {
      App.showToast(I18n.t('t_install_err_blocked'), 'danger');
      return;
    }
    const isStackMode = this.modpackType === 'mod' && !this.pendingMrpackFile;
    if (isStackMode) {
      if (!this.selectedModStack || this.selectedModStack.length === 0) {
        App.showToast(I18n.t('t_install_mp_stack_empty'), 'danger');
        return;
      }
      if (this.resolvedModStack && !this.resolvedModStack.can_install) {
        App.showToast(I18n.t('t_install_mp_err_select'), 'danger');
        return;
      }
    } else if (!this.pendingMrpackFile && !this.selectedModpack) {
      App.showToast(I18n.t('t_install_mp_err_select'), 'danger');
      return;
    }
    if (this.isInstalling) return;
    this.isInstalling = true;

    const minRam = document.getElementById('install-min-ram')?.value.trim() || '2G';
    const maxRam = document.getElementById('install-max-ram')?.value.trim() || '4G';
    const aikar = document.getElementById('install-aikar-flags')?.checked ?? true;
    const serverName = document.getElementById('installer-server-name')?.value.trim() || 'Mi Servidor Dockraft';
    const cpuCores = parseInt(document.getElementById('install-cpu-cores')?.value || '2', 10);
    const diskLimit = parseFloat(document.getElementById('install-disk-limit')?.value || '10');

    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }

    this._activeUpdateMode = 'install';
    const btn = document.getElementById('btn-install-server');
    if (btn) btn.disabled = true;
    this._setInstallButtonText(I18n.t('t_install_btn_downloading'));

    const progressBox = document.getElementById('install-progress-box');
    const progressBar = document.getElementById('install-progress-bar');
    const progressText = document.getElementById('install-progress-text');
    if (progressBox) progressBox.style.display = 'block';
    if (progressBar) progressBar.style.width = '2%';
    if (progressText) progressText.textContent = I18n.t('t_install_status_preparing');

    try {
      let res;
      if (this.pendingMrpackFile) {
        const form = new FormData();
        form.append('file', this.pendingMrpackFile);
        form.append('server_name', serverName);
        form.append('min_ram', minRam);
        form.append('max_ram', maxRam);
        form.append('aikar_flags', aikar ? 'true' : 'false');
        form.append('cpu_cores', String(cpuCores));
        form.append('disk_limit_gb', String(diskLimit));
        form.append('force', this.allowForce ? 'true' : 'false');
        res = await fetch('/api/installer/modpacks/upload-mrpack', { method: 'POST', body: form });
      } else if (isStackMode) {
        const payload = {
          project_ids: this.selectedModStack.map(m => m.project_id),
          loader: document.getElementById('mod-builder-loader')?.value || 'fabric',
          mc_version: document.getElementById('mod-builder-mc-version')?.value || '1.21.1',
          allow_beta: Boolean(document.getElementById('modpack-allow-beta')?.checked),
          server_name: serverName,
          min_ram: minRam,
          max_ram: maxRam,
          aikar_flags: aikar,
          cpu_cores: cpuCores,
          disk_limit_gb: diskLimit,
          force: Boolean(this.allowForce)
        };
        res = await fetch('/api/installer/modpacks/install-stack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        const verSel = document.getElementById('modpack-version-select');
        const versionId = verSel ? verSel.value : '';
        if (!versionId) {
          throw new Error(I18n.t('t_install_err_select_version'));
        }
        const payload = {
          source: 'modrinth',
          project_type: 'modpack',
          project_id: this.selectedModpack.project_id,
          version_id: versionId,
          server_name: serverName,
          min_ram: minRam,
          max_ram: maxRam,
          aikar_flags: aikar,
          cpu_cores: cpuCores,
          disk_limit_gb: diskLimit,
          force: Boolean(this.allowForce)
        };
        res = await fetch('/api/installer/modpacks/install', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      await window.readApiJson(res, I18n.t('t_install_err_install_failed'));
      App.showToast(I18n.t('t_install_toast_download_bg'), 'success');

      this._pollInstallerProgress({
        barEl: progressBar,
        textEl: progressText,
        defaultStatus: 'downloading_modpack',
        onComplete: async () => {
          this.isInstalling = false;
          this._activeUpdateMode = null;
          this.pendingMrpackFile = null;
          App.showToast(I18n.t('t_install_toast_installed_ok'), 'success');
          await this.checkLockState();
          setTimeout(() => {
            App.switchTab('console');
          }, 1200);
        },
        onError: (statusMsg) => {
          this.isInstalling = false;
          this._activeUpdateMode = null;
          if (btn) btn.disabled = false;
          this._setInstallButtonText(I18n.t('t_install_btn_install_modpack') || I18n.t('t_install_btn_install'));
          if (statusMsg) {
            App.showToast(I18n.fmt('t_install_err_download', [statusMsg]), 'danger');
          }
        }
      });
    } catch (e) {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
      this.isInstalling = false;
      this._activeUpdateMode = null;
      App.showToast(e.message, 'danger');
      if (btn) btn.disabled = false;
      this._setInstallButtonText(I18n.t('t_install_btn_install_modpack') || I18n.t('t_install_btn_install'));
      if (progressBox) progressBox.style.display = 'none';
    }
  },

  // --- Installed Modpack Updater & Installed Mods Manager ---
  async loadModpackUpdateStatus() {
    const card = document.getElementById('installer-modpack-update-card');
    if (!card) return;
    const allowBeta = Boolean(document.getElementById('modpack-upd-allow-beta')?.checked);
    try {
      const res = await fetch(`/api/installer/modpacks/update-status?allow_beta=${allowBeta}`);
      if (!res.ok) return;
      const data = await res.json();
      this.modpackUpdateData = data;
      this.renderModpackUpdateCard(data);
    } catch (e) {
      console.warn('[Installer] Could not load modpack update status:', e);
    }
  },

  renderModpackUpdateCard(data) {
    const card = document.getElementById('installer-modpack-update-card');
    if (!card || !data || !data.has_modpack) {
      if (card) {
        card.classList.add('d-none');
        card.style.display = 'none';
      }
      return;
    }

    card.classList.remove('d-none');
    card.style.display = 'block';

    const icon = document.getElementById('modpack-upd-icon');
    if (icon) {
      if (data.icon_url) {
        icon.src = data.icon_url;
        icon.style.display = 'block';
      } else {
        icon.style.display = 'none';
      }
    }
    const nameEl = document.getElementById('modpack-upd-name');
    if (nameEl) nameEl.textContent = data.name || 'Modpack';
    const envEl = document.getElementById('modpack-upd-env-badge');
    if (envEl) envEl.textContent = `${String(data.current_loader || '').toUpperCase()} · ${data.current_mc_version || ''}`;
    const curEl = document.getElementById('modpack-upd-current-ver');
    if (curEl) curEl.textContent = data.current_version_name || data.current_version_id || '--';

    const sel = document.getElementById('modpack-update-version-select');
    if (sel) {
      sel.innerHTML = '';
      (data.versions || []).forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.id;
        const betaTag = v.version_type !== 'release' ? ` [${v.version_type.toUpperCase()}]` : '';
        const curTag = v.is_current ? ` (${I18n.t('t_install_current_ver_tag') || 'Actual'})` : '';
        opt.textContent = `${v.version_number || v.name} · MC ${v.target_mc_version}${betaTag}${curTag}`;
        sel.appendChild(opt);
      });
      if (data.latest_version && data.latest_version.id) {
        sel.value = data.latest_version.id;
      }
    }

    const notice = document.getElementById('modpack-upd-notice-banner');
    const noticeTxt = document.getElementById('modpack-upd-notice-text');
    if (notice && noticeTxt) {
      if (data.update_available && data.latest_version) {
        const lv = data.latest_version;
        let msg = I18n.fmt('t_install_mp_upd_available', [lv.version_number || lv.name, String(lv.target_loader || '').toUpperCase(), lv.target_mc_version || '']);
        if (lv.changes_mc_version) {
          msg += ' — ' + I18n.fmt('t_install_mp_upd_mc_warn', [data.current_mc_version, lv.target_mc_version]);
        }
        noticeTxt.textContent = msg;
        notice.style.display = 'block';
      } else {
        noticeTxt.textContent = I18n.t('t_install_mp_upd_up_to_date');
        notice.style.display = 'block';
      }
    }
  },

  async startModpackUpdate() {
    if (this.isInstalling) {
      App.showToast(I18n.t('t_install_toast_already_busy'), 'info');
      return;
    }
    const sel = document.getElementById('modpack-update-version-select');
    const versionId = sel ? sel.value : '';
    if (!versionId) return;
    const allowBeta = Boolean(document.getElementById('modpack-upd-allow-beta')?.checked);
    const data = this.modpackUpdateData || {};
    const verObj = (data.versions || []).find(v => v.id === versionId) || {};
    const labelVer = verObj.version_number || verObj.name || versionId;

    const ok = await App.confirm({
      title: I18n.t('t_install_mp_btn_update_pack'),
      message: I18n.fmt('t_install_mods_confirm_update_pack', [data.name || 'Modpack', labelVer]),
      confirmText: I18n.t('t_install_mp_btn_update_pack'),
      type: verObj.changes_mc_version ? 'warning' : 'info'
    });
    if (!ok) return;

    this.isInstalling = true;
    this._setUpdateBusy(true, 'version');

    const pBox = document.getElementById('update-progress-box');
    const pBar = document.getElementById('update-progress-bar');
    const pText = document.getElementById('update-progress-text');
    const pPct = document.getElementById('update-progress-percent');
    if (pBox) pBox.style.display = 'block';
    if (pBar) pBar.style.width = '2%';
    if (pPct) pPct.textContent = '2%';
    if (pText) pText.textContent = I18n.t('t_install_status_downloading_modpack');

    try {
      const res = await fetch('/api/installer/modpacks/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_id: versionId, allow_beta: allowBeta, update_custom_mods: true })
      });
      await window.readApiJson(res, I18n.t('t_install_err_update_start'));
      App.showToast(I18n.t('t_install_toast_update_started'), 'info');

      this._pollInstallerProgress({
        barEl: pBar,
        pctEl: pPct,
        textEl: pText,
        defaultStatus: 'downloading_modpack',
        onComplete: async () => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
          await this.checkLockState();
        },
        onError: (statusMsg) => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          if (statusMsg) App.showToast(I18n.fmt('t_install_err_update_fail', [statusMsg]), 'danger');
        }
      });
    } catch (e) {
      this.isInstalling = false;
      this._setUpdateBusy(false);
      if (pBox) pBox.style.display = 'none';
      App.showToast(e.message, 'danger');
    }
  },

  async loadInstalledMods(checkUpdates = true) {
    const listEl = document.getElementById('installed-mods-list');
    if (!listEl) return;
    const allowBeta = Boolean(document.getElementById('mods-upd-allow-beta')?.checked);

    try {
      const res = await fetch(`/api/installer/mods/installed?check_updates=${checkUpdates}&allow_beta=${allowBeta}`);
      if (!res.ok) {
        listEl.innerHTML = `<div style="text-align:center;padding:14px;font-size:0.82rem;color:var(--text-muted);">${escapeHtml(I18n.t('t_install_mods_load_error'))}</div>`;
        return;
      }
      const data = await res.json();
      this.installedModsData = data;
      this.renderInstalledMods(data);
    } catch (e) {
      console.warn('[Installer] Could not load installed mods:', e);
      listEl.innerHTML = `<div style="text-align:center;padding:14px;font-size:0.82rem;color:var(--text-muted);">${escapeHtml(I18n.t('t_install_mods_load_error'))}</div>`;
    }
  },

  renderInstalledMods(data) {
    const listEl = document.getElementById('installed-mods-list');
    const countBadge = document.getElementById('mods-count-badge');
    const updBadge = document.getElementById('mods-updates-badge');
    const btnUpdAll = document.getElementById('btn-update-all-mods');
    const conflictBox = document.getElementById('mods-conflict-banner');
    if (!listEl || !data) return;

    const mods = data.mods || [];
    if (countBadge) countBadge.textContent = `${mods.length} mods`;

    const updCount = Number(data.updates_available_count || 0);
    if (updBadge) {
      updBadge.textContent = I18n.fmt('t_install_mods_updates_count', [updCount]);
      updBadge.style.display = updCount > 0 ? 'inline-block' : 'none';
    }
    if (btnUpdAll) {
      btnUpdAll.style.display = updCount > 0 ? 'inline-flex' : 'none';
    }

    if (conflictBox) {
      const conflicts = data.conflicts || [];
      if (conflicts.length > 0) {
        conflictBox.innerHTML = conflicts.map(c => `<div>${escapeHtml(c.reason)}</div>`).join('');
        conflictBox.style.display = 'block';
      } else {
        conflictBox.style.display = 'none';
      }
    }

    if (mods.length === 0) {
      listEl.innerHTML = `<div style="text-align: center; padding: 14px; font-size: 0.82rem; color: var(--text-muted);">${escapeHtml(I18n.t('t_install_mods_empty'))}</div>`;
      return;
    }

    listEl.innerHTML = '';
    mods.forEach(m => {
      const row = document.createElement('div');
      row.className = `installed-mod-row${m.enabled ? '' : ' disabled'}`;

      const iconHtml = m.icon_url
        ? `<img src="${escapeHtml(m.icon_url)}" alt="" style="width:28px;height:28px;border-radius:6px;object-fit:cover;">`
        : `<div style="width:28px;height:28px;border-radius:6px;background:var(--bg-subtle);display:flex;align-items:center;justify-content:center;font-size:0.75rem;color:var(--text-muted);">J</div>`;

      const originLabel = m.origin === 'modpack' ? I18n.t('t_install_mods_origin_modpack') : I18n.t('t_install_mods_origin_manual');
      const verBadge = m.version_number ? `<span class="mod-origin-badge">${escapeHtml(m.version_number)}</span>` : '';
      const updTag = m.update_available
        ? `<span class="mod-update-badge">${escapeHtml(m.version_number || '')} &rarr; ${escapeHtml(m.latest_version_number || '')}</span>`
        : '';

      row.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;min-width:0;flex:1 1 220px;">
          ${iconHtml}
          <div style="min-width:0;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <strong style="font-size:0.84rem;color:var(--text-main);">${escapeHtml(m.title)}</strong>
              <span class="mod-origin-badge">${escapeHtml(originLabel)}</span>
              ${verBadge}
              ${updTag}
            </div>
            <div style="font-size:0.74rem;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              ${escapeHtml(m.filename)}${m.recognized ? '' : ' · ' + escapeHtml(I18n.t('t_install_mods_unrecognized'))}
            </div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;"></div>
      `;

      const actionsEl = row.lastElementChild;
      if (m.update_available) {
        const bUpd = document.createElement('button');
        bUpd.type = 'button';
        bUpd.className = 'btn btn-primary';
        bUpd.style.cssText = 'font-size:0.74rem;padding:3px 9px;';
        bUpd.textContent = I18n.t('t_install_mods_btn_update_one');
        bUpd.addEventListener('click', () => this.updateInstalledMods([m.filename]));
        actionsEl.appendChild(bUpd);
      }

      const bTog = document.createElement('button');
      bTog.type = 'button';
      bTog.className = 'btn btn-outline';
      bTog.style.cssText = 'font-size:0.74rem;padding:3px 9px;';
      bTog.textContent = m.enabled ? I18n.t('t_install_mods_btn_disable') : I18n.t('t_install_mods_btn_enable');
      bTog.addEventListener('click', () => this.toggleInstalledMod(m.filename));
      actionsEl.appendChild(bTog);

      const bDel = document.createElement('button');
      bDel.type = 'button';
      bDel.className = 'btn btn-outline';
      bDel.style.cssText = 'font-size:0.74rem;padding:3px 9px;color:#f85149;border-color:rgba(248,81,73,0.35);';
      bDel.textContent = I18n.t('t_install_mods_btn_delete');
      bDel.addEventListener('click', () => this.deleteInstalledMod(m.filename));
      actionsEl.appendChild(bDel);

      listEl.appendChild(row);
    });
  },

  openAddModModal() {
    const modal = document.getElementById('add-mod-modal');
    if (!modal) return;
    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const badge = document.getElementById('add-mod-env-badge');
    if (badge) badge.textContent = `${String(data.server_type || '').toUpperCase()} · ${data.current_version || ''}`;
    modal.classList.add('open');
    modal.classList.add('show');
    modal.style.display = 'flex';
    modal.onclick = (e) => {
      if (e.target === modal) this.closeAddModModal();
    };
    if (this._addModEscHandler) {
      window.removeEventListener('keydown', this._addModEscHandler);
    }
    this._addModEscHandler = (e) => {
      if (e.key === 'Escape') this.closeAddModModal();
    };
    window.addEventListener('keydown', this._addModEscHandler);
    this.searchCompatibleModsForServer();
  },

  closeAddModModal() {
    const modal = document.getElementById('add-mod-modal');
    if (modal) {
      modal.classList.remove('open');
      modal.classList.remove('show');
      modal.style.display = 'none';
    }
    if (this._addModEscHandler) {
      window.removeEventListener('keydown', this._addModEscHandler);
      this._addModEscHandler = null;
    }
  },

  async searchCompatibleModsForServer() {
    const resultsEl = document.getElementById('add-mod-results');
    const q = document.getElementById('add-mod-search-input')?.value.trim() || '';
    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const ldr = String(data.server_type || '').toLowerCase();
    const mc = String(data.current_version || '');
    if (!resultsEl) return;

    resultsEl.innerHTML = `<div style="font-size:0.82rem;color:var(--text-muted);">${escapeHtml(I18n.t('t_install_mp_searching'))}</div>`;
    try {
      const qs = new URLSearchParams({ q, project_type: 'mod', limit: '10' });
      if (ldr) qs.set('loader', ldr);
      if (mc) qs.set('game_version', mc);
      const res = await fetch(`/api/installer/modpacks/search?${qs.toString()}`);
      const d = await window.readApiJson(res, 'Error');
      const hits = d.hits || [];
      if (hits.length === 0) {
        resultsEl.innerHTML = `<div style="font-size:0.82rem;color:var(--text-muted);">${escapeHtml(I18n.t('t_install_mp_empty'))}</div>`;
        return;
      }
      resultsEl.innerHTML = '';
      hits.forEach(h => {
        const row = document.createElement('div');
        row.className = 'mod-add-row';
        row.innerHTML = `
          <div style="min-width:0;flex:1;">
            <div style="font-weight:600;font-size:0.86rem;color:var(--text-main);">${escapeHtml(h.title)}</div>
            <div style="font-size:0.76rem;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(h.description || '')}</div>
          </div>
          <button type="button" class="btn btn-primary" style="font-size:0.76rem;padding:4px 10px;white-space:nowrap;">+ ${escapeHtml(I18n.t('t_install_mods_btn_install_one') || 'Instalar')}</button>
        `;
        row.querySelector('button').addEventListener('click', (ev) => this.installCompatibleMod(h.project_id, ev.target));
        resultsEl.appendChild(row);
      });
    } catch (e) {
      resultsEl.innerHTML = `<div style="font-size:0.82rem;color:#f85149;">${escapeHtml(e.message)}</div>`;
    }
  },

  async installCompatibleMod(projectId, btnEl) {
    const allowBeta = Boolean(document.getElementById('add-mod-allow-beta')?.checked);
    if (btnEl) btnEl.disabled = true;
    try {
      const res = await fetch('/api/installer/mods/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId, allow_beta: allowBeta })
      });
      const d = await window.readApiJson(res, 'Error');
      App.showToast(I18n.fmt('t_install_mods_toast_added', [d.title || projectId]), 'success');
      this.closeAddModModal();
      await this.loadInstalledMods(true);
    } catch (e) {
      App.showToast(e.message, 'danger');
    } finally {
      if (btnEl) btnEl.disabled = false;
    }
  },

  async updateInstalledMods(filenames = null) {
    if (this.isInstalling) {
      App.showToast(I18n.t('t_install_toast_already_busy'), 'info');
      return;
    }
    const allowBeta = Boolean(document.getElementById('mods-upd-allow-beta')?.checked);
    const count = filenames ? filenames.length : Number((this.installedModsData && this.installedModsData.updates_available_count) || 0);
    const ok = await App.confirm({
      title: I18n.t('t_install_mods_btn_update_all'),
      message: I18n.fmt('t_install_mods_confirm_update_mods', [Math.max(1, count)]),
      confirmText: I18n.t('t_install_mods_btn_update_all'),
      type: 'info'
    });
    if (!ok) return;

    this.isInstalling = true;
    this._setUpdateBusy(true, 'version');
    const pBox = document.getElementById('update-progress-box');
    const pBar = document.getElementById('update-progress-bar');
    const pText = document.getElementById('update-progress-text');
    const pPct = document.getElementById('update-progress-percent');
    if (pBox) pBox.style.display = 'block';
    if (pBar) pBar.style.width = '5%';
    if (pPct) pPct.textContent = '5%';
    if (pText) pText.textContent = I18n.t('t_install_status_downloading_mods');

    try {
      const res = await fetch('/api/installer/mods/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames, allow_beta: allowBeta })
      });
      await window.readApiJson(res, 'Error');
      this._pollInstallerProgress({
        barEl: pBar,
        pctEl: pPct,
        textEl: pText,
        defaultStatus: 'downloading_mods',
        onComplete: async () => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          App.showToast(I18n.t('t_install_mods_toast_updated'), 'success');
          await this.loadInstalledMods(true);
        },
        onError: (statusMsg) => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          if (statusMsg) App.showToast(I18n.fmt('t_install_err_update_fail', [statusMsg]), 'danger');
        }
      });
    } catch (e) {
      this.isInstalling = false;
      this._setUpdateBusy(false);
      if (pBox) pBox.style.display = 'none';
      App.showToast(e.message, 'danger');
    }
  },

  async toggleInstalledMod(filename) {
    try {
      const res = await fetch('/api/installer/mods/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
      });
      await window.readApiJson(res, 'Error');
      App.showToast(I18n.t('t_install_mods_toast_toggled'), 'info');
      await this.loadInstalledMods(true);
    } catch (e) {
      App.showToast(e.message, 'danger');
    }
  },

  async deleteInstalledMod(filename) {
    const ok = await App.confirm({
      title: I18n.t('t_install_mods_btn_delete'),
      message: I18n.fmt('t_install_mods_confirm_delete', [filename]),
      confirmText: I18n.t('t_install_mods_btn_delete'),
      danger: true
    });
    if (!ok) return;
    try {
      const res = await fetch(`/api/installer/mods/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      await window.readApiJson(res, 'Error');
      App.showToast(I18n.t('t_install_mods_toast_deleted'), 'success');
      await this.loadInstalledMods(true);
    } catch (e) {
      App.showToast(e.message, 'danger');
    }
  },

  async checkMcUpgradeModCompatibility(targetMc) {
    const box = document.getElementById('modded-mc-compat-box');
    const summary = document.getElementById('modded-mc-compat-summary');
    if (!box || !summary) return;

    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const ldr = String(data.server_type || '').toLowerCase();
    const curVer = String(data.current_version || '').trim();
    const isModded = ['fabric', 'neoforge', 'forge', 'quilt'].includes(ldr);
    if (!isModded || !targetMc || targetMc === curVer) {
      box.style.display = 'none';
      return;
    }

    box.style.display = 'block';
    summary.textContent = I18n.fmt('t_install_mods_compat_checking', [targetMc]);
    try {
      const allowBeta = Boolean(document.getElementById('mods-upd-allow-beta')?.checked);
      const res = await fetch(`/api/installer/mods/check-compatibility?target_mc=${encodeURIComponent(targetMc)}&allow_beta=${allowBeta}`);
      const c = await window.readApiJson(res, 'Error');
      const okCount = (c.compatible || []).length;
      const badCount = (c.incompatible || []).length + (c.unknown || []).length;
      if (badCount === 0) {
        summary.textContent = I18n.fmt('t_install_mods_compat_all_ok', [okCount, targetMc]);
      } else {
        const names = (c.incompatible || []).slice(0, 4).map(x => x.title).join(', ');
        summary.textContent = I18n.fmt('t_install_mods_compat_warn', [okCount, badCount, targetMc, names || '--']);
      }
    } catch (e) {
      summary.textContent = e.message;
    }
  },

  // --- Dedicated Server Engine Build Modal & Operations ---
  _buildCommitMap: {},
  _buildEscHandler: null,

  _pollInstallerProgress({ barEl, pctEl, textEl, defaultStatus = 'downloading', onComplete, onError }) {
    if (this.pollingInterval) clearInterval(this.pollingInterval);
    let consecutiveErrors = 0;
    let sawActive = false;

    this.pollingInterval = setInterval(async () => {
      try {
        const pRes = await fetch('/api/installer/progress');
        if (!pRes.ok) {
          throw new Error(`HTTP ${pRes.status}`);
        }
        const pData = await pRes.json();
        consecutiveErrors = 0;

        const pct = Number(pData.percent || 0);
        const st = String(pData.status || defaultStatus);
        const stNorm = st.trim().toLowerCase();
        const isActiveNow = Boolean(
          pData.is_active ||
          pData.is_downloading ||
          (stNorm !== 'idle' && stNorm !== 'completed' && !stNorm.startsWith('error'))
        );
        if (isActiveNow) {
          sawActive = true;
        }

        if (barEl) barEl.style.width = `${pct}%`;
        if (pctEl) pctEl.textContent = `${pct}%`;

        const detailMsg = pData.detail ? String(pData.detail).trim() : '';
        const stText = stNorm === 'idle' && !sawActive
          ? I18n.t('t_install_status_preparing')
          : (detailMsg || this.mapStatusText(st));
        if (textEl) {
          textEl.textContent = (stNorm === 'downloading' || stNorm === 'extracting')
            ? `${stText} (${pct}%)`
            : (detailMsg && pct > 0 && pct < 100 && !detailMsg.includes('%') ? `${stText} (${pct}%)` : stText);
        }

        const isCompleted =
          stNorm === 'completed' ||
          (stNorm === 'idle' && pct >= 100 && !pData.is_downloading && !pData.is_active) ||
          (stNorm === 'idle' && sawActive && !pData.is_downloading && !pData.is_active);

        if (isCompleted) {
          clearInterval(this.pollingInterval);
          this.pollingInterval = null;
          if (barEl) barEl.style.width = '100%';
          if (pctEl) pctEl.textContent = '100%';
          if (textEl) textEl.textContent = I18n.t('t_install_status_completed');
          if (onComplete) await onComplete(pData);
        } else if (stNorm.startsWith('error')) {
          clearInterval(this.pollingInterval);
          this.pollingInterval = null;
          this.isInstalling = false;
          if (onError) onError(st);
        }
      } catch (err) {
        consecutiveErrors += 1;
        if (consecutiveErrors < 5) {
          return;
        }
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
        this.isInstalling = false;
        if (onError) onError(err && err.message ? err.message : null);
      }
    }, 800);
  },

  ensureBuildModal() {
    return document.getElementById('modal-change-build');
  },

  async openBuildModal(targetBuildId) {
    if (this.isInstalling) {
      App.showToast(I18n.t('t_install_toast_already_busy'), 'info');
      return;
    }
    try {
      const modal = this.ensureBuildModal();
      if (!modal) {
        console.error('[Installer] Could not find or instantiate #modal-change-build');
        return;
      }

      // Sanitize targetBuildId if called directly from click event or string with '#'
      let cleanTarget = null;
      if (targetBuildId && typeof targetBuildId !== 'object') {
        const numStr = String(targetBuildId).replace(/\D/g, '');
        if (numStr) cleanTarget = parseInt(numStr, 10);
      }

      const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
      const curVer = String(data.current_version || data.latest_stable || '26.3').trim();
      const curBuild = data.current_build ? parseInt(String(data.current_build).replace(/\D/g, ''), 10) : null;
      const latestBuild = data.latest_build ? parseInt(String(data.latest_build).replace(/\D/g, ''), 10) : null;
      const initialTarget = cleanTarget || latestBuild || curBuild;

      // Fill version
      const mcVerEl = document.getElementById('modal-build-mc-version');
      if (mcVerEl) mcVerEl.textContent = curVer;

      // Fill current build
      const curValEl = document.getElementById('modal-build-current-val');
      if (curValEl) curValEl.textContent = curBuild ? `#${curBuild}` : (I18n.t('t_install_unknown') || 'No detectada');

      // Fill target build display
      const targetDispEl = document.getElementById('modal-build-target-display');
      if (targetDispEl) targetDispEl.textContent = initialTarget ? `#${initialTarget}` : '--';

      const btnApply = document.getElementById('btn-modal-apply-build-text');
      if (btnApply) {
        btnApply.textContent = initialTarget
          ? (I18n.fmt('t_install_btn_update_to_build', [initialTarget]) || `Instalar Build #${initialTarget}`)
          : (I18n.t('t_install_build_modal_btn_install_generic') || 'Instalar Build');
      }

      // Add 'open' class for system pop animation and backdrop display
      modal.classList.add('open');
      modal.classList.add('show');
      modal.style.display = 'flex';

      // Dismiss on backdrop click
      modal.onclick = (e) => {
        if (e.target === modal) this.closeBuildModal();
      };

      // Dismiss on Escape key
      if (this._buildEscHandler) {
        window.removeEventListener('keydown', this._buildEscHandler);
      }
      this._buildEscHandler = (e) => {
        if (e.key === 'Escape') this.closeBuildModal();
      };
      window.addEventListener('keydown', this._buildEscHandler);

      // Show loading spinner
      const spinner = document.getElementById('modal-build-loading-spinner');
      if (spinner) spinner.style.display = 'inline-flex';

      const select = document.getElementById('modal-build-select');
      if (select) {
        select.innerHTML = `<option value="">${I18n.t('t_install_build_modal_loading') || 'Cargando builds disponibles...'}</option>`;
        select.disabled = true;
      }

      this._buildCommitMap = {};

      try {
        const res = await fetch(`/api/installer/builds?version=${encodeURIComponent(curVer)}`);
        if (res.ok) {
          const buildData = await res.json();
          const builds = buildData.builds || [];
          if (select) {
            select.innerHTML = '';
            if (builds.length === 0) {
              select.innerHTML = `<option value="${initialTarget || ''}">Build #${initialTarget || 'Recomendada'}</option>`;
            } else {
              builds.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.id;
                let label = `Build #${b.id}`;
                if (b.channel && b.channel !== 'STABLE' && b.channel !== 'DEFAULT') {
                  label += ` [${b.channel}]`;
                }
                if (b.id === buildData.latest_build || b.id === latestBuild) {
                  label += ` (${I18n.t('t_install_build_modal_recommended') || 'Recomendada'})`;
                } else if (b.id === curBuild) {
                  label += ` (${I18n.t('t_install_current_build_badge') || 'Instalada actual'})`;
                }
                opt.textContent = label;
                select.appendChild(opt);

                if (b.summary) {
                  this._buildCommitMap[b.id] = b.summary;
                }
              });
            }
            select.disabled = false;
            if (initialTarget && builds.some(b => parseInt(b.id, 10) === parseInt(initialTarget, 10))) {
              select.value = String(initialTarget);
            } else if (builds.length > 0) {
              select.value = String(builds[0].id);
            }
            this.onModalBuildChange();
          }
        } else {
          if (select) {
            select.disabled = false;
            if (initialTarget) {
              select.innerHTML = `<option value="${initialTarget}">Build #${initialTarget} (Recomendada)</option>`;
            }
          }
        }
      } catch (e) {
        console.warn('[Installer] Error loading builds:', e);
        if (select) {
          select.disabled = false;
          if (initialTarget) {
            select.innerHTML = `<option value="${initialTarget}">Build #${initialTarget} (Recomendada)</option>`;
          }
        }
      } finally {
        if (spinner) spinner.style.display = 'none';
      }
    } catch (err) {
      console.error('[Installer] Error in openBuildModal:', err);
      if (typeof App !== 'undefined' && App.showToast) {
        App.showToast('Error al abrir compilaciones de build: ' + (err.message || err), 'danger');
      }
    }
  },

  closeBuildModal() {
    const modal = document.getElementById('modal-change-build');
    if (modal) {
      modal.classList.remove('open');
      modal.classList.remove('show');
      modal.style.display = 'none';
    }
    if (this._buildEscHandler) {
      window.removeEventListener('keydown', this._buildEscHandler);
      this._buildEscHandler = null;
    }
  },

  onModalBuildChange() {
    const select = document.getElementById('modal-build-select');
    if (!select) return;
    const val = select.value;
    if (!val) return;

    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const latestBuild = data.latest_build;
    const curBuild = data.current_build;

    const targetDispEl = document.getElementById('modal-build-target-display');
    if (targetDispEl) targetDispEl.textContent = `#${val}`;

    const badgeEl = document.getElementById('modal-build-target-badge');
    if (badgeEl) {
      const parsedVal = parseInt(val, 10);
      if (latestBuild && parsedVal === parseInt(latestBuild, 10)) {
        badgeEl.textContent = I18n.t('t_install_build_modal_recommended') || 'Recomendada';
        badgeEl.style.color = '#3fb950';
      } else if (curBuild && parsedVal === parseInt(curBuild, 10)) {
        badgeEl.textContent = I18n.t('t_install_current_build_badge') || 'Instalada';
        badgeEl.style.color = '#8b949e';
      } else {
        badgeEl.textContent = 'Seleccionada';
        badgeEl.style.color = '#38bdf8';
      }
    }

    const btnApply = document.getElementById('btn-modal-apply-build-text');
    if (btnApply) {
      btnApply.textContent = I18n.fmt('t_install_btn_update_to_build', [val]) || `Instalar Build #${val}`;
    }

    const changeBox = document.getElementById('modal-build-changelog-box');
    const changeText = document.getElementById('modal-build-changelog-text');
    if (this._buildCommitMap && this._buildCommitMap[val]) {
      if (changeBox) changeBox.style.display = 'block';
      if (changeText) changeText.textContent = this._buildCommitMap[val];
    } else {
      if (changeBox) changeBox.style.display = 'none';
    }
  },

  async applyBuildFromModal() {
    if (this.isInstalling) {
      App.showToast(I18n.t('t_install_toast_already_busy'), 'info');
      return;
    }
    const select = document.getElementById('modal-build-select');
    const targetBuild = select ? select.value : null;

    const data = this.updateData || window.__LAST_UPDATE_DATA__ || {};
    const curVer = String(data.current_version || data.latest_stable || '26.3').trim();

    if (!curVer) {
      App.showToast(I18n.t('t_install_err_update_version'), 'danger');
      return;
    }

    // Close the build modal first
    this.closeBuildModal();

    // Now execute the install pipeline with build parameter
    this.isInstalling = true;
    this._setUpdateBusy(true, 'build');

    // Show installer progress box immediately with descriptive phase
    const pBox = document.getElementById('update-progress-box');
    const pBar = document.getElementById('update-progress-bar');
    const pText = document.getElementById('update-progress-text');
    const pPct = document.getElementById('update-progress-percent');
    if (pBox) pBox.style.display = 'block';
    if (pBar) pBar.style.width = '0%';
    if (pText) pText.textContent = targetBuild
      ? (I18n.fmt('t_install_build_toast_started', [targetBuild]) || `Iniciando instalación de Build #${targetBuild}...`)
      : I18n.t('t_install_status_preparing');
    if (pPct) pPct.textContent = '0%';

    App.showToast(targetBuild ? I18n.fmt('t_install_build_toast_started', [targetBuild]) : I18n.t('t_install_toast_update_started'), 'info');

    try {
      const payload = { version: curVer };
      if (targetBuild) {
        const cleanBuild = parseInt(String(targetBuild).replace(/\D/g, ''), 10);
        if (!isNaN(cleanBuild)) {
          payload.build = cleanBuild;
        }
      }
      const res = await fetch('/api/installer/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      await window.readApiJson(res, I18n.t('t_install_err_update_start'));

      this._pollInstallerProgress({
        barEl: pBar,
        pctEl: pPct,
        textEl: pText,
        defaultStatus: 'updating',
        onComplete: () => {
          setTimeout(async () => {
            if (pBox) pBox.style.display = 'none';
            this.isInstalling = false;
            this._setUpdateBusy(false);
            App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
            await this.checkLockState();
          }, 600);
        },
        onError: (statusMsg) => {
          if (pBox) pBox.style.display = 'none';
          this.isInstalling = false;
          this._setUpdateBusy(false);
          if (statusMsg) {
            App.showToast(I18n.fmt('t_install_err_update_fail', [statusMsg]), 'danger');
          }
        }
      });

    } catch (e) {
      this.isInstalling = false;
      this._setUpdateBusy(false);
      if (pBox) pBox.style.display = 'none';
      App.showToast(I18n.fmt('t_install_err_update_fail', [e.message]), 'danger');
    }
  }
};

window.Installer = Installer;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => Installer.init());
} else {
  Installer.init();
}
