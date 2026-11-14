# Registro de Cambios (Changelog)

Todos los cambios notables en **Dockraft** se documentan en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

---

## [1.5.0] - 2026-11-13

### Añadido (Added)
- **Políticas de Respaldo Reutilizables y Rotación Global (`app/core/backup_manager.py`, `app/routers/backups.py`, `app/routers/tasks.py`, `app/core/task_scheduler.py`, `web/templates/tabs/backups.html`, `web/templates/components/modals.html`, `web/static/js/backups.js`, `web/static/js/tasks.js`):**
  - Gestión de hasta 4 políticas de respaldo configurables (alcance completo o personalizado, compresión ZIP, apagado seguro, `pre_command` y `post_command`), seleccionables al programar tareas de tipo `backup`.
  - Ejecución automática de `save-all` antes de copias con el servidor en línea, soporte para comando posterior (`post_command`), nombres normalizados (`<server-slug>_YYYY-MM-DD_HH-MM-SS.zip`) con metadatos en `.backups_meta.json`, filtros por origen (`Todas`, `Automáticas`, `Manuales`) y modal rápido de retención global.
- **Selector de Idioma en el Login (`web/templates/login.html`, `web/static/js/login.js`, `web/static/js/i18n.js`):**
  - Botón `ES` / `EN` en la tarjeta de inicio de sesión conectado mediante `addEventListener` (compatible con CSP) y mensaje simplificado de sesión caducada (`login_session_expired_desc`).

### Cambiado (Changed)
- **Rediseño Visual del Frontend (`web/static/css/style.css`, `web/static/css/redesign.css`, `web/templates/base.html`, `web/templates/index.html`, `web/templates/components/banner.html`, `web/templates/tabs/console.html`):**
  - Adopción de la paleta *Mineral Slate & Moss* (`#141619` Basalt, `#1b1e23` Andesite, `#23272e` Slate, `#e5e7eb` Chalk, `#3ca374` Moss) con tipografías `Outfit` y `JetBrains Mono` y consola inspirada en Nord (`#101215` / `#d8dee9`).
  - Navegación con barra lateral fija en escritorio (`244px`, `>= 1141px`), barra superior adaptable en móvil (`<= 1140px`) y tira de telemetría sticky (`.server-overview-banner`).
  - Unificación de estilos de tablas, tarjetas y badges en Jugadores, Tareas Programadas, Backups y Métricas.
  - Rediseño del modal de tareas programadas (`#task-modal`) con selector segmentado de programación.
- **Rediseño de Webhooks y Notificaciones (`web/templates/tabs/webhooks.html`, `web/templates/components/modals.html`, `web/static/js/webhooks.js`):**
  - Reorganización de los eventos desencadenantes en una grilla de 3 columnas con switches de activación/desactivación y autoguardado inmediato (`saveEvents()`).
  - Agrupación de los canales de notificación (Discord, Telegram, Correo Electrónico) dentro del modal `#webhooks-channels-modal` y ajuste de `z-index: 1050` en `#webhook-config-modal`.
- **Nuevos Logos SVG y PWA (`web/static/img/dockraft_logo.svg`, `web/static/img/dockraft_mark.svg`, `web/templates/base.html`, `web/templates/components/header.html`, `web/templates/components/footer.html`, `web/templates/login.html`, `web/static/manifest.json`, `web/static/sw.js`, `README.md`):**
  - Reemplazo integral de los logos PNG por `dockraft_logo.svg` y `dockraft_mark.svg` en toda la interfaz, metadatos PWA, `README.md` y Service Worker (`dockraft-v13`).
- **Simplificación de Ajustes (`web/templates/tabs/settings.html`, `web/static/js/i18n-ext/i18n-settings.js`):**
  - Limpieza de textos y etiquetas en la vista de configuración del servidor.

### Corregido (Fixed)
- **Integridad de Layout y Controles (`web/templates/tabs/installer.html`, `web/templates/tabs/settings.html`, `web/static/js/installer.js`):**
  - Eliminación de un cierre `</div>` huérfano en `installer.html`.
  - Corrección del ancho del input `#setting-session-timeout` en `settings.html`.
  - Persistencia del estado deshabilitado de `#btn-install-server` al cambiar de pestaña durante una instalación activa en `installer.js`.
- **Protección de Backups Durante Descargas/Instalaciones (`app/core/backup_manager.py`, `app/core/task_scheduler.py`):**
  - Bloqueo de copias manuales y omisión de copias programadas mientras `downloader.progress["is_downloading"]` está activo.
- **Exportación CSV de Logs con UTF-8 BOM (`app/core/activity_manager.py`):**
  - Escritura de BOM UTF-8 (`\ufeff`) al exportar logs a CSV para conservar correctamente tildes y `ñ`/`Ñ` en Excel.
- **Cobertura Completa de Traducciones ES/EN (`web/static/js/i18n.js`, `web/static/js/i18n-ext/*.js`, `web/static/js/console.js`, `web/static/js/logs.js`, `web/static/js/installer.js`, `web/static/js/backups.js`, `web/static/js/tasks.js`, `web/templates/tabs/logs.html`, `web/templates/components/modals.html`):**
  - Traducción de estados de servidor (`No iniciado` / `Fuera de línea`), placeholders en modales de respaldo, buscador/insignias/registros en Logs y selectores/tarjetas de versiones en el Instalador.
  - Refactorización de `refreshLanguage()` en `installer.js` (`_renderUpdateInfo()`) para actualizar el idioma al instante usando la caché en memoria sin reconsultar `/api/installer/update-info`.

