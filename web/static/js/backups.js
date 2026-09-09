// Dockraft Backups Management Script
const Backups = {
  backupsList: [],
  isLoading: false,
  selectedScope: 'full',
  configScope: 'full',
  configTargets: [],
  availableTargets: null,

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

  init() {
    if (this._initialized) return;
    this._initialized = true;
    window.addEventListener('dockraft:language_changed', () => {
      if (typeof App !== 'undefined' && App.activeTab === 'backups') {
        this.loadBackups();
      }
    });
  },

  async loadBackups() {
    await Promise.all([
      this.fetchBackupsList(),
      this.fetchBackupConfig()
    ]);
  },

  async fetchBackupsList() {
    const tableBody = document.getElementById('backups-table-body');
    const emptyState = document.getElementById('backups-empty-state');
    const totalCountEl = document.getElementById('backups-total-count');
    const totalSizeEl = document.getElementById('backups-total-size');

    if (!tableBody) return;

    try {
      const res = await fetch('/api/backups/list');
      if (!res.ok) throw new Error(this._t('t_backup_err_fetch_list', 'Error al obtener la lista de backups'));
      this.backupsList = await res.json();

      let totalBytes = 0;
      this.backupsList.forEach(b => { totalBytes += (b.size_bytes || 0); });

      if (totalCountEl) totalCountEl.textContent = this._tf('t_backup_count_copies', [this.backupsList.length], '{0} copias');
      if (totalSizeEl) totalSizeEl.textContent = this.formatBytes(totalBytes);

      tableBody.innerHTML = '';
      if (this.backupsList.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        return;
      }

      if (emptyState) emptyState.style.display = 'none';

      this.backupsList.forEach(b => {
        const tr = document.createElement('tr');
        
        // Origin badge (Manual vs Auto)
        const originBadge = b.is_auto 
          ? `<span class="badge" style="display:inline-flex; align-items:center; gap:4px; background: rgba(56, 139, 253, 0.15); border: 1px solid #388bfd; color: #58a6ff;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${this._t('t_backup_badge_auto', 'Automático')}</span>`
          : `<span class="badge" style="display:inline-flex; align-items:center; gap:4px; background: rgba(46, 160, 67, 0.15); border: 1px solid #2ea043; color: #3fb950;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg> ${this._t('t_backup_badge_manual', 'Manual')}</span>`;

        // Scope badge
        const scope = b.scope || 'full';
        let scopeBadge = '';
        if (scope === 'worlds') {
          scopeBadge = `<span class="badge-scope badge-scope-worlds">${this._t('t_backup_scope_worlds', 'Solo Mundos')}</span>`;
        } else if (scope === 'worlds_plugins') {
          scopeBadge = `<span class="badge-scope badge-scope-worlds_plugins">${this._t('t_backup_scope_worlds_plugins', 'Mundos + Plugins')}</span>`;
        } else if (scope === 'custom') {
          scopeBadge = `<span class="badge-scope badge-scope-custom">${this._t('t_backup_scope_custom', 'Personalizado')}</span>`;
        } else {
          scopeBadge = `<span class="badge-scope badge-scope-full">${this._t('t_backup_badge_full', 'Completo')}</span>`;
        }

        tr.innerHTML = `
          <td>
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 600; font-family: var(--font-mono); font-size: 0.88rem; color: #c9d1d9;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
              ${this.escapeHtml(b.filename)}
            </div>
          </td>
          <td>${originBadge}</td>
          <td>${scopeBadge}</td>
          <td style="color: var(--text-dim); font-size: 0.85rem;">${b.created_at || '--'}</td>
          <td style="font-family: var(--font-mono); font-size: 0.85rem; color: #79c0ff;">${b.size_formatted || '--'}</td>
          <td style="text-align: right;">
            <div style="display: inline-flex; gap: 6px;">
              <a href="/api/backups/download/${encodeURIComponent(b.filename)}" class="btn btn-outline" style="padding: 4px 10px; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 4px;" title="${this._t('t_backup_download_title', 'Descargar archivo zip')}">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                ${this._t('t_backup_download', 'Descargar')}
              </a>
              <button class="btn btn-warning" style="padding: 4px 10px; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 4px;" data-action="restore" title="${this._t('t_backup_restore_title', 'Restaurar copia de seguridad')}">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
                ${this._t('t_backup_restore', 'Restaurar')}
              </button>
              <button class="btn btn-danger" style="padding: 4px 10px; font-size: 0.8rem; display: inline-flex; align-items: center;" data-action="delete" title="${this._t('t_backup_delete_title', 'Eliminar copia')}">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </td>
        `;
        tr.querySelector('[data-action="restore"]')?.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.restoreBackup(b.filename);
        });
        tr.querySelector('[data-action="delete"]')?.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.deleteBackup(b.filename);
        });
        tableBody.appendChild(tr);
      });

    } catch (err) {
      console.error(err);
      App.showToast(err.message, 'danger');
    }
  },

  openCreateModal() {
    const modal = document.getElementById('modal-create-backup');
    if (modal) {
      modal.classList.add('open');
      this.selectScope('full');
      const tagInput = document.getElementById('backup-modal-tag');
      if (tagInput) tagInput.value = 'manual';

      const compModal = document.getElementById('backup-modal-compression');
      if (compModal) compModal.checked = this.configCompression !== undefined ? this.configCompression : true;

      const stopModal = document.getElementById('backup-modal-stop');
      if (stopModal) stopModal.checked = this.configStopServer !== undefined ? this.configStopServer : false;

      const preCmdModal = document.getElementById('backup-modal-pre-cmd');
      if (preCmdModal) preCmdModal.value = this.configPreCommand !== undefined ? this.configPreCommand : 'save-all';
    }
  },

  closeCreateModal() {
    const modal = document.getElementById('modal-create-backup');
    if (modal) {
      modal.classList.remove('open');
    }
  },

  selectScope(scope) {
    const cleanScope = (scope === 'custom') ? 'custom' : 'full';
    this.selectedScope = cleanScope;
    const cards = document.querySelectorAll('#modal-create-backup .backup-scope-card');
    cards.forEach(c => {
      c.classList.toggle('selected', c.getAttribute('data-scope') === cleanScope);
    });

    const customBox = document.getElementById('backup-custom-targets-box');
    if (cleanScope === 'custom') {
      if (customBox) customBox.style.display = 'block';
      this.loadTargets();
    } else {
      if (customBox) customBox.style.display = 'none';
    }
  },

  selectConfigScope(scope) {
    const cleanScope = (scope === 'custom') ? 'custom' : 'full';
    this.configScope = cleanScope;
    const cards = document.querySelectorAll('.backup-cfg-scope-card');
    cards.forEach(c => {
      c.classList.toggle('selected', c.getAttribute('data-scope') === cleanScope);
    });

    const customBox = document.getElementById('backup-cfg-custom-targets-box');
    if (cleanScope === 'custom') {
      if (customBox) customBox.style.display = 'block';
      this.loadConfigTargets();
    } else {
      if (customBox) customBox.style.display = 'none';
    }
  },

  async loadConfigTargets() {
    const container = document.getElementById('backup-cfg-targets-list');
    if (!container) return;

    if (!this.availableTargets) {
      container.innerHTML = `<div style="color: var(--text-dim); font-size: 0.82rem; padding: 12px; text-align: center;">${this._t('t_backup_analyzing', 'Analizando carpetas del servidor...')}</div>`;
      try {
        const res = await fetch('/api/backups/targets');
        if (res.ok) {
          this.availableTargets = await res.json();
        }
      } catch (e) {}
    }

    container.innerHTML = '';
    if (!this.availableTargets || this.availableTargets.length === 0) {
      container.innerHTML = `<div style="color: var(--text-dim); font-size: 0.82rem; padding: 12px; text-align: center;">${this._t('t_backup_no_targets', 'No hay carpetas ni archivos disponibles en el servidor aún.')}</div>`;
      return;
    }

    const savedTargets = Array.isArray(this.configTargets) ? this.configTargets : [];

    this.availableTargets.forEach(target => {
      const item = document.createElement('div');
      item.className = 'backup-target-item';

      let iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
      if (target.category === 'world' || target.type === 'world') {
        iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';
      } else if (target.category === 'plugin' || target.type === 'plugin') {
        iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>';
      } else if (target.category === 'config' || target.type === 'config') {
        iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
      } else if (!target.is_dir) {
        iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
      }

      let isChecked = false;
      if (savedTargets.length > 0) {
        isChecked = savedTargets.includes(target.name);
      } else {
        isChecked = target.category === 'world' || target.category === 'plugin' || (target.name && (target.name.endsWith('.properties') || target.name.endsWith('.yml')));
      }

      item.innerHTML = `
        <label class="backup-target-label" for="cfg-target-cb-${this.escapeHtml(target.name)}">
          <input type="checkbox" id="cfg-target-cb-${this.escapeHtml(target.name)}" class="backup-cfg-target-cb" value="${this.escapeHtml(target.name)}" ${isChecked ? 'checked' : ''}>
          <span style="display:inline-flex; align-items:center;">${iconSvg}</span>
          <span style="font-family: var(--font-mono);">${this.escapeHtml(target.name)}</span>
        </label>
        <span class="backup-target-size">${target.size_formatted || target.size_fmt || '0 B'}</span>
      `;
      container.appendChild(item);
    });
  },

  toggleAllConfigTargets(check) {
    const cbs = document.querySelectorAll('.backup-cfg-target-cb');
    cbs.forEach(cb => { cb.checked = !!check; });
  },

  async loadTargets() {
    const container = document.getElementById('backup-targets-list');
    if (!container) return;

    if (this.availableTargets && container.children.length > 0) {
      return;
    }

    container.innerHTML = `<div style="color: var(--text-dim); font-size: 0.82rem; padding: 12px; text-align: center;">${this._t('t_backup_analyzing', 'Analizando carpetas del servidor...')}</div>`;

    try {
      const res = await fetch('/api/backups/targets');
      if (!res.ok) throw new Error(this._t('t_backup_err_targets', 'Error al consultar estructura de carpetas'));
      this.availableTargets = await res.json();

      container.innerHTML = '';
      if (this.availableTargets.length === 0) {
        container.innerHTML = `<div style="color: var(--text-dim); font-size: 0.82rem; padding: 12px; text-align: center;">${this._t('t_backup_no_targets', 'No hay carpetas ni archivos disponibles en el servidor aún.')}</div>`;
        return;
      }

      this.availableTargets.forEach(target => {
        const item = document.createElement('div');
        item.className = 'backup-target-item';

        let iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
        let defaultChecked = true;
        if (target.type === 'world') {
          iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';
        } else if (target.type === 'plugin') {
          iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>';
        } else if (target.type === 'config') {
          iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
        } else if (!target.is_dir) {
          iconSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
          defaultChecked = target.name.endsWith('.properties') || target.name.endsWith('.json') || target.name.endsWith('.yml');
        }

        item.innerHTML = `
          <label class="backup-target-label" for="target-cb-${this.escapeHtml(target.name)}">
            <input type="checkbox" id="target-cb-${this.escapeHtml(target.name)}" class="backup-target-cb" value="${this.escapeHtml(target.name)}" ${defaultChecked ? 'checked' : ''}>
            <span style="display:inline-flex; align-items:center;">${iconSvg}</span>
            <span style="font-family: var(--font-mono);">${this.escapeHtml(target.name)}</span>
          </label>
          <span class="backup-target-size">${target.size_fmt || '0 B'}</span>
        `;
        container.appendChild(item);
      });

    } catch (err) {
      container.innerHTML = `<div style="color: #f85149; font-size: 0.82rem; padding: 8px;">${this._tf('t_backup_err_loading_targets', [err.message], 'Error al cargar elementos: {0}')}</div>`;
    }
  },

  toggleAllTargets(check) {
    const cbs = document.querySelectorAll('.backup-target-cb');
    cbs.forEach(cb => { cb.checked = !!check; });
  },

  async submitCreateBackup() {
    const btn = document.getElementById('btn-modal-submit-backup');
    const progBox = document.getElementById('backup-progress-box');
    const tagInput = document.getElementById('backup-modal-tag');
    const tag = (tagInput ? tagInput.value.trim() : '') || 'manual';

    const compModal = document.getElementById('backup-modal-compression');
    const stopModal = document.getElementById('backup-modal-stop');
    const preCmdModal = document.getElementById('backup-modal-pre-cmd');

    const compression = compModal ? compModal.checked : true;
    const stopServer = stopModal ? stopModal.checked : false;
    const preCommand = preCmdModal ? preCmdModal.value.trim() : 'save-all';

    let selectedTargets = null;

    if (this.selectedScope === 'custom') {
      const cbs = document.querySelectorAll('.backup-target-cb:checked');
      selectedTargets = Array.from(cbs).map(cb => cb.value);
      if (selectedTargets.length === 0) {
        App.showToast(this._t('t_backup_warn_select_target', 'Debes seleccionar al menos una carpeta o archivo para respaldar'), 'warning');
        return;
      }
    }

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<span class="spin-icon">↻</span> ${this._t('t_backup_compressing', 'Comprimiendo...')}`;
    }
    if (progBox) progBox.style.display = 'block';

    try {
      App.showToast(this._t('t_backup_toast_start_compression', 'Iniciando compresión del respaldo...'), 'info');
      
      const payload = {
        tag: tag,
        scope: this.selectedScope,
        targets: selectedTargets,
        compression: compression,
        stop_server: stopServer,
        pre_command: preCommand
      };

      const res = await fetch('/api/backups/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || this._t('t_backup_err_create', 'Error al crear la copia de seguridad'));

      App.showToast(this._tf('t_backup_toast_created', [data.filename, data.size_formatted], 'Copia creada con éxito: {0} ({1})'), 'success');
      this.closeCreateModal();
      await this.fetchBackupsList();
    } catch (err) {
      App.showToast(err.message, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> ${this._t('t_backup_create_btn', 'Crear Copia de Seguridad')}`;
      }
      if (progBox) progBox.style.display = 'none';
    }
  },

  async restoreBackup(filename) {
    const ok = await App.confirm({
      title: this._t('t_backup_confirm_restore_title', 'Restaurar Copia de Seguridad'),
      message: this._tf('t_backup_confirm_restore_msg', [filename], "¿Estás seguro de que deseas restaurar la copia de seguridad '{0}'?\n\nADVERTENCIA: Esta acción reemplazará los archivos y mundos actuales por los contenidos en la copia de seguridad. El servidor debe estar APAGADO."),
      confirmText: this._t('t_backup_confirm_restore_btn', 'Restaurar Copia'),
      warning: true
    });
    if (!ok) return;

    try {
      App.showToast(this._t('t_backup_toast_restoring', 'Restaurando copia de seguridad...'), 'info');
      const res = await fetch('/api/backups/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || this._t('t_backup_err_restore', 'Error al restaurar la copia'));

      App.showToast(this._t('t_backup_toast_restored', 'Copia de seguridad restaurada correctamente.'), 'success');
    } catch (err) {
      App.showToast(err.message, 'danger');
    }
  },

  async deleteBackup(filename) {
    const ok = await App.confirm({
      title: this._t('t_backup_confirm_delete_title', 'Eliminar Copia de Seguridad'),
      message: this._tf('t_backup_confirm_delete_msg', [filename], "¿Deseas eliminar permanentemente la copia de seguridad '{0}'?"),
      confirmText: this._t('t_backup_confirm_delete_btn', 'Eliminar Copia'),
      danger: true
    });
    if (!ok) return;

    try {
      const res = await fetch(`/api/backups/${encodeURIComponent(filename)}`, {
        method: 'DELETE'
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || this._t('t_backup_err_delete', 'Error al eliminar copia'));

      App.showToast(this._t('t_backup_toast_deleted', 'Copia de seguridad eliminada'), 'success');
      await this.fetchBackupsList();
    } catch (err) {
      App.showToast(err.message, 'danger');
    }
  },

  async fetchBackupConfig() {
    try {
      const res = await fetch('/api/backups/config');
      if (!res.ok) return;
      const cfg = await res.json();

      const inputMax = document.getElementById('backup-config-max');
      if (inputMax) inputMax.value = cfg.backup_max_count || 5;

      const compToggle = document.getElementById('backup-config-compression');
      if (compToggle) compToggle.checked = cfg.backup_compression !== false;

      const stopToggle = document.getElementById('backup-config-stop');
      if (stopToggle) stopToggle.checked = !!cfg.backup_stop_server;

      const preCmdInput = document.getElementById('backup-config-pre-cmd');
      if (preCmdInput) preCmdInput.value = cfg.backup_pre_command !== undefined ? cfg.backup_pre_command : 'save-all';

      this.configCompression = cfg.backup_compression !== false;
      this.configStopServer = !!cfg.backup_stop_server;
      this.configPreCommand = cfg.backup_pre_command !== undefined ? cfg.backup_pre_command : 'save-all';

      this.configScope = (cfg.backup_scope === 'custom') ? 'custom' : 'full';
      this.configTargets = Array.isArray(cfg.backup_targets) ? cfg.backup_targets : [];
      this.selectConfigScope(this.configScope);
    } catch (err) {
      console.warn("Could not fetch backup config:", err);
    }
  },

  async saveBackupConfig() {
    const inputMax = document.getElementById('backup-config-max');
    const compToggle = document.getElementById('backup-config-compression');
    const stopToggle = document.getElementById('backup-config-stop');
    const preCmdInput = document.getElementById('backup-config-pre-cmd');

    let selectedTargets = [];

    if (this.configScope === 'custom') {
      const cbs = document.querySelectorAll('.backup-cfg-target-cb:checked');
      selectedTargets = Array.from(cbs).map(cb => cb.value);
      if (selectedTargets.length === 0) {
        App.showToast(this._t('t_backup_warn_select_target', 'Debes seleccionar al menos una carpeta o archivo para respaldar'), 'warning');
        return;
      }
    }

    const payload = {
      backup_max_count: parseInt(inputMax?.value || '5', 10),
      backup_scope: this.configScope || 'full',
      backup_targets: selectedTargets,
      backup_compression: compToggle ? compToggle.checked : true,
      backup_stop_server: stopToggle ? stopToggle.checked : false,
      backup_pre_command: preCmdInput ? preCmdInput.value.trim() : 'save-all'
    };

    try {
      const res = await fetch('/api/backups/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || this._t('t_backup_err_save_cfg', 'Error guardando configuración de respaldo'));

      this.configCompression = payload.backup_compression;
      this.configStopServer = payload.backup_stop_server;
      this.configPreCommand = payload.backup_pre_command;

      App.showToast(this._t('t_backup_toast_cfg_saved', 'Configuración de alcance y retención guardada correctamente.'), 'success');
    } catch (err) {
      App.showToast(err.message, 'danger');
    }
  },

  saveRetentionConfig() {
    return this.saveBackupConfig();
  },

  formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => Backups.init());
} else {
  Backups.init();
}
