<table>
  <tr>
    <td width="140" align="center" valign="middle">
      <img src="web/static/img/logo.png" alt="Dockraft Logo" width="120" style="border-radius: 14px;" />
    </td>
    <td valign="middle">
      <h2>🎮 Dockraft — Dedicated Minecraft Server in Docker</h2>
      <p><strong>Panel web ultra-ligero y automatizado para administrar una única instancia dedicada de servidor de Minecraft (Java & Bedrock).</strong></p>
      <p>
        <a href="https://hub.docker.com/r/marcusm99/dockraft"><img src="https://img.shields.io/badge/docker%20hub-marcusm99%2Fdockraft-0db7ed?style=flat-square&logo=docker" alt="Docker Hub" /></a>
        <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL%20v3-007ec6?style=flat-square" alt="License" /></a>
        <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/framework-fastapi-009688?style=flat-square&logo=fastapi" alt="FastAPI" /></a>
        <a href="https://gmsec.cc"><img src="https://img.shields.io/badge/author-gmsec.cc-8a2be2?style=flat-square" alt="gmsec.cc" /></a>
        <br />
        <img src="https://img.shields.io/badge/platform-linux%20amd64-black?style=flat-square&logo=linux" alt="Platform" />
      </p>
    </td>
  </tr>
</table>

<p>
  🌐 <strong>Select Language / Selecciona Idioma:</strong> <a href="#-versión-en-español"><strong>ES Español</strong></a> | <a href="#-english-version"><strong>GB English</strong></a>
</p>

---

## 🇪🇸 Versión en Español

### 💡 ¿Por qué Dockraft? (Arquitectura de Instancia Única)

Los paneles tradicionales para Minecraft como **Crafty Controller** o **Pterodactyl** fueron diseñados para alojar decenas de servidores concurrentes. Por esa razón, requieren bases de datos pesadas (MySQL/PostgreSQL), colas de procesos (Redis/Celery), demonios en segundo plano y múltiples servicios que consumen entre **350 MB y más de 1 GB de memoria RAM en reposo**, incluso antes de encender el juego.

**Dockraft fue diseñado bajo una filosofía intencionalmente distinta: 1 Contenedor = 1 Servidor Dedicado.**

Al enfocarse exclusivamente en mantener y optimizar **una única instancia de servidor por contenedor**:
* **No requiere bases de datos externas**: Todas las opciones y configuraciones se gestionan limpiamente en archivos JSON locales.
* **No tiene intermediarios pesados**: El panel corre en un único proceso asíncrono en Python con FastAPI y Uvicorn.
* **Aprovechamiento máximo del hardware**: En un VPS o servidor con 2 GB, 4 GB u 8 GB de memoria, Dockraft consume entre **~50 y 75 MB de RAM** (según el sistema operativo) y **~0 % de CPU en reposo**. En un 2 GB quedan libres más del 96 % de la RAM y en un 8 GB más del 99 %, **todo ese resto disponible para el juego, tus mundos, mods y jugadores.**

> 🏆 **¿Servidor pequeño o gigantesco? No importa.** 
> Dockraft tiene todo lo que necesitas para administrar tu servidor Minecraft de forma profesional — sin consumir los recursos que tu mundo, jugadores y plugins necesitan.
> Desde un servidor de amigos con 2 GB hasta una instancia de alto rendimiento con 64 GB, el panel está pensado para apenas notarse: el resto de tus recursos queda libre para el juego.

---

### 📊 Comparativa de Consumo Real de Memoria RAM (Prueba Empírica)

| Panel de Control | Consumo en Reposo (Idle) | Tiempo de Arranque | Enfoque de Servidores |
| :--- | :---: | :---: | :--- |
| **Dockraft** | **~50–75 MB** (~0 % CPU) | **~1 segundo** | **Instancia única dedicada (ultra-ligero y optimizado)** |
| Crafty Controller v4 | ~350 MB a 700 MB | ~20 a 30 segundos | Multi-servidor pesado (Tornado, Flask, SQLite/Postgres) |
| Pterodactyl Panel | ~800 MB a 1.2 GB | Múltiples servicios | Infraestructura distribuida (PHP, Nginx, DB, Redis, Wings) |

---

### ✨ Características Principales

