// Dockraft Internationalization (i18n) Module
const I18n = {
  currentLang: 'es',

  translations: {
    es: {
      lang_code: 'ES',
      lang_label: 'Español',
      toggle_lang_title: 'Cambiar idioma / Change language',

      // Header & Navigation
      nav_console: 'Consola',
      nav_metrics: 'Métricas',
      nav_players: 'Jugadores',
      nav_tasks: 'Tareas',
      nav_backups: 'Respaldos',
      nav_logs: 'Registros',
      nav_webhooks: 'Webhooks',
      nav_files: 'Archivos',
      nav_settings: 'Ajustes',
      nav_installer: 'Instalador',
      nav_logout: 'Salir',

      // Banner metrics
      banner_server_title: 'Servidor',
      banner_server_label: 'Tipo y Motor',
      banner_version_label: 'Versión',
      banner_online_players: 'Jugadores en Línea',
      banner_memory_title: 'Memoria RAM',
      banner_ram_assigned: 'Asignada',
      banner_system_title: 'Sistema y Almacenamiento',
      banner_cpu_server: 'CPU Servidor',
      banner_disk_usage: 'Uso de Disco',
      banner_status_offline: 'Fuera de Línea',
      banner_status_running: 'En Ejecución',
      banner_status_starting: 'Iniciando...',
      banner_status_stopping: 'Deteniendo...',
      banner_uptime: 'Tiempo activo',
      banner_none_installed: 'Ningún servidor instalado',
      banner_status_label: 'Estado del Servidor:',
      banner_started_label: 'Servidor Iniciado:',
      banner_uptime_label: 'Actividad del Servidor:',
      banner_tz_label: 'Zona horaria del servidor:',
      banner_cpu_label: 'Uso de CPU:',
      banner_mem_label: 'Uso de memoria:',
      banner_players_label: 'Jugadores:',
      banner_name_label: 'Nombre del Servidor:',
      banner_version_label: 'Versión:',
      banner_desc_label: 'Descripción:',
      banner_type_label: 'Tipo de Servidor:',
      banner_tps_label: 'Rendimiento (TPS):',
      banner_server_details: 'Detalles del Servidor',
      banner_expand: 'Expandir',
      banner_collapse: 'Ocultar',

      // Console Tab
      console_title: 'Consola en Tiempo Real',
      stat_cpu: 'CPU',
      stat_cpu_sub: 'Uso en núcleos activos',
      stat_ram: 'RAM',
      stat_mem_sub: 'De la memoria asignada',
      stat_disk: 'Disco',
      stat_disk_sub: 'Almacenamiento (/server_data)',
      stat_control: 'Control',
      console_auto_scroll: 'Desplazamiento automático',
      console_quick_cmds: 'Comandos Rápidos',
      btn_start: 'Iniciar',
      btn_start_title: 'Iniciar Servidor',
      btn_stop: 'Detener',
      btn_stop_title: 'Detener Servidor',
      btn_restart: 'Reiniciar',
      btn_restart_title: 'Reiniciar Servidor',
      btn_kill: 'Forzar Cierre (Kill)',
      btn_kill_title: 'Forzar Apagado Inmediato (Kill)',
      cmd_placeholder: 'Escribe un comando de Minecraft (ej: list, op usuario, time set day)...',
      cmd_send: 'Enviar',
      console_clear: 'Limpiar Consola',
      console_view_audit: 'Historial de Registros',

      // Installer Tab
      inst_title: 'Selecciona el Tipo de Servidor',
      inst_import_btn: 'Importar Servidor (.zip)',
      inst_unlock_btn: 'Desbloquear Reinstalación',
      inst_delete_btn: 'Eliminar Servidor',
      inst_reinstall_badge: 'REINSTALACIÓN DESBLOQUEADA',
      inst_current_info: 'Ya existe un servidor en este directorio (/data). La instalación está bloqueada para proteger tus mundos, plugins y configuraciones de sobrescritura accidental.',
      inst_desc_paper: 'Rápido y optimizado. El más recomendado para jugar con amigos y usar plugins.',
      inst_desc_purpur: 'Variante de Paper con máxima personalización y gran rendimiento.',
      inst_desc_vanilla: 'El Minecraft clásico original, sin añadidos, plugins ni mods.',
      inst_desc_fabric: 'Ligero y rápido para jugar con mods modernos.',
      inst_desc_forge: 'El sistema tradicional y con mayor variedad de mods.',
      inst_desc_bedrock: 'Para jugar desde celulares, consolas (Xbox, PlayStation, Switch) y Windows.',
      inst_res_title: 'Versión y Asignación de Recursos',
      inst_server_name: 'Nombre del Servidor',
      inst_server_name_hint: 'Nombre descriptivo que se mostrará en la barra superior y notificaciones Webhooks.',
      inst_mc_version: 'Versión del Servidor de Minecraft',
      inst_loading_versions: 'Cargando versiones oficiales...',
      inst_min_ram: 'RAM Mínima (-Xms)',
      inst_max_ram: 'RAM Máxima (-Xmx)',
      inst_cpu_cores: 'Núcleos de CPU',
      inst_cpu_cores_hint: 'Límite de procesadores lógicos para Java (0 = sin límite).',
      inst_disk_limit: 'Límite Disco (GB)',
      inst_disk_limit_hint: 'Capacidad asignada a la carpeta de datos.',
      inst_aikar_title: 'Optimizaciones de Rendimiento (Aikar\'s Flags)',
      inst_aikar_desc: 'Parámetros avanzados recomendados para evitar tirones (lag) en Java G1GC.',
      inst_btn_install: 'Descargar e Instalar Servidor',
      inst_update_title: 'Actualizar Servidor',
      inst_update_desc: 'Esta función actualiza el motor y ejecutables de tu servidor a la versión seleccionada. Tus mundos, plugins, mods y configuraciones se conservan intactos.',
      inst_update_btn: 'Actualizar Servidor',

      // Tasks Tab
      tasks_title: 'Tareas Programadas y Automatizaciones',
      tasks_desc: 'Automatiza reinicios periódicos, encendido, apagado, copias de seguridad recurrentes y ejecución de comandos en intervalos o con Cron.',
      tasks_search_placeholder: 'Buscar tareas por nombre, acción, comando o cron...',
      tasks_btn_new: 'Nueva Tarea',
      tasks_col_name: 'Nombre de la Tarea',
      tasks_col_action: 'Acción',
      tasks_col_schedule: 'Frecuencia / Horario',
      tasks_col_next: 'Próxima Ejecución',
      tasks_col_status: 'Estado',
      tasks_col_actions: 'Acciones',
      tasks_empty: 'No hay tareas programadas. Haz clic en "Nueva Tarea" para crear una.',

      // Backups Tab
      backups_title: 'Gestión de Copias de Seguridad',
      backups_desc: 'Crea copias de seguridad de todo el servidor o selecciona únicamente carpetas críticas para ahorrar espacio.',
      backups_btn_create: 'Crear Copia de Seguridad',
      backups_retention_title: 'Configuración y Alcance de Respaldos',
      backups_retention_desc: 'Configura qué carpetas incluir por defecto en copias programadas y el límite de retención para evitar saturar el almacenamiento en disco.',
      backups_max_label: 'Máximo de respaldos a conservar:',
      backups_save_quota: 'Guardar Límite',
      backups_col_file: 'Archivo de Respaldo',
      backups_col_scope: 'Alcance',
      backups_col_date: 'Fecha de Creación',
      backups_col_size: 'Tamaño',
      backups_col_type: 'Tipo',
      backups_empty: 'No se encontraron copias de seguridad.',

      // Webhooks Tab
      webhooks_title: 'Notificaciones Webhook',
      webhooks_desc: 'Recibe avisos automáticos en tus canales de Discord, grupos de Telegram o por Correo Electrónico cuando el servidor cambie de estado o concluyan tareas.',
      webhooks_events_title: 'Eventos que enviarán notificaciones',
      webhooks_ev_started: 'Servidor Iniciado',
      webhooks_ev_stopped: 'Servidor Detenido',
      webhooks_ev_crashed: 'Caída del Servidor (Crash)',
      webhooks_ev_backup: 'Copia de Seguridad Completada',
      webhooks_ev_task: 'Tarea Programada Ejecutada',

      // Files Tab
      files_title: 'Explorador de Archivos',
      files_upload: 'Subir Archivo',
      files_new_file: 'Nuevo Archivo',
      files_new_folder: 'Nueva Carpeta',
      files_refresh: 'Refrescar',
      files_root: 'Raíz del Servidor',
      files_rename_title: 'Renombrar',
      files_rename_label: 'Nuevo Nombre:',
      files_btn_rename: 'Guardar',
      files_create_file_title: 'Nuevo Archivo',
      files_create_file_label: 'Nombre del Archivo (con extensión):',
      files_btn_create_file: 'Crear Archivo',
      ctx_open_edit: 'Abrir / Editar',
      ctx_open_folder: 'Abrir Carpeta',
      ctx_rename: 'Renombrar',
      ctx_download: 'Descargar',
      ctx_compress_zip: 'Comprimir a .ZIP',
      ctx_extract_zip: 'Extraer aquí',
      ctx_duplicate: 'Duplicar',
      ctx_copy_path: 'Copiar ruta',
      ctx_delete: 'Eliminar',
      ctx_new_file: 'Nuevo Archivo',
      ctx_new_folder: 'Nueva Carpeta',
      ctx_upload: 'Subir Archivo',
      ctx_refresh: 'Refrescar',

      // Settings Tab
      settings_title: 'Configuración del Servidor',
      settings_save_btn: 'Guardar Configuración',
      settings_danger_zone: 'Zona de Peligro',
      settings_system_behavior_title: 'Comportamiento del Servidor y Sistema',
      settings_autostart_label: 'Inicio automático del servidor',
      settings_autostart_hint: 'Inicia automáticamente el servidor de Minecraft al encender el contenedor o servicio Dockraft.',
      settings_crash_label: 'Detección de crasheos y auto-reinicio',
      settings_crash_hint: 'Detecta caídas inesperadas del servidor y lo reinicia automáticamente con protección anti-bucle (máx 3 reintentos en 2 min).',

      // Metrics Tab
      metrics_title: 'Telemetría y Rendimiento',
      metrics_subtitle: 'Monitoreo en tiempo real de CPU, memoria y jugadores. Búfer en memoria ultra-liviano (0% disco).',
      metrics_live_active: 'En Vivo (10s)',
      metrics_btn_reset: 'Vaciar Historial',
      metrics_kpi_cpu: 'Uso de CPU',
      metrics_kpi_ram: 'Memoria RAM',
      metrics_kpi_players: 'Jugadores Online',
      metrics_kpi_uptime: 'Tiempo Activo',
      metrics_peak: 'Pico:',
      metrics_avg: 'Media:',
      metrics_assigned: 'Asignada:',
      metrics_record: 'Récord de sesión:',
      metrics_status: 'Estado:',
      metrics_chart_title: 'Historial de Rendimiento',
      metrics_legend_cpu: 'CPU %',
      metrics_legend_ram_pct: 'RAM %',
      metrics_legend_ram_mb: 'RAM (MB)',
      metrics_legend_players: 'Jugadores',
      metrics_gathering: 'Recopilando telemetría del servidor en memoria...',

      // Players Tab
      players_section_title: 'Jugadores:',
      players_banned_title: 'Jugadores Baneados:',
      players_btn_add: 'Añadir',
      players_btn_kick_all: 'Expulsar a todos',
      players_col_player: 'Player',
      players_col_status: 'Status',
      players_col_actions: 'Actions',
      players_col_reason: 'Reason',
      players_modal_add_title: 'Añadir Jugador al Directorio',
      players_modal_name_label: 'Nombre de usuario (Gamertag / Nick)',
      players_modal_btn_confirm: 'Guardar Jugador',
      players_reason_label: 'Motivo o Razón (Opcional):',

      // Logs Tab
      logs_title: 'Registro de Auditoría y Comandos de Consola',
      logs_stat_total: 'Registros Totales',
      logs_stat_total_sub: 'Historial cronológico auditado',
      logs_stat_commands: 'Comandos Consola',
      logs_stat_commands_sub: 'Enviados por administradores',
      logs_stat_system: 'Eventos del Sistema',
      logs_stat_system_sub: 'Inicios, copias y actualizaciones',
      logs_auto_refresh: 'Auto-actualizar (5s)',
      logs_refresh: 'Actualizar',
      logs_cat_all: 'Todos',
      logs_cat_console: '⌨️ Comandos',
      logs_cat_server: '⚡ Servidor',
      logs_cat_backup: '💾 Respaldos',
      logs_cat_update: '🔄 Actualizaciones',
      logs_cat_security: '🛡️ Seguridad',
      logs_cat_tasks: '⏱️ Tareas',
      logs_empty_title: 'No hay registros que coincidan con la búsqueda.',
      logs_empty_desc: 'Los comandos ejecutados en consola y eventos del servidor aparecerán aquí automáticamente.',
      logs_col_timestamp: 'Fecha / Hora',
      logs_col_category: 'Categoría',
      logs_col_action: 'Acción',
      logs_col_details: 'Detalle / Comando',
      logs_col_user: 'Usuario',
      logs_col_status: 'Estado',

      // Footer
      footer_desc: 'Panel de control ultra-ligero y modular para servidores de Minecraft Java y Bedrock sobre contenedores Docker.',
      footer_copyright: '© 2026 Dockraft · Distribuido bajo Licencia GNU GPLv3',

      // Modals
      modal_create_backup_title: 'Crear Copia de Seguridad',
      modal_scope_full: 'Todo el Servidor',
      modal_scope_full_desc: 'Copia absoluta de mundos, plugins, mods, configuraciones y binarios.',
      modal_scope_worlds: 'Solo Mundos',
      modal_scope_worlds_desc: 'Respalda únicamente las carpetas de mapas de Minecraft y server.properties.',
      modal_scope_plugins: 'Mundos + Plugins / Mods',
      modal_scope_plugins_desc: 'Protege tu progreso y las extensiones instaladas sin incluir binarios grandes.',
      modal_scope_custom: 'Personalizado',
      modal_scope_custom_desc: 'Elige individualmente qué carpetas y archivos específicos respaldar.',
      modal_btn_cancel: 'Cancelar',
      modal_btn_confirm: 'Confirmar',

      // Settings: System behavior & Session timeout
      settings_system_behavior_title: 'Comportamiento del Servidor y Sistema',
      settings_autostart_label: 'Inicio automático del servidor',
      settings_autostart_hint: 'Inicia automáticamente el servidor de Minecraft al encender el contenedor o servicio Dockraft.',
      settings_crash_label: 'Detección de crasheos y auto-reinicio',
      settings_crash_hint: 'Detecta caídas inesperadas del servidor y lo reinicia automáticamente con protección anti-bucle (máx 3 reintentos en 2 min).',
      settings_session_timeout_label: 'Caducidad de sesión (minutos)',
      settings_session_timeout_hint: 'Tiempo de inactividad tras el cual la sesión expira automáticamente por seguridad (por defecto: 60 min).',

      // Login
      login_title: 'Iniciar Sesión — Dockraft',
      login_heading: 'Dockraft',
      login_subtitle: 'Panel de Control para Minecraft',
      login_username_label: 'Usuario',
      login_password_label: 'Contraseña',
      login_submit_btn: 'Iniciar Sesión',
      login_locked_notice: 'Acceso bloqueado por seguridad debido a demasiados intentos fallidos.',
      login_retry_in: 'Podrás intentar de nuevo en:',
      login_session_expired_title: 'Sesión Caducada',
      login_session_expired_desc: 'Tu sesión ha expirado por inactividad o seguridad. Por favor, inicia sesión de nuevo para continuar.',
      
      // Toasts
      toast_lang_changed: 'Idioma cambiado a Español',
      toast_server_started: 'Servidor iniciado',
      toast_server_stopped: 'Detención solicitada',
      toast_server_restarted: 'Reinicio solicitado',
      toast_server_killed: 'Servidor finalizado forzadamente (Kill)'
    },

    en: {
      lang_code: 'EN',
      lang_label: 'English',
      toggle_lang_title: 'Change language / Cambiar idioma',

      // Header & Navigation
      nav_console: 'Console',
      nav_metrics: 'Metrics',
      nav_players: 'Players',
      nav_tasks: 'Tasks',
      nav_backups: 'Backups',
      nav_logs: 'Logs',
      nav_webhooks: 'Webhooks',
      nav_files: 'Files',
      nav_settings: 'Settings',
      nav_installer: 'Installer',
      nav_logout: 'Logout',

      // Banner metrics
      banner_server_title: 'Server',
      banner_server_label: 'Type & Engine',
      banner_version_label: 'Version',
      banner_online_players: 'Online Players',
      banner_memory_title: 'RAM Memory',
      banner_ram_assigned: 'Allocated',
      banner_system_title: 'System & Storage',
      banner_cpu_server: 'Server CPU',
      banner_disk_usage: 'Disk Usage',
      banner_status_offline: 'Offline',
      banner_status_running: 'Running',
      banner_status_starting: 'Starting...',
      banner_status_stopping: 'Stopping...',
      banner_uptime: 'Uptime',
      banner_none_installed: 'No server installed',
      banner_status_label: 'Server Status:',
      banner_started_label: 'Server Started:',
      banner_uptime_label: 'Server Uptime:',
      banner_tz_label: 'Server Timezone:',
      banner_cpu_label: 'CPU Usage:',
      banner_mem_label: 'Memory Usage:',
      banner_players_label: 'Players:',
      banner_name_label: 'Server Name:',
      banner_version_label: 'Version:',
      banner_desc_label: 'Description:',
      banner_type_label: 'Server Type:',
      banner_tps_label: 'TPS Performance:',
      banner_server_details: 'Server Details',
      banner_expand: 'Expand',
      banner_collapse: 'Collapse',

      // Console Tab
      console_title: 'Real-Time Console',
      stat_cpu: 'CPU',
      stat_cpu_sub: 'Active core usage',
      stat_ram: 'RAM',
      stat_mem_sub: 'Of allocated memory',
      stat_disk: 'Storage',
      stat_disk_sub: 'Storage volume (/server_data)',
      stat_control: 'Control',
      console_auto_scroll: 'Auto-scroll',
      console_quick_cmds: 'Quick Commands',
      btn_start: 'Start',
      btn_start_title: 'Start Server',
      btn_stop: 'Stop',
      btn_stop_title: 'Stop Server',
      btn_restart: 'Restart',
      btn_restart_title: 'Restart Server',
      btn_kill: 'Force Kill',
      btn_kill_title: 'Force Kill Server',
      cmd_placeholder: 'Type a Minecraft command (e.g., list, op player, time set day)...',
      cmd_send: 'Send',
      console_clear: 'Clear Console',
      console_view_audit: 'Audit & Command History',

      // Installer Tab
      inst_title: 'Select Server Engine',
      inst_import_btn: 'Import Server (.zip)',
      inst_unlock_btn: 'Unlock Reinstall',
      inst_delete_btn: 'Delete Server',
      inst_reinstall_badge: 'REINSTALLATION UNLOCKED',
      inst_current_info: 'A server already exists in this directory (/data). Installation is locked to protect your worlds, plugins, and settings from accidental overwriting.',
      inst_desc_paper: 'Fast and optimized. Recommended for friends and plugins.',
      inst_desc_purpur: 'Enhanced Paper fork with high performance and deep customization.',
      inst_desc_vanilla: 'Pure original classic Minecraft, without plugins or mods.',
      inst_desc_fabric: 'Lightweight and fast for modern modpacks.',
      inst_desc_forge: 'The classic, battle-tested modding ecosystem.',
      inst_desc_bedrock: 'For mobile devices, consoles (Xbox, PlayStation, Switch), and Windows.',
      inst_res_title: 'Version & Resource Allocation',
      inst_server_name: 'Server Name',
      inst_server_name_hint: 'Descriptive name displayed in the top bar and Webhook notifications.',
      inst_mc_version: 'Minecraft Server Version',
      inst_loading_versions: 'Loading official versions...',
      inst_min_ram: 'Minimum RAM (-Xms)',
      inst_max_ram: 'Maximum RAM (-Xmx)',
      inst_cpu_cores: 'CPU Cores',
      inst_cpu_cores_hint: 'Logical processor limit for Java (0 = unlimited).',
      inst_disk_limit: 'Disk Limit (GB)',
      inst_disk_limit_hint: 'Assigned disk capacity for the data volume.',
      inst_aikar_title: 'Performance Optimizations (Aikar\'s Flags)',
      inst_aikar_desc: 'Recommended advanced flags to prevent garbage collection lag in Java G1GC.',
      inst_btn_install: 'Download & Install Server',
      inst_update_title: 'Update Server',
      inst_update_desc: 'Updates the server engine and binaries to the selected version. Your worlds, plugins, mods, and configuration files remain intact.',
      inst_update_btn: 'Update Server',

      // Tasks Tab
      tasks_title: 'Scheduled Tasks & Automations',
      tasks_desc: 'Automate periodic restarts, power schedules, recurring backups, and command execution using intervals or Cron expressions.',
      tasks_search_placeholder: 'Search tasks by name, action, command, or cron...',
      tasks_btn_new: 'New Task',
      tasks_col_name: 'Task Name',
      tasks_col_action: 'Action',
      tasks_col_schedule: 'Schedule',
      tasks_col_next: 'Next Run',
      tasks_col_status: 'Status',
      tasks_col_actions: 'Actions',
      tasks_empty: 'No scheduled tasks found. Click "New Task" to create one.',

      // Backups Tab
      backups_title: 'Backup Management',
      backups_desc: 'Create full server backups or select critical directories to save storage space.',
      backups_btn_create: 'Create Backup',
      backups_retention_title: 'Backup Configuration & Scope',
      backups_retention_desc: 'Configure which directories to include by default in scheduled backups and set retention limits to prevent filling up disk space.',
      backups_max_label: 'Maximum backups to keep:',
      backups_save_quota: 'Save Limit',
      backups_col_file: 'Backup Archive',
      backups_col_scope: 'Scope',
      backups_col_date: 'Creation Date',
      backups_col_size: 'Size',
      backups_col_type: 'Type',
      backups_empty: 'No backup archives found.',

      // Logs Tab
      logs_title: 'Audit & Console Command Logs',
      logs_stat_total: 'Total Records',
      logs_stat_total_sub: 'Chronological audit history',
      logs_stat_commands: 'Console Commands',
      logs_stat_commands_sub: 'Issued by administrators',
      logs_stat_system: 'System Events',
      logs_stat_system_sub: 'Starts, backups, and updates',
      logs_auto_refresh: 'Auto-refresh (5s)',
      logs_refresh: 'Refresh',
      logs_cat_all: 'All',
      logs_cat_console: '⌨️ Commands',
      logs_cat_server: '⚡ Server',
      logs_cat_backup: '💾 Backups',
      logs_cat_update: '🔄 Updates',
      logs_cat_security: '🛡️ Security',
      logs_cat_tasks: '⏱️ Tasks',
      logs_empty_title: 'No activity records match your search.',
      logs_empty_desc: 'Commands sent to the console and server lifecycle events will appear here automatically.',
      logs_col_timestamp: 'Date / Time',
      logs_col_category: 'Category',
      logs_col_action: 'Action',
      logs_col_details: 'Detail / Command',
      logs_col_user: 'User',
      logs_col_status: 'Status',

      // Webhooks Tab
      webhooks_title: 'Webhook Notifications',
      webhooks_desc: 'Receive automated notifications in your Discord channels, Telegram groups, or Email upon server state changes.',
      webhooks_events_title: 'Events to Trigger Notifications',
      webhooks_ev_started: 'Server Started',
      webhooks_ev_stopped: 'Server Stopped',
      webhooks_ev_crashed: 'Server Crashed',
      webhooks_ev_backup: 'Backup Completed',
      webhooks_ev_task: 'Scheduled Task Executed',

      // Files Tab
      files_title: 'File Manager',
      files_upload: 'Upload File',
      files_new_file: 'New File',
      files_new_folder: 'New Folder',
      files_refresh: 'Refresh',
      files_root: 'Server Root',
      files_rename_title: 'Rename',
      files_rename_label: 'New Name:',
      files_btn_rename: 'Save',
      files_create_file_title: 'New File',
      files_create_file_label: 'File Name (with extension):',
      files_btn_create_file: 'Create File',
      ctx_open_edit: 'Open / Edit',
      ctx_open_folder: 'Open Folder',
      ctx_rename: 'Rename',
      ctx_download: 'Download',
      ctx_compress_zip: 'Compress to .ZIP',
      ctx_extract_zip: 'Extract here',
      ctx_duplicate: 'Duplicate',
      ctx_copy_path: 'Copy path',
      ctx_delete: 'Delete',
      ctx_new_file: 'New File',
      ctx_new_folder: 'New Folder',
      ctx_upload: 'Upload File',
      ctx_refresh: 'Refresh',

      // Settings Tab
      settings_title: 'Server Settings',
      settings_save_btn: 'Save Settings',
      settings_danger_zone: 'Danger Zone',
      settings_system_behavior_title: 'Server & System Behavior',
      settings_autostart_label: 'Server Autostart',
      settings_autostart_hint: 'Automatically start the Minecraft server when the Dockraft container or service turns on.',
      settings_crash_label: 'Crash Detection & Auto-Restart',
      settings_crash_hint: 'Detect unexpected server exits and automatically restart with crash-loop backoff protection (max 3 retries in 2 min).',

      // Metrics Tab
      metrics_title: 'Telemetry & Performance',
      metrics_subtitle: 'Real-time CPU, RAM and player tracking. Ultra-lightweight in-memory buffer (0% disk).',
      metrics_live_active: 'Live (10s)',
      metrics_btn_reset: 'Clear History',
      metrics_kpi_cpu: 'CPU Usage',
      metrics_kpi_ram: 'RAM Memory',
      metrics_kpi_players: 'Online Players',
      metrics_kpi_uptime: 'Active Uptime',
      metrics_peak: 'Peak:',
      metrics_avg: 'Avg:',
      metrics_assigned: 'Assigned:',
      metrics_record: 'Session Peak:',
      metrics_status: 'Status:',
      metrics_chart_title: 'Performance History',
      metrics_legend_cpu: 'CPU %',
      metrics_legend_ram_pct: 'RAM %',
      metrics_legend_ram_mb: 'RAM (MB)',
      metrics_legend_players: 'Players',
      metrics_gathering: 'Gathering in-memory server telemetry...',

      // Players Tab
      players_section_title: 'Players:',
      players_banned_title: 'Banned Players:',
      players_btn_add: 'Add',
      players_btn_kick_all: 'Kick all',
      players_col_player: 'Player',
      players_col_status: 'Status',
      players_col_actions: 'Actions',
      players_col_reason: 'Reason',
      players_modal_add_title: 'Add Player to Directory',
      players_modal_name_label: 'Username (Gamertag / Nick)',
      players_modal_btn_confirm: 'Save Player',
      players_reason_label: 'Reason (Optional):',

      // Footer
      footer_desc: 'Ultra-lightweight, modular control panel for Minecraft Java and Bedrock servers in Docker.',
      footer_copyright: '© 2026 Dockraft · Distributed under GNU GPLv3 License',

      // Modals
      modal_create_backup_title: 'Create Backup Archive',
      modal_scope_full: 'Full Server',
      modal_scope_full_desc: 'Complete backup of worlds, plugins, mods, configuration, and binaries.',
      modal_scope_worlds: 'Worlds Only',
      modal_scope_worlds_desc: 'Backs up only Minecraft world folders and server.properties.',
      modal_scope_plugins: 'Worlds + Plugins / Mods',
      modal_scope_plugins_desc: 'Protects game progress and installed extensions without large binaries.',
      modal_scope_custom: 'Custom Selection',
      modal_scope_custom_desc: 'Individually choose specific files and folders to back up.',
      modal_btn_cancel: 'Cancel',
      modal_btn_confirm: 'Confirm',

      // Settings: System behavior & Session timeout
      settings_system_behavior_title: 'Server & System Behavior',
      settings_autostart_label: 'Automatic Server Startup',
      settings_autostart_hint: 'Automatically start the Minecraft server when Dockraft container/service starts.',
      settings_crash_label: 'Crash Detection & Auto-Restart',
      settings_crash_hint: 'Detects unexpected server crashes and restarts automatically with loop protection (max 3 retries in 2 min).',
      settings_session_timeout_label: 'Session Timeout (minutes)',
      settings_session_timeout_hint: 'Inactivity period after which the panel session automatically expires for security (default: 60 min).',

      // Login
      login_title: 'Sign In — Dockraft',
      login_heading: 'Dockraft',
      login_subtitle: 'Minecraft Server Control Panel',
      login_username_label: 'Username',
      login_password_label: 'Password',
      login_submit_btn: 'Sign In',
      login_locked_notice: 'Access temporarily locked for security due to too many failed attempts.',
      login_retry_in: 'You can retry in:',
      login_session_expired_title: 'Session Expired',
      login_session_expired_desc: 'Your session has expired due to inactivity or security timeout. Please sign in again to continue.',

      // Toasts
      toast_lang_changed: 'Language switched to English',
      toast_server_started: 'Server started',
      toast_server_stopped: 'Stop requested',
      toast_server_restarted: 'Restart requested',
      toast_server_killed: 'Server force-killed'
    }
  },

  init() {
    // 1. Detect language preference: localStorage > cookie > navigator language > 'es'
    let saved = localStorage.getItem('dockraft_lang');
    if (!saved) {
      const match = document.cookie.match(/(?:^|;\s*)dockraft_lang=([^;]+)/);
      if (match) saved = match[1];
    }
    if (!saved && navigator.language && navigator.language.startsWith('en')) {
      saved = 'en';
    }
    this.currentLang = (saved === 'en') ? 'en' : 'es';
    this.applyLanguage(this.currentLang, false);
  },

  t(key, fallback = '') {
    const dict = this.translations[this.currentLang] || this.translations['es'];
    return dict[key] || fallback || key;
  },

  toggleLanguage() {
    const nextLang = this.currentLang === 'es' ? 'en' : 'es';
    this.setLanguage(nextLang);
    if (typeof App !== 'undefined' && App.showToast) {
      App.showToast(this.t('toast_lang_changed'), 'success');
    }
  },

  setLanguage(lang) {
    if (lang !== 'es' && lang !== 'en') lang = 'es';
    this.currentLang = lang;
    localStorage.setItem('dockraft_lang', lang);
    document.cookie = `dockraft_lang=${lang}; path=/; max-age=31536000; SameSite=Lax`;
    this.applyLanguage(lang, true);
  },

  applyLanguage(lang, triggerEvent = true) {
    const dict = this.translations[lang] || this.translations['es'];
    document.documentElement.lang = lang;

    // Update Language Button in Footer
    const labelEl = document.getElementById('lang-current-label');
    if (labelEl) {
      labelEl.textContent = dict.lang_code;
    }
    const btnEl = document.getElementById('btn-lang-toggle');
    if (btnEl) {
      btnEl.title = dict.toggle_lang_title;
      btnEl.setAttribute('aria-label', dict.toggle_lang_title);
    }

    // Update Elements with data-i18n
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (dict[key]) {
        el.textContent = dict[key];
      }
    });

    // Update Placeholders with data-i18n-placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (dict[key]) {
        el.placeholder = dict[key];
      }
    });

    // Update Titles with data-i18n-title
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      if (dict[key]) {
        el.title = dict[key];
      }
    });

    // Common Static Elements by ID if present
    this.translateKnownElements(dict);

    if (triggerEvent) {
      window.dispatchEvent(new CustomEvent('dockraft:language_changed', { detail: { lang } }));
    }
  },

  translateKnownElements(dict) {
    // Navigation Tabs
    const tabMap = {
      'console': dict.nav_console,
      'tasks': dict.nav_tasks,
      'backups': dict.nav_backups,
      'webhooks': dict.nav_webhooks,
      'files': dict.nav_files,
      'settings': dict.nav_settings,
      'installer': dict.nav_installer
    };
    document.querySelectorAll('.nav-btn[data-tab]').forEach(btn => {
      const tab = btn.getAttribute('data-tab');
      if (tabMap[tab]) {
        const textSpan = btn.querySelector('.tab-text') || btn.querySelector('span:not(.tab-icon)');
        if (textSpan) {
          textSpan.textContent = tabMap[tab];
        }
      }
    });

    // Console control buttons
    const btnStart = document.getElementById('btn-start') || document.getElementById('btn-server-start');
    if (btnStart) {
      const text = btnStart.querySelector('span') || btnStart;
      text.textContent = dict.btn_start;
      if (dict.btn_start_title) {
        btnStart.title = dict.btn_start_title;
        btnStart.setAttribute('aria-label', dict.btn_start_title);
      }
    }
    const btnStop = document.getElementById('btn-stop') || document.getElementById('btn-server-stop');
    if (btnStop) {
      const text = btnStop.querySelector('span') || btnStop;
      text.textContent = dict.btn_stop;
      if (dict.btn_stop_title) {
        btnStop.title = dict.btn_stop_title;
        btnStop.setAttribute('aria-label', dict.btn_stop_title);
      }
    }
    const btnRestart = document.getElementById('btn-restart') || document.getElementById('btn-server-restart');
    if (btnRestart) {
      btnRestart.title = dict.btn_restart_title || dict.btn_restart;
      btnRestart.setAttribute('aria-label', dict.btn_restart_title || dict.btn_restart);
    }
    const btnKill = document.getElementById('btn-kill') || document.getElementById('btn-server-kill');
    if (btnKill) {
      btnKill.title = dict.btn_kill_title || dict.btn_kill;
      btnKill.setAttribute('aria-label', dict.btn_kill_title || dict.btn_kill);
    }

    // Console input & send button
    const cmdInput = document.getElementById('terminal-cmd-input') || document.getElementById('console-cmd-input');
    if (cmdInput) cmdInput.placeholder = dict.cmd_placeholder;
    const btnSend = document.getElementById('btn-send-cmd') || document.querySelector('.terminal-input-bar button');
    if (btnSend) {
      const t = btnSend.querySelector('span') || btnSend;
      t.textContent = dict.cmd_send;
    }

    // Installer cards
    const cardDescs = {
      'paper': dict.inst_desc_paper,
      'purpur': dict.inst_desc_purpur,
      'vanilla': dict.inst_desc_vanilla,
      'fabric': dict.inst_desc_fabric,
      'forge': dict.inst_desc_forge,
      'bedrock': dict.inst_desc_bedrock
    };
    document.querySelectorAll('.type-card[data-type]').forEach(card => {
      const type = card.getAttribute('data-type');
      if (cardDescs[type]) {
        const descEl = card.querySelector('.type-desc');
        if (descEl) descEl.textContent = cardDescs[type];
      }
    });

    // Installer action buttons
    const btnInstall = document.getElementById('btn-install-server');
    if (btnInstall && !btnInstall.disabled) {
      btnInstall.textContent = dict.inst_btn_install;
    }

    // Footer description & copyright
    const footerDesc = document.querySelector('.footer-desc');
    if (footerDesc) footerDesc.textContent = dict.footer_desc;
    const footerCopy = document.querySelector('.footer-copyright');
    if (footerCopy) footerCopy.textContent = dict.footer_copyright;

    // Login page elements
    const loginSubtitle = document.querySelector('.dockraft-brand-subtitle');
    if (loginSubtitle) loginSubtitle.textContent = dict.login_subtitle;
    const btnLogin = document.getElementById('btn-login-submit');
    if (btnLogin && !btnLogin.disabled) {
      const t = document.getElementById('btn-login-text') || btnLogin.querySelector('#btn-login-text');
      if (t) t.textContent = dict.login_submit_btn;
    }

    // Refresh dynamic Console stats if available
    if (typeof Console !== 'undefined' && Console.lastStats) {
      Console.updateStatsUI(Console.lastStats);
    }
  },

  formatUptime(seconds) {
    if (!seconds || seconds <= 0) {
      return this.t('banner_status_offline', 'Fuera de línea');
    }
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    const isEn = this.currentLang === 'en';

    const parts = [];
    if (days > 0) {
      parts.push(isEn ? (days === 1 ? '1 day' : `${days} days`) : (days === 1 ? '1 día' : `${days} días`));
    }
    if (hours > 0) {
      parts.push(isEn ? (hours === 1 ? '1 hour' : `${hours} hours`) : (hours === 1 ? '1 hora' : `${hours} horas`));
    }
    if (minutes > 0 || hours > 0 || days > 0) {
      parts.push(isEn ? (minutes === 1 ? '1 minute' : `${minutes} minutes`) : (minutes === 1 ? '1 minuto' : `${minutes} minutos`));
    }
    parts.push(isEn ? (secs === 1 ? '1 second' : `${secs} seconds`) : (secs === 1 ? '1 segundo' : `${secs} segundos`));

    const andWord = isEn ? ' and ' : ' y ';
    if (parts.length === 1) return parts[0];
    if (parts.length === 2) return parts[0] + andWord + parts[1];
    return parts.slice(0, -1).join(', ') + andWord + parts[parts.length - 1];
  }
};

// Initialize on DOM Ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => I18n.init());
} else {
  I18n.init();
}
