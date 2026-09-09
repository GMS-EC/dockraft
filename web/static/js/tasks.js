// Dockraft Scheduled Tasks Script
const Tasks = {
  tasksList: [],
  filteredList: [],
  pageSize: 10,
  currentPage: 1,
  searchQuery: '',

  init() {
    if (this._initialized) return;
    this._initialized = true;
    this.loadTasks();
    window.addEventListener('dockraft:language_changed', () => {
      if ((typeof App === 'undefined' || App.activeTab === 'tasks') && document.getElementById('tasks-table-body')) {
        this.applyFilter();
      }
    });
  },

  tr(key, fallback) {
    return (typeof I18n !== 'undefined' && I18n.t) ? I18n.t(key, fallback) : fallback;
  },

  trf(key, args, fallback) {
    return (typeof I18n !== 'undefined' && I18n.fmt) ? I18n.fmt(key, args, fallback) : fallback;
  },

  async loadTasks() {
    try {
      const res = await fetch('/api/tasks');
      if (res.ok) {
        this.tasksList = await res.json();
        this.applyFilter();
      } else if (res.status === 401) {
        if (typeof App !== 'undefined' && App.handleSessionExpired) App.handleSessionExpired();
      }
    } catch (e) {
      console.error('Error loading tasks:', e);
    }
  },

  setPageSize(size) {
    this.pageSize = parseInt(size) || 10;
    this.currentPage = 1;
    this.render();
  },

  setSearchQuery(q) {
    this.searchQuery = (q || '').trim().toLowerCase();
    this.currentPage = 1;
    this.applyFilter();
  },

  applyFilter() {
    if (!this.searchQuery) {
      this.filteredList = [...this.tasksList];
    } else {
      this.filteredList = this.tasksList.filter(t => {
        const name = (t.name || '').toLowerCase();
        const action = (t.action || '').toLowerCase();
        const cmd = (t.command || '').toLowerCase();
        const cron = (t.cron_expression || '').toLowerCase();
        return name.includes(this.searchQuery) ||
               action.includes(this.searchQuery) ||
               cmd.includes(this.searchQuery) ||
               cron.includes(this.searchQuery);
      });
    }
    this.render();
  },

  render() {
    const tbody = document.getElementById('tasks-table-body');
    const info = document.getElementById('tasks-pagination-info');
    const controls = document.getElementById('tasks-pagination-controls');
    if (!tbody) return;

    if (this.filteredList.length === 0) {
      const emptyMsg = this.searchQuery
        ? this.tr('t_tasks_empty_search', 'No se encontraron tareas con esa búsqueda.')
        : this.tr('t_tasks_empty_no_data', 'No hay tareas programadas. ¡Crea una nueva con el botón superior!');
      tbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align:center; padding: 36px; color: var(--text-dim);">
            <div style="margin-bottom: 8px; display:flex; justify-content:center;">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            </div>
            ${emptyMsg}
          </td>
        </tr>
      `;
      if (info) info.textContent = this.trf('t_tasks_pagination', [0, 0, 0], 'Mostrando 0 hasta 0 de 0 entradas');
      if (controls) controls.innerHTML = '';
      return;
    }

    const total = this.filteredList.length;
    const totalPages = Math.ceil(total / this.pageSize);
    if (this.currentPage > totalPages) this.currentPage = totalPages;
    if (this.currentPage < 1) this.currentPage = 1;

    const startIdx = (this.currentPage - 1) * this.pageSize;
    const endIdx = Math.min(startIdx + this.pageSize, total);
    const pageItems = this.filteredList.slice(startIdx, endIdx);

    tbody.innerHTML = pageItems.map(t => {
      const isEnabled = t.enabled;
      const actionBadge = this.getActionBadge(t.action);
      const commandDisplay = this.getCommandDisplay(t);
      const intervalDisplay = this.getIntervalDisplay(t);
      const nameDisplay = t.name || this.tr('t_tasks_unnamed', 'Sin nombre');
      const nextRunDisplay = isEnabled && t.next_run ? t.next_run : '<span style="color:var(--text-dim);">' + this.tr('t_tasks_disabled', 'Deshabilitada') + '</span>';
      const editTitle = this.tr('t_tasks_action_edit', 'Editar tarea');
      const runTitle = this.tr('t_tasks_action_run', 'Ejecutar ahora');
      const deleteTitle = this.tr('t_tasks_action_delete', 'Eliminar tarea');

      return `
        <tr class="task-row">
          <td style="text-align: center;">
            <label class="toggle-switch-compact">
              <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="Tasks.toggleTask('${t.id}', this.checked)">
              <span class="slider-compact"></span>
            </label>
          </td>
          <td style="font-weight: 600; color: #f0f6fc;">
            ${this.escapeHtml(nameDisplay)}
          </td>
          <td>${actionBadge}</td>
          <td>
            <code class="cmd-snippet">${this.escapeHtml(commandDisplay)}</code>
          </td>
          <td>
            <span class="interval-tag">${this.escapeHtml(intervalDisplay)}</span>
          </td>
          <td style="font-size: 0.85rem; color: #8b949e; white-space: nowrap;">
            ${nextRunDisplay}
          </td>
          <td style="text-align: center;">
            <div style="display: inline-flex; gap: 6px; align-items: center;">
              <button class="btn-action-task edit" title="${this.escapeHtml(editTitle)}" data-i18n-title="t_tasks_action_edit" onclick="Tasks.openEditModal('${t.id}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="btn-action-task run" title="${this.escapeHtml(runTitle)}" data-i18n-title="t_tasks_action_run" onclick="Tasks.runTaskNow('${t.id}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              </button>
              <button class="btn-action-task delete" title="${this.escapeHtml(deleteTitle)}" data-i18n-title="t_tasks_action_delete" onclick="Tasks.deleteTask('${t.id}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    if (info) {
      info.textContent = this.trf('t_tasks_pagination', [startIdx + 1, endIdx, total], `Mostrando ${startIdx + 1} hasta ${endIdx} de ${total} entradas`);
    }

    if (controls) {
      let btns = `
        <button class="pagination-btn ${this.currentPage === 1 ? 'disabled' : ''}" 
                onclick="Tasks.goToPage(${this.currentPage - 1})" ${this.currentPage === 1 ? 'disabled' : ''}>
          ${this.tr('t_tasks_pagination_prev', 'Anterior')}
        </button>
      `;

      for (let p = 1; p <= totalPages; p++) {
        btns += `
          <button class="pagination-btn ${p === this.currentPage ? 'active' : ''}" 
                  onclick="Tasks.goToPage(${p})">
            ${p}
          </button>
        `;
      }

      btns += `
        <button class="pagination-btn ${this.currentPage === totalPages ? 'disabled' : ''}" 
                onclick="Tasks.goToPage(${this.currentPage + 1})" ${this.currentPage === totalPages ? 'disabled' : ''}>
          ${this.tr('t_tasks_pagination_next', 'Siguiente')}
        </button>
      `;
      controls.innerHTML = btns;
    }
  },

  goToPage(p) {
    this.currentPage = p;
    this.render();
  },

  getActionBadge(action) {
    switch (action) {
      case 'start':
        return '<span class="task-badge badge-start">start</span>';
      case 'stop':
        return '<span class="task-badge badge-stop">stop</span>';
      case 'restart':
        return '<span class="task-badge badge-restart">restart</span>';
      case 'backup':
        return '<span class="task-badge badge-backup">backup</span>';
      case 'check_updates':
        return '<span class="task-badge badge-updates">updates</span>';
      case 'command':
        return '<span class="task-badge badge-cmd">command</span>';
      default:
        return `<span class="task-badge">${this.escapeHtml(action)}</span>`;
    }
  },

  getCommandDisplay(t) {
    if (t.action === 'command' && t.command) {
      return t.command;
    }
    switch (t.action) {
      case 'start': return 'start_server';
      case 'stop': return 'stop_server';
      case 'restart': return 'restart_server';
      case 'backup': return 'backup_server';
      case 'check_updates': return 'check_versions';
      default: return t.command || t.action;
    }
  },

  getIntervalDisplay(t) {
    if (t.schedule_type === 'cron') {
      const expr = t.cron_expression || '0 4 * * *';
      return this.trf('t_tasks_interval_cron', [expr], `Cron: ${expr}`);
    }
    const val = t.interval_value || 1;
    const unit = t.interval_unit || 'days';
    const single = val === 1;
    let unitKey;
    if (unit === 'minutes') {
      unitKey = single ? 't_tasks_unit_minute' : 't_tasks_unit_minutes';
    } else if (unit === 'hours') {
      unitKey = single ? 't_tasks_unit_hour' : 't_tasks_unit_hours';
    } else {
      unitKey = single ? 't_tasks_unit_day' : 't_tasks_unit_days';
    }
    const unitText = this.tr(unitKey, single
      ? (unit === 'minutes' ? 'minuto' : unit === 'hours' ? 'hora' : 'día')
      : (unit === 'minutes' ? 'minutos' : unit === 'hours' ? 'horas' : 'días'));
    return this.trf('t_tasks_interval_every', [val, unitText], `Cada ${val} ${unitText}`);
  },

  async toggleTask(taskId, enabled) {
    try {
      const res = await fetch(`/api/tasks/${taskId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      });
      if (res.ok) {
        const updated = await res.json();
        const idx = this.tasksList.findIndex(t => t.id === taskId);
        if (idx !== -1) {
          this.tasksList[idx] = updated;
          this.applyFilter();
        }
        if (typeof App !== 'undefined') {
          App.showToast(this.tr(
            enabled ? 't_tasks_toast_enabled' : 't_tasks_toast_disabled',
            enabled ? 'Tarea habilitada correctamente' : 'Tarea deshabilitada correctamente'
          ), 'success');
        }
      } else {
        this.loadTasks();
      }
    } catch (e) {
      console.error('Error toggling task:', e);
      this.loadTasks();
    }
  },

  async runTaskNow(taskId) {
    const task = this.tasksList.find(t => t.id === taskId);
    const taskName = task ? task.name : taskId;

    const ok = await App.confirm({
      title: this.tr('t_tasks_confirm_run_title', 'Ejecutar Tarea Inmediatamente'),
      message: this.trf('t_tasks_confirm_run_msg', [taskName], `¿Deseas ejecutar inmediatamente la tarea '${taskName}'?`),
      confirmText: this.tr('t_tasks_confirm_run_btn', 'Ejecutar Tarea'),
      type: 'info'
    });
    if (!ok) return;

    try {
      if (typeof App !== 'undefined') {
        App.showToast(this.trf('t_tasks_toast_running', [taskName], `Ejecutando '${taskName}'...`), 'info');
      }
      const res = await fetch(`/api/tasks/${taskId}/run`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        if (typeof App !== 'undefined') {
          App.showToast(data.message || this.tr('t_tasks_toast_run_success', 'Tarea ejecutada con éxito'), 'success');
        }
        this.loadTasks();
      } else {
        const err = await res.json();
        if (typeof App !== 'undefined') {
          App.showToast(err.detail || this.tr('t_tasks_toast_run_error', 'Error al ejecutar tarea'), 'danger');
        }
      }
    } catch (e) {
      if (typeof App !== 'undefined') {
        App.showToast(this.tr('t_tasks_toast_conn_error', 'Error de conexión al ejecutar tarea'), 'danger');
      }
    }
  },

  async deleteTask(taskId) {
    const task = this.tasksList.find(t => t.id === taskId);
    const taskName = task ? task.name : taskId;

    const ok = await App.confirm({
      title: this.tr('t_tasks_confirm_delete_title', 'Eliminar Tarea Programada'),
      message: this.trf('t_tasks_confirm_delete_msg', [taskName], `¿Estás seguro de que deseas eliminar la tarea programada '${taskName}'?`),
      confirmText: this.tr('t_tasks_confirm_delete_btn', 'Eliminar Tarea'),
      danger: true
    });
    if (!ok) return;

    try {
      const res = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
      if (res.ok) {
        if (typeof App !== 'undefined') {
          App.showToast(this.trf('t_tasks_toast_deleted', [taskName], `Tarea '${taskName}' eliminada`), 'success');
        }
        this.tasksList = this.tasksList.filter(t => t.id !== taskId);
        this.applyFilter();
      }
    } catch (e) {
      console.error('Error deleting task:', e);
    }
  },

  openCreateModal() {
    document.getElementById('task-modal-title').textContent = this.tr('t_tasks_modal_create_title', 'Crear Nueva Tarea Programada');
    document.getElementById('task-edit-id').value = '';
    document.getElementById('task-name-input').value = '';
    document.getElementById('task-action-select').value = 'restart';
    document.getElementById('task-command-input').value = '';
    document.getElementById('task-interval-val').value = '1';
    document.getElementById('task-interval-unit').value = 'days';
    document.getElementById('task-cron-input').value = '0 4 * * *';
    document.getElementById('task-enabled-input').checked = true;

    document.querySelectorAll('input[name="task-schedule-type"]').forEach(r => {
      r.checked = r.value === 'interval';
    });

    this.onActionChange('restart');
    this.onScheduleTypeChange('interval');

    const modal = document.getElementById('task-modal');
    if (modal) modal.classList.add('open');
  },

  openEditModal(taskId) {
    const task = this.tasksList.find(t => t.id === taskId);
    if (!task) return;

    document.getElementById('task-modal-title').textContent = this.tr('t_tasks_modal_edit_title', 'Editar Tarea Programada');
    document.getElementById('task-edit-id').value = task.id;
    document.getElementById('task-name-input').value = task.name || '';
    document.getElementById('task-action-select').value = task.action || 'restart';
    document.getElementById('task-command-input').value = task.command || '';
    document.getElementById('task-interval-val').value = task.interval_value || 1;
    document.getElementById('task-interval-unit').value = task.interval_unit || 'days';
    document.getElementById('task-cron-input').value = task.cron_expression || '0 4 * * *';
    document.getElementById('task-enabled-input').checked = task.enabled !== false;

    const schedType = task.schedule_type || 'interval';
    document.querySelectorAll('input[name="task-schedule-type"]').forEach(r => {
      r.checked = r.value === schedType;
    });

    this.onActionChange(task.action || 'restart');
    this.onScheduleTypeChange(schedType);

    const modal = document.getElementById('task-modal');
    if (modal) modal.classList.add('open');
  },

  closeModal() {
    const modal = document.getElementById('task-modal');
    if (modal) modal.classList.remove('open');
  },

  onActionChange(action) {
    const cmdGroup = document.getElementById('task-command-group');
    if (cmdGroup) {
      cmdGroup.style.display = action === 'command' ? 'block' : 'none';
    }
  },

  onScheduleTypeChange(type) {
    const intervalGroup = document.getElementById('task-interval-group');
    const cronGroup = document.getElementById('task-cron-group');
    if (intervalGroup && cronGroup) {
      if (type === 'interval') {
        intervalGroup.style.display = 'flex';
        cronGroup.style.display = 'none';
      } else {
        intervalGroup.style.display = 'none';
        cronGroup.style.display = 'block';
      }
    }
  },

  applyCronPreset(expr) {
    const input = document.getElementById('task-cron-input');
    if (input) input.value = expr;
  },

  async saveTask() {
    const editId = document.getElementById('task-edit-id').value;
    const name = document.getElementById('task-name-input').value.trim();
    const action = document.getElementById('task-action-select').value;
    const command = document.getElementById('task-command-input').value.trim();
    const schedTypeRadio = document.querySelector('input[name="task-schedule-type"]:checked');
    const schedule_type = schedTypeRadio ? schedTypeRadio.value : 'interval';
    const interval_value = parseInt(document.getElementById('task-interval-val').value) || 1;
    const interval_unit = document.getElementById('task-interval-unit').value;
    const cron_expression = document.getElementById('task-cron-input').value.trim();
    const enabled = document.getElementById('task-enabled-input').checked;

    if (!name) {
      if (typeof App !== 'undefined') App.showToast(this.tr('t_tasks_toast_need_name', 'Ingresa un nombre para la tarea'), 'warning');
      return;
    }

    const payload = {
      name,
      action,
      command,
      schedule_type,
      interval_value,
      interval_unit,
      cron_expression,
      enabled
    };

    try {
      let res;
      if (editId) {
        res = await fetch(`/api/tasks/${editId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        res = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      if (res.ok) {
        this.closeModal();
        if (typeof App !== 'undefined') {
          App.showToast(this.trf(
            editId ? 't_tasks_toast_saved_updated' : 't_tasks_toast_saved_created',
            [name],
            editId ? `Tarea '${name}' actualizada con éxito` : `Tarea '${name}' creada con éxito`
          ), 'success');
        }
        this.loadTasks();
      } else {
        const err = await res.json();
        if (typeof App !== 'undefined') {
          App.showToast(err.detail || this.tr('t_tasks_toast_save_error', 'Error al guardar tarea'), 'danger');
        }
      }
    } catch (e) {
      console.error('Error saving task:', e);
    }
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