* 🕹️ **Instalador en 1 Clic**: Elige el tipo de servidor y la versión; Dockraft descarga los binarios oficiales, acepta el EULA automáticamente y configura los puertos y archivos iniciales:
  * **PaperMC**: Rápido y optimizado. El más recomendado para jugar con amigos y usar plugins.
  * **Purpur**: Variante de Paper con máxima personalización y gran rendimiento.
  * **Mojang Vanilla**: El Minecraft clásico original, sin añadidos ni plugins.
  * **Fabric**: Ligero y rápido para jugar con mods modernos.
  * **Minecraft Forge**: El sistema tradicional y con mayor catálogo de mods.
  * **Bedrock Dedicated**: Para jugar desde celulares, consolas (Xbox, PlayStation, Switch) y Windows.
  * **Importar Servidor (.zip)**: Migra cualquier servidor previo subiendo un archivo comprimido.
* 📟 **Consola en Vivo**: Transmisión de registros en tiempo real, envío de comandos con respuesta instantánea, historial con flechas del teclado y botones de comandos frecuentes.
* 💾 **Respaldos Selectivos**: Elige si respaldar todo el servidor o únicamente carpetas clave (como los mundos o los plugins) para ahorrar espacio en disco.
* ⏰ **Tareas Programadas**: Automatiza reinicios periódicos, encendido/apagado o copias de seguridad usando intervalos de tiempo o expresiones Cron.
* 🔔 **Notificaciones Webhooks**: Recibe avisos automáticos en tu canal de **Discord**, grupo de **Telegram** o **Correo Electrónico** cuando el servidor inicie, se detenga o concluya una tarea.
* 📁 **Gestor de Archivos Integrado**: Modifica archivos de texto (`server.properties`, `bukkit.yml`), sube archivos o descomprime paquetes `.zip` directamente desde el navegador.
* 🔒 **Seguridad y Control de Acceso**:
  * Autenticación por contraseña de administrador y sesiones seguras firmadas con HMAC.
  * **Protección contra ataques de fuerza bruta**: Bloqueo temporal automático de 10 minutos tras 5 intentos fallidos de inicio de sesión.

---

### ⚡ ¿Cómo entender el Rendimiento y los TPS (Ticks Per Second)?

En Minecraft, el bucle principal de procesamiento del servidor se ejecuta en ciclos discretos denominados **ticks**. Cada tick actualiza la inteligencia artificial de las criaturas (mobs), el crecimiento de los cultivos, los circuitos de redstone, el tiempo del día y las interacciones de los jugadores.

* **Frecuencia ideal**: **20.0 TPS** (significa que el servidor procesa exactamente 20 ciclos cada segundo, es decir, **1 tick cada 50 milisegundos**).
* **Diferencia entre FPS y TPS**: Los **FPS** (cuadros por segundo) dependen de la tarjeta gráfica de tu computadora (lado cliente). Los **TPS**, en cambio, dependen de la capacidad del procesador de tu servidor para calcular la física del mundo en tiempo real.

#### 🚦 Escala de Rendimiento en el Panel:

| TPS en Dockraft | Estado | Experiencia en el Juego | Qué significa |
| :---: | :---: | :--- | :--- |
| **20.0 TPS** | 🟢 **Óptimo** | Fluidez absoluta. Sin retrasos ni desincronizaciones. | El servidor procesa el mundo en menos de 50 ms por ciclo. |
| **18.0 – 19.9 TPS** | 🟡 **Carga Ligera** | Prácticamente imperceptible para los jugadores. | Carga temporal normal al guardar mundos (`save-all`) o al conectarse varios usuarios a la vez. |
| **15.0 – 17.9 TPS** | 🟠 **Degradación Moderada** | Retardo leve al interactuar con cofres, puertas o redstone; los mobs se mueven más despacio. | El servidor tarda más de 50 ms por tick. Conviene vigilar granjas masivas y generación de chunks. |
| **< 15.0 TPS** | 🔴 **Sobrecarga (Lag)** | *Rubberbanding* (jugadores retroceden al caminar), bloques rotos reaparecen, daño retardado al golpear. | El servidor está saturado. Se recomienda optimizar entidades, reducir la distancia de simulación o auditar plugins. |

