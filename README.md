# FTP-Terminal

Terminal remota por **FTP** cuando en tu red solo está permitido el puerto 21 (y no SSH, HTTP, etc.). Ideal para extraer logs y controlar dispositivos sin tener que ir hasta el equipo.

## Cómo funciona

- **Cliente** (en tu PC): escribe comandos en `{dispositivo}/in.txt` y lee la salida de `{dispositivo}/out.txt`.
- **Agente** (en el dispositivo): cada pocos segundos lee `in.txt`, ejecuta el comando en la shell local (cmd en Windows, sh en Linux) y escribe el resultado en `out.txt`.

La **ruta base** donde están todas las carpetas de dispositivos se define en **`config.ini`** (clave `root`). Puede ser:
- **Modo FTP:** URL en el servidor (ej. `ftp://usuario:contraseña@ftp.miempresa.com:21/devices`).
- **Modo local:** ruta en disco (ej. `D:/devices` o `/mnt/ftp/devices`), útil si ya tienes el FTP montado como carpeta.

Compatible con **Windows y Linux** en cliente y agente.

## Requisitos

- Python 3.6+ (solo biblioteca estándar).
- Un servidor FTP accesible desde tu PC y desde cada dispositivo (mismo servidor o uno por dispositivo, según tu infraestructura).

## Compilación (ejecutable con PyInstaller)

Puedes generar un ejecutable para no depender de tener Python instalado en cada máquina. El proyecto incluye `main.spec` para PyInstaller.

**Windows (cmd o PowerShell):**

```cmd
pip install pyinstaller
pyinstaller main.spec
```

El ejecutable queda en `dist\main.exe`. Copia `config.ini` (o `config.ini.example` renombrado) junto al `.exe` para que lea la configuración.

**Linux:**

```bash
pip install pyinstaller
pyinstaller main.spec
```

El ejecutable queda en `dist/main`. Copia `config.ini` en el mismo directorio (o en el directorio de trabajo desde el que lo ejecutes) para que lea la configuración.

Uso del ejecutable:

- **Agente (en el dispositivo):** `main.exe agent` (Windows) o `./main agent` (Linux).
- **Cliente:** `main.exe client BCM025` (Windows) o `./main client BCM025` (Linux).

## Configuración: `config.ini`

Copia `config.ini.example` a `config.ini` en la raíz del proyecto (o en el directorio desde el que ejecutas) y edita la sección `[ftp_terminal]`. El programa busca `config.ini` en el directorio actual y en la raíz del proyecto.

Ejemplo mínimo:

```ini
[ftp_terminal]
# Ruta base: URL FTP (con ://) o ruta local (sin ://)
root = ftp://usuario:contraseña@ftp.miempresa.com:21/devices
# En el dispositivo, nombre único (ej. hostname o ID)
device = BCM025
```

- **`root`:** si contiene `://` se usa FTP (ej. `ftp://usuario:contraseña@host:21/devices`); si no, es ruta local (ej. `D:/devices`, `/mnt/ftp/devices`). Opcionalmente puedes usar `host`, `user`, `password`, `port` por separado en lugar de la URL.
- **`device`:** nombre del dispositivo (obligatorio en el agente; en el cliente es el dispositivo al que te conectas por defecto o el que pasas como argumento).

**No subas `config.ini` al repositorio** (contiene contraseña); sí puedes subir `config.ini.example`.

## Uso rápido

### Punto de entrada único: `main.py`

Todo se ejecuta desde un solo programa:

```bash
# En el dispositivo: arrancar el agente (lee config.ini)
python main.py agent

# En tu PC: abrir la terminal hacia un dispositivo
python main.py client
python main.py client BCM025
python main.py client BCM025 --cmd "dir"
```

Si no pasas subcomando y das solo el nombre del dispositivo, se asume cliente: `python main.py BCM025` = `python main.py client BCM025`.

**Cambiar de dispositivo sin salir:** dentro de la sesión del cliente puedes usar **`device <nombre>`** o **`switch <nombre>`** (ej. `device BCM026`, `switch BCM026`) para pasar a otro dispositivo sin cerrar la terminal. Requiere tener `config.ini` con `root` (y credenciales si usas FTP).

### 1. En el dispositivo (una vez por equipo)

Tiene que estar corriendo el **agente** para que ejecute lo que tú envías. Configura `config.ini` con `root` y `device` (nombre único por equipo, ej. hostname o ID). El agente crea la carpeta del dispositivo si no existe.

**Linux / WSL:**

```bash
python3 main.py agent
# o  python3 run_agent.py
```

**Windows (cmd):**

```cmd
python main.py agent
```

### 2. En tu PC (cuando quieras “entrar” al dispositivo)

Solo necesitas el **cliente**. Con `config.ini` en la raíz (o en el directorio actual), indica el dispositivo:

**Linux / WSL:**

