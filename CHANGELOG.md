# Registro de Cambios (Changelog)

Todos los cambios notables en **Dockraft** se documentan en este archivo.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

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