### Eliminado (Removed)
- **Activos y Código Obsoleto:**
  - Eliminación de los archivos de imagen obsoletos `web/static/img/dockraft_logo.png` y `web/static/img/logo.svg`.
  - Retiro del badge de edición `#settings-badge-edition`, el banner de ejecución nativa C++ en `settings.html` (junto con sus claves `t_setting_native_*` en `i18n-settings.js`) y el botón redundante `#btn-save-webhooks` en `webhooks.html`.

---

## [1.4.3] - 2026-11-13

### Corregido (Fixed)
- **Compatibilidad CSP con Manejadores de Eventos Inline (`app/main.py`, `web/templates/login.html`, `web/static/js/login.js`):**
  - Restauración de `'unsafe-inline'` en `script-src` del encabezado `Content-Security-Policy` para que los manejadores inline de los templates (`onclick`, `onchange`, `onsubmit`) funcionen en producción, y migración de los listeners de `login.html` a `addEventListener` en `login.js` para evitar envíos HTML nativos a `/api/auth/login`.

---

## [1.4.2] - 2026-11-13

### Notas de Actualización (Upgrade Notes)

- **Usuario no privilegiado en Docker (`UID/GID 1000`):** El contenedor deja de ejecutarse como `root` (`UID 0`) y pasa al usuario `dockraft` (`1000:1000`). En despliegues existentes con volúmenes montados como `root`, ejecuta `chown -R 1000:1000 ./data ./backups` antes de iniciar la nueva imagen.
- **Autenticación obligatoria (`ADMIN_PASSWORD`):** Se elimina el modo _fail-open_; si `ADMIN_PASSWORD` está vacío, se genera una contraseña aleatoria temporal en los logs de arranque. Define `ADMIN_PASSWORD` y `SECRET_KEY` en `.env` para conservar credenciales y sesiones entre recreaciones del contenedor.
- **Re-inicio de sesión y Proxy inverso:** Los tokens de sesión existentes se invalidarán una única vez tras actualizar debido al nuevo formato vinculado a la contraseña. Si usas proxy inverso con `TRUST_PROXY_HEADERS=true`, configura `TRUSTED_PROXIES` con la IP/CIDR del proxy (por defecto `127.0.0.1,::1`).

### Seguridad (Security)

- **Eliminación de Acceso _Fail-Open_ y Aislamiento de Secretos (`app/config.py`, `app/core/security.py`, `app/routers/auth.py`, `app/main.py`, `Dockerfile`):**
  - Bloqueo estricto de `get_current_user()`, `is_authenticated()`, `verify_admin_credentials()`, `POST /api/auth/login` y `WS /ws/console` cuando `ADMIN_PASSWORD` está vacío, con generación automática de contraseña efímera en arranque fuera de pruebas.
  - Aislamiento del entorno de subprocesos Minecraft/Forge mediante _allowlist_ (`build_sanitized_subprocess_env()`) en `ProcessManager.start_server()` y `DownloadManager.install_forge_server()`, evitando exponer `ADMIN_PASSWORD` y `SECRET_KEY`.
  - Traslado y migración automática de `.secret_key` fuera de `data/` hacia `panel_state_dir` (`/app/.dockraft_state/.secret_key`) con permisos `0o600`/`0o700`, y eliminación del `chmod` permisivo (`0o644`/`0o755`) en `clean_stale_session_locks()` y `safe_extract_zip()`.
- **Sesiones, WebSocket `/ws/console` y Rate Limiting (`app/core/security.py`, `app/routers/auth.py`, `app/main.py`, `app/core/process_manager.py`):**
  - Persistencia atómica y acotada (`_MAX_REVOKED_TOKENS = 10000`) de `_revoked_tokens` en `.revoked_tokens.json`, rechazando tokens forjados o con marca temporal futura, y vinculación de tokens HMAC a la huella de `ADMIN_PASSWORD`.
  - Revocación de todos los portadores (`Bearer` y cookies) en `logout` y del token anterior en `/api/auth/refresh`.
  - Defensa contra CSWSH en `/ws/console` validando `Origin` antes de `accept()`, eliminación de `?token=` en query string, y cierre automático (`4001`) en `stats_pusher()` y `broadcast_message()` al expirar o revocarse la sesión.
  - Protección contra _bypass_ de `LoginRateLimiter` validando que el _peer_ pertenezca a `TRUSTED_PROXIES` y tomando la IP no confiable más a la derecha en `X-Forwarded-For`.
- **Protección de Backups, Archivos, Diagnósticos y Cadena de Suministro (`app/core/fs_utils.py`, `backup_manager.py`, `file_manager.py`, `diagnostic_manager.py`, `downloader.py`, `plugin_manager.py`, `app/routers/installer.py`):**
  - Exclusión de `PROTECTED_INTERNAL_FILES` (incluyendo `plugin_updates.json` y `dockraft_players.json`) de `create_backup()` y `get_available_targets()`, además de rechazo de compresión de raíz y symlinks en `FileManager` y `BackupManager`.
  - Límites anti-ZipBomb por streaming (`max_entries`, `max_total_bytes`, `max_ratio`) en `safe_extract_zip()` y validación de tamaño de `plugin.yml`.
  - Bloqueo de symlinks y redacción completa de secretos (`admin_password`, `secret_key`, variables de entorno, `webhooks.json` y `rcon.password`) en `DiagnosticManager.share_to_mclogs()`.
  - Verificación criptográfica `SHA-256` (PaperMC) / `SHA-1` (Mojang), validación de dominios HTTPS tras redirecciones y rechazo de `build_id` inexistente en `get_paper_build()`.
  - Coincidencia exacta o por ID explícito de SpigotMC en `PluginManager` (eliminando confusión por subcadena en Spiget).
