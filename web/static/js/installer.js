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
      if (updateCard) {
        this.loadUpdateInfo(this.updateData || window.__INITIAL_STATS__);
        this.updateApplyButtonText();
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
        info.innerHTML = `${I18n.t('t_install_banner_locked_installed_a')} <strong>${escapeHtml(typeName)} ${escapeHtml(ver)}</strong> (<code>${escapeHtml(cfg.server_file || 'server.jar')}</code>)${I18n.t('t_install_banner_locked_installed_b')}`;
      }
      if (btn) {
        btn.disabled = true;
        btn.textContent = I18n.t('t_install_btn_installed_locked');
        btn.className = "btn btn-outline";
      }
      const updateCard = document.getElementById('installer-update-card');
      if (updateCard) {
        updateCard.classList.remove('d-none');
        updateCard.style.display = 'block';
      }
      const isBedrock = (cfg && cfg.server_type || '').toLowerCase() === 'bedrock';
      const pluginsSub = document.getElementById('update-plugins-subsection');
      if (pluginsSub) {
        if (isBedrock) {
          pluginsSub.classList.add('d-none');
          pluginsSub.style.display = 'none';
        } else {
          pluginsSub.classList.remove('d-none');
          pluginsSub.style.display = 'block';
        }
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
      const sub = document.getElementById('update-plugins-subsection');
      if (sub) {
        sub.classList.add('d-none');
        sub.style.display = 'none';
      }
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
        if (mainCard) {
          mainCard.classList.remove('d-none');
          mainCard.style.display = 'block'; // Mostrar selector al desbloquear
        }
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
      if (mainCard) {
        mainCard.classList.add('d-none');
        mainCard.style.display = 'none'; // Ocultar nuevamente al bloquear
      }
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
      this.onInstallVersionChange();
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
      this.updateData = data;
      window.__LAST_UPDATE_DATA__ = data;

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

          if (data.build_update_available && data.latest_build) {
            if (bNotice) bNotice.style.display = 'block';
            if (bNoticeNum) bNoticeNum.textContent = `#${data.latest_build}`;
            if (bNoticeVer) bNoticeVer.textContent = data.current_version || data.latest_stable || '26.3';
            if (bBtnText) bBtnText.textContent = I18n.fmt('t_install_btn_update_to_build', [data.latest_build]) || `Actualizar a Build #${data.latest_build}`;
          } else {
            if (bNotice) bNotice.style.display = 'none';
            if (bBtnText) bBtnText.textContent = I18n.t('t_install_build_btn_change') || 'Cambiar / Actualizar Build';
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
          opt.textContent = v.label || v.id;
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
          opt.textContent = v.label || v.id;
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
          opt.textContent = v.label || v.id;
          select.appendChild(opt);
        });
        if (items.length === 0) {
          select.innerHTML = `<option value="${data.current_version}">${data.current_version}</option>`;
        }
      }

      this.switchUpdateChannel(this.currentUpdateChannel || 'stable');
      this.updateApplyButtonText();

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
    if (item.official_label) meta.officialLabel = item.official_label;
    if (item.wiki_url) meta.wikiUrl = item.wiki_url;
    if (item.wiki_label) meta.wikiLabel = item.wiki_label;
    if (item.advice_title) meta.adviceTitle = item.advice_title;
    if (item.advice_text) meta.adviceText = item.advice_text;
    if (item.clean_version) meta.cleanVer = item.clean_version;

    card.style.display = 'block';

    const chBadge = document.getElementById('update-details-channel-badge');
    const titleEl = document.getElementById('update-details-version-title');
    const btnOfficial = document.getElementById('btn-view-changelog');
    const btnOfficialText = document.getElementById('btn-view-changelog-text');
    const btnWiki = document.getElementById('btn-view-engine-notes');
    const btnWikiLabel = document.getElementById('btn-engine-notes-label');
    const adviceTitle = document.getElementById('update-details-advice-title');
    const adviceText = document.getElementById('update-details-advice-text');

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
      titleEl.textContent = `${meta.serverType.toUpperCase()} ${item.label || meta.versionId}`;
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
    card.style.display = 'block';

    const chBadge = document.getElementById('install-details-channel-badge');
    const titleEl = document.getElementById('install-details-version-title');
    const btnOfficial = document.getElementById('btn-install-view-changelog');
    const btnOfficialText = document.getElementById('btn-install-view-changelog-text');
    const btnWiki = document.getElementById('btn-install-view-engine-notes');
    const btnWikiLabel = document.getElementById('btn-install-engine-notes-label');
    const adviceTitle = document.getElementById('install-details-advice-title');
    const adviceText = document.getElementById('install-details-advice-text');

    if (chBadge) {
      if (meta.isStable) {
        chBadge.textContent = I18n.t('t_install_channel_stable') || 'Estable';
        chBadge.style.background = 'rgba(46, 160, 67, 0.15)';
        chBadge.style.border = '1px solid #2ea043';
        chBadge.style.color = '#3fb950';
      } else {
        chBadge.textContent = (meta.versionId.includes('-pre') ? 'Pre-Release' : (meta.versionId.includes('-rc') ? 'Release Candidate' : 'Snapshot / Beta'));
        chBadge.style.background = 'rgba(210, 153, 34, 0.15)';
        chBadge.style.border = '1px solid #d29922';
        chBadge.style.color = '#e3b341';
      }
    }

    if (titleEl) {
      titleEl.textContent = `${(meta.serverType || 'Minecraft').toUpperCase()} ${meta.versionId}`;
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
    const btn = document.getElementById('btn-apply-update');
    const spinnerSvg = '<svg class="spin-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `${spinnerSvg} <span>${I18n.t('t_install_downloading_ellipsis')}</span>`;
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
            }
            this.updateApplyButtonText();
            App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
            await this.checkLockState();
          } else if (pData.status && pData.status.startsWith('error')) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            if (btn) {
              btn.disabled = false;
            }
            this.updateApplyButtonText();
            App.showToast(I18n.fmt('t_install_err_update_fail', [pData.status]), 'danger');
          }
        } catch (err) {
          clearInterval(this.pollingInterval);
          this.pollingInterval = null;
          this.isInstalling = false;
          if (btn) {
            btn.disabled = false;
          }
          this.updateApplyButtonText();
        }
      }, 800);

    } catch (e) {
      this.isInstalling = false;
      if (btn) {
        btn.disabled = false;
      }
      this.updateApplyButtonText();
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

  // --- Dedicated Server Engine Build Modal & Operations ---
  _buildCommitMap: {},
  _buildEscHandler: null,

  ensureBuildModal() {
    let modal = document.getElementById('modal-change-build');
    if (modal) return modal;

    modal = document.createElement('div');
    modal.className = 'modal-backdrop modal-dialog-backdrop';
    modal.id = 'modal-change-build';
    modal.style.zIndex = '1200';
    modal.innerHTML = `
      <div class="modal-box modal-dialog-box" style="max-width: 580px;">
        <div class="modal-header" style="padding: 16px 20px; border-bottom: 1px solid #30363d;">
          <div style="display: flex; align-items: center; gap: 12px;">
            <div style="width: 38px; height: 38px; border-radius: 8px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.3); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
            </div>
            <div>
              <h3 style="font-size: 1.05rem; font-weight: 700; color: #f0f6fc; margin: 0;" data-i18n="t_install_build_modal_title">${I18n.t('t_install_build_modal_title') || 'Cambiar Compilación del Motor (Build)'}</h3>
              <div style="font-size: 0.8rem; color: #8b949e; margin-top: 2px;" data-i18n="t_install_build_modal_subtitle">
                ${I18n.t('t_install_build_modal_subtitle') || 'Actualización del motor interno de Paper / Purpur'}
              </div>
            </div>
          </div>
          <button class="action-icon-btn" onclick="Installer.closeBuildModal()" type="button" aria-label="Cerrar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body" style="padding: 20px;">
          <div style="padding: 12px 14px; background: rgba(13, 17, 23, 0.85); border: 1px solid #30363d; border-radius: 8px; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#58a6ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              <strong style="color: #f0f6fc; font-size: 0.88rem;" data-i18n="t_install_build_modal_info_title">${I18n.t('t_install_build_modal_info_title') || 'Información de la Actualización de Build'}</strong>
            </div>
            <p style="font-size: 0.84rem; color: #8b949e; line-height: 1.5; margin: 0;">
              La versión base de Minecraft se mantendrá en <strong id="modal-build-mc-version" style="color: #58a6ff;">--</strong>.
              Cambiar la <em>build</em> actualiza los ejecutables internos del servidor con las últimas correcciones de rendimiento, parches de seguridad y estabilidad publicados por el equipo desarrollador.
            </p>
          </div>
          <div style="display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px; margin-bottom: 18px; padding: 14px; background: #0d1117; border: 1px solid #30363d; border-radius: 8px;">
            <div style="text-align: center; padding: 8px;">
              <div style="font-size: 0.75rem; text-transform: uppercase; color: #8b949e; font-weight: 600; margin-bottom: 4px;" data-i18n="t_install_build_modal_installed">${I18n.t('t_install_build_modal_installed') || 'Build Instalada'}</div>
              <div id="modal-build-current-val" style="font-size: 1.35rem; font-weight: 700; color: #f0f6fc;">--</div>
              <div style="font-size: 0.75rem; color: #8b949e; margin-top: 2px;">En uso actual</div>
            </div>
            <div style="display: flex; justify-content: center; align-items: center; color: #38bdf8;">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
            <div style="text-align: center; padding: 8px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 6px;">
              <div style="font-size: 0.75rem; text-transform: uppercase; color: #38bdf8; font-weight: 600; margin-bottom: 4px;" data-i18n="t_install_build_modal_target">${I18n.t('t_install_build_modal_target') || 'Build de Destino'}</div>
              <div id="modal-build-target-display" style="font-size: 1.35rem; font-weight: 700; color: #38bdf8;">--</div>
              <div style="font-size: 0.75rem; color: #3fb950; font-weight: 600; margin-top: 2px;" id="modal-build-target-badge" data-i18n="t_install_build_modal_recommended">${I18n.t('t_install_build_modal_recommended') || 'Recomendada'}</div>
            </div>
          </div>
          <div class="form-group" style="margin-bottom: 16px;">
            <label class="form-label" for="modal-build-select" style="font-size: 0.85rem; font-weight: 600; color: #f0f6fc; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
              <span data-i18n="t_install_build_modal_select_label">${I18n.t('t_install_build_modal_select_label') || 'Seleccionar Compilación (Build):'}</span>
              <span id="modal-build-loading-spinner" style="display: none; font-size: 0.75rem; color: #8b949e; align-items: center; gap: 4px;">
                <svg class="spin-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                <span data-i18n="t_install_build_modal_loading">${I18n.t('t_install_build_modal_loading') || 'Cargando lista...'}</span>
              </span>
            </label>
            <select class="form-select" id="modal-build-select" onchange="Installer.onModalBuildChange()" style="font-size: 0.92rem; padding: 9px 12px;">
              <option value="">Cargando builds disponibles...</option>
            </select>
            <div class="field-hint" style="margin-top: 4px; font-size: 0.78rem; color: #8b949e;" data-i18n="t_install_build_modal_select_hint">
              ${I18n.t('t_install_build_modal_select_hint') || 'Puedes seleccionar la compilación más reciente o cualquier versión anterior disponible para tu versión de Minecraft.'}
            </div>
          </div>
          <div id="modal-build-changelog-box" style="display: none; padding: 10px 12px; background: #161b22; border: 1px solid #30363d; border-radius: 6px; margin-bottom: 16px; font-size: 0.8rem; color: #c9d1d9;">
            <div style="font-weight: 600; color: #8b949e; margin-bottom: 4px; font-size: 0.75rem; text-transform: uppercase;">Cambios en esta Build:</div>
            <div id="modal-build-changelog-text" style="line-height: 1.4; color: #e6edf3;"></div>
          </div>
          <div style="padding: 12px 14px; background: rgba(46, 160, 67, 0.08); border: 1px solid rgba(46, 160, 67, 0.3); border-radius: 8px;">
            <div style="font-size: 0.82rem; font-weight: 700; color: #3fb950; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              <span data-i18n="t_install_build_modal_safety_title">${I18n.t('t_install_build_modal_safety_title') || 'Garantías de Seguridad del Proceso'}</span>
            </div>
            <ul style="margin: 0; padding-left: 18px; font-size: 0.8rem; color: #cbd5e1; line-height: 1.6;">
              <li data-i18n="t_install_build_modal_safety_1"><strong>Copia de seguridad preventiva</strong> automática antes de aplicar cualquier cambio.</li>
              <li data-i18n="t_install_build_modal_safety_2"><strong>Tus mundos, inventarios, plugins y configuraciones</strong> quedan 100% intactos.</li>
              <li data-i18n="t_install_build_modal_safety_3"><strong>Verificación de integridad (SHA-256)</strong> para prevenir archivos corruptos o descargas truncadas.</li>
              <li data-i18n="t_install_build_modal_safety_4"><strong>Guardado seguro</strong> (<code>save-all</code>) y reinicio automático del servidor si estaba encendido.</li>
            </ul>
          </div>
        </div>
        <div class="modal-footer" style="padding: 14px 20px; border-top: 1px solid #30363d; display: flex; justify-content: flex-end; gap: 10px;">
          <button type="button" class="btn btn-outline" onclick="Installer.closeBuildModal()" data-i18n="t_install_btn_cancel">${I18n.t('t_install_btn_cancel') || 'Cancelar'}</button>
          <button type="button" class="btn btn-primary" id="btn-modal-apply-build" onclick="Installer.applyBuildFromModal()" style="display: inline-flex; align-items: center; gap: 8px; font-weight: 600;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            <span id="btn-modal-apply-build-text">Instalar Build</span>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    return modal;
  },

  async openBuildModal(targetBuildId) {
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

    // Show installer progress box
    const pBox = document.getElementById('update-progress-box');
    const pBar = document.getElementById('update-progress-bar');
    const pText = document.getElementById('update-progress-text');
    const pPct = document.getElementById('update-progress-percent');
    if (pBox) pBox.style.display = 'block';
    if (pBar) pBar.style.width = '0%';
    if (pText) pText.textContent = targetBuild
      ? (I18n.fmt('t_install_build_toast_started', [targetBuild]) || `Descargando Build #${targetBuild}...`)
      : I18n.t('t_install_update_downloading');
    if (pPct) pPct.textContent = '0%';

    const btnApply = document.getElementById('btn-apply-update');
    const spinnerSvg = '<svg class="spin-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>';
    if (btnApply) {
      btnApply.disabled = true;
      btnApply.innerHTML = `${spinnerSvg} <span>${I18n.t('t_install_downloading_ellipsis')}</span>`;
    }

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
      const resData = await res.json();
      if (!res.ok) {
        throw new Error(resData.detail || I18n.t('t_install_err_update_start'));
      }

      // Poll progress
      if (this.pollingInterval) clearInterval(this.pollingInterval);
      this.pollingInterval = setInterval(async () => {
        try {
          const pRes = await fetch('/api/installer/progress');
          const pData = await pRes.json();
          const pct = pData.percent || 0;
          if (pBar) pBar.style.width = `${pct}%`;
          if (pPct) pPct.textContent = `${pct}%`;

          let statusText = pData.status || '';
          if (statusText === 'downloading') statusText = I18n.t('t_install_status_downloading');
          else if (statusText === 'verifying') statusText = I18n.t('t_install_status_verifying');
          else if (statusText === 'extracting') statusText = I18n.t('t_install_status_extracting');
          else if (statusText === 'updating') statusText = I18n.t('t_install_status_updating');
          else if (statusText === 'completed') statusText = I18n.t('t_install_status_completed');

          if (pText && statusText) {
            pText.textContent = `${statusText}...`;
          }

          if (pct >= 100 || !pData.is_downloading) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
            this.isInstalling = false;
            setTimeout(() => {
              if (pBox) pBox.style.display = 'none';
              if (btnApply) {
                btnApply.disabled = false;
                btnApply.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> <span data-i18n="t_install_btn_update">${I18n.t('t_install_btn_update')}</span>`;
              }
              App.showToast(I18n.t('t_install_toast_updated_ok'), 'success');
              this.checkUpdateInfo();
            }, 1500);
          }
        } catch (err) {
          console.error('[Installer] Poll progress error:', err);
        }
      }, 1000);

    } catch (e) {
      this.isInstalling = false;
      if (pBox) pBox.style.display = 'none';
      if (btnApply) {
        btnApply.disabled = false;
        btnApply.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> <span data-i18n="t_install_btn_update">${I18n.t('t_install_btn_update')}</span>`;
      }
      App.showToast(I18n.fmt('t_install_err_update_fail', [e.message]), 'danger');
    }
  }
};

window.Installer = Installer;
