// Dockraft Backups tab i18n dictionary (ES / EN)
// Registered into I18n before I18n.init() so [data-i18n] elements and
// dynamic JS strings (Backups module) resolve to the active language.
(function () {
  if (typeof I18n === 'undefined') return;

  I18n.registerModule({
    // --- Stat boxes ---
    t_backup_stat_total: 'Copias Totales',
    t_backup_stat_total_hint: 'Almacenadas en volumen externo ./backups',
    t_backup_stat_size: 'Espacio Ocupado',
    t_backup_stat_size_hint: 'Archivos comprimidos .zip',

    // --- Immediate backup card ---
    t_backup_immediate_title: 'Copia Inmediata',
    t_backup_immediate_desc: 'Comprime el servidor protegiendo mundos y configuraciones',
    t_backup_btn_create_now: 'Crear Copia Ahora',

    // --- Backup progress ---
    t_backup_progress_compressing: 'Comprimiendo archivos del servidor...',
    t_backup_progress_wait: 'Espere por favor',

    // --- Retention / scope policy card ---
    t_backup_retention_title: 'Configuración y Alcance de Respaldos',
    t_backup_retention_desc: 'Configura qué carpetas incluir por defecto en copias programadas y el límite de retención para evitar saturar el almacenamiento en disco.',
    t_backup_scope_question: '¿Qué deseas respaldar? (Alcance)',
    t_backup_scope_full: 'Servidor Completo',
    t_backup_scope_full_desc: 'Respalda todos los archivos, mundos, plugins y configs.',
    t_backup_scope_custom: 'Personalizado',
    t_backup_scope_custom_desc: 'Seleccionar carpetas o archivos específicos.',
    t_backup_cfg_targets_title: 'Carpetas y archivos a incluir:',
    t_backup_targets_all: 'Todos',
    t_backup_targets_none: 'Ninguno',
    t_backup_cfg_max_label: 'Copias Máximas a Conservar (Rotación)',
    t_backup_cfg_max_hint: 'Límite recomendado entre 3 y 10 según el espacio disponible en disco.',
    t_backup_cfg_exec_title: 'Parámetros de Ejecución del Respaldo',
    t_backup_cfg_compression_label: 'Comprimir la copia (.zip)',
    t_backup_cfg_compression_hint: 'Aplica compresión DEFLATED para reducir espacio. Desactivado (STORE) es más rápido y sin uso de CPU.',
    t_backup_cfg_stop_label: 'Apagar el servidor durante el backup',
    t_backup_cfg_stop_hint: 'Detiene el servidor para liberar session.lock e integridad total, y lo reinicia automáticamente al finalizar.',
    t_backup_cfg_precmd_label: 'Ejecutar comando antes del respaldo',
    t_backup_cfg_precmd_hint: "Comando enviado a la consola antes de iniciar la copia (ej: 'save-all' para forzar volcado de bloques a disco o 'say').",
    t_backup_btn_save_cfg: 'Guardar Configuración de Respaldo',

    // --- Best practices ---
    t_backup_tips_title: 'Buenas Prácticas de Respaldo',
    t_backup_tip1a: 'Las copias se guardan en el volumen externo aislado ',
    t_backup_tip1b: ' para seguridad total.',
    t_backup_scope_label: 'Alcance de Respaldo',
    t_backup_tip2a: 'Los respaldos automáticos usarán el ',
    t_backup_tip2b: ' que hayas configurado aquí.',
    t_backup_tip3a: 'Antes de ',
    t_backup_restore: 'Restaurar',
    t_backup_tip3b: ' una copia, el servidor debe estar apagado para evitar bloqueos de archivos de mundos (',
    t_backup_tip3c: ').',
    t_backup_tip4a: 'Puedes descargar los archivos ',
    t_backup_download: 'Descargar',
    t_backup_tip4b: ' a tu ordenador local con el botón ',
    t_backup_tip4c: ' en cualquier momento.',

    // --- Scheduling promo ---
    t_backup_schedule_prompt: '¿Deseas programar copias automáticas periódicas?',
    t_backup_schedule_desc: 'Puedes programar respaldos periódicos por intervalo de tiempo o expresión Cron directamente desde la pestaña de tareas programadas.',
    t_backup_btn_go_tasks: 'Ir a Programar Tareas',

    // --- Backups table ---
    t_backup_list_title: 'Archivos de Copias de Seguridad Disponibles',
    t_backup_btn_refresh: 'Actualizar',
    t_backup_empty_title: 'No hay copias de seguridad generadas todavía.',
    t_backup_empty_desc: 'Pulsa "Crear Copia Ahora" o programa una tarea automática.',
    t_backup_col_filename: 'Nombre del Archivo',
    t_backup_col_origin: 'Origen',
    t_backup_col_scope: 'Ámbito / Contenido',
    t_backup_col_date: 'Fecha y Hora',
    t_backup_col_size: 'Tamaño',
    t_backup_col_actions: 'Acciones',

    // --- Dynamic list (badges / row actions) ---
    t_backup_count_copies: '{0} copias',
    t_backup_badge_auto: 'Automático',
    t_backup_badge_manual: 'Manual',
    t_backup_badge_full: 'Completo',
    t_backup_scope_worlds: 'Solo Mundos',
    t_backup_scope_worlds_plugins: 'Mundos + Plugins',
    t_backup_download_title: 'Descargar archivo zip',
    t_backup_restore_title: 'Restaurar copia de seguridad',
    t_backup_delete_title: 'Eliminar copia',

    // --- Target scanning / messages ---
    t_backup_analyzing: 'Analizando carpetas del servidor...',
    t_backup_no_targets: 'No hay carpetas ni archivos disponibles en el servidor aún.',
    t_backup_err_fetch_list: 'Error al obtener la lista de backups',
    t_backup_err_targets: 'Error al consultar estructura de carpetas',
    t_backup_err_loading_targets: 'Error al cargar elementos: {0}',
    t_backup_warn_select_target: 'Debes seleccionar al menos una carpeta o archivo para respaldar',

    // --- Create backup flow ---
    t_backup_compressing: 'Comprimiendo...',
    t_backup_toast_start_compression: 'Iniciando compresión del respaldo...',
    t_backup_err_create: 'Error al crear la copia de seguridad',
    t_backup_toast_created: 'Copia creada con éxito: {0} ({1})',
    t_backup_create_btn: 'Crear Copia de Seguridad',

    // --- Restore flow ---
    t_backup_confirm_restore_title: 'Restaurar Copia de Seguridad',
    t_backup_confirm_restore_msg: "¿Estás seguro de que deseas restaurar la copia de seguridad '{0}'?\n\nADVERTENCIA: Esta acción reemplazará los archivos y mundos actuales por los contenidos en la copia de seguridad. El servidor debe estar APAGADO.",
    t_backup_confirm_restore_btn: 'Restaurar Copia',
    t_backup_toast_restoring: 'Restaurando copia de seguridad...',
    t_backup_err_restore: 'Error al restaurar la copia',
    t_backup_toast_restored: 'Copia de seguridad restaurada correctamente.',

    // --- Delete flow ---
    t_backup_confirm_delete_title: 'Eliminar Copia de Seguridad',
    t_backup_confirm_delete_msg: "¿Deseas eliminar permanentemente la copia de seguridad '{0}'?",
    t_backup_confirm_delete_btn: 'Eliminar Copia',
    t_backup_err_delete: 'Error al eliminar copia',
    t_backup_toast_deleted: 'Copia de seguridad eliminada',

    // --- Config save ---
    t_backup_err_save_cfg: 'Error guardando configuración de respaldo',
    t_backup_toast_cfg_saved: 'Configuración de alcance y retención guardada correctamente.'
  }, {
    // --- Stat boxes ---
    t_backup_stat_total: 'Total Backups',
    t_backup_stat_total_hint: 'Stored in external volume ./backups',
    t_backup_stat_size: 'Used Space',
    t_backup_stat_size_hint: 'Compressed .zip archives',

    // --- Immediate backup card ---
    t_backup_immediate_title: 'Immediate Backup',
    t_backup_immediate_desc: 'Compresses the server protecting worlds and configurations',
    t_backup_btn_create_now: 'Create Backup Now',

    // --- Backup progress ---
    t_backup_progress_compressing: 'Compressing server files...',
    t_backup_progress_wait: 'Please wait',

    // --- Retention / scope policy card ---
    t_backup_retention_title: 'Backup Configuration & Scope',
    t_backup_retention_desc: 'Configure which folders to include by default in scheduled backups and set the retention limit to avoid filling up disk storage.',
    t_backup_scope_question: 'What do you want to back up? (Scope)',
    t_backup_scope_full: 'Full Server',
    t_backup_scope_full_desc: 'Backs up all files, worlds, plugins, and configs.',
    t_backup_scope_custom: 'Custom',
    t_backup_scope_custom_desc: 'Select specific folders or files.',
    t_backup_cfg_targets_title: 'Folders and files to include:',
    t_backup_targets_all: 'All',
    t_backup_targets_none: 'None',
    t_backup_cfg_max_label: 'Maximum Backups to Keep (Rotation)',
    t_backup_cfg_max_hint: 'Recommended limit between 3 and 10 depending on available disk space.',
    t_backup_cfg_exec_title: 'Backup Execution Parameters',
    t_backup_cfg_compression_label: 'Compress the backup (.zip)',
    t_backup_cfg_compression_hint: 'Applies DEFLATED compression to save space. Disabled (STORE) is faster with no CPU usage.',
    t_backup_cfg_stop_label: 'Stop the server during the backup',
    t_backup_cfg_stop_hint: 'Stops the server to release session.lock for full integrity, and restarts it automatically when finished.',
    t_backup_cfg_precmd_label: 'Run a command before the backup',
    t_backup_cfg_precmd_hint: "Command sent to the console before starting the backup (e.g., 'save-all' to force chunk data to disk or 'say').",
    t_backup_btn_save_cfg: 'Save Backup Configuration',

    // --- Best practices ---
    t_backup_tips_title: 'Backup Best Practices',
    t_backup_tip1a: 'Backups are stored on the isolated external volume ',
    t_backup_tip1b: ' for total security.',
    t_backup_scope_label: 'Backup Scope',
    t_backup_tip2a: 'Automatic backups will use the ',
    t_backup_tip2b: ' you configured here.',
    t_backup_tip3a: 'Before ',
    t_backup_restore: 'Restore',
    t_backup_tip3b: ' a backup, the server must be stopped to avoid world file locks (',
    t_backup_tip3c: ').',
    t_backup_tip4a: 'You can download the ',
    t_backup_download: 'Download',
    t_backup_tip4b: ' to your local computer using the ',
    t_backup_tip4c: ' button at any time.',

    // --- Scheduling promo ---
    t_backup_schedule_prompt: 'Would you like to schedule periodic automatic backups?',
    t_backup_schedule_desc: 'You can schedule periodic backups by time interval or Cron expression directly from the scheduled tasks tab.',
    t_backup_btn_go_tasks: 'Go to Schedule Tasks',

    // --- Backups table ---
    t_backup_list_title: 'Available Backup Files',
    t_backup_btn_refresh: 'Refresh',
    t_backup_empty_title: 'No backups have been created yet.',
    t_backup_empty_desc: 'Click "Create Backup Now" or schedule an automatic task.',
    t_backup_col_filename: 'File Name',
    t_backup_col_origin: 'Origin',
    t_backup_col_scope: 'Scope / Content',
    t_backup_col_date: 'Date and Time',
    t_backup_col_size: 'Size',
    t_backup_col_actions: 'Actions',

    // --- Dynamic list (badges / row actions) ---
    t_backup_count_copies: '{0} copies',
    t_backup_badge_auto: 'Automatic',
    t_backup_badge_manual: 'Manual',
    t_backup_badge_full: 'Full',
    t_backup_scope_worlds: 'Worlds Only',
    t_backup_scope_worlds_plugins: 'Worlds + Plugins',
    t_backup_download_title: 'Download zip file',
    t_backup_restore_title: 'Restore backup',
    t_backup_delete_title: 'Delete backup',

    // --- Target scanning / messages ---
    t_backup_analyzing: 'Analyzing server folders...',
    t_backup_no_targets: 'No folders or files are available on the server yet.',
    t_backup_err_fetch_list: 'Error fetching the backups list',
    t_backup_err_targets: 'Error querying folder structure',
    t_backup_err_loading_targets: 'Error loading items: {0}',
    t_backup_warn_select_target: 'You must select at least one folder or file to back up',

    // --- Create backup flow ---
    t_backup_compressing: 'Compressing...',
    t_backup_toast_start_compression: 'Starting backup compression...',
    t_backup_err_create: 'Error creating the backup',
    t_backup_toast_created: 'Backup created successfully: {0} ({1})',
    t_backup_create_btn: 'Create Backup',

    // --- Restore flow ---
    t_backup_confirm_restore_title: 'Restore Backup',
    t_backup_confirm_restore_msg: "Are you sure you want to restore the backup '{0}'?\n\nWARNING: This action will replace the current files and worlds with the contents of the backup. The server must be OFF.",
    t_backup_confirm_restore_btn: 'Restore Backup',
    t_backup_toast_restoring: 'Restoring backup...',
    t_backup_err_restore: 'Error restoring the backup',
    t_backup_toast_restored: 'Backup restored successfully.',

    // --- Delete flow ---
    t_backup_confirm_delete_title: 'Delete Backup',
    t_backup_confirm_delete_msg: "Do you want to permanently delete the backup '{0}'?",
    t_backup_confirm_delete_btn: 'Delete Backup',
    t_backup_err_delete: 'Error deleting backup',
    t_backup_toast_deleted: 'Backup deleted',

    // --- Config save ---
    t_backup_err_save_cfg: 'Error saving backup configuration',
    t_backup_toast_cfg_saved: 'Backup scope and retention configuration saved successfully.'
  });
})();
