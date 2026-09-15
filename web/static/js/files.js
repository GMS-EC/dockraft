// Dockraft File Manager Script
const Files = {
  currentPath: '',
  activeEditingPath: '',
  activeRenamePath: '',
  initialized: false,
  rawItems: [],
  searchQuery: '',
  selectedPaths: new Set(),
  dragTargetCounter: 0,
  editorInitDone: false,

  tr(key, fallback) {
    return (typeof I18n !== 'undefined' && I18n.t) ? I18n.t(key, fallback) : fallback;
  },

  trf(key, args, fallback) {
    return (typeof I18n !== 'undefined' && I18n.fmt) ? I18n.fmt(key, args, fallback) : fallback;
  },

  init() {
    if (this.initialized) return;
    this.initialized = true;

    // Global listener: close context menu on click outside
    window.addEventListener('click', (e) => {
      if (!e.target.closest('#file-context-menu') && !e.target.closest('.mobile-more-btn')) {
        this.hideContextMenu();
      }
    });

    // Close context menu and modals on Escape
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.hideContextMenu();
        this.closeRenameModal();
        this.closeCreateFileModal();
      }
    });

    // Close context menu on page scroll
    window.addEventListener('scroll', () => {
      this.hideContextMenu();
    }, true);

    // Re-render the current listing (translated) when the UI language changes
    window.addEventListener('dockraft:language_changed', () => {
      if ((typeof App === 'undefined' || App.activeTab === 'files') && document.getElementById('files-table-body')) {
        this.loadDirectory(this.currentPath);
      }
    });

    // Background right-click on the table
    const table = document.getElementById('file-manager-table');
    if (table) {
      table.addEventListener('contextmenu', (e) => {
        if (e.target.closest('.file-row')) return;
        this.showContextMenu(e, null);
      });
    }

    // Setup Drag and Drop
    this.setupDragAndDrop();
  },

  setupDragAndDrop() {
    const card = document.getElementById('file-manager-card') || document.getElementById('tab-files');
    const overlay = document.getElementById('file-dropzone-overlay');
    const targetText = document.getElementById('dropzone-target-text');
    if (!card || !overlay) return;

    const showOverlay = (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.dragTargetCounter++;
      if (e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes('Files')) {
        if (targetText) {
          const dest = this.currentPath ? `/data/${this.currentPath}` : '/data';
          targetText.textContent = this.trf('t_file_dropzone_target', [this.currentPath || ''], `Destino: ${dest}`);
        }
        overlay.style.display = 'flex';
      }
    };

    const hideOverlay = (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.dragTargetCounter--;
      if (this.dragTargetCounter <= 0) {
        this.dragTargetCounter = 0;
        overlay.style.display = 'none';
      }
    };

    card.addEventListener('dragenter', showOverlay);
    card.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    });
    card.addEventListener('dragleave', hideOverlay);
    card.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.dragTargetCounter = 0;
      overlay.style.display = 'none';

      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        this.uploadFiles(e.dataTransfer.files);
      }
    });
  },

  async loadDirectory(path = '') {
    this.currentPath = path;
    this.selectedPaths.clear();
    this.updateBulkBar();

    // Reset search input on directory change
    const searchInput = document.getElementById('file-search-input');
    if (searchInput) searchInput.value = '';
    this.searchQuery = '';

    const tbody = document.getElementById('files-table-body');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-dim);">' + this.tr('t_file_loading', 'Cargando archivos...') + '</td></tr>';
    this.updateBreadcrumbs(path);
    this.hideContextMenu();

    try {
      const res = await fetch(`/api/files/list?path=${encodeURIComponent(path)}`);
      if (!res.ok) throw new Error(this.tr('t_file_err_list', 'No se pudieron listar los archivos'));
      const data = await res.json();
      this.rawItems = Array.isArray(data.items) ? data.items : [];
      this.renderFileList(this.rawItems);
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--status-danger);">${this.escapeHtml(e.message)}</td></tr>`;
    }
  },

  updateBreadcrumbs(path) {
    const container = document.getElementById('file-breadcrumbs');
    if (!container) return;

    container.innerHTML = '';
    const rootCrumb = document.createElement('span');
    rootCrumb.className = 'crumb-item';
    rootCrumb.textContent = '/data';
    rootCrumb.addEventListener('click', () => this.loadDirectory(''));
    container.appendChild(rootCrumb);

    if (!path) return;

    const parts = path.split('/').filter(p => p.length > 0);
    let accum = '';
    parts.forEach(p => {
      accum += (accum ? '/' : '') + p;
      const thisPath = accum;

      const sep = document.createElement('span');
      sep.className = 'crumb-sep';
      sep.textContent = ' / ';
      container.appendChild(sep);

      const item = document.createElement('span');
      item.className = 'crumb-item';
      item.textContent = p;
      item.addEventListener('click', () => this.loadDirectory(thisPath));
      container.appendChild(item);
    });
  },

  filterFiles(query) {
    this.searchQuery = (query || '').toLowerCase().trim();
    if (!this.searchQuery) {
      this.renderFileList(this.rawItems, true);
    } else {
      const filtered = this.rawItems.filter(it => it.name.toLowerCase().includes(this.searchQuery));
      this.renderFileList(filtered, true);
    }
  },

  renderFileList(items, isFiltered = false) {
    const tbody = document.getElementById('files-table-body');
    if (!tbody) return;

    if (!isFiltered) {
      this.rawItems = items || [];
      if (this.searchQuery) {
        items = this.rawItems.filter(it => it.name.toLowerCase().includes(this.searchQuery));
      }
    }

    if (!items || items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:24px; color:var(--text-dim);">' + this.tr('t_file_empty', 'La carpeta está vacía. Haz clic derecho para crear archivos.') + '</td></tr>';
      this.syncSelectAllCheckbox();
      return;
    }

    tbody.innerHTML = '';

    // If inside a subfolder, add '..' parent directory row
    if (this.currentPath && !this.searchQuery) {
      const parentRow = document.createElement('tr');
      parentRow.className = 'file-row';
      parentRow.innerHTML = `
        <td style="text-align: center; color: var(--text-dim);">-</td>
        <td colspan="4">
          <div class="file-name-cell">
            <span class="file-icon" style="display:inline-flex; align-items:center;">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            </span>
            <span>${this.tr('t_file_up_level', '.. (Subir un nivel)')}</span>
          </div>
        </td>
      `;
      parentRow.querySelector('.file-name-cell').addEventListener('click', () => {
        const parts = this.currentPath.split('/');
        parts.pop();
        this.loadDirectory(parts.join('/'));
      });
      parentRow.addEventListener('contextmenu', (e) => {
        this.showContextMenu(e, null);
      });
      tbody.appendChild(parentRow);
    }

    items.forEach(item => {
      const row = document.createElement('tr');
      const itemRelativePath = (this.currentPath ? this.currentPath + '/' : '') + item.name;
      const isSelected = this.selectedPaths.has(itemRelativePath);

      row.className = `file-row ${isSelected ? 'row-selected' : ''}`;
      row.dataset.path = itemRelativePath;

      const iconSvg = item.is_dir 
        ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`
        : this.getFileIcon(item.extension);
      const formattedSize = item.is_dir ? '-' : this.formatBytes(item.size);
      const formattedDate = new Date(item.modified * 1000).toLocaleString();

      row.innerHTML = `
        <td style="width: 38px; text-align: center;" class="file-select-cell">
          <input type="checkbox" class="form-checkbox file-item-checkbox" data-path="${this.escapeHtml(itemRelativePath)}" ${isSelected ? 'checked' : ''}>
        </td>
        <td>
          <div class="file-name-cell">
            <span class="file-icon" style="display:inline-flex; align-items:center;">${iconSvg}</span>
            <span>${this.escapeHtml(item.name)}</span>
          </div>
        </td>
        <td style="color:var(--text-muted);">${formattedSize}</td>
        <td class="col-modified" style="color:var(--text-dim); font-size:0.8rem;">${formattedDate}</td>
        <td>
          <div class="file-actions">
            ${!item.is_dir && this.isEditable(item.extension) ? 
              `<button class="action-icon-btn btn-edit" title="${this.tr('t_file_tip_edit', 'Editar archivo')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>` : ''}
            ${!item.is_dir && item.extension === 'zip' ? 
              `<button class="action-icon-btn btn-unzip" title="${this.tr('t_file_tip_unzip', 'Extraer ZIP')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg></button>` : ''}
            ${!item.is_dir ? 
              `<button class="action-icon-btn btn-dl" title="${this.tr('t_file_download', 'Descargar')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></button>` : ''}
            <button class="action-icon-btn danger btn-del" title="${this.tr('t_file_delete', 'Eliminar')}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg></button>
            <button class="action-icon-btn mobile-more-btn btn-more" title="${this.tr('t_file_col_actions', 'Acciones')}"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></button>
          </div>
        </td>
      `;

      // Checkbox click
      const checkbox = row.querySelector('.file-item-checkbox');
      if (checkbox) {
        checkbox.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleRowSelect(itemRelativePath, checkbox.checked, row);
        });
      }

      // Name cell click
      const nameCell = row.querySelector('.file-name-cell');
      nameCell.addEventListener('click', () => {
        if (item.is_dir) {
          this.loadDirectory(itemRelativePath);
        } else if (this.isEditable(item.extension)) {
          this.openEditor(itemRelativePath);
        }
      });

      // Actions
      const editBtn = row.querySelector('.btn-edit');
      if (editBtn) editBtn.addEventListener('click', () => this.openEditor(itemRelativePath));

      const unzipBtn = row.querySelector('.btn-unzip');
      if (unzipBtn) unzipBtn.addEventListener('click', () => this.unzipFile(itemRelativePath));

      const dlBtn = row.querySelector('.btn-dl');
      if (dlBtn) dlBtn.addEventListener('click', () => this.downloadFile(itemRelativePath));

      const delBtn = row.querySelector('.btn-del');
      if (delBtn) delBtn.addEventListener('click', () => this.deleteItem(itemRelativePath, item.name));

      // Mobile More button click
      const moreBtn = row.querySelector('.btn-more');
      if (moreBtn) {
        moreBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          const rect = moreBtn.getBoundingClientRect();
          const fakeEvent = {
            preventDefault() {},
            stopPropagation() {},
            clientX: rect.left - 150,
            clientY: rect.bottom + 4
          };
          this.showContextMenu(fakeEvent, item, itemRelativePath, row);
        });
      }

      // Right-click context menu event
      row.addEventListener('contextmenu', (e) => {
        this.showContextMenu(e, item, itemRelativePath, row);
      });

      tbody.appendChild(row);
    });

    this.syncSelectAllCheckbox();
  },

  toggleRowSelect(path, isChecked, rowElement) {
    if (isChecked) {
      this.selectedPaths.add(path);
      if (rowElement) rowElement.classList.add('row-selected');
    } else {
      this.selectedPaths.delete(path);
      if (rowElement) rowElement.classList.remove('row-selected');
    }
    this.updateBulkBar();
  },

  toggleSelectAll(checked) {
    const checkboxes = document.querySelectorAll('.file-item-checkbox');
    checkboxes.forEach(cb => {
      const p = cb.getAttribute('data-path');
      cb.checked = checked;
      const r = cb.closest('.file-row');
      if (checked) {
        this.selectedPaths.add(p);
        if (r) r.classList.add('row-selected');
      } else {
        this.selectedPaths.delete(p);
        if (r) r.classList.remove('row-selected');
      }
    });
    this.updateBulkBar();
  },

  clearSelection() {
    this.selectedPaths.clear();
    document.querySelectorAll('.file-item-checkbox').forEach(cb => {
      cb.checked = false;
      const r = cb.closest('.file-row');
      if (r) r.classList.remove('row-selected');
    });
    this.updateBulkBar();
  },

  updateBulkBar() {
    const bulkBar = document.getElementById('files-bulk-bar');
    const countEl = document.getElementById('bulk-selected-count');
    const count = this.selectedPaths.size;

    if (count > 0) {
      if (bulkBar) bulkBar.style.display = 'flex';
      if (countEl) countEl.textContent = this.trf('t_file_bulk_selected', [count], `${count} seleccionados`);
    } else {
      if (bulkBar) bulkBar.style.display = 'none';
    }

    this.syncSelectAllCheckbox();
  },

  syncSelectAllCheckbox() {
    const selectAll = document.getElementById('file-select-all');
    if (!selectAll) return;
    const checkboxes = Array.from(document.querySelectorAll('.file-item-checkbox'));
    if (checkboxes.length === 0) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      return;
    }
    const allChecked = checkboxes.every(cb => cb.checked);
    const someChecked = checkboxes.some(cb => cb.checked);
    selectAll.checked = allChecked;
    selectAll.indeterminate = !allChecked && someChecked;
  },

  async bulkDelete() {
    if (this.selectedPaths.size === 0) return;
    const count = this.selectedPaths.size;

    const ok = await App.confirm({
      title: this.tr('t_file_bulk_delete_confirm_title', 'Eliminar Elementos Seleccionados'),
      message: this.trf('t_file_bulk_delete_confirm_msg', [count], `¿Confirmas la eliminación permanente de los ${count} elementos seleccionados?`),
      confirmText: this.tr('t_file_bulk_delete', 'Eliminar'),
      danger: true
    });
    if (!ok) return;

    const paths = Array.from(this.selectedPaths);
    try {
      const res = await fetch('/api/files/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths })
      });
      const data = await res.json();
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(this.trf('t_file_bulk_deleted', [data.deleted_count || count], `${data.deleted_count || count} elementos eliminados`), 'success');
        }
        this.clearSelection();
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(data.detail || this.tr('t_file_bulk_err_delete', 'Error al eliminar algunos elementos'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async bulkCompress() {
    if (this.selectedPaths.size === 0) return;
    const count = this.selectedPaths.size;
    const defaultName = (this.currentPath ? this.currentPath.split('/').pop() : 'dockraft') + '_bundle.zip';

    const archiveName = await App.prompt({
      title: this.tr('t_file_bulk_compress', 'Comprimir ZIP'),
      message: this.tr('t_file_bulk_compress_prompt', 'Nombre para el archivo ZIP:'),
      defaultValue: defaultName,
      confirmText: this.tr('t_file_bulk_compress', 'Comprimir ZIP')
    });
    if (!archiveName || !archiveName.trim()) return;

    if (typeof App !== 'undefined' && App.showToast) {
      App.showToast(this.trf('t_file_bulk_compressing', [count], `Comprimiendo ${count} elementos...`), 'info');
    }

    const paths = Array.from(this.selectedPaths);
    try {
      const res = await fetch('/api/files/bulk-compress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths,
          target_dir: this.currentPath,
          archive_name: archiveName.trim()
        })
      });
      const data = await res.json();
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(this.trf('t_file_bulk_compressed', [data.archive_name], `Archivo ZIP creado: "${data.archive_name}"`), 'success');
        }
        this.clearSelection();
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(data.detail || this.tr('t_file_bulk_err_compress', 'Error al comprimir elementos'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  showContextMenu(e, item = null, itemRelativePath = '', targetRow = null) {
    e.preventDefault();
    e.stopPropagation();

    // Clear existing highlight
    document.querySelectorAll('.file-row.context-selected').forEach(r => r.classList.remove('context-selected'));
    if (targetRow) {
      targetRow.classList.add('context-selected');
    }

    const menu = document.getElementById('file-context-menu');
    if (!menu) return;

    menu.innerHTML = '';
    const actions = this._buildContextActions(item, itemRelativePath);

    if (!item) {
      // Background context menu
      menu.innerHTML = `
        <button type="button" class="context-menu-item" data-act="newFile">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>
          <span>${this.tr('t_file_new_file', 'Nuevo Archivo')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="newFolder">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
          <span>${this.tr('t_file_new_folder', 'Nueva Carpeta')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="upload">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          <span>${this.tr('t_file_upload', 'Subir Archivo')}</span>
        </button>
        <div class="context-menu-divider"></div>
        <button type="button" class="context-menu-item" data-act="refresh">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
          <span>${this.tr('t_file_refresh', 'Refrescar')}</span>
        </button>
      `;
    } else if (item.is_dir) {
      // Folder context menu
      menu.innerHTML = `
        <button type="button" class="context-menu-item" data-act="open">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          <span>${this.tr('t_file_open_folder', 'Abrir Carpeta')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="rename">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          <span>${this.tr('t_file_rename', 'Renombrar')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="compress">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
          <span>${this.tr('t_file_compress_zip', 'Comprimir a .ZIP')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="duplicate">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>${this.tr('t_file_duplicate', 'Duplicar')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="copy">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          <span>${this.tr('t_file_copy_path', 'Copiar ruta')}</span>
        </button>
        <div class="context-menu-divider"></div>
        <button type="button" class="context-menu-item danger" data-act="delete">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          <span>${this.tr('t_file_delete_folder', 'Eliminar Carpeta')}</span>
        </button>
      `;
    } else {
      // File context menu
      const canEdit = this.isEditable(item.extension);
      const isZip = item.extension === 'zip';

      let itemsHtml = '';
      if (canEdit) {
        itemsHtml += `
          <button type="button" class="context-menu-item" data-act="edit">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            <span>${this.tr('t_file_edit_file', 'Editar Archivo')}</span>
          </button>
        `;
      }
      if (isZip) {
        itemsHtml += `
          <button type="button" class="context-menu-item" data-act="unzip">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
            <span>${this.tr('t_file_unzip_here', 'Extraer aquí')}</span>
          </button>
        `;
      }

      itemsHtml += `
        <button type="button" class="context-menu-item" data-act="download">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>${this.tr('t_file_download', 'Descargar')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="rename">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          <span>${this.tr('t_file_rename', 'Renombrar')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="compress">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
          <span>${this.tr('t_file_compress_zip', 'Comprimir a .ZIP')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="duplicate">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>${this.tr('t_file_duplicate', 'Duplicar')}</span>
        </button>
        <button type="button" class="context-menu-item" data-act="copy">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          <span>${this.tr('t_file_copy_path', 'Copiar ruta')}</span>
        </button>
        <div class="context-menu-divider"></div>
        <button type="button" class="context-menu-item danger" data-act="delete">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          <span>${this.tr('t_file_delete', 'Eliminar')}</span>
        </button>
      `;
      menu.innerHTML = itemsHtml;
    }

    // Bind actions via closures (no inline onclick with user-controlled data => XSS-safe)
    menu.querySelectorAll('.context-menu-item[data-act]').forEach(btn => {
      const handler = actions[btn.getAttribute('data-act')];
      if (!handler) return;
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        this.hideContextMenu();
        handler();
      });
    });

    // Position context menu safely within viewport
    menu.style.display = 'flex';
    menu.classList.add('open');

    const rect = menu.getBoundingClientRect();
    let x = e.clientX;
    let y = e.clientY;

    if (x + rect.width > window.innerWidth) {
      x = window.innerWidth - rect.width - 12;
    }
    if (y + rect.height > window.innerHeight) {
      y = window.innerHeight - rect.height - 12;
    }

    menu.style.left = `${Math.max(10, x)}px`;
    menu.style.top = `${Math.max(10, y)}px`;
  },

  hideContextMenu() {
    const menu = document.getElementById('file-context-menu');
    if (menu) {
      menu.classList.remove('open');
      menu.style.display = 'none';
    }
    document.querySelectorAll('.file-row.context-selected').forEach(r => r.classList.remove('context-selected'));
  },

  downloadFile(filePath) {
    this.hideContextMenu();
    window.open(`/api/files/download?path=${encodeURIComponent(filePath)}`);
  },

  async copyPath(filePath) {
    this.hideContextMenu();
    const fullRel = `/data/${filePath}`;
    try {
      await navigator.clipboard.writeText(fullRel);
      if (typeof App !== 'undefined' && App.showToast) {
        App.showToast(this.trf('t_file_path_copied', [fullRel], `Ruta copiada: ${fullRel}`), 'success');
      }
    } catch (e) {
      await App.prompt({
        title: this.tr('t_file_path_prompt_title', 'Ruta del elemento'),
        message: this.tr('t_file_path_prompt_msg', 'Copia la siguiente ruta:'),
        defaultValue: fullRel,
        confirmText: this.tr('t_file_btn_accept', 'Aceptar')
      });
    }
  },

  openRenameModal(filePath, currentName) {
    this.hideContextMenu();
    this.activeRenamePath = filePath;
    const modal = document.getElementById('modal-file-rename');
    const input = document.getElementById('input-file-rename');
    if (input) input.value = currentName;
    if (modal) modal.classList.add('open');
    if (input) setTimeout(() => {
      input.focus();
      const dotIdx = currentName.lastIndexOf('.');
      if (dotIdx > 0) {
        input.setSelectionRange(0, dotIdx);
      } else {
        input.select();
      }
    }, 60);
  },

  closeRenameModal() {
    const modal = document.getElementById('modal-file-rename');
    if (modal) modal.classList.remove('open');
    this.activeRenamePath = '';
  },

  async submitRename() {
    const input = document.getElementById('input-file-rename');
    const newName = input ? input.value.trim() : '';
    if (!newName || !this.activeRenamePath) return;

    try {
      const res = await fetch('/api/files/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.activeRenamePath, new_name: newName })
      });
      const data = await res.json();
      if (res.ok) {
        this.closeRenameModal();
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(this.trf('t_file_renamed_to', [data.name], `Renombrado a "${data.name}"`), 'success');
        }
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(data.detail || this.tr('t_file_err_rename', 'Error al renombrar'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  openCreateFileModal() {
    this.hideContextMenu();
    const modal = document.getElementById('modal-file-create');
    const input = document.getElementById('input-file-create-name');
    if (input) input.value = '';
    if (modal) modal.classList.add('open');
    if (input) setTimeout(() => input.focus(), 60);
  },

  closeCreateFileModal() {
    const modal = document.getElementById('modal-file-create');
    if (modal) modal.classList.remove('open');
  },

  async submitCreateFile() {
    const input = document.getElementById('input-file-create-name');
    const fileName = input ? input.value.trim() : '';
    if (!fileName) return;

    const newPath = (this.currentPath ? this.currentPath + '/' : '') + fileName;
    try {
      const res = await fetch('/api/files/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newPath })
      });
      const data = await res.json();
      if (res.ok) {
        this.closeCreateFileModal();
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(this.trf('t_file_created', [fileName], `Archivo "${fileName}" creado`), 'success');
        }
        await this.loadDirectory(this.currentPath);
        const ext = fileName.split('.').pop().toLowerCase();
        if (this.isEditable(ext)) {
          this.openEditor(newPath);
        }
      } else {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(data.detail || this.tr('t_file_err_create', 'Error al crear archivo'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async duplicateItem(filePath, name) {
    this.hideContextMenu();
    if (typeof App !== 'undefined' && App.showToast) App.showToast(this.trf('t_file_duplicating', [name], `Duplicando "${name}"...`), 'info');
    try {
      const res = await fetch('/api/files/duplicate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath })
      });
      const data = await res.json();
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(this.trf('t_file_copy_created', [data.new_name], `Copia creada: "${data.new_name}"`), 'success');
        }
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(data.detail || this.tr('t_file_err_duplicate', 'Error al duplicar'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async compressItem(filePath, name) {
    this.hideContextMenu();
    if (typeof App !== 'undefined' && App.showToast) App.showToast(this.trf('t_file_compressing', [name], `Comprimiendo "${name}" a .zip...`), 'info');
    try {
      const res = await fetch('/api/files/compress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath })
      });
      const data = await res.json();
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(this.trf('t_file_compressed', [data.archive_name], `Archivo comprimido: "${data.archive_name}"`), 'success');
        }
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) {
          App.showToast(data.detail || this.tr('t_file_err_compress', 'Error al comprimir'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  getFileIcon(ext) {
    switch (ext) {
      case 'jar':
        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ec4899" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>`;
      case 'zip':
      case 'tar':
      case 'gz':
        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>`;
      case 'yml':
      case 'yaml':
      case 'properties':
      case 'json':
      case 'conf':
      case 'cfg':
        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`;
      case 'txt':
      case 'log':
        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'ico':
        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`;
      default:
        return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
    }
  },

  isEditable(ext) {
    const BINARY_EXTENSIONS = new Set([
      'jar', 'zip', 'gz', 'tar', 'rar', '7z', 'bz2', 'xz', 'zst', 'lz4',
      'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'ico', 'tiff', 'tif',
      'mp3', 'wav', 'ogg', 'flac', 'mp4', 'avi', 'mkv', 'mov', 'webm',
      'exe', 'dll', 'so', 'dylib', 'bin', 'elf', 'o', 'a', 'lib', 'class',
      'db', 'sqlite', 'sqlite3', 'dat', 'nbt', 'mca', 'mcworld', 'ldb',
      'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
      'ttf', 'otf', 'woff', 'woff2', 'eot'
    ]);
    return !BINARY_EXTENSIONS.has((ext || '').toLowerCase());
  },

  formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  setupEditorListeners() {
    if (this.editorInitDone) return;
    this.editorInitDone = true;

    const textarea = document.getElementById('editor-textarea');
    if (!textarea) return;

    // Tab key inserts 2 spaces without losing focus
    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const value = textarea.value;
        textarea.value = value.substring(0, start) + '  ' + value.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + 2;
        this.updateEditorStatusBar();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        this.saveCurrentFile();
      }
    });

    textarea.addEventListener('input', () => this.updateEditorStatusBar());
    textarea.addEventListener('keyup', () => this.updateEditorStatusBar());
    textarea.addEventListener('click', () => this.updateEditorStatusBar());

    // Window Ctrl+S shortcut when modal is open
    window.addEventListener('keydown', (e) => {
      const modal = document.getElementById('file-editor-modal');
      if (modal && modal.classList.contains('open')) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault();
          this.saveCurrentFile();
        }
      }
    });
  },

  updateEditorStatusBar() {
    const textarea = document.getElementById('editor-textarea');
    const posEl = document.getElementById('editor-cursor-pos');
    const charEl = document.getElementById('editor-char-count');
    if (!textarea || !posEl || !charEl) return;

    const val = textarea.value || '';
    const pos = textarea.selectionStart || 0;
    const textBefore = val.substring(0, pos);
    const line = textBefore.split('\n').length;
    const lastNewline = textBefore.lastIndexOf('\n');
    const col = lastNewline === -1 ? pos + 1 : pos - lastNewline;
    const charCount = val.length;

    posEl.textContent = `Línea ${line}, Columna ${col}`;
    charEl.textContent = `${charCount} caracteres`;
  },

  async openEditor(filePath) {
    this.hideContextMenu();
    this.activeEditingPath = filePath;
    this.setupEditorListeners();

    const modal = document.getElementById('file-editor-modal');
    const title = document.getElementById('editor-file-title');
    const textarea = document.getElementById('editor-textarea');
    const saveBtn = document.getElementById('btn-editor-save');

    if (title) title.textContent = filePath;
    if (textarea) { 
      textarea.value = this.tr('t_file_loading_file', 'Cargando archivo...'); 
      textarea.disabled = false; 
    }
    if (saveBtn) saveBtn.disabled = false;
    if (modal) modal.classList.add('open');

    try {
      const res = await fetch(`/api/files/content?path=${encodeURIComponent(filePath)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || this.tr('t_file_err_load', 'Error al cargar el archivo'));
      if (textarea) {
        textarea.value = data.content;
        this.updateEditorStatusBar();
      }
    } catch (e) {
      if (textarea) {
        textarea.value = this.trf('t_file_err_open_big', [e.message], `No se puede abrir el archivo:\n${e.message}\n\nSi el archivo es muy grande, descárgalo para editarlo localmente.`);
        textarea.disabled = true;
      }
      if (saveBtn) saveBtn.disabled = true;
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async saveCurrentFile() {
    if (!this.activeEditingPath) return;
    const textarea = document.getElementById('editor-textarea');
    const content = textarea.value;

    try {
      const res = await fetch('/api/files/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.activeEditingPath, content })
      });
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_saved', 'Archivo guardado (Ctrl+S)'), 'success');
      } else {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_err_save', 'Error al guardar archivo'), 'danger');
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  closeEditor() {
    const modal = document.getElementById('file-editor-modal');
    if (modal) modal.classList.remove('open');
    this.activeEditingPath = '';
  },

  async deleteItem(filePath, name) {
    this.hideContextMenu();
    const ok = await App.confirm({
      title: this.tr('t_file_confirm_delete_title', 'Eliminar Elemento'),
      message: this.trf('t_file_confirm_delete_msg', [name], `¿Confirmas la eliminación permanente de "${name}"?`),
      confirmText: this.tr('t_file_delete', 'Eliminar'),
      danger: true
    });
    if (!ok) return;

    try {
      const res = await fetch(`/api/files/delete?path=${encodeURIComponent(filePath)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.trf('t_file_deleted', [name], `"${name}" eliminado`), 'success');
        this.selectedPaths.delete(filePath);
        this.updateBulkBar();
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_err_delete', 'Error al eliminar'), 'danger');
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async unzipFile(filePath) {
    this.hideContextMenu();
    try {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_unzipping', 'Extrayendo archivo zip...'), 'info');
      const res = await fetch('/api/files/unzip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath, target_dir: this.currentPath })
      });
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_unzip_done', 'Extracción completada'), 'success');
        this.loadDirectory(this.currentPath);
      } else {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_err_unzip', 'Error en la extracción'), 'danger');
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async createNewFolder() {
    this.hideContextMenu();
    const folderName = await App.prompt({
      title: this.tr('t_file_new_folder', 'Nueva Carpeta'),
      message: this.tr('t_file_folder_prompt_msg', 'Ingresa el nombre de la nueva carpeta:'),
      placeholder: this.tr('t_file_folder_prompt_ph', 'ej: plugins_backup, configs'),
      confirmText: this.tr('t_file_btn_create_folder', 'Crear Carpeta')
    });
    if (!folderName || !folderName.trim()) return;

    const newPath = (this.currentPath ? this.currentPath + '/' : '') + folderName.trim();
    try {
      const res = await fetch('/api/files/folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: newPath })
      });
      if (res.ok) {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(this.tr('t_file_folder_created', 'Carpeta creada'), 'success');
        this.loadDirectory(this.currentPath);
      } else {
        const err = await res.json();
        if (typeof App !== 'undefined' && App.showToast) App.showToast(err.detail || this.tr('t_file_err_create_folder', 'Error al crear carpeta'), 'danger');
      }
    } catch (e) {
      if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
    }
  },

  async uploadFiles(fileList) {
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList);
    const total = files.length;
    let uploadedCount = 0;

    for (let i = 0; i < total; i++) {
      const file = files[i];
      if (typeof App !== 'undefined' && App.showToast) {
        App.showToast(this.trf('t_file_upload_progress', [i + 1, total, file.name], `Subiendo ${i + 1} de ${total}: ${file.name}...`), 'info');
      }

      const formData = new FormData();
      formData.append('path', this.currentPath);
      formData.append('file', file);

      try {
        const res = await fetch('/api/files/upload', {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          uploadedCount++;
        } else {
          const errData = await res.json().catch(() => ({}));
          if (typeof App !== 'undefined' && App.showToast) {
            App.showToast(errData.detail || this.trf('t_file_err_upload', [file.name], `Error al subir ${file.name}`), 'danger');
          }
        }
      } catch (e) {
        if (typeof App !== 'undefined' && App.showToast) App.showToast(e.message, 'danger');
      }
    }

    // Reset upload input value so same files can be re-selected if desired
    const uploadInput = document.getElementById('file-upload-input');
    if (uploadInput) uploadInput.value = '';

    if (uploadedCount > 0) {
      if (typeof App !== 'undefined' && App.showToast) {
        App.showToast(this.trf('t_file_upload_complete', [uploadedCount], `${uploadedCount} archivo(s) subido(s) correctamente`), 'success');
      }
      this.loadDirectory(this.currentPath);
    }
  },

  async uploadFile(file) {
    if (!file) return;
    return this.uploadFiles([file]);
  },

  _buildContextActions(item, itemRelativePath) {
    const name = item ? item.name : '';
    return {
      newFile: () => this.openCreateFileModal(),
      newFolder: () => this.createNewFolder(),
      upload: () => {
        const input = document.getElementById('file-upload-input');
        if (input) input.click();
      },
      refresh: () => this.loadDirectory(this.currentPath),
      open: () => this.loadDirectory(itemRelativePath),
      edit: () => this.openEditor(itemRelativePath),
      unzip: () => this.unzipFile(itemRelativePath),
      download: () => this.downloadFile(itemRelativePath),
      rename: () => this.openRenameModal(itemRelativePath, name),
      compress: () => this.compressItem(itemRelativePath, name),
      duplicate: () => this.duplicateItem(itemRelativePath, name),
      copy: () => this.copyPath(itemRelativePath),
      delete: () => this.deleteItem(itemRelativePath, name)
    };
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

// Initialize listeners on DOM ready
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Files.init());
  } else {
    Files.init();
  }
}
