// Dockraft Console tab i18n dictionary (ES / EN)
// Registered into I18n before I18n.init() so [data-i18n] elements and
// dynamic JS strings (Console module) resolve to the active language.
(function () {
  if (typeof I18n === 'undefined') return;

  I18n.registerModule({
    // --- WebSocket / terminal status lines emitted by the panel (not server logs) ---
    t_console_ws_connected: '[Dockraft] Connected to live server console stream.',

    // --- Server action (Kill) confirmation dialog ---
    t_console_kill_confirm_title: 'Forzar Apagado Inmediato (Kill)',
    t_console_kill_confirm_msg: '¿Confirmas forzar el apagado inmediato (Kill) del servidor?\n\nSe terminará cualquier proceso de Minecraft activo inmediatamente y se liberarán los bloqueos de disco.',
    t_console_kill_confirm_btn: 'Forzar Apagado',

    // --- Server action result toasts (fallbacks) ---
    t_console_action_success: 'Acción {0} ejecutada',
    t_console_action_error: 'Error al ejecutar acción {0}',

    // --- Install wizard welcome ---
    t_console_welcome_toast: 'Bienvenido: Selecciona una versión para instalar tu servidor',

    // --- Not-installed banner ---
    t_console_banner_no_install: 'No instalado',

    // --- Top overview (installed server) ---
    t_console_type_server: 'Servidor',
    t_console_not_started: 'No iniciado',
    t_console_motd_default: 'A Dockraft Minecraft Server',

    // --- TPS health badges ---
    t_console_tps_optimal: 'Óptimo',
    t_console_tps_lag: 'Lag Severo',
    t_console_tps_moderate: 'Carga Moderada',
    t_console_tps_offline: 'Fuera de línea',

    // --- Crash alert banner ---
    t_console_crash_alert: '¡Alerta de Caída! ',
    t_console_crash_unknown: 'Error no controlado',
    t_console_crash_view_cause: 'Ver Causa y Solución',
    t_console_crash_title_default: 'Caída inesperada',
    t_console_crash_toast: 'El servidor se detuvo: {0}',

    // --- Diagnostics modal ---
    t_console_diag_open: 'Diagnóstico & Logs',
    t_console_diag_no_issue: 'Sin problemas detectados',
    t_console_diag_ok_message: 'El servidor opera con normalidad.',
    t_console_diag_ok_reco: 'Todo en orden.',
    t_console_diag_err_analysis: 'Error al ejecutar análisis',
    t_console_diag_err_query: 'No se pudo consultar el endpoint de diagnósticos.',

    // --- Share log (mclo.gs) ---
    t_console_share_btn: 'Subir y Generar Enlace Seguro (mclo.gs)',
    t_console_share_uploading: 'Subiendo y anonimizando registro...',
    t_console_share_err_upload: 'Error al subir log a mclo.gs',
    t_console_share_ok: 'Log subido a mclo.gs con éxito',
    t_console_share_err: 'Error al compartir log',
    t_console_share_copied_mclogs: 'Enlace de mclo.gs copiado al portapapeles',
    t_console_share_copied: 'Enlace copiado'
  }, {
    // --- WebSocket / terminal status lines emitted by the panel (not server logs) ---
    t_console_ws_connected: '[Dockraft] Connected to live server console stream.',

    // --- Server action (Kill) confirmation dialog ---
    t_console_kill_confirm_title: 'Force Kill Server',
    t_console_kill_confirm_msg: 'Do you confirm the immediate forced shutdown (Kill) of the server?\n\nAny active Minecraft process will be terminated immediately and disk locks will be released.',
    t_console_kill_confirm_btn: 'Force Kill',

    // --- Server action result toasts (fallbacks) ---
    t_console_action_success: 'Action {0} executed',
    t_console_action_error: 'Error executing action {0}',

    // --- Install wizard welcome ---
    t_console_welcome_toast: 'Welcome: pick a version to install your server',

    // --- Not-installed banner ---
    t_console_banner_no_install: 'Not installed',

    // --- Top overview (installed server) ---
    t_console_type_server: 'Server',
    t_console_not_started: 'Not started',
    t_console_motd_default: 'A Dockraft Minecraft Server',

    // --- TPS health badges ---
    t_console_tps_optimal: 'Optimal',
    t_console_tps_lag: 'Severe Lag',
    t_console_tps_moderate: 'Moderate Load',
    t_console_tps_offline: 'Offline',

    // --- Crash alert banner ---
    t_console_crash_alert: 'Crash Alert! ',
    t_console_crash_unknown: 'Unhandled error',
    t_console_crash_view_cause: 'View Cause & Solution',
    t_console_crash_title_default: 'Unexpected crash',
    t_console_crash_toast: 'The server stopped: {0}',

    // --- Diagnostics modal ---
    t_console_diag_open: 'Diagnostics & Logs',
    t_console_diag_no_issue: 'No issues detected',
    t_console_diag_ok_message: 'The server is operating normally.',
    t_console_diag_ok_reco: 'All good.',
    t_console_diag_err_analysis: 'Error running the analysis',
    t_console_diag_err_query: 'The diagnostics endpoint could not be queried.',

    // --- Share log (mclo.gs) ---
    t_console_share_btn: 'Upload & Generate Safe Link (mclo.gs)',
    t_console_share_uploading: 'Uploading and anonymizing log...',
    t_console_share_err_upload: 'Error uploading log to mclo.gs',
    t_console_share_ok: 'Log uploaded to mclo.gs successfully',
    t_console_share_err: 'Error sharing log',
    t_console_share_copied_mclogs: 'mclo.gs link copied to clipboard',
    t_console_share_copied: 'Link copied'
  });
})();
