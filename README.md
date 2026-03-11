# FTP-Terminal

Terminal remota por **FTP** cuando en tu red solo está permitido el puerto 21 (y no SSH, HTTP, etc.). Ideal para extraer logs y controlar dispositivos sin tener que ir hasta el equipo.

## Cómo funciona

- **Cliente** (en tu PC): escribe comandos en `{dispositivo}/in.txt` y lee la salida de `{dispositivo}/out.txt`.
- **Agente** (en el dispositivo): cada pocos segundos lee `in.txt`, ejecuta el comando en la shell local (cmd en Windows, sh en Linux) y escribe el resultado en `out.txt`.

La **ruta base** donde están todas las carpetas de dispositivos se define con **`FTP_TERMINAL_ROOT`** (casi siempre fija en todos los equipos). Puede ser:
- **Modo FTP:** ruta en el servidor (ej. `devices` → `devices/BCM025/`).
- **Modo local:** carpeta en disco (ej. `D:\devices` o `/mnt/ftp/devices`), útil si ya tienes el FTP montado como carpeta.

Compatible con **Windows y Linux** en cliente y agente.

## Requisitos

- Python 3.6+ (solo biblioteca estándar).
- Un servidor FTP accesible desde tu PC y desde cada dispositivo (mismo servidor o uno por dispositivo, según tu infraestructura).

## Configuración con archivo (.env o config.ini)

Puedes guardar la configuración en un archivo en lugar de definir variables de entorno a mano:

- **.env** — Copia `.env.example` a `.env` y edita los valores (una línea por variable).
- **config.ini** — Copia `config.ini.example` a `config.ini` y edita la sección `[ftp_terminal]`.

El programa busca primero `.env` y, si no existe, `config.ini` en el directorio actual o en la raíz del proyecto. Las variables que ya estén definidas en el sistema no se sobrescriben.

- **Una sola variable `root`:** si tiene `://` se usa FTP (ej. `ftp://usuario:contraseña@ftp.miempresa.com:21/devices`); si no, es ruta local (ej. `D:/devices`). No hace falta `ftp = true/false` ni `host` por separado.

**No subas `.env` ni `config.ini` al repositorio** (contienen contraseña); sí puedes subir los `.example`.

## Uso rápido

### Punto de entrada único: `main.py`

Todo se ejecuta desde un solo programa:

```bash
# En el dispositivo: arrancar el agente (lee config.ini o .env)
python main.py agent

# En tu PC: abrir la terminal hacia un dispositivo
python main.py client
python main.py client BCM025
python main.py client BCM025 --cmd "dir"
```

Si no pasas subcomando y das solo el nombre del dispositivo, se asume cliente: `python main.py BCM025` = `python main.py client BCM025`.

### 1. En el dispositivo (una vez por equipo)

Tiene que estar corriendo el **agente** para que ejecute lo que tú envías.

**Opción A – Línea de comandos**

```bash
# Linux / WSL
python3 -m ftp_terminal.agent FTP_HOST usuario contraseña BCM025

# Windows (cmd)
python -m ftp_terminal.agent FTP_HOST usuario contraseña BCM025
```

**Opción B – Variables de entorno (recomendado; misma config en todos los dispositivos)**

`FTP_TERMINAL_ROOT` es la ruta base donde están (o estarán) las carpetas de cada dispositivo; suele ser fija.

**Modo FTP:**
```bash
# Linux
export FTP_TERMINAL_ROOT=devices
export FTP_TERMINAL_HOST=ftp.miempresa.com
export FTP_TERMINAL_USER=usuario
export FTP_TERMINAL_PASS=tu_contraseña
export FTP_TERMINAL_DEVICE=BCM025
python main.py agent
# o  python run_agent.py
```

```cmd
:: Windows
set FTP_TERMINAL_ROOT=devices
set FTP_TERMINAL_HOST=ftp.miempresa.com
set FTP_TERMINAL_USER=usuario
set FTP_TERMINAL_PASS=tu_contraseña
set FTP_TERMINAL_DEVICE=BCM025
python main.py agent
```

**Modo local** (carpeta en disco, p. ej. espejo o montaje del FTP):
```bash
export FTP_TERMINAL_ROOT=/mnt/ftp/devices
export FTP_TERMINAL_DEVICE=BCM025
python main.py agent
```

```cmd
set FTP_TERMINAL_ROOT=D:\devices
set FTP_TERMINAL_DEVICE=BCM025
python main.py agent
```

Sustituye `BCM025` por un nombre único por dispositivo (ej. hostname o ID). El agente crea la carpeta del dispositivo si no existe.

### 2. En tu PC (cuando quieras “entrar” al dispositivo)

Solo necesitas el **cliente**.

**Con FTP_TERMINAL_* ya configuradas** (misma ruta base, solo cambia el dispositivo):