- **Frontera de Consola, Webhooks, DOM XSS y Endurecimiento General (`process_manager.py`, `player_manager.py`, `webhook_manager.py`, `activity_manager.py`, `task_scheduler.py`, `web/static/js/`):**
  - Filtrado de líneas de chat (`_is_chat_line()`) antes de procesar eventos de consola/plugins/TPS y validación de nombres de jugador en `online_players` y `kick_all_players()`.
  - Escape HTML en Telegram y Email (`_send_email_sync`), `allowed_mentions={"parse": []}` y escape de enlaces Markdown en Discord.
  - Corrección de DOM XSS en `Files.buildUploadItemElement()` (`targetDir`) e `Installer.loadUpdateInfo()`, validación del formato `version.json['id']`, eliminación de `'unsafe-inline'` en `script-src` del CSP y adición de `rel="noopener noreferrer"` en enlaces externos.
  - Validación de `java_path`, comprobación _case-insensitive_ de archivos protegidos, bloqueo `RLock` y neutralización de fórmulas CSV en `ActivityManager`, validación de enums en `tasks.py`, iteración segura en `scheduler_loop()` y ocultación de detalles internos de error en `WebhookManager.test_channel()`.

---

## [1.4.1] - 2026-11-12

### Seguridad (Security)

- **Persistencia Automática de `SECRET_KEY` (`app/config.py`, `app/core/fs_utils.py`):**
  - Cuando no se configura la variable de entorno `SECRET_KEY`, la clave generada se persiste automáticamente en `data/.secret_key` (protegida en `PROTECTED_INTERNAL_FILES`) para conservar las sesiones activas tras reiniciar la aplicación o el contenedor.
- **Sanitización de Comandos de Consola (`app/core/process_manager.py`):**
  - Limpieza de saltos de línea (`\r`, `\n`) y caracteres nulos (`\x00`) en `send_command()` para prevenir inyección multilínea en el flujo `stdin` del servidor.

### Mejorado y Optimizado (Changed & Performance)

- **Modularización Completa de `app/main.py` (`app/routers/`):**
  - Extracción de los endpoints restantes hacia routers dedicados: `auth.py`, `server.py`, `installer.py` y `activity.py`, reduciendo `app/main.py` de ~1,600 a ~291 líneas.
  - Eliminación de 18 esquemas Pydantic duplicados que permanecían huérfanos en `app/main.py`, además de ramas muertas (`inspect.isawaitable`) y scripts temporales (`scratch/`).
- **Consolidación de Lógica Compartida:**
  - Unificación del manejo de cookies de sesión (`set_session_cookies()` y `clear_session_cookies()` en `app/routers/auth.py`).
  - Centralización de la sincronización de alias Java/Bedrock en `server.properties` (`_sync_property_aliases()` en `app/routers/server.py`).
  - Unificación de la resolución de descargas entre `install_server` y `update_server` mediante `resolve_server_download()` (`app/routers/installer.py`).
  - Extracción de `_handle_player_event()` en `app/core/process_manager.py` para centralizar el tracking y los webhooks de conexión/desconexión en formato Java y Bedrock.
  - Centralización de `format_size()` en `app/core/fs_utils.py`, reutilizado por `backup_manager.py` y `plugin_manager.py`.
- **Estabilidad de Tareas Asíncronas (`asyncio.create_task`):**
  - Retención explícita de referencias fuertes para tareas en segundo plano mediante `_track_task()` / `_background_tasks` en `app/routers/installer.py` y atributos dedicados en `ProcessManager` y `app/main.py`, evitando su recolección prematura por el Garbage Collector en Python 3.11/3.12+.
- **Estandarización de Logging:**
  - Reemplazo de todas las llamadas `print()` en producción por `logging` estándar con niveles adecuados (`info`, `warning`, `error`, `debug`) y añadido de trazabilidad en bloques `except Exception:` relevantes (`downloader.py`, `java_manager.py`, `backup_manager.py`, `plugin_manager.py`).

### Corregido (Fixed)

- **Registro Diferenciado de Conexión y Desconexión de Jugadores (`app/core/player_manager.py`):**
  - Unificación de `record_connection()` y `record_disconnection()` mediante `_record_activity()` para distinguir eventos `"join"` y `"leave"`, manteniendo compatibilidad con `last_connection` y registrando además `last_event` y `last_disconnection`.
- **Limpieza de Importación Duplicada (`app/core/plugin_manager.py`):**
  - Eliminación de un `import time` redundante dentro de `parse_console_update_line()`.

---

## [1.4.0] - 2026-11-04

### Seguridad (Security)

- **Protección contra SSRF en Webhooks (`app/core/webhook_manager.py`):**
  - Validación estricta del esquema (`http`/`https`) y resolución DNS con bloqueo de direcciones IP privadas, loopback (`127.0.0.1`), link-local (`169.254.169.254`) y rangos reservados antes de despachar notificaciones o pruebas de webhook.
