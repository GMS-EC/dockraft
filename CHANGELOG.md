# Registro de Cambios (Changelog)

Todos los cambios notables en **Dockraft** se documentan en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

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
- **Flujo de Publicación de Releases en GitHub:**
  - Flujo de GitHub Actions para generar automáticamente GitHub Releases con notas de cambios al publicar tags de versión (`v*`).
- **Pruebas Automatizadas:**
  - Nuevas suites de pruebas unitarias para clasificación de versiones PaperMC (`tests/test_paper_classification.py`) y supresión de comandos silenciosos (`tests/test_silent_commands.py`).

### Modificado (Changed)
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