```bash
# Indicar solo el nombre del dispositivo
python -m ftp_terminal.client BCM025
```

**Sin variables de entorno** (host, usuario y dispositivo por argumentos):

```bash
python -m ftp_terminal.client FTP_HOST usuario BCM025
```

Te pedirá la contraseña FTP (en modo FTP) y entrarás en una sesión donde cada línea que escribas se envía al dispositivo y la salida se muestra en pantalla. Comandos útiles: `dir`, `ls -la`, `type archivo.log`, `cat /var/log/app.log`, etc.

### Cambiar de dispositivo en la misma sesión (desde BCM027 a BCM025/BCM026)

Si ejecutas el cliente en un dispositivo (ej. BCM027) con las variables `FTP_TERMINAL_*` definidas, puedes conectarte primero a un dispositivo y **cambiar a otro sin salir**:

```bash
# En BCM027, con FTP_TERMINAL_* ya configuradas
python -m ftp_terminal.client BCM025
```

En el prompt verás algo como `ftp-term [BCM025]>`. Para pasar a BCM026:

```
ftp-term [BCM025]> device BCM026
→ Cambiado a dispositivo 'BCM026'.

ftp-term [BCM026]> dir
...
```

También vale `switch BCM026`. Los comandos que escribas a partir de ahí se ejecutan en el dispositivo actual (BCM026 hasta que cambies de nuevo).

## Montar FTP como carpeta (opcional)

Si prefieres que el dispositivo solo lea/escriba archivos en una carpeta montada (sin usar FTP desde el propio script), puedes montar el FTP en una ruta local y adaptar el agente para usar esa ruta en lugar de `ftplib`. Por ahora el agente usa FTP directamente, así que no es obligatorio montar nada.

- **Windows:** WinSCP, NetDrive o “Asignar unidad de red” con un cliente FTP.
- **Linux:** `curlftpfs`, `rclone mount`, etc.

## Limitaciones

- **Latencia:** Hay polling (p. ej. cada 1–2 s), no es tiempo real como SSH.
- **Un comando a la vez:** Se espera la salida de un comando antes de enviar el siguiente.
- **Comandos interactivos:** Los que piden input (ej. `sudo` con contraseña) no son adecuados; mejor usar comandos que terminen solos (logs, listados, scripts).

### Comandos bloqueados en el agente

Para evitar que la sesión quede colgada, el agente **no ejecuta** editores ni programas interactivos, por ejemplo: `vim`, `vi`, `nano`, `less`, `more`, `top`, `htop`, `man`, `ssh`, `screen`, `tmux`, etc. Si alguien los intenta, verá un mensaje sugiriendo alternativas (`cat`/`type` para ver archivos, `head`/`tail`, `grep`). Puedes añadir más con la variable de entorno `FTP_TERMINAL_BLOCKED` (lista separada por comas).

## Alternativas que podrías valorar

1. **Salida outbound del firewall:** Si los dispositivos pueden abrir conexiones hacia fuera y ustedes tienen un servidor accesible por internet, un “reverse shell” (el dispositivo se conecta a vuestro servidor) podría dar terminal “de verdad” sin tocar reglas de IT.
2. **VPN o túnel aprobado por IT:** Si en el futuro permiten un único túnel (VPN o similar), podrían usar SSH por encima.
3. **FTP + este proyecto:** Es la opción que tienes ya con lo que IT permite; este repo implementa exactamente esa idea.

## Estructura del repo

- `main.py` – Entrada única: `python main.py agent` o `python main.py client [dispositivo]`.
- `ftp_terminal/client.py` – Cliente (terminal).
- `ftp_terminal/agent.py` – Agente (en cada dispositivo).
- `ftp_terminal/backend.py` – Backends FTP y local.
- `run_agent.py` – Atajo para el agente (`python run_agent.py` = `python main.py agent`).
- `docs/PROTOCOLO.md` – Detalle del protocolo.

Si quieres extender (varios comandos en cola, timeouts distintos, etc.), se puede hacer sobre esta base sin cambiar el esquema FTP.

---

## Un solo comando (scripts)

Para automatizar (p. ej. extraer un log sin sesión interactiva):

```bash
python -m ftp_terminal.client ftp.miempresa.com usuario BCM025 --cmd "type C:\logs\app.log"
# En Linux en el dispositivo:
# python -m ftp_terminal.client ftp.miempresa.com usuario BCM025 --cmd "cat /var/log/app.log"
```

---

## Dejar el agente corriendo en el dispositivo

- **Windows:** Programador de tareas o un servicio (NSSM, etc.) para ejecutar `python main.py agent` al inicio.
- **Linux:** systemd o cron `@reboot` con las variables de entorno y `python3 main.py agent`.

Así el dispositivo siempre está “escuchando” comandos por FTP y no tienes que levantar el agente a mano cada vez.