#### 🛠️ Causas frecuentes de caída de TPS y cómo prevenirlas:
1. **Acumulación excesiva de entidades**: Granjas con cientos de aldeanos o animales apiñados en pocos bloques calculando colisiones.
2. **Generación acelerada de terreno**: Jugadores volando con Elytras a gran velocidad obligando a generar y guardar cientos de chunks nuevos en el disco.
3. **Relojes de Redstone infinitos**: Bucles rápidos sin tolvas reguladas o pistones automáticos continuos.
4. **Distancia de simulación muy alta**: Ajustar `simulation-distance=6` u `8` en `server.properties` reduce notablemente el uso de CPU sin perjudicar la distancia visual (`view-distance`).

---

### 🚀 Despliegue con Docker Compose (Recomendado)

#### Opción 1: Copiar y Pegar (Más rápido, sin clonar repositorio)
Crea una carpeta en tu servidor y un archivo `docker-compose.yml` con el siguiente contenido:

```yaml
services:
  dockraft:
    image: marcusm99/dockraft:latest
    container_name: dockraft
    restart: unless-stopped
    ports:
      - "8000:8000"       # Panel Web
      - "25565:25565"     # Minecraft Java (TCP)
      - "19132:19132/udp" # Minecraft Bedrock (UDP)
    environment:
      - TZ=America/Guayaquil
      - ADMIN_USER=admin
      - ADMIN_PASSWORD=MiContraseñaSegura
      - SECRET_KEY=genera_una_clave_secreta_con_openssl
    volumes:
      - ./data:/server_data
      - ./backups:/server_backups
```

Luego inicia el contenedor:
```bash
docker compose up -d
```

#### Opción 2: Clonando el repositorio oficial
1. Clona el repositorio:
   ```bash
   git clone https://github.com/GMS-EC/dockraft.git
   cd dockraft
   ```

2. (Opcional) Configura tus credenciales en un archivo `.env`:
   ```bash
   cp .env.example .env
   ```

3. Inicia el servidor:
   ```bash
   docker compose up -d
   ```

El panel estará disponible de inmediato en **`http://localhost:8000`** (o en la IP pública de tu servidor).

---

### 🐳 Despliegue con Docker Run Directo

```bash
docker run -d \
  --name dockraft \
  -p 8000:8000 \
  -p 25565:25565 \
  -p 19132:19132/udp \
  -v ./data:/server_data \
  -v ./backups:/server_backups \
  -e ADMIN_USER=admin \
  -e ADMIN_PASSWORD=MiContraseñaSegura \
  -e TZ=America/Guayaquil \
  --restart unless-stopped \
  marcusm99/dockraft:latest
```

---

### ⚙️ Variables de Entorno

| Variable | Valor por Defecto | Descripción |
| :--- | :---: | :--- |
| `PORT` | `8000` | Puerto web de acceso al panel. |
| `ADMIN_USER` | `admin` | Nombre de usuario de inicio de sesión. |
| `ADMIN_PASSWORD` | *(vacío)* | Contraseña del panel. Si se deja vacía, no se solicita inicio de sesión. |
| `SECRET_KEY` | *(aleatoria)* | Clave para firmar sesiones criptográficas HMAC. |
| `TZ` | `America/Guayaquil` | Zona horaria del servidor para tareas programadas y respaldos. |
| `LOGIN_MAX_ATTEMPTS` | `5` | Intentos fallidos permitidos antes de aplicar rate limiting. |
| `LOGIN_COOLDOWN_SECONDS` | `600` | Segundos de enfriamiento y bloqueo tras superar el límite de intentos (10 min). |

---

### 📂 Volúmenes Persistentes

* **`/server_data`**: Aloja el servidor activo (mundos, plugins, mods, configuraciones y logs).
* **`/server_backups`**: Carpeta aislada donde se guardan las copias de seguridad `.zip`.

---

### 🧪 Pruebas Automatizadas

```bash
pytest tests/ -v
```

---

<br />

---

## 🇬🇧 English Version

### 💡 Why Dockraft? (Single-Instance Dedicated Architecture)

Traditional Minecraft control panels like **Crafty Controller** or **Pterodactyl** were architected to host dozens of game servers simultaneously. Because of this, they bundle heavy relational databases (MySQL/PostgreSQL), background worker queues (Redis/Celery), and multiple background daemons that consume between **350 MB and over 1 GB of idle RAM** before any game is even started.

**Dockraft was purposefully built under a different philosophy: 1 Container = 1 Dedicated Server.**

