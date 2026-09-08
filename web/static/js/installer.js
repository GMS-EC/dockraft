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
        await this.loadUpdateInfo();
      } else {
        this.isLocked = false;
        this.allowForce = true;
        if (banner) banner.style.display = 'none';
        if (mainCard) mainCard.style.display = 'block'; // Mostrar si no hay servidor
        if (btnDelete) btnDelete.style.display = 'none';
        const updateCard = document.getElementById('installer-update-card');
        if (updateCard) updateCard.style.display = 'none';
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

  toggleUnlockReinstall() {
    const btnUnlock = document.getElementById('btn-unlock-reinstall');
    const badge = document.getElementById('reinstall-warning-badge');
    const btnInstall = document.getElementById('btn-install-server');
    const mainCard = document.getElementById('installer-main-card');
    const btnDelete = document.getElementById('btn-delete-server');

    if (this.isLocked) {
      const ok = confirm("¿Deseas desbloquear la reinstalación y opciones avanzadas?\n\nADVERTENCIA: Se desbloqueará la selección de software y la opción de eliminar el servidor actual.");
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

  async loadUpdateInfo() {
    const card = document.getElementById('installer-update-card');
    if (!card) return;

    try {
      const res = await fetch('/api/installer/update-info');
      if (!res.ok) return;
      const data = await res.json();

      if (!data.is_installed) {
        card.style.display = 'none';
        return;
      }

      card.style.display = 'block';
      const typeBadge = document.getElementById('update-server-type-badge');
      const curBadge = document.getElementById('update-current-version-badge');
      const statusBadge = document.getElementById('update-status-badge');
      const previewBadge = document.getElementById('update-preview-badge');
      const select = document.getElementById('update-version-select');
      const warningBadge = document.getElementById('update-warning-badge');

      if (typeBadge) typeBadge.textContent = (data.server_type || '').toUpperCase();

      const chName = data.current_channel === 'stable' ? 'Estable' :
                     data.current_channel === 'pre' ? 'Pre-Release' :
                     data.current_channel === 'preview' ? 'Preview / Beta' : 'Snapshot';

      if (curBadge) {
        curBadge.innerHTML = `Versión Actual: <strong>${data.current_version || 'Desconocida'}</strong> <span style="font-size:0.75rem; opacity:0.85; margin-left:4px;">(${chName})</span>`;
      }

      if (statusBadge) {
        if (data.update_available) {
          statusBadge.textContent = `Nueva versión disponible: ${data.latest_stable}`;
          statusBadge.style.background = 'rgba(56, 139, 253, 0.15)';
          statusBadge.style.borderColor = '#388bfd';
          statusBadge.style.color = '#58a6ff';
        } else {
          statusBadge.textContent = `Servidor actualizado (Estable: ${data.latest_stable || data.current_version})`;
          statusBadge.style.background = 'rgba(46, 160, 67, 0.15)';
          statusBadge.style.borderColor = '#2ea043';
          statusBadge.style.color = '#3fb950';
        }
      }

      if (previewBadge) {
        if (data.preview_available && data.latest_preview) {
          previewBadge.style.display = 'inline-block';
          previewBadge.textContent = `Beta disponible: ${data.latest_preview}`;
        } else {
          previewBadge.style.display = 'none';
        }
      }

      if (select) {
        select.innerHTML = '';
        const items = data.versions || [];
        const stables = items.filter(v => v.channel === 'stable');
        const previews = items.filter(v => v.channel !== 'stable');

        if (stables.length > 0) {
          const optgStable = document.createElement('optgroup');
          optgStable.label = "Versiones Estables (Recomendado)";
          stables.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.label || v.id;
            opt.setAttribute('data-channel', v.channel);
            optgStable.appendChild(opt);
          });
          select.appendChild(optgStable);
        }

        if (previews.length > 0) {
          const optgPrev = document.createElement('optgroup');
          optgPrev.label = "Pre-releases, Snapshots y Betas";
          previews.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.label || v.id;
            opt.setAttribute('data-channel', v.channel);
            optgPrev.appendChild(opt);
          });
          select.appendChild(optgPrev);
        }

        if (stables.length === 0 && previews.length === 0) {
          select.innerHTML = `<option value="${data.current_version}">${data.current_version}</option>`;
        }

        // On change, check if selected option is pre/snapshot and display warning
        const checkWarning = () => {
          const selectedOpt = select.options[select.selectedIndex];
          const ch = selectedOpt ? selectedOpt.getAttribute('data-channel') : 'stable';
          if (warningBadge) {
            if (ch && ch !== 'stable') {
              warningBadge.style.display = 'block';
              warningBadge.textContent = "Advertencia: Has seleccionado una versión de prueba (Pre-Release / Snapshot / Beta). Puede contener errores experimentales y causar incompatibilidades con mundos o plugins.";
            } else {
              warningBadge.style.display = 'none';
            }
          }
        };

        select.onchange = checkWarning;
        checkWarning();
      }

    } catch (err) {
      console.warn("Could not load update info:", err);
    }
  },

  async startUpdate() {
    if (this.isInstalling) return;

    // Check if server is running
    try {
      const sRes = await fetch('/api/server/status');
      const stats = await sRes.json();
      if (stats.status !== 'OFFLINE') {
        App.showToast("Por favor detén el servidor antes de actualizarlo.", 'warning');
        return;
      }
    } catch (e) {}

    const select = document.getElementById('update-version-select');
    if (!select || !select.value) {
      App.showToast("Por favor selecciona una versión válida para actualizar.", 'danger');
      return;
    }

    const targetVer = select.value;
    const ok = confirm(`¿Deseas actualizar tu servidor a la versión "${targetVer}"?\n\nEsta operación reemplazará los binarios del servidor. Tus mundos, configuraciones y plugins se mantendrán intactos.`);
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

      const ok = confirm("ATENCIÓN: ¿Estás completamente seguro de que deseas ELIMINAR el servidor actual?\n\nEsta acción borrará permanentemente los ejecutables, mundos, plugins, mods y archivos de configuración actuales.\n\n(Las copias de seguridad en la pestaña 'Copias de Seguridad' permanecerán intactas y a salvo).\n\n¿Confirmas la eliminación definitiva?");
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
  }
};