- **Protección Anti-Zip Bomb y Cuotas en Importación/Restauración (`app/main.py`, `app/core/backup_manager.py`, `app/core/file_manager.py`):**
  - Inspección previa de metadatos (`infolist`) para verificar que el tamaño total descomprimido no supere la cuota de disco disponible ni el ratio máximo de compresión (`100:1`).
  - Extracción segura por streaming en bloques de `64 KB` con contadores en tiempo real y rechazo de enlaces simbólicos o rutas fuera del directorio destino (`Path Traversal`).
- **Endurecimiento de Autenticación y Sesiones (`app/core/security.py`, `app/config.py`):**
  - Persistido automático de `SECRET_KEY` en `data/.secret_key` con permisos restringidos (`0o600`) para conservar las sesiones activas tras reiniciar el contenedor cuando no se define por variable de entorno.
  - Protección contra enumeración de usuarios ejecutando siempre una verificación BCrypt dummy en tiempo constante cuando el usuario no existe.
  - Límite de memoria (`MAX_TRACKED_IPS = 10000`) y purga automática de registros expirados en el limitador de intentos de inicio de sesión (`LoginRateLimiter`).
  - Bandera `Secure` en cookies de sesión configurable dinámicamente según protocolo (`HTTPS` / `X-Forwarded-Proto`) o variable `COOKIE_SECURE`.
- **Sanitización de Argumentos JVM (`app/core/process_manager.py`):**
  - Bloqueo explícito de flags peligrosos de ejecución arbitraria (`-XX:OnOutOfMemoryError`, `-XX:OnError`, `-XX:AbortVMOnException`, `-javaagent`, `-agentlib`, `-agentpath`).

### Mejorado y Optimizado (Changed & Performance)

- ** Modularización del Backend con APIRouter (`app/routers/`):**
  - Desacoplamiento de endpoints de `app/main.py` en módulos dedicados: `auth.py`, `server.py`, `files.py`, `backups.py`, `players.py`, `tasks.py` y `plugins.py`.
- **Optimización Asíncrona y de I/O (`app/core/`):**
  - Descargas de motores de servidor en streaming mediante `client.stream("GET", ...)` con cálculo incremental de SHA-256 sin cargar el `.jar` completo en RAM (`downloader.py`).
  - Ejecución en hilos (`asyncio.to_thread`) de llamadas bloqueantes a `psutil` y escaneo de disco con caché TTL de 10 segundos e invalidación inmediata tras cambios en archivos o respaldos (`fs_utils.py`, `process_manager.py`).
  - Precompilación de expresiones regulares en el motor de análisis de logs y lectura eficiente de las últimas líneas de `latest.log` mediante `deque(f, maxlen=500)` (`process_manager.py`).
- **Persistencia Atómica y Precisión del Programador de Tareas:**
  - Escritura atómica mediante archivo temporal y `os.replace()` para `dockraft_config.json` y `tasks.json`.
  - Evaluación de tareas programadas basada en minuto calendario (`(now.year, now.month, now.day, now.hour, now.minute)`) para evitar omisiones o dobles ejecuciones por deriva del bucle asíncrono (`task_scheduler.py`).
- **Limpieza y Unificación del Frontend (`web/`):**
  - Centralización de `escapeHtml` y `formatBytes` en `window.App` (`console.js`), eliminando implementaciones duplicadas en `backups.js`, `files.js`, `installer.js`, `logs.js`, `players.js` y `tasks.js`.
  - Consolidación de traducciones en `i18n.js`, reglas CSS duplicadas en `style.css` y controles de certificado SSL en `settings.html`.
- **Optimización de Contenedor Docker (`Dockerfile`, `requirements.txt`):**
  - Reparación automática de permisos POSIX en archivos extraídos y directorios del mundo (`level.dat`) antes del arranque, y eliminación de dependencias innecesarias (`passlib`, `pydantic-settings`).

### Corregido (Fixed)

- **Carga del Logo de la Aplicación (`web/templates/`):**
  - Unificación del recurso gráfico en `/static/img/dockraft_logo.png` en `base.html`, `login.html`, `components/header.html`, `footer.html`, `manifest.json` y `sw.js`.
- **Títulos de la Sección de Actualizaciones del Instalador (`installer.html`, `i18n-installer.js`):**
  - Eliminación de la numeración fija (`1.` y `2.`) en las tarjetas _Parches del Motor (Compilación / Build)_ y _Versión del Juego (Minecraft)_ para mantener coherencia visual tanto en motores con builds (Paper/Purpur) como en motores de tarjeta única (Vanilla/Fabric/Forge/Bedrock).

---

## [1.3.3] - 2026-10-14

### Añadido (Added)

- **Módulo y Ventana Modal Exclusiva para Actualización y Cambio de Compilaciones (Builds):**
  - **Tarjeta Exclusiva de Compilación (`#installer-build-card`):** Bloque visual destacado en la pestaña de Instalación, independiente del selector de versiones de Minecraft, que muestra la versión base instalada (`26.3`), la compilación activa (`#186`), y notifica de inmediato cuando hay una nueva compilación oficial disponible con el botón `Cambiar / Actualizar Build`.
  - **Ventana Modal Dedicada (`#modal-change-build`):** Diseñada específicamente para clarificar al usuario la diferencia entre la versión base del juego y la compilación del motor:
    - Explica que la versión de Minecraft permanece inalterada en `26.3` mientras que se actualizan el núcleo interno y los parches de estabilidad de Paper/Purpur.
    - Comparativa visual lado a lado: Build instalada (`#186`) vs. Build de destino (`#189` recomendada).
    - Selector dinámico de compilaciones que consulta la API de builds (`/api/installer/builds`) con resúmenes de commits/cambios.
    - Lista de garantías de seguridad visibles (copia de seguridad preventiva automática, integridad de archivos verificada por SHA-256, datos y mundos 100% preservados, guardado con `save-all` y reinicio automático).
  - **Endpoint Backend `/api/installer/builds` y Parámetro `build` en `/api/installer/update`:**
    - Soporte completo para consultar el historial de builds recientes y descargar exactamente la compilación solicitada por el usuario (o la más reciente por defecto), etiquetando las copias preventivas como `pre-update-26.3-b189`.