By focusing strictly on managing and optimizing **a single server instance per container**:
* **No external databases required**: All settings and state are stored cleanly in lightweight local JSON files.
* **No bloated middleware**: Runs as a single asynchronous Python process powered by FastAPI and Uvicorn.
* **Maximum hardware efficiency**: On a 2 GB, 4 GB, or 8 GB VPS, Dockraft consumes about **50–75 MB of RAM** (OS-dependent) and **~0% CPU at idle**. That leaves over 96% free on a 2 GB box and over 99% on 8 GB, **all of it available to Minecraft, your worlds, mods, and players.**

> 🏆 **Small server or massive one? Doesn't matter.**
> Dockraft gives you everything you need to manage a Minecraft server professionally — without eating into the resources your world, players and plugins actually need.
> From a small 2 GB friends box to a 64 GB high-performance machine, the panel is designed to stay out of the way: the rest of your resources stay free for the game.

---

### 📊 Real RAM Consumption Benchmark

| Panel | Idle RAM Usage | Startup Time | Multi-server Model |
| :--- | :---: | :---: | :--- |
| **Dockraft** | **~50–75 MB** (~0% CPU) | **~1 second** | **Single dedicated instance (ultra-lightweight & focused)** |
| Crafty Controller v4 | ~350 MB to 700 MB | ~20 to 30 seconds | Heavy multi-instance stack (Tornado, Flask, SQLite/Postgres) |
| Pterodactyl Panel | ~800 MB to 1.2 GB | Multiple services | Distributed infrastructure (PHP, Nginx, DB, Redis, Wings) |

---

### ✨ Key Features

* 🕹️ **1-Click Server Installer**: Select your desired engine and Minecraft version; Dockraft downloads official builds, automatically accepts the Mojang EULA, and generates initial configuration files:
  * **PaperMC**: Fast and optimized. The top choice for playing with friends and plugins.
  * **Purpur**: Enhanced Paper fork with high performance and deep gameplay customization.
  * **Mojang Vanilla**: Pure, unmodified official Minecraft server.
  * **Fabric**: Lightweight and fast for modern modpacks.
  * **Minecraft Forge**: The classic, battle-tested modding ecosystem.
  * **Bedrock Dedicated**: For mobile devices, consoles (Xbox, PlayStation, Switch), and Windows.
  * **Import Server (.zip)**: Easily migrate any existing server by uploading a `.zip` archive.
* 📟 **Live Web Console**: Real-time log streaming, instant command input, keyboard arrow command history, and quick-action buttons.
* 💾 **Selective Backups**: Choose whether to back up the entire server or just crucial directories (such as worlds or plugins) to save storage space.
* ⏰ **Automated Scheduled Tasks**: Schedule automated restarts, power on/off times, or recurring backups using custom intervals or Cron expressions.
* 🔔 **Webhook Alerts**: Receive automatic notifications in your **Discord** channel, **Telegram** group, or **Email** when the server starts, stops, or finishes a scheduled task.
* 📁 **Built-in Web File Manager**: Browse server directories, edit configuration files (`server.properties`, `bukkit.yml`) right in your browser, upload files, or extract `.zip` archives safely.
* 🔒 **Security & Access Control**:
  * Password authentication with tamper-proof HMAC session cookies.
  * **Brute-force protection**: Automatic 10-minute cooldown lockout after 5 consecutive failed login attempts.

---

### ⚡ Understanding Server Performance & TPS (Ticks Per Second)

In Minecraft, the server's internal simulation loop runs in discrete cycles called **ticks**. Each tick calculates mob AI, crop growth, redstone logic, time of day, and player interactions.

* **Target Rate**: **20.0 TPS** (the server processes exactly 20 ticks every second, meaning **1 tick every 50 milliseconds**).
* **FPS vs. TPS**: **FPS** (Frames Per Second) is client-side and determined by your computer's GPU and monitor. **TPS** is strictly server-side and measures the server CPU's ability to keep the world running in real time without lag.

#### 🚦 Performance Interpretation Scale:

