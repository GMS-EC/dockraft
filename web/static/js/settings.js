// Dockraft Server Settings Script
const Settings = {
  properties: {},
  runtimeConfig: {},
  serverStatus: {},
  javaRuntimes: [],

  eventsSetup: false,

  _t(key, fallback) {
    if (typeof I18n !== 'undefined' && I18n.t) return I18n.t(key, fallback);
    return (fallback !== undefined ? fallback : key);
  },

  _tf(key, args, fallback) {
    if (typeof I18n !== 'undefined' && I18n.fmt) return I18n.fmt(key, args || [], fallback);
    let text = (fallback !== undefined ? fallback : key);
    (args || []).forEach((value, i) => {
      text = String(text).split(`{${i}}`).join(value);
    });
    return text;
  },

  async loadSettings() {
    this.setupEvents();
    if (window.__INITIAL_STATS__) {
      this.serverStatus = window.__INITIAL_STATS__;
    }
    if (window.__INITIAL_CONFIG__) {
      this.runtimeConfig = window.__INITIAL_CONFIG__;
    }
    this.renderViewByServerType();
    await Promise.all([
      this.fetchServerStatus(),
      this.fetchRuntimeConfig(),
      this.fetchJavaRuntimes(),
      this.fetchProperties(),
      this.loadRawProperties()
    ]);
    this.renderViewByServerType();
  },

  setupEvents() {
    if (this.eventsSetup) return;
    this.eventsSetup = true;

    const btnVisual = document.getElementById('btn-mode-props-visual');
    const btnRaw = document.getElementById('btn-mode-props-raw');
    if (btnVisual) {
      btnVisual.onclick = (e) => {
        if (e) e.preventDefault();
        this.setPropertiesMode('visual');
      };
    }
    if (btnRaw) {
      btnRaw.onclick = (e) => {
        if (e) e.preventDefault();
        this.setPropertiesMode('raw');
      };
    }

    const searchInput = document.getElementById('props-search-input');
    if (searchInput) {
      searchInput.oninput = (e) => this.filterProperties(e.target.value);
    }

    document.querySelectorAll('.prop-cat-btn').forEach(btn => {
      btn.onclick = (e) => {
        if (e) e.preventDefault();
        const cat = btn.getAttribute('data-cat') || 'all';
        this.setPropertiesCategory(cat);
      };
    });

    window.addEventListener('dockraft:language_changed', () => {
      if (typeof App === 'undefined' || App.activeTab === 'settings') {
        this.refreshLanguageUI();
      }
    });
  },

  javaServerName(serverType, fallbackName) {
    const keys = {
      paper: 't_setting_name_paper',
      purpur: 't_setting_name_purpur',
      fabric: 't_setting_name_fabric',
      vanilla: 't_setting_name_vanilla'
    };
    const key = keys[serverType];
    if (key) return this._t(key, fallbackName);
    return this._tf('t_setting_name_generic', [serverType.toUpperCase()], fallbackName);
  },

  javaServerTip(serverType, fallbackTip) {
    if (serverType === 'paper') return this._tf('t_setting_tip_paper', ['paper-global.yml', 'paper-world-defaults.yml'], fallbackTip);
    if (serverType === 'purpur') return this._tf('t_setting_tip_purpur', ['purpur.yml'], fallbackTip);
    if (serverType === 'fabric') return this._tf('t_setting_tip_fabric', ['mods/'], fallbackTip);
    if (serverType === 'vanilla') return this._t('t_setting_tip_vanilla', fallbackTip);
    return this._t('t_setting_tip_generic', fallbackTip);
  },

  refreshJavaRuntimeSelect() {
    const select = document.getElementById('setting-java-select');
    if (!select) return;
    const previous = select.value;
    const customGroup = document.getElementById('setting-java-custom-group');
    const inputPath = document.getElementById('setting-java-path');
    const wasCustomVisible = customGroup ? (customGroup.style.display !== 'none') : false;
    const previousPath = inputPath ? inputPath.value : '';

    this.populateJavaRuntimesUI();

    const hasOption = Array.prototype.some.call(select.options, o => o.value === previous);
    select.value = hasOption ? previous : 'custom';

    const isCustom = select.value === 'custom';
    if (customGroup) customGroup.style.display = isCustom ? 'block' : 'none';
    if (inputPath) {
      if (isCustom && wasCustomVisible && previousPath) {
        inputPath.value = previousPath;
      } else if (!isCustom) {
        inputPath.value = select.value;
      }
    }
  },

  refreshLanguageUI() {
    const isInstalled = this.serverStatus.is_installed;
    const serverType = (this.serverStatus.server_type || this.runtimeConfig.server_type || 'vanilla').toLowerCase();
    const status = this.serverStatus.status || 'OFFLINE';
    const titleEl = document.getElementById('settings-badge-title');
    const editionEl = document.getElementById('settings-badge-edition');
    const statusEl = document.getElementById('settings-badge-status');

    if (statusEl) {
      const isRunning = status === 'RUNNING';
      const isStarting = status === 'STARTING';
      const color = isRunning ? '#3fb950' : (isStarting ? '#d29922' : '#8b949e');
      const text = isRunning
        ? this._t('t_setting_status_online', 'En Línea')
        : (isStarting ? this._t('t_setting_status_starting', 'Iniciando') : this._t('t_setting_status_stopped', 'Detenido'));
      statusEl.innerHTML = `<span class="badge" style="display:inline-flex; align-items:center; background-color: rgba(255,255,255,0.06); border: 1px solid ${color}; color: ${color};"><span style="display:inline-block; width:7px; height:7px; border-radius:50%; background-color:${color}; margin-right:6px;"></span>${text}</span>`;
    }

    if (!isInstalled) {
      if (titleEl) titleEl.textContent = this._t('t_setting_no_server', 'Sin Servidor Instalado');
      if (editionEl) editionEl.textContent = this._t('t_setting_not_detected', 'No Detectado');
      return;
    }

    if (serverType === 'bedrock') {
      if (titleEl) titleEl.textContent = this._t('t_setting_name_bedrock', 'Bedrock Dedicated Server');
      if (editionEl) editionEl.textContent = this._t('t_setting_edition_bedrock', 'Bedrock C++ Nativo');
      return;
    }

    if (titleEl) titleEl.textContent = this.javaServerName(serverType, 'Servidor Minecraft Java Edition');
    if (editionEl) editionEl.textContent = 'Java Edition';

    const tipText = document.getElementById('settings-software-tip-text');
    if (tipText) tipText.innerHTML = this.javaServerTip(serverType, 'Servidor Minecraft Java Edition.');

    const aikarDesc = document.getElementById('setting-aikar-desc');
    if (aikarDesc) {
      aikarDesc.textContent = (serverType === 'paper' || serverType === 'purpur')
        ? this._t('t_setting_aikar_paper', 'Optimización avanzada del recolector G1GC (Altamente recomendado para Paper y Purpur).')
        : this._t('t_setting_aikar_other', 'Flags de optimización de memoria G1GC desarrollados por la comunidad de Minecraft.');
    }

    this.refreshJavaRuntimeSelect();
  },

  async fetchServerStatus() {
    try {
      const res = await fetch('/api/server/status');
      if (res.ok) {
        this.serverStatus = await res.json();
      }
    } catch (e) {
      console.warn("Could not load server status:", e);
    }
  },

  async fetchRuntimeConfig() {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        this.runtimeConfig = await res.json();
      }
    } catch (e) {
      console.warn("Could not load runtime config:", e);
    }
  },

  async fetchJavaRuntimes() {
    try {
      const res = await fetch('/api/java/runtimes');
      if (res.ok) {
        this.javaRuntimes = await res.json();
      }
    } catch (e) {
      console.warn("Could not load Java runtimes:", e);
    }
  },

  async fetchProperties() {
    try {
      const res = await fetch('/api/server/properties');
      if (res.ok) {
        const data = await res.json();
        this.properties = data.properties || {};
      }
    } catch (e) {
      console.warn("Could not load server.properties:", e);
    }
  },

  renderViewByServerType() {
    const isInstalled = this.serverStatus.is_installed;
    const serverType = (this.serverStatus.server_type || this.runtimeConfig.server_type || 'vanilla').toLowerCase();
    const serverVersion = this.serverStatus.server_version || this.runtimeConfig.server_version || '';
    const status = this.serverStatus.status || 'OFFLINE';

    // Header badge elements
    const iconEl = document.getElementById('settings-badge-icon');
    const titleEl = document.getElementById('settings-badge-title');
    const verEl = document.getElementById('settings-badge-version');
    const editionEl = document.getElementById('settings-badge-edition');
    const statusEl = document.getElementById('settings-badge-status');

    // Containers
    const emptyState = document.getElementById('settings-empty-state');
    const bedrockContainer = document.getElementById('settings-bedrock-container');
    const javaContainer = document.getElementById('settings-java');

    // Status pill
    if (statusEl) {
      const isRunning = status === 'RUNNING';
      const isStarting = status === 'STARTING';
      const color = isRunning ? '#3fb950' : (isStarting ? '#d29922' : '#8b949e');
      const text = isRunning
        ? this._t('t_setting_status_online', 'En Línea')
        : (isStarting ? this._t('t_setting_status_starting', 'Iniciando') : this._t('t_setting_status_stopped', 'Detenido'));
      statusEl.innerHTML = `<span class="badge" style="display:inline-flex; align-items:center; background-color: rgba(255,255,255,0.06); border: 1px solid ${color}; color: ${color};"><span style="display:inline-block; width:7px; height:7px; border-radius:50%; background-color:${color}; margin-right:6px;"></span>${text}</span>`;
    }

    if (!isInstalled) {
      if (iconEl) iconEl.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#d29922" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
      if (titleEl) titleEl.textContent = this._t('t_setting_no_server', 'Sin Servidor Instalado');
      if (verEl) verEl.style.display = 'none';
      if (editionEl) {
        editionEl.textContent = this._t('t_setting_not_detected', 'No Detectado');
        editionEl.style.color = 'var(--text-muted)';
        editionEl.style.backgroundColor = 'var(--bg-subtle)';
      }
      if (emptyState) emptyState.style.display = 'block';
      if (bedrockContainer) bedrockContainer.style.display = 'none';
      if (javaContainer) javaContainer.style.display = 'none';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (verEl) {
      verEl.style.display = 'inline-block';
      verEl.textContent = serverVersion ? `v${serverVersion}` : '';
    }

    // Configure according to server type
    if (serverType === 'bedrock') {
      if (iconEl) iconEl.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><line x1="6" y1="12" x2="10" y2="12"/><line x1="8" y1="10" x2="8" y2="14"/><circle cx="16" cy="10" r="1"/><circle cx="18" cy="13" r="1"/></svg>`;
      if (titleEl) titleEl.textContent = this._t('t_setting_name_bedrock', 'Bedrock Dedicated Server');
      if (editionEl) {
        editionEl.textContent = this._t('t_setting_edition_bedrock', 'Bedrock C++ Nativo');
        editionEl.style.color = '#79c0ff';
        editionEl.style.backgroundColor = 'rgba(56, 139, 253, 0.15)';
      }

      if (bedrockContainer) bedrockContainer.style.display = 'block';
      if (javaContainer) javaContainer.style.display = 'none';

      this.populateBedrockUI();
    } else {
      // Java Edition servers
      const titles = {
        paper: { 
          icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`, 
          name: 'Servidor PaperMC', 
          tip: 'Sugerencia PaperMC: Puedes personalizar opciones de optimización en <strong>paper-global.yml</strong> y <strong>paper-world-defaults.yml</strong> en la pestaña Archivos.' 
        },
        purpur: { 
          icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`, 
          name: 'Servidor PurpurMC', 
          tip: 'Sugerencia PurpurMC: Cientos de opciones de juego y rendimiento avanzadas en <strong>purpur.yml</strong> accesibles en la pestaña Archivos.' 
        },
        fabric: { 
          icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>`, 
          name: 'Servidor Fabric Loader', 
          tip: 'Sugerencia Fabric: Puedes instalar mods (.jar) subiéndolos directamente a la carpeta <strong>mods/</strong> desde la pestaña Archivos.' 
        },
        vanilla: { 
          icon: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="1"/><rect x="2" y="14" width="20" height="8" rx="1"/><line x1="6" y1="6" x2="6" y2="6"/><line x1="18" y1="18" x2="18" y2="18"/></svg>`, 
          name: 'Servidor Minecraft Vanilla', 
          tip: 'Servidor Vanilla Oficial: Sin modificaciones ni plugins externos.' 
        }
      };

      const defaultIcon = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ec4899" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>`;
      const info = titles[serverType] || { icon: defaultIcon, name: `Servidor ${serverType.toUpperCase()}`, tip: 'Servidor Minecraft Java Edition.' };

      if (iconEl) iconEl.innerHTML = info.icon;
      if (titleEl) titleEl.textContent = this.javaServerName(serverType, info.name);
      if (editionEl) {
        editionEl.textContent = 'Java Edition';
        editionEl.style.color = '#58a6ff';
        editionEl.style.backgroundColor = 'rgba(56, 139, 253, 0.15)';
      }

      const tipText = document.getElementById('settings-software-tip-text');
      if (tipText) tipText.innerHTML = this.javaServerTip(serverType, info.tip);

      const aikarDesc = document.getElementById('setting-aikar-desc');
      if (aikarDesc) {
        if (serverType === 'paper' || serverType === 'purpur') {
          aikarDesc.textContent = this._t('t_setting_aikar_paper', 'Optimización avanzada del recolector G1GC (Altamente recomendado para Paper y Purpur).');
        } else {
          aikarDesc.textContent = this._t('t_setting_aikar_other', 'Flags de optimización de memoria G1GC desarrollados por la comunidad de Minecraft.');
        }
      }

      if (bedrockContainer) bedrockContainer.style.display = 'none';
      if (javaContainer) javaContainer.style.display = 'block';

      this.populateJavaRuntimesUI();
      this.populateJavaPropertiesUI();
      this.populateRuntimeConfigUI();
    }
  },

  populateBedrockUI() {
    const p = this.properties;

    const setVal = (id, key, def = '') => {
      const el = document.getElementById(id);
      if (el) el.value = p[key] !== undefined ? p[key] : def;
    };

    const setCheck = (id, key, def = true) => {
      const el = document.getElementById(id);
      if (el) el.checked = p[key] !== undefined ? (String(p[key]).toLowerCase() === 'true') : def;
    };

    setVal('bedrock-prop-server-name', 'server-name', p['motd'] || 'Dedicated Server');
    setVal('bedrock-prop-port', 'server-port', '19132');
    setVal('bedrock-prop-portv6', 'server-portv6', '19133');
    setVal('bedrock-prop-gamemode', 'gamemode', 'survival');
    setVal('bedrock-prop-difficulty', 'difficulty', 'easy');
    setVal('bedrock-prop-permission-level', 'default-player-permission-level', 'member');
    setVal('bedrock-prop-max-players', 'max-players', '10');
    setVal('bedrock-prop-view-distance', 'view-distance', '32');
    setVal('bedrock-prop-tick-distance', 'tick-distance', '4');

    setCheck('bedrock-prop-online-mode', 'online-mode', true);
    setCheck('bedrock-prop-allow-cheats', 'allow-cheats', false);
    setCheck('bedrock-prop-white-list', 'white-list', p['allow-list'] !== undefined ? (String(p['allow-list']).toLowerCase() === 'true') : false);
    setCheck('bedrock-prop-texturepack-required', 'texturepack-required', false);

    // Bedrock Native Performance & Disk limit
    setVal('bedrock-prop-max-threads', 'max-threads', '8');
    setVal('bedrock-prop-idle-timeout', 'player-idle-timeout', '30');
    setVal('bedrock-prop-compression', 'compression-threshold', '1');
    setCheck('bedrock-prop-content-log', 'content-log-file-enabled', false);

    const bedrockDisk = document.getElementById('bedrock-setting-disk-limit');
    if (bedrockDisk) bedrockDisk.value = this.runtimeConfig.disk_limit_gb !== undefined ? this.runtimeConfig.disk_limit_gb : 10;
  },

  async saveBedrockProperties() {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    const getCheck = (id) => {
      const el = document.getElementById(id);
      return el ? (el.checked ? 'true' : 'false') : 'true';
    };

    const serverName = getVal('bedrock-prop-server-name') || 'Dedicated Server';
    const isWhitelist = getCheck('bedrock-prop-white-list');

    const newProps = {
      ...this.properties,
      'server-name': serverName,
      'motd': serverName,
      'server-port': getVal('bedrock-prop-port') || '19132',
      'server-portv6': getVal('bedrock-prop-portv6') || '19133',
      'gamemode': getVal('bedrock-prop-gamemode') || 'survival',
      'difficulty': getVal('bedrock-prop-difficulty') || 'easy',
      'default-player-permission-level': getVal('bedrock-prop-permission-level') || 'member',
      'max-players': getVal('bedrock-prop-max-players') || '10',
      'view-distance': getVal('bedrock-prop-view-distance') || '32',
      'tick-distance': getVal('bedrock-prop-tick-distance') || '4',
      'online-mode': getCheck('bedrock-prop-online-mode'),
      'allow-cheats': getCheck('bedrock-prop-allow-cheats'),
      'white-list': isWhitelist,
      'allow-list': isWhitelist,
      'texturepack-required': getCheck('bedrock-prop-texturepack-required'),
      'max-threads': getVal('bedrock-prop-max-threads') || '8',
      'player-idle-timeout': getVal('bedrock-prop-idle-timeout') || '30',
      'compression-threshold': getVal('bedrock-prop-compression') || '1',
      'content-log-file-enabled': getCheck('bedrock-prop-content-log')
    };

    try {
      const res = await fetch('/api/server/properties', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProps)
      });
      if (res.ok) {
        // Also save disk limit and server name in runtime config if present
        const diskEl = document.getElementById('bedrock-setting-disk-limit');
        const bServerName = document.getElementById('bedrock-setting-server-name')?.value.trim();
        const bAutostart = document.getElementById('bedrock-setting-autostart-server')?.checked ?? (this.runtimeConfig.autostart_server || false);
        const bCrashEl = document.getElementById('bedrock-setting-crash-detection');
        const bCrash = bCrashEl ? bCrashEl.checked : (this.runtimeConfig.crash_detection !== false);
        const bTimeoutEl = document.getElementById('bedrock-setting-session-timeout');
        const bSessionTimeout = bTimeoutEl ? (parseInt(bTimeoutEl.value, 10) || 60) : (this.runtimeConfig.session_timeout_minutes || 60);

        const diskVal = diskEl ? (parseFloat(diskEl.value) || 0) : 10;
        const updatePayload = {
          ...this.runtimeConfig,
          disk_limit_gb: diskVal,
          autostart_server: bAutostart,
          crash_detection: bCrash,
          session_timeout_minutes: bSessionTimeout
        };
        if (bServerName) updatePayload.server_name = bServerName;
        await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updatePayload)
        });
        this.runtimeConfig = updatePayload;
        if (typeof App !== 'undefined' && App.setupSessionMonitoring) {
          App.setupSessionMonitoring(bSessionTimeout);
        }

        App.showToast(this._t('t_setting_toast_bedrock_saved', 'Configuración de Bedrock guardada exitosamente'), 'success');
        this.properties = newProps;
      } else {
        App.showToast(this._t('t_setting_toast_bedrock_error', 'Error al guardar la configuración de Bedrock'), 'danger');
      }
    } catch (e) {
      App.showToast(e.message, 'danger');
    }
  },

  populateJavaRuntimesUI() {
    const select = document.getElementById('setting-java-select');
    const customGroup = document.getElementById('setting-java-custom-group');
    const inputPath = document.getElementById('setting-java-path');
    if (!select) return;

    const currentPath = (this.runtimeConfig.java_path || 'java').trim();
    select.innerHTML = '';

    // Default system java option
    const optDefault = document.createElement('option');
    optDefault.value = 'java';
    optDefault.textContent = this._t('t_setting_opt_java_default', 'Java Predeterminado del Sistema (PATH)');
    select.appendChild(optDefault);

    let matched = (currentPath === 'java' || currentPath === '');

    // Add detected runtimes
    if (Array.isArray(this.javaRuntimes)) {
      this.javaRuntimes.forEach(rt => {
        if (!rt.path || rt.path === 'java') return;
        const opt = document.createElement('option');
        opt.value = rt.path;
        const isRec = rt.version === 21 ? this._t('t_setting_rec_suffix', ' (Recomendado)') : '';
        opt.textContent = `${rt.name || ('Java ' + rt.version)} (${rt.path})${isRec}`;
        if (rt.path === currentPath) {
          opt.selected = true;
          matched = true;
        }
        select.appendChild(opt);
      });
    }

    // Custom path option
    const optCustom = document.createElement('option');
    optCustom.value = 'custom';
    optCustom.textContent = this._t('t_setting_opt_custom_path', 'Otra ruta personalizada...');
    select.appendChild(optCustom);

    if (matched) {
      select.value = currentPath || 'java';
      if (customGroup) customGroup.style.display = 'none';
    } else {
      select.value = 'custom';
      if (customGroup) customGroup.style.display = 'block';
    }

    if (inputPath) inputPath.value = currentPath;
  },

  onJavaSelectChange() {
    const select = document.getElementById('setting-java-select');
    const customGroup = document.getElementById('setting-java-custom-group');
    const inputPath = document.getElementById('setting-java-path');
    if (!select) return;

    if (select.value === 'custom') {
      if (customGroup) customGroup.style.display = 'block';
      if (inputPath) inputPath.focus();
    } else {
      if (customGroup) customGroup.style.display = 'none';
      if (inputPath) inputPath.value = select.value;
    }
  },

  activePropsMode: 'visual',
  activePropsCategory: 'all',

  setPropertiesMode(mode) {
    this.activePropsMode = mode;
    const btnVisual = document.getElementById('btn-mode-props-visual');
    const btnRaw = document.getElementById('btn-mode-props-raw');
    const viewVisual = document.getElementById('props-view-visual');
    const viewRaw = document.getElementById('props-view-raw');

    if (mode === 'raw') {
      if (btnRaw) {
        btnRaw.classList.add('active');
        btnRaw.style.background = '#238636';
        btnRaw.style.color = '#fff';
      }
      if (btnVisual) {
        btnVisual.classList.remove('active');
        btnVisual.style.background = 'transparent';
        btnVisual.style.color = '#8b949e';
      }
      if (viewVisual) viewVisual.style.display = 'none';
      if (viewRaw) viewRaw.style.display = 'block';
      this.loadRawProperties();
    } else {
      if (btnVisual) {
        btnVisual.classList.add('active');
        btnVisual.style.background = '#238636';
        btnVisual.style.color = '#fff';
      }
      if (btnRaw) {
        btnRaw.classList.remove('active');
        btnRaw.style.background = 'transparent';
        btnRaw.style.color = '#8b949e';
      }
      if (viewVisual) viewVisual.style.display = 'block';
      if (viewRaw) viewRaw.style.display = 'none';
    }
  },

  async loadRawProperties() {
    const textarea = document.getElementById('props-raw-textarea');
    if (!textarea) return;
    try {
      const res = await fetch('/api/server/properties/raw');
      if (res.ok) {
        const data = await res.json();
        textarea.value = data.content || '';
      }
    } catch (e) {
      console.warn("Could not load raw properties:", e);
      App.showToast(this._t('t_setting_toast_raw_load_error', 'Error al cargar server.properties en modo texto'), 'danger');
    }
  },

  async saveRawProperties() {
    const textarea = document.getElementById('props-raw-textarea');
    if (!textarea) return;
    try {
      const res = await fetch('/api/server/properties/raw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: textarea.value })
      });
      if (res.ok) {
        App.showToast(this._t('t_setting_toast_props_saved', 'server.properties guardado exitosamente'), 'success');
        await this.fetchProperties();
        this.populateJavaPropertiesUI();
      } else {
        App.showToast(this._t('t_setting_toast_props_error', 'Error al guardar server.properties'), 'danger');
      }
    } catch (e) {
      App.showToast(e.message, 'danger');
    }
  },

  setPropertiesCategory(cat) {
    this.activePropsCategory = cat;
    document.querySelectorAll('.prop-cat-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-cat') === cat);
    });
    const searchVal = document.getElementById('props-search-input')?.value || '';
    this.filterProperties(searchVal);
  },

  filterProperties(query) {
    const q = (query || '').toLowerCase().trim();
    const activeCat = this.activePropsCategory || 'all';

    document.querySelectorAll('.prop-item').forEach(item => {
      const cat = item.getAttribute('data-cat') || 'game';
      const key = (item.getAttribute('data-key') || '').toLowerCase();
      const text = (item.textContent || '').toLowerCase();

      const matchesCat = (activeCat === 'all' || cat === activeCat);
      const matchesSearch = (!q || key.includes(q) || text.includes(q));

      if (matchesCat && matchesSearch) {
        item.style.display = '';
      } else {
        item.style.display = 'none';
      }
    });
  },

  populateJavaPropertiesUI() {
    const p = this.properties;

    const setVal = (id, key, def = '') => {
      const el = document.getElementById(id);
      if (el) el.value = p[key] !== undefined ? p[key] : def;
    };

    const setCheck = (id, key, def = true) => {
      const el = document.getElementById(id);
      if (el) el.checked = p[key] !== undefined ? (String(p[key]).toLowerCase() === 'true') : def;
    };

    setVal('prop-motd', 'motd', p['server-name'] || 'A Dockraft Minecraft Server');
    setVal('prop-gamemode', 'gamemode', 'survival');
    setVal('prop-difficulty', 'difficulty', 'easy');
    setVal('prop-max-players', 'max-players', '20');
    setVal('prop-server-port', 'server-port', '25565');
    setVal('prop-view-distance', 'view-distance', '10');
    setVal('prop-simulation-distance', 'simulation-distance', '8');

    // Extended properties
    setVal('prop-level-name', 'level-name', 'world');
    setVal('prop-level-seed', 'level-seed', '');
    setVal('prop-level-type', 'level-type', 'minecraft:normal');
    setVal('prop-spawn-protection', 'spawn-protection', '16');
    setVal('prop-compression-threshold', 'network-compression-threshold', '256');
    setVal('prop-rate-limit', 'rate-limit', '0');

    setCheck('prop-online-mode', 'online-mode', true);
    setCheck('prop-pvp', 'pvp', true);
    setCheck('prop-white-list', 'white-list', false);
    setCheck('prop-enforce-whitelist', 'enforce-whitelist', false);
    setCheck('prop-allow-flight', 'allow-flight', false);
    setCheck('prop-allow-nether', 'allow-nether', true);
    setCheck('prop-generate-structures', 'generate-structures', true);
    setCheck('prop-spawn-monsters', 'spawn-monsters', true);
    setCheck('prop-spawn-animals', 'spawn-animals', true);
    setCheck('prop-enable-command-block', 'enable-command-block', false);
    setCheck('prop-hardcore', 'hardcore', false);
  },

  async saveJavaProperties() {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    const getCheck = (id) => {
      const el = document.getElementById(id);
      return el ? (el.checked ? 'true' : 'false') : 'true';
    };

    const motd = getVal('prop-motd') || 'A Dockraft Minecraft Server';
    const isWhitelist = getCheck('prop-white-list');

    const newProps = {
      ...this.properties,
      'motd': motd,
      'server-name': motd,
      'gamemode': getVal('prop-gamemode') || 'survival',
      'difficulty': getVal('prop-difficulty') || 'easy',
      'level-name': getVal('prop-level-name') || 'world',
      'level-seed': getVal('prop-level-seed') || '',
      'level-type': getVal('prop-level-type') || 'minecraft:normal',
      'spawn-protection': getVal('prop-spawn-protection') || '16',
      'max-players': getVal('prop-max-players') || '20',
      'server-port': getVal('prop-server-port') || '25565',
      'view-distance': getVal('prop-view-distance') || '10',
      'simulation-distance': getVal('prop-simulation-distance') || '8',
      'network-compression-threshold': getVal('prop-compression-threshold') || '256',
      'rate-limit': getVal('prop-rate-limit') || '0',
      'online-mode': getCheck('prop-online-mode'),
      'pvp': getCheck('prop-pvp'),
      'white-list': isWhitelist,
      'allow-list': isWhitelist,
      'enforce-whitelist': getCheck('prop-enforce-whitelist'),
      'allow-flight': getCheck('prop-allow-flight'),
      'allow-nether': getCheck('prop-allow-nether'),
      'generate-structures': getCheck('prop-generate-structures'),
      'spawn-monsters': getCheck('prop-spawn-monsters'),
      'spawn-animals': getCheck('prop-spawn-animals'),
      'enable-command-block': getCheck('prop-enable-command-block'),
      'hardcore': getCheck('prop-hardcore')
    };

    try {
      const res = await fetch('/api/server/properties', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProps)
      });
      if (res.ok) {
        App.showToast(this._t('t_setting_toast_props_saved', 'server.properties guardado exitosamente'), 'success');
        this.properties = newProps;
      } else {
        App.showToast(this._t('t_setting_toast_props_error', 'Error al guardar server.properties'), 'danger');
      }
    } catch (e) {
      App.showToast(e.message, 'danger');
    }
  },

  // Alias for backward compatibility
  async saveProperties() {
    return this.saveJavaProperties();
  },

  populateRuntimeConfigUI() {
    const cfg = this.runtimeConfig;
    const nameEl = document.getElementById('setting-server-name');
    const bNameEl = document.getElementById('bedrock-setting-server-name');
    if (nameEl) nameEl.value = cfg.server_name || 'Mi Servidor Dockraft';
    if (bNameEl) bNameEl.value = cfg.server_name || 'Mi Servidor Dockraft';

    const minRam = document.getElementById('setting-min-ram');
    const maxRam = document.getElementById('setting-max-ram');
    const aikar = document.getElementById('setting-aikar-flags');
    const customFlags = document.getElementById('setting-custom-flags');

    const diskEl = document.getElementById('setting-disk-limit');
    const cpuEl = document.getElementById('setting-cpu-cores');
    if (minRam) minRam.value = cfg.min_ram || '1G';
    if (maxRam) maxRam.value = cfg.max_ram || '2G';
    if (aikar) aikar.checked = cfg.aikar_flags !== false;
    if (customFlags) customFlags.value = cfg.custom_jvm_flags || '';
    if (diskEl) diskEl.value = cfg.disk_limit_gb !== undefined ? cfg.disk_limit_gb : 10;
    if (cpuEl) cpuEl.value = cfg.cpu_cores !== undefined ? cfg.cpu_cores : 2;

    const autostartEl = document.getElementById('setting-autostart-server');
    const bAutostartEl = document.getElementById('bedrock-setting-autostart-server');
    if (autostartEl) autostartEl.checked = !!cfg.autostart_server;
    if (bAutostartEl) bAutostartEl.checked = !!cfg.autostart_server;

    const crashEl = document.getElementById('setting-crash-detection');
    const bCrashEl = document.getElementById('bedrock-setting-crash-detection');
    if (crashEl) crashEl.checked = cfg.crash_detection !== false;
    if (bCrashEl) bCrashEl.checked = cfg.crash_detection !== false;

    const timeoutEl = document.getElementById('setting-session-timeout');
    const bTimeoutEl = document.getElementById('bedrock-setting-session-timeout');
    const sessionTimeout = cfg.session_timeout_minutes !== undefined ? cfg.session_timeout_minutes : 60;
    if (timeoutEl) timeoutEl.value = sessionTimeout;
    if (bTimeoutEl) bTimeoutEl.value = sessionTimeout;
  },

  async saveRuntimeConfig() {
    const serverName = document.getElementById('setting-server-name')?.value.trim() || this.runtimeConfig.server_name || 'Mi Servidor Dockraft';
    const minRam = document.getElementById('setting-min-ram')?.value.trim() || this.runtimeConfig.min_ram || '1G';
    const maxRam = document.getElementById('setting-max-ram')?.value.trim() || this.runtimeConfig.max_ram || '2G';
    const select = document.getElementById('setting-java-select');
    let javaPath = 'java';

    if (select && select.value !== 'custom') {
      javaPath = select.value;
    } else {
      const pathEl = document.getElementById('setting-java-path');
      javaPath = pathEl ? pathEl.value.trim() : 'java';
    }

    const aikar = document.getElementById('setting-aikar-flags')?.checked ?? this.runtimeConfig.aikar_flags ?? true;
    const diskEl = document.getElementById('setting-disk-limit');
    const diskLimit = diskEl ? (parseFloat(diskEl.value) || 0) : (this.runtimeConfig.disk_limit_gb || 10);
    const cpuEl = document.getElementById('setting-cpu-cores');
    const cpuCores = cpuEl ? (parseInt(cpuEl.value, 10) || 2) : (this.runtimeConfig.cpu_cores || 2);
    const customFlags = document.getElementById('setting-custom-flags');

    const autostartEl = document.getElementById('setting-autostart-server');
    const crashEl = document.getElementById('setting-crash-detection');
    const autostart = autostartEl ? autostartEl.checked : (this.runtimeConfig.autostart_server || false);
    const crashDetection = crashEl ? crashEl.checked : (this.runtimeConfig.crash_detection !== false);

    const timeoutEl = document.getElementById('setting-session-timeout');
    const sessionTimeout = timeoutEl ? (parseInt(timeoutEl.value, 10) || 60) : (this.runtimeConfig.session_timeout_minutes || 60);

    const payload = {
      ...this.runtimeConfig,
      server_name: serverName,
      min_ram: minRam,
      max_ram: maxRam,
      java_path: javaPath,
      aikar_flags: aikar,
      custom_jvm_flags: customFlags ? customFlags.value.trim() : (this.runtimeConfig.custom_jvm_flags || ''),
      cpu_cores: cpuCores,
      disk_limit_gb: diskLimit,
      autostart_server: autostart,
      crash_detection: crashDetection,
      session_timeout_minutes: sessionTimeout
    };

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        App.showToast(this._t('t_setting_toast_runtime_saved', 'Ajustes de memoria y runtime guardados correctamente'), 'success');
        this.runtimeConfig = payload;
        if (typeof App !== 'undefined' && App.setupSessionMonitoring) {
          App.setupSessionMonitoring(sessionTimeout);
        }
      } else {
        App.showToast(this._t('t_setting_toast_runtime_error', 'Error al guardar los ajustes de memoria'), 'danger');
      }
    } catch (e) {
      App.showToast(e.message, 'danger');
    }
  }
};

window.Settings = Settings;