- **Detección y Notificación de Compilaciones Continuas (Builds) para Paper, Purpur, Folia y Velocity:**
  - `downloader.detect_server_build()`: Extracción automática del número de compilación interno (`Build #`) desde `version_history.json`, registros de arranque (`logs/latest.log`), nombres de archivo jar y metadatos del manifiesto (`META-INF/MANIFEST.MF`).
  - Persistencia de `server_build` en la configuración de runtime (`dockraft_config.json`) al instalar o actualizar servidores.
  - Alerta inteligente de nueva compilación: cuando el servidor se encuentra en la última versión de Minecraft (ej. `26.3`), pero el portal oficial ha publicado una compilación posterior (ej. `#187` / `#188` / `#189` frente a `#186`), el panel notifica `Nueva build disponible` y abre directamente la ventana modal exclusiva para aplicar el cambio.

- **Rediseño y Separación Clara de Actualizadores en el Instalador:**
  - **Estructura Visual Unificada e Intuitiva:** Se unificó la sección de actualizaciones del servidor en un panel principal subdividido en 2 bloques independientes y numerados:
    - **1. Parches del Motor (Compilación / Build):** Exclusivo para optimizaciones internas, parches de estabilidad y seguridad de Paper/Purpur manteniendo la misma versión del juego (sin impacto en los clientes de los jugadores). Cuenta con su propio indicador de build activa, aviso de nueva build y acceso directo a la ventana modal de selección de build.
    - **2. Versión del Juego (Minecraft):** Exclusivo para ascensos o descensos de la versión mayor del juego (ej. de 26.3 a 26.4 o 26.2), aclarando explícitamente que requiere que los clientes de los jugadores usen esa misma versión para conectarse.
  - **Desacoplamiento Funcional Completo:** Se eliminó la inyección cruzada donde las compilaciones de build sobrescribían el selector de versiones y el botón de versión de Minecraft, así como la redirección forzada que abría la modal de builds al pulsar "Actualizar Servidor". El botón de la versión mayor ahora indica de manera precisa `Cambiar a Minecraft {versión}` o `Reinstalar Minecraft {versión}`.
  - **Depuración de Código Muerto y Redundancias:** Limpieza de importaciones no utilizadas y variables huérfanas en el backend (`process_manager.py`, `file_manager.py`, `task_scheduler.py`, etc.), eliminación de selectores de compatibilidad obsoletos en JavaScript y remoción de bloques de barra de progreso duplicados en la plantilla HTML.

---

## [1.3.2] - 2026-09-22

### Corregido (Fixed)

- **Extracción Automática de Versión de la Aplicación en Docker:**
  - `CHANGELOG.md` ahora se copia explícitamente en la imagen Docker (`Dockerfile`), permitiendo que `_read_version_from_changelog()` lea la versión real dinámicamente tanto en local como dentro de contenedores.
  - Se amplió la búsqueda a múltiples rutas posibles (`BASE_DIR`, `/app`, `cwd`) y se actualizó el valor de respaldo a `1.3.2` (eliminando la versión `1.0.0` que quedaba residual si el archivo no se encontraba).
- **Detección de Avisos sin Prefijos de Corchetes (ej. CMILib) y sin Enlace Directo:**
  - El motor de análisis de consola ahora reconoce anuncios en lenguaje natural donde el nombre del plugin está dentro del mensaje en lugar de al inicio entre corchetes (ej: `"New version of CMILib was detected. Please update it (1.5.9.9 -> 1.6.0.0)"`).
  - Extracción de versiones en transiciones numéricas (`1.5.9.9 -> 1.6.0.0`) y enriquecimiento automático mediante la API de Spiget para localizar el recurso en SpigotMC.
  - En la interfaz web, si un aviso no dispone de enlace oficial, se añade un botón de búsqueda alternativa (`Buscar ↗`) hacia Google/Spigot para evitar dejar enlaces muertos.
- **Soporte para Avisos de Actualización en Español y Multilínea (ej. EssentialsX):**
  - Reconocimiento de avisos localizados en español (`¡Estás a 1 compilación(es) de desactualización de EssentialsX!`) y en inglés (`build(s) out of date`).
  - Fusión automática de avisos complementarios de múltiples líneas: cuando un plugin emite el aviso en una línea y el enlace en la siguiente (`Descárgala aquí: https://...` / `Download here: ...`), Dockraft combina ambos en una única tarjeta unificada con la versión y el botón de descarga.
- **Filtro de Falsos Positivos de Plugins Actualizados (ej. RealScoreboard):**
  - Incorporadas frases como `"The plugin is updated to the latest version"` y `"está actualizado a la última versión"` al filtro de avisos negativos (`is_negative_notice`), evitando que confirmaciones de que un plugin ya está al día se clasifiquen como actualizaciones pendientes.