| TPS in Dockraft | Status | In-Game Player Experience | Interpretation |
| :---: | :---: | :--- | :--- |
| **20.0 TPS** | 🟢 **Optimal** | Perfect fluidity. No block delays or desync. | The server easily finishes every tick cycle well under 50 ms. |
| **18.0 – 19.9 TPS** | 🟡 **Light Load** | Virtually imperceptible to players. | Normal temporary dip during world saves (`save-all`) or batch player logins. |
| **15.0 – 17.9 TPS** | 🟠 **Moderate Lag** | Slight delay opening chests, buttons, or doors; mobs move slower. | The server takes longer than 50 ms per tick. Monitor entity counts and fast exploration. |
| **< 15.0 TPS** | 🔴 **Heavy Overload** | Severe rubberbanding, broken blocks reappearing, delayed attack registrations. | Server CPU bottleneck. Simulation distance should be lowered or heavy plugins profiled. |

#### 🛠️ Common Causes of Low TPS and Optimization Tips:
1. **Entity Stacking**: Dense farms with hundreds of villagers, cows, or zombies crowded in small pens calculating physics collisions.
2. **Rapid Chunk Generation**: Players flying fast with Elytras forcing synchronous chunk generation and disk writes.
3. **Unregulated Redstone Clocks**: Fast hopper loops or piston clocks running indefinitely.
4. **High Simulation Distance**: Setting `simulation-distance=6` or `8` in `server.properties` drastically cuts CPU usage while keeping visual `view-distance` high.

---

### 🚀 Quick Start with Docker Compose (Recommended)

#### Option 1: Copy & Paste (Fastest, no git clone needed)
Create a new directory and save the following as `docker-compose.yml`:

```yaml
services:
  dockraft:
    image: marcusm99/dockraft:latest
    container_name: dockraft
    restart: unless-stopped
    ports:
      - "8000:8000"       # Web Panel
      - "25565:25565"     # Minecraft Java (TCP)
      - "19132:19132/udp" # Minecraft Bedrock (UDP)
    environment:
      - TZ=America/Guayaquil
      - ADMIN_USER=admin
      - ADMIN_PASSWORD=MySecurePassword
      - SECRET_KEY=generate_a_secret_key_with_openssl
    volumes:
      - ./data:/server_data
      - ./backups:/server_backups
```

Then launch the container:
```bash
docker compose up -d
```

#### Option 2: Clone the Repository
1. Clone the repository:
   ```bash
   git clone https://github.com/GMS-EC/dockraft.git
   cd dockraft
   ```

2. (Optional) Configure your environment variables:
   ```bash
   cp .env.example .env
   ```

3. Launch Dockraft:
   ```bash
   docker compose up -d
   ```

Open your browser at **`http://localhost:8000`** (or your server's public IP).

---

### 🐳 Run Directly with Docker

```bash
docker run -d \
  --name dockraft \
  -p 8000:8000 \
  -p 25565:25565 \
  -p 19132:19132/udp \
  -v ./data:/server_data \
  -v ./backups:/server_backups \
  -e ADMIN_USER=admin \
  -e ADMIN_PASSWORD=MySecurePassword \
  -e TZ=America/Guayaquil \
  --restart unless-stopped \
  marcusm99/dockraft:latest
```

---

### ⚙️ Environment Variables

| Variable | Default Value | Description |
| :--- | :---: | :--- |
| `PORT` | `8000` | Web panel port. |
| `ADMIN_USER` | `admin` | Administrator username for login. |
| `ADMIN_PASSWORD` | *(empty)* | Web panel password. If empty, authentication is disabled (suitable for local testing). |
| `SECRET_KEY` | *(random)* | Cryptographic key used to sign HMAC session tokens. |
| `TZ` | `America/Guayaquil` | Server timezone for scheduled tasks and backup timestamps. |
| `LOGIN_MAX_ATTEMPTS` | `5` | Maximum failed login attempts allowed before IP cooldown. |
| `LOGIN_COOLDOWN_SECONDS` | `600` | Duration of lockout in seconds (10 minutes). |

---

### 📂 Storage Volumes

* **`/server_data`**: Holds the active Minecraft server (worlds, plugins, mods, configs, and logs).
* **`/server_backups`**: Isolated directory storing compressed `.zip` backup archives.

---

### 🧪 Automated Testing

```bash
pytest tests/ -v
```

---

## 📄 License

Distributed under the **GNU General Public License v3.0 (GPLv3)**. See [`LICENSE`](LICENSE) for details.

Developed with care by [**GMS-EC**](https://gmsec.cc).
