// Dockraft Players Tab i18n (ES/EN)
// Registered into I18n before I18n.init() so [data-i18n] elements and
// dynamic JS strings (Players module) resolve to the active language.
(function () {
  if (typeof I18n === 'undefined') return;

  I18n.registerModule({
    // --- Players tab headers / toolbar ---
    t_player_section_title: 'Jugadores:',
    t_player_banned_section_title: 'Jugadores Baneados:',
    t_player_search_placeholder: 'Buscar jugador...',
    t_player_refresh_title: 'Actualizar lista',
    t_player_refresh_banned_title: 'Actualizar lista de baneados',
    t_player_btn_add: 'Añadir',
    t_player_btn_add_title: 'Registrar jugador manualmente',
    t_player_btn_kick_all: 'Expulsar a todos',
    t_player_btn_kick_all_title: 'Expulsar a todos los jugadores conectados',
    t_player_online_badge: '{0} en línea',
    t_player_kickall_count_title: 'Expulsar a los {0} jugador(es) en línea',
    t_player_kickall_none_title: 'No hay jugadores conectados actualmente',

    // --- Players table columns / empty states / status ---
    t_player_col_player: 'Jugador',
    t_player_col_status: 'Estado',
    t_player_col_reason: 'Motivo',
    t_player_col_actions: 'Acciones',
    t_player_empty_players: 'No hay jugadores registrados en el servidor aún.',
    t_player_empty_banned: 'No hay jugadores baneados actualmente.',
    t_player_online: 'En línea',
    t_player_offline: 'Fuera de línea',
    t_player_never: 'Nunca',
    t_player_last_seen: 'Última vez',
    t_player_status_banned: 'Baneado',
    t_player_reason_default: 'Baneado por un operador',

    // --- Row action buttons ---
    t_player_btn_ban: 'Banear',
    t_player_btn_ban_title: 'Banear jugador',
    t_player_btn_kick: 'Expulsar',
    t_player_btn_kick_title: 'Expulsar jugador',
    t_player_btn_op_title: 'Hacer Operador del servidor',
    t_player_btn_deop_title: 'Revocar permisos de operador',
    t_player_btn_pardon: 'Desbanear',
    t_player_btn_pardon_title: 'Desbanear jugador',

    // --- Action modal (static labels) ---
    t_player_action_hint: 'Este mensaje se mostrará directamente en la pantalla de desconexión del cliente Minecraft.',
    t_player_chips_label: 'Motivos rápidos sugeridos:',

    // --- Quick reason chips: ban ---
    t_player_chip_ban_hacks: 'Uso de Hacks / Trampas',
    t_player_chip_ban_grief: 'Griefing / Destrucción',
    t_player_chip_ban_toxic: 'Comportamiento Tóxico',
    t_player_chip_ban_spam: 'Spam o Publicidad',
    t_player_chip_ban_rules: 'Incumplimiento de Reglas',

    // --- Quick reason chips: kick ---
    t_player_chip_kick_afk: 'Inactividad prolongada (AFK)',
    t_player_chip_kick_warn: 'Advertencia del Administrador',
    t_player_chip_kick_lag: 'Lag / Ping excesivo',
    t_player_chip_kick_chat: 'Spam en el chat',
    t_player_chip_kick_maint: 'Mantenimiento temporal',

    // --- Quick reason chips: kick all ---
    t_player_chip_all_maint: 'Mantenimiento programado del servidor',
    t_player_chip_all_restart: 'Reinicio del servidor',
    t_player_chip_all_backup: 'Copia de seguridad en progreso',
    t_player_chip_all_update: 'Actualización del sistema',

    // --- Add player modal ---
    t_player_modal_add_title: 'Añadir Jugador al Directorio',
    t_player_modal_name_label: 'Nombre de usuario (Gamertag / Nick)',
    t_player_modal_name_placeholder: 'ej: Marcus8604',
    t_player_modal_add_hint: 'Registra el nombre de un jugador para gestionarlo antes de que se conecte.',
    t_player_modal_btn_confirm: 'Guardar Jugador',

    // --- Kick action modal ---
    t_player_kick_title: 'Expulsar a {0}',
    t_player_kick_subtitle: 'Jugador conectado a la partida',
    t_player_kick_desc: 'El jugador será desconectado inmediatamente pero podrá volver a conectarse. Minecraft mostrará este motivo directamente en su pantalla de desconexión.',
    t_player_kick_reason_label: 'Motivo de Expulsión (Visible en Minecraft):',
    t_player_kick_reason_placeholder: 'ej: Inactividad prolongada o advertencia del admin',
    t_player_kick_confirm_btn: 'Expulsar (Kick)',

    // --- Ban action modal ---
    t_player_ban_title: 'Banear a {0}',
    t_player_ban_subtitle: 'Bloqueo permanente en banned-players.json',
    t_player_ban_desc: 'El jugador será desconectado inmediatamente y bloqueado permanentemente. Minecraft mostrará este motivo cada vez que intente conectarse al servidor.',
    t_player_ban_reason_label: 'Motivo del Baneo (Visible en Minecraft):',
    t_player_ban_reason_placeholder: 'ej: Infracción de normas o trampas',
    t_player_ban_confirm_btn: 'Banear Jugador',

    // --- Kick-all action modal ---
    t_player_kickall_modal_title: 'Expulsar a Todos los Jugadores',
    t_player_kickall_target: 'Todos los jugadores en línea (@a)',
    t_player_kickall_subtitle: '{0} jugador(es) conectado(s) actualmente',
    t_player_kickall_desc: 'Se desconectará de inmediato a todos los jugadores que están dentro de la partida. Todos verán este motivo en su pantalla de Minecraft.',
    t_player_kickall_reason_label: 'Motivo de Expulsión Masiva (Visible para todos):',
    t_player_kickall_default_reason: 'Mantenimiento del servidor',
    t_player_kickall_reason_placeholder: 'ej: Mantenimiento del servidor o reinicio',
    t_player_kickall_confirm_btn: 'Expulsar a Todos',

    // --- Pardon (unban) confirm ---
    t_player_pardon_confirm_title: 'Desbanear Jugador',
    t_player_pardon_confirm_msg: '¿Deseas desbanear y permitir el acceso de nuevo a {0}?',
    t_player_pardon_confirm_btn: 'Desbanear',

    // --- OP / De-OP confirm ---
    t_player_op_confirm_title: 'Dar Operador (OP)',
    t_player_op_confirm_msg: '¿Confirmas dar permisos de Operador (OP) a {0}?',
    t_player_op_confirm_btn: 'Hacer OP',
    t_player_deop_confirm_title: 'Quitar Operador (DEOP)',
    t_player_deop_confirm_msg: '¿Confirmas quitar permisos de Operador (DEOP) a {0}?',
    t_player_deop_confirm_btn: 'Quitar OP',

    // --- Error toast fallbacks ---
    t_player_err_kick: 'Error al expulsar',
    t_player_err_kickall: 'Error al expulsar a todos',
    t_player_err_ban: 'Error al banear',
    t_player_err_pardon: 'Error al desbanear',
    t_player_err_op: 'Error al cambiar permisos de operador'
  }, {
    // --- Players tab headers / toolbar ---
    t_player_section_title: 'Players:',
    t_player_banned_section_title: 'Banned Players:',
    t_player_search_placeholder: 'Search player...',
    t_player_refresh_title: 'Refresh list',
    t_player_refresh_banned_title: 'Refresh banned list',
    t_player_btn_add: 'Add',
    t_player_btn_add_title: 'Manually register a player',
    t_player_btn_kick_all: 'Kick all',
    t_player_btn_kick_all_title: 'Kick all connected players',
    t_player_online_badge: '{0} online',
    t_player_kickall_count_title: 'Kick {0} online player(s)',
    t_player_kickall_none_title: 'No players are currently online',

    // --- Players table columns / empty states / status ---
    t_player_col_player: 'Player',
    t_player_col_status: 'Status',
    t_player_col_reason: 'Reason',
    t_player_col_actions: 'Actions',
    t_player_empty_players: 'No players registered on the server yet.',
    t_player_empty_banned: 'No banned players right now.',
    t_player_online: 'Online',
    t_player_offline: 'Offline',
    t_player_never: 'Never',
    t_player_last_seen: 'Last seen',
    t_player_status_banned: 'Banned',
    t_player_reason_default: 'Banned by an operator',

    // --- Row action buttons ---
    t_player_btn_ban: 'Ban',
    t_player_btn_ban_title: 'Ban player',
    t_player_btn_kick: 'Kick',
    t_player_btn_kick_title: 'Kick player',
    t_player_btn_op_title: 'Make server operator',
    t_player_btn_deop_title: 'Revoke operator permissions',
    t_player_btn_pardon: 'Unban',
    t_player_btn_pardon_title: 'Unban player',

    // --- Action modal (static labels) ---
    t_player_action_hint: 'This message will be shown directly on the Minecraft client disconnect screen.',
    t_player_chips_label: 'Suggested quick reasons:',

    // --- Quick reason chips: ban ---
    t_player_chip_ban_hacks: 'Use of Hacks / Cheating',
    t_player_chip_ban_grief: 'Griefing / Destruction',
    t_player_chip_ban_toxic: 'Toxic Behavior',
    t_player_chip_ban_spam: 'Spam or Advertising',
    t_player_chip_ban_rules: 'Breaking the Rules',

    // --- Quick reason chips: kick ---
    t_player_chip_kick_afk: 'Extended inactivity (AFK)',
    t_player_chip_kick_warn: 'Administrator Warning',
    t_player_chip_kick_lag: 'Excessive Lag / Ping',
    t_player_chip_kick_chat: 'Chat spam',
    t_player_chip_kick_maint: 'Temporary maintenance',

    // --- Quick reason chips: kick all ---
    t_player_chip_all_maint: 'Scheduled server maintenance',
    t_player_chip_all_restart: 'Server restart',
    t_player_chip_all_backup: 'Backup in progress',
    t_player_chip_all_update: 'System update',

    // --- Add player modal ---
    t_player_modal_add_title: 'Add Player to Directory',
    t_player_modal_name_label: 'Username (Gamertag / Nick)',
    t_player_modal_name_placeholder: 'e.g., Marcus8604',
    t_player_modal_add_hint: 'Register a player name to manage them before they connect.',
    t_player_modal_btn_confirm: 'Save Player',

    // --- Kick action modal ---
    t_player_kick_title: 'Kick {0}',
    t_player_kick_subtitle: 'Player currently connected to the game',
    t_player_kick_desc: 'The player will be disconnected immediately but will be able to reconnect. Minecraft will show this reason directly on their disconnect screen.',
    t_player_kick_reason_label: 'Kick Reason (Visible in Minecraft):',
    t_player_kick_reason_placeholder: 'e.g., Extended inactivity or admin warning',
    t_player_kick_confirm_btn: 'Kick Player',

    // --- Ban action modal ---
    t_player_ban_title: 'Ban {0}',
    t_player_ban_subtitle: 'Permanent block stored in banned-players.json',
    t_player_ban_desc: 'The player will be disconnected immediately and permanently banned. Minecraft will show this reason every time they try to connect to the server.',
    t_player_ban_reason_label: 'Ban Reason (Visible in Minecraft):',
    t_player_ban_reason_placeholder: 'e.g., Breaking the rules or cheating',
    t_player_ban_confirm_btn: 'Ban Player',

    // --- Kick-all action modal ---
    t_player_kickall_modal_title: 'Kick All Players',
    t_player_kickall_target: 'All online players (@a)',
    t_player_kickall_subtitle: '{0} player(s) currently connected',
    t_player_kickall_desc: 'All players currently inside the game will be disconnected immediately. Everyone will see this reason on their Minecraft screen.',
    t_player_kickall_reason_label: 'Mass Kick Reason (Visible to everyone):',
    t_player_kickall_default_reason: 'Server maintenance',
    t_player_kickall_reason_placeholder: 'e.g., Server maintenance or restart',
    t_player_kickall_confirm_btn: 'Kick All',

    // --- Pardon (unban) confirm ---
    t_player_pardon_confirm_title: 'Unban Player',
    t_player_pardon_confirm_msg: 'Do you want to unban {0} and allow access again?',
    t_player_pardon_confirm_btn: 'Unban',

    // --- OP / De-OP confirm ---
    t_player_op_confirm_title: 'Grant Operator (OP)',
    t_player_op_confirm_msg: 'Do you want to grant Operator (OP) permissions to {0}?',
    t_player_op_confirm_btn: 'Make OP',
    t_player_deop_confirm_title: 'Remove Operator (DEOP)',
    t_player_deop_confirm_msg: 'Do you want to remove Operator (DEOP) permissions from {0}?',
    t_player_deop_confirm_btn: 'Remove OP',

    // --- Error toast fallbacks ---
    t_player_err_kick: 'Error kicking player',
    t_player_err_kickall: 'Error kicking all players',
    t_player_err_ban: 'Error banning player',
    t_player_err_pardon: 'Error unbanning player',
    t_player_err_op: 'Error changing operator permissions'
  });
})();