- **Avisos de Actualización de Plugins Persistentes y Cotejo en Disco:**
  - Los avisos de actualización de plugins ya no persisten tras actualizar. `_is_false_positive_entry()` ahora coteja automáticamente la versión anunciada contra la versión instalada en el directorio de plugins (`data/plugins/*.jar`). Si el plugin ya cuenta con una versión igual o superior (ej: `CMILib 1.6.0.0` instalado), el aviso se descarta de inmediato.
  - Al consultar actualizaciones (`get_detected_updates`), se depura la memoria en tiempo real purgando cualquier plugin que ya haya sido actualizado en disco.
  - Al iniciar el servidor, el cache se limpia (`clear_for_server_start()`), y el escaneo de registros (`scan_console_logs()`) respeta los límites de sesión (`session_markers`), analizando exclusivamente las líneas generadas desde el último arranque del servidor para evitar procesar logs de sesiones previas al reinicio.
  - Expandido el detector de frases negativas (`NEGATIVE_UPDATE_PATTERN` / `_NEGATIVE_EXTRA_PHRASES`) con protección contra falsos negativos cuando la frase va precedida de `NOT` (ej: `"You are NOT running the latest version"`).
  - Añadido helper `_is_false_positive_entry()`: descarta casos donde la versión "disponible" reportada en el aviso no es numéricamente mayor que la versión actual indicada en el mismo mensaje (ej: ViaVersion en `5.12.0-SNAPSHOT` recibiendo aviso de `5.12.0`).
- **Restauración Fiable del Botón de Escaneo:**
  - Se implementó `_restoreScanButton()` en `installer.js` para garantizar que el botón de escaneo retorne invariablemente a su icono y texto original en reposo, evitando que quede fijado en `"Escaneando..."`, y sincronizando la notificación toast para mostrarse una vez restaurado el botón.

---

## [1.3.1] - 2026-09-20

### Corregido (Fixed)

- **Unificación de Diálogos de Confirmación Flotantes:**
  - Sustitución del cuadro de diálogo nativo del navegador (`confirm()`) por la ventana modal flotante del panel (`App.confirm()`) al limpiar los avisos de actualización de plugins en el Instalador (`clearAllConsoleUpdates`), garantizando una estética visual coherente y con diseño oscuro unificado.
- **Depuración de Diccionarios y Traducciones:**
  - Eliminación de claves redundantes en `i18n.js` (`banner_version_label` y bloque duplicado de opciones de inicio automático y caídas).
  - Incorporación de la clave de traducción `t_file_upload_cancel_confirm` en español e inglés para la confirmación al cerrar el gestor de subidas con transferencias activas.

### Modificado (Changed)

- **Cache-Busting de Recursos del Cliente:**
  - Actualización de parámetros de versión de recursos en `base.html`, `footer.html` e `index.html` a `v1.3.1`.

---

## [1.3.0] - 2026-09-20

### Agregado (Added)

- **Administrador de Subidas Flotante (Upload Manager Widget):**
  - Panel flotante moderno y minimizable en la esquina inferior derecha (estilo Google Drive/OneDrive).
  - Visualización del progreso individual y global con contador de bytes transferidos, porcentaje en tiempo real y velocidad de transferencia en MB/s (`XMLHttpRequest.upload.onprogress`).
  - Control de cola concurrente (hasta 2 subidas simultáneas) para no saturar la red ni la I/O del servidor.
  - Opciones de cancelación individual (`xhr.abort()`), reintento tras fallo y limpieza de completados.
- **Soporte de Subida Múltiple y Drag & Drop:**
  - Atributo `multiple` habilitado en el selector de archivos del gestor de archivos.
  - Zona de arrastre y soltar (Drag & Drop) sobre la tabla de archivos con overlay visual translúcido e indicación dinámica de la carpeta destino.
  - Prevención global de eventos de arrastre en `window` para evitar que el navegador abra el archivo directamente o recargue la pestaña por error.
- **Persistencia de Navegación y Scroll:**
  - Almacenamiento y restauración automática del directorio activo en `sessionStorage` (`dockraft_files_current_path`).
  - Refresco silencioso de la tabla (`silent: true`) al terminar de subir archivos, eliminando el parpadeo y conservando la posición exacta de scroll del usuario.
  - Conservación de la subcarpeta actual al alternar entre pestañas (Consola, Métricas, Archivos, etc.).
- **Internacionalización (i18n):**
  - Nuevas cadenas de traducción en español e inglés para todos los estados de subida, badges, botones y textos de arrastre en `i18n-files.js`.

### Modificado (Changed)

- **Cache-Busting de Recursos del Cliente:**
  - Incremento de versiones de scripts y estilos en `base.html`, `footer.html`, `index.html` y módulos correspondientes a `v1.3.0`.

### Corregido (Fixed)

- **Salto al inicio al subir archivos:**
  - Solucionado el colapso del contenedor que restablecía el scroll a `0` y la pérdida de la ruta actual durante las recargas de la lista de archivos.
- **Incompatibilidad en llamada a BackupManager:**
  - Corregida llamada a `backup_manager.create_backup` en el pipeline de actualización de `app/main.py` y añadido soporte para el alias `compress` en `BackupManager.create_backup`.

---

## [1.2.0] - 2026-09-15

### Agregado (Added)

