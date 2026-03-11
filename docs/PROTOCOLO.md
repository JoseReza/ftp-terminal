# Protocolo FTP-Terminal

## Idea

Cuando solo FTP está permitido en la red, se simula una terminal usando **dos archivos por dispositivo** en una **carpeta base** (FTP o local):

```
FTP_TERMINAL_ROOT (ruta base, fija en la configuración)
  BCM025/
    in.txt    → comandos que envía el ingeniero (cliente escribe, agente lee)
    out.txt   → salida del comando (agente escribe, cliente lee)
    status.txt → estado del agente: IDLE | RUNNING | DONE (Opción B)
  BCM026/
    in.txt
    out.txt
    status.txt
```

La variable de entorno **FTP_TERMINAL_ROOT** apunta a esa carpeta:
- **Modo FTP:** ruta base en el servidor (ej. `devices` → `devices/BCM025/in.txt`).
- **Modo local:** directorio en disco (ej. `D:\devices` o `/mnt/ftp/devices`), que puede ser un espejo o montaje del FTP.

- **Cliente** (en la PC del ingeniero): escribe en `in.txt`, hace polling de `out.txt` y muestra la salida.
- **Agente** (en el dispositivo): hace polling de `in.txt`, ejecuta el comando en la shell local y escribe en `out.txt`.

## Flujo por comando (Opción B)

1. Cliente escribe en `{dispositivo}/in.txt` el comando.
2. Agente en bucle: lee `in.txt`; si hay comando nuevo:
   - Escribe `RUNNING` en `status.txt`.
   - Ejecuta el comando en la shell y va escribiendo la salida en `out.txt` (streaming).
   - Al terminar, limpia `in.txt` y escribe `DONE` en `status.txt`.
3. Cliente hace polling de `out.txt` (muestra salida en vivo) y de `status.txt`: espera a ver `RUNNING` (agente tomó el comando) y luego `DONE` (comando terminado).

## Evitar condiciones de carrera

- **Opción A (simple):** El agente después de ejecutar limpia `in.txt`. El cliente sabe que el comando terminó cuando `in.txt` está vacío.
- **Opción B (marcadores):** Un tercer archivo `status.txt` con valores: `IDLE`, `RUNNING`, `DONE`. El agente escribe `RUNNING` al tomar el comando, ejecuta, escribe en `out.txt`, y al terminar escribe `DONE`. El cliente espera a ver `RUNNING` (agente tomó el comando) y luego `DONE` (comando terminado). Así se detecta el fin del comando de forma precisa sin depender de tiempos.

En esta implementación se usa **Opción B**: el agente escribe en `status.txt` al inicio `IDLE`, al leer un comando `RUNNING`, y al terminar `DONE`. El cliente hace polling de `status.txt` y considera el comando terminado cuando ve `DONE` (después de haber visto `RUNNING` para no confundir con un `DONE` anterior).

## Variable FTP_TERMINAL_ROOT (recomendada)

En la práctica la **ruta base** suele ser la misma en todos los dispositivos. Se configura una sola vez:

- **FTP:** `FTP_TERMINAL_ROOT=devices` (o la ruta que use el servidor).
- **Local:** `FTP_TERMINAL_ROOT=D:\devices` / `FTP_TERMINAL_ROOT=/mnt/ftp/devices` (carpeta local; puede ser espejo o montaje del FTP).

El mismo código y variables se distribuyen en todos los dispositivos; solo cambia `FTP_TERMINAL_DEVICE` (ej. BCM025, BCM026).

## Montajes (opcional)

Si en el dispositivo montan el FTP como carpeta local:

- **Windows:** WinSCP, NetDrive, o "Map network drive" con cliente FTP.
- **Linux:** `curlftpfs`, `rclone mount`, etc.

Entonces pueden usar **modo local**: `FTP_TERMINAL_ROOT` apunta a esa carpeta montada (sin definir `FTP_TERMINAL_HOST`). El agente solo lee/escribe archivos en disco.

El **cliente** puede usar modo FTP o modo local según tenga definido `FTP_TERMINAL_HOST` o solo `FTP_TERMINAL_ROOT`.

## Multiplataforma

- **Agente:** un único script Python que detecte OS (`sys.platform` o `os.name`) y ejecute con `subprocess` usando `cmd /c` en Windows o `sh -c` en Linux.
- **Cliente:** mismo código Python; solo necesita conectarse por FTP desde Windows o Linux.