```bash
python3 main.py client BCM025
```

**Windows (cmd):**

```cmd
python main.py client BCM025
```

Entrarás en una sesión donde cada línea que escribas se envía al dispositivo y la salida se muestra en pantalla. Comandos útiles: `dir`, `ls -la`, `type archivo.log`, `cat /var/log/app.log`, etc.

### Cambiar de dispositivo en la misma sesión: `device` y `switch`

Dentro de una sesión del cliente puedes **cambiar a otro dispositivo sin salir** usando:

- **`device <nombre>`** — ej. `device BCM026`
- **`switch <nombre>`** — ej. `switch BCM026`

Ambos hacen lo mismo. Ejemplo:

```bash
python main.py client BCM025
```

En el prompt verás algo como `ftp-term [BCM025]>`. Para pasar a BCM026:

```
ftp-term [BCM025]> device BCM026
→ Cambiado a dispositivo 'BCM026'.

ftp-term [BCM026]> dir
...
```

Los comandos que escribas a partir de ahí se ejecutan en el dispositivo actual (BCM026 hasta que cambies de nuevo). El cambio de dispositivo solo está disponible si el cliente usa `config.ini` (con `root` y credenciales si aplica).

## Montar FTP como carpeta (opcional)

Si prefieres que el dispositivo solo lea/escriba archivos en una carpeta montada (sin usar FTP desde el propio script), puedes montar el FTP en una ruta local y adaptar el agente para usar esa ruta en lugar de `ftplib`. Por ahora el agente usa FTP directamente, así que no es obligatorio montar nada.

- **Windows:** WinSCP, NetDrive o “Asignar unidad de red” con un cliente FTP.
- **Linux:** `curlftpfs`, `rclone mount`, etc.

## Limitaciones

- **Latencia:** Hay polling (p. ej. cada 1–2 s), no es tiempo real como SSH.
- **Un comando a la vez:** Se espera la salida de un comando antes de enviar el siguiente.
- **Comandos interactivos:** Los que piden input (ej. `sudo` con contraseña) no son adecuados; mejor usar comandos que terminen solos (logs, listados, scripts).

### Comandos bloqueados en el agente

Para evitar que la sesión quede colgada, el agente **no ejecuta** editores ni programas interactivos, por ejemplo: `vim`, `vi`, `nano`, `less`, `more`, `top`, `htop`, `man`, `ssh`, `screen`, `tmux`, etc. Si alguien los intenta, verá un mensaje sugiriendo alternativas (`cat`/`type` para ver archivos, `head`/`tail`, `grep`). Para añadir más comandos bloqueados, consulta la configuración del agente en el código.

## Alternativas que podrías valorar

1. **Salida outbound del firewall:** Si los dispositivos pueden abrir conexiones hacia fuera y ustedes tienen un servidor accesible por internet, un “reverse shell” (el dispositivo se conecta a vuestro servidor) podría dar terminal “de verdad” sin tocar reglas de IT.
2. **VPN o túnel aprobado por IT:** Si en el futuro permiten un único túnel (VPN o similar), podrían usar SSH por encima.
3. **FTP + este proyecto:** Es la opción que tienes ya con lo que IT permite; este repo implementa exactamente esa idea.

## Estructura del repo

- `main.py` – Entrada única: `python main.py agent` o `python main.py client [dispositivo]`.
- `main.spec` – Especificación de PyInstaller para generar el ejecutable.
- `ftp_terminal/client.py` – Cliente (terminal).
- `ftp_terminal/agent.py` – Agente (en cada dispositivo).
- `ftp_terminal/backend.py` – Backends FTP y local.
- `run_agent.py` – Atajo para el agente (`python run_agent.py` = `python main.py agent`).
- `config.ini.example` – Plantilla de configuración (copiar a `config.ini`).
- `docs/PROTOCOLO.md` – Detalle del protocolo.

Si quieres extender (varios comandos en cola, timeouts distintos, etc.), se puede hacer sobre esta base sin cambiar el esquema FTP.

---

## Un solo comando (scripts)

Para automatizar (p. ej. extraer un log sin sesión interactiva), usa `config.ini` y:

**Linux / WSL:**

```bash
python3 main.py client BCM025 --cmd "cat /var/log/app.log"
```

**Windows:**

```cmd
python main.py client BCM025 --cmd "type C:\logs\app.log"
```

---

## Dejar el agente corriendo en el dispositivo

Con `config.ini` en su sitio, haz que el agente se ejecute al arranque:

- **Windows:** Programador de tareas o un servicio (NSSM, etc.) para ejecutar `python main.py agent` al inicio.
- **Linux:** systemd o cron `@reboot` con `python3 main.py agent` (el agente lee `config.ini` del directorio de trabajo o de la raíz del proyecto).

Así el dispositivo siempre está “escuchando” comandos por FTP y no tienes que levantar el agente a mano cada vez.