- **Monitoreo de Espacio en Disco y Alerta Inteligente en Métricas:**
  - Nueva tarjeta KPI de Espacio en Disco en la pestaña de Métricas que muestra en tiempo real los GB usados vs límite asignado, porcentaje de uso y espacio libre disponible.
  - Barra de progreso visual compacta con cambio de color automático (cian para estado normal, ámbar para advertencia y rojo para crítico).
  - Banner inteligente de alerta de espacio en disco en la parte superior del panel de telemetría:
    - **Modo Advertencia (`>= 75%`):** Aviso preventivo para recomendar limpieza de respaldos o archivos antes de agotar la capacidad.
    - **Modo Crítico (`>= 90%`):** Alerta de alta prioridad con botones de acceso directo para explorar archivos (`/data`) o ajustar el límite en Configuración antes de que se bloqueen las escrituras del servidor.
  - Telemetría histórica de almacenamiento: ahora cada muestra del búfer circular registra `disk_used_mb`, `disk_limit_mb` y `disk_percent`.
  - Nueva serie opcional `Disco %` en el lienzo interactivo de telemetría (Canvas) y detalle de almacenamiento en el tooltip flotante al pasar el cursor.
- **Mejoras Integrales en el Administrador de Archivos (Files Tab):**
  - **Subida por Arrastre (Drag & Drop):** Superposición visual con detección de destino (`/data/...`) al arrastrar archivos externos hacia el explorador.
  - **Subida múltiple de archivos:** Carga masiva secuencial con notificaciones de progreso en vivo.
  - **Buscador en Tiempo Real:** Campo de búsqueda interactivo con filtrado instantáneo en memoria sin recargar la página ni realizar peticiones adicionales.
  - **Selección Múltiple y Acciones en Lote:** Checkbox general y por fila, barra de herramientas flotante con contador dinámico, borrado masivo seguro (`/api/files/bulk-delete`) y empaquetado en archivo `.zip` simultáneo (`/api/files/bulk-compress`).
  - **Editor de Texto Mejorado:** Soporte para indentación con la tecla `Tab` (2 espacios sin desenfocar), atajo de teclado global `Ctrl+S` / `Cmd+S`, y barra de estado inferior con contador dinámico de línea, columna y caracteres.
  - **Optimización Táctil y Móvil:** Botón contextual de tres puntos `•••` por elemento para pantallas táctiles y ocultación de columnas secundarias en pantallas reducidas.
- **Redirección Oficial de Versiones y Changelogs por Motor:**
  - Botones contextuales que enlazan directamente a los portales oficiales de descarga y notas de cada software (PaperMC en `papermc.io`, Purpur en `purpurmc.org`, Fabric en `fabricmc.net`, Forge en `minecraftforge.net`, Bedrock Changelogs en `feedback.minecraft.net` y Vanilla en `minecraft.net`).
- **Pruebas Automatizadas:**
  - Suite de pruebas unitarias para operaciones de archivo por lote (`tests/test_file_operations.py`).
  - Suite de pruebas para telemetría de rendimiento y almacenamiento en disco (`tests/test_metrics_telemetry.py`).

### Modificado (Changed)

- **Estandarización Visual de Iconos (Sin Emojis):**
  - Sustitución de todos los emojis residuales (`⚠️`) por iconos vectoriales SVG limpios y consistentes en las pestañas de Instalador, Archivos y Métricas.
  - Unificación de estilos y badges de estado.
- **Telemetría Dinámica de Rendimiento TPS:**
  - Conexión dinámica de la tarjeta KPI de TPS en Métricas para reflejar los valores de 1m, 5m y 15m recopilados por el gestor de procesos en tiempo real, distinguiendo estados `Óptimo` (>=18), `Aceptable` (15-17.9), `Bajo` (<15) y `Fuera de línea`.
- **Actualización de Versiones de Recursos (Cache-Busting):**
  - Actualización de versiones de scripts `files.js?v=1.2.4`, `i18n-files.js?v=1.2.4`, `metrics.js?v=1.2.4`, `i18n-metrics.js?v=1.2.4` e `installer.js?v=1.2.4`.

### Corregido (Fixed)

- **Desplazamiento y Espacio Blanco del Teclado Virtual en Login Móvil:**
  - Corrección del espacio en blanco al desplegar el teclado en teléfonos móviles mediante la directiva `interactive-widget=resizes-content` en el viewport, altura dinámica `100dvh`, declaración de `color-scheme: dark` y fondo oscuro permanente en la etiqueta `html`.
- **Eliminación de Advertencias Duplicadas en el Instalador:**
  - Supresión de la alerta redundante de inestabilidad de versiones beta para mantener una interfaz limpia con la tarjeta oficial de versiones.

---

## [1.1.0] - 2026-09-15

### Agregado (Added)

- **Paginación en Registros de Actividad:**
  - Selector interactivo de cantidad de registros por página (15, 25, 50, 100 registros).
  - Controles de navegación dinámica con páginas numeradas, botones previo/siguiente y elipsis inteligente (`web/templates/tabs/logs.html` y `web/static/js/logs.js`).
  - Nuevas traducciones i18n para controles de paginación en español e inglés (`web/static/js/i18n.js`).
- **Soporte Completo para Gestores de Contraseñas (Bitwarden y Móvil):**
  - Formulario estructurado con `method="post"` y `action="/api/auth/login"` en la pantalla de acceso.
  - Atributos `name="username"`, `name="password"`, `autocomplete="username"`, `autocomplete="current-password"`, `autocapitalize="none"`, `autocorrect="off"`, `spellcheck="false"`.
  - Detección nativa y autorrelleno instantáneo en Android, iOS, Bitwarden y extensiones de navegador.
- **Detección Avanzada de Canales en PaperMC:**
  - Nuevo método `get_paper_classified_versions` en `app/core/downloader.py` con caché en memoria (180s) que consulta el canal real de compilaciones (`builds/latest`) en la API v3 de PaperMC.
  - Distinción automática entre versiones experimentales (`ALPHA`) y versiones estables (`STABLE`), evitando falsos positivos de actualización cuando se lanzan versiones preliminares (como Minecraft 26.3 en Paper).
- **Visualizador de Cambios y Notas de Versión (Changelog & Betas):**
  - Enlaces directos y contextuales al registro oficial de cambios (`minecraft.wiki` y portales oficiales de cada motor) para cualquier versión seleccionada (Vanilla, Bedrock, Paper, Purpur, Fabric, Forge).
  - Tarjeta informativa dinámica con consejo de actualización: orientación comparativa sobre cuándo conviene quedarse en la versión Estable (para comunidades y servidores con plugins) o cuándo probar versiones Beta/Snapshot/Experimental (en entornos de prueba o para explorar novedades).
- **Flujo de Publicación de Releases en GitHub:**
  - Flujo de GitHub Actions para generar automáticamente GitHub Releases con notas de cambios al publicar tags de versión (`v*`).
- **Pruebas Automatizadas:**
  - Nuevas suites de pruebas unitarias para clasificación de versiones PaperMC (`tests/test_paper_classification.py`) y supresión de comandos silenciosos (`tests/test_silent_commands.py`).

### Modificado (Changed)

- **Centralización i18n de Versión en Footer y Cache-Busting de Cliente:**
  - La versión del panel mostrada en el pie de página ahora se administra de forma centralizada en el diccionario de traducciones (`web/static/js/i18n.js` con clave `footer_version`), respetando la arquitectura de internacionalización del proyecto.
  - Se incrementaron los parámetros de versión de los scripts en `index.html`, `base.html` y el Service Worker PWA (`dockraft-v7`) para garantizar una actualización instantánea en el navegador sin retención de scripts antiguos en caché.
- **Consola Interactiva Silenciosa:**
  - Supresión limpia de la salida en consola para sondeos automáticos en segundo plano (`tps` cada 45s y `/list` cada 3 min), evitando inundar el terminal interactivo.
  - Las métricas de TPS y jugadores en línea se siguen actualizando en tiempo real sin interrupciones.
  - Los comandos ejecutados manualmente por el administrador en la consola continúan mostrándose con normalidad.
- **Estandarización de Plantillas Jinja2:**
  - Migración de las variables de sesión del login a atributos `data-*` en `#login-card`.
  - Reemplazo de directivas de plantilla en atributos `style=""` por condicionales HTML completos, eliminando advertencias y errores de analizadores CSS y JavaScript.

### Corregido (Fixed)

- **Índice de Versiones en Purpur:**
  - Corrección en `app/core/task_scheduler.py` para leer la versión más reciente en el índice `vers[0]` (la API de Purpur retorna versiones en orden descendente).
- **Llamada de Copia de Seguridad Preventiva:**
  - Corrección de tipado en `app/main.py` al llamar `backup_manager.create_backup(...)` sincrónicamente y con soporte para el parámetro `compression` / `compress`.
  - Soporte de compatibilidad para el alias `compress` en `app/core/backup_manager.py`.

### Seguridad (Security)

- **Mitigación contra Zip Slip por Enlaces Simbólicos:**
  - Inspección con `stat.S_ISLNK` en la restauración de respaldos (`backup_manager.py`) y en la descompresión de archivos (`file_manager.py`) para rechazar archivos zip con enlaces simbólicos que apunten fuera de la raíz de datos.
- **Sanitización Preventiva de Credenciales:**
  - Redacción automática de contraseñas (`admin_password`) y claves secretas (`secret_key`) antes de subir registros de error o caídas al servicio de diagnóstico externo `mclo.gs`.

---

## [1.0.0] - 2026-09-10

### Agregado (Added)

- **Panel de Control Web Dockraft:**
  - Interfaz web moderna, responsiva y temática oscura para la administración de servidores de Minecraft Java y Bedrock.
  - Soporte para múltiples motores de servidor: PaperMC, Purpur, Vanilla, Fabric, Bedrock y Forge.
- **Consola Interactiva en Vivo:**
  - Conexión WebSocket bidireccional para visualización de logs en tiempo real y ejecución de comandos de consola.
- **Administrador de Archivos:**
  - Explorador de archivos con soporte para subir, descargar, editar, renombrar, duplicar y descomprimir archivos del servidor.
- **Copias de Seguridad (Backups):**
  - Generación y restauración de copias de seguridad con compresión ZIP y filtros de alcance (Mundos, Plugins, Completo).
- **Gestión de Jugadores:**
  - Administración en vivo de jugadores conectados, operadores (OP), lista blanca (Whitelist), baneos y expulsiones.
- **Instalador y Actualizador:**
  - Instalación guiada de versiones oficiales con verificación de integridad y reinicios automáticos seguros.
- **Tareas Automatizadas (Cron Scheduler):**
  - Programación periódica de comandos, respaldos automáticos y reinicios del servidor.
- **Webhooks y Notificaciones:**
  - Alertas automáticas para Discord, Telegram y Correo Electrónico (SMTP).
- **Seguridad Base:**
  - Autenticación mediante tokens de sesión HMAC-SHA256, cookies seguras `HttpOnly` / `SameSite=Lax`, limitador de intentos de acceso (Rate Limiting) y bloqueo temporal tras fallos reiterados.
