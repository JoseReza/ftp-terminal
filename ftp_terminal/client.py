#!/usr/bin/env python3
"""
Cliente FTP-Terminal: tu PC (ingeniero).
Escribe comandos en {dispositivo}/in.txt y lee la salida de {dispositivo}/out.txt.
Soporta FTP_TERMINAL_ROOT (ruta base en servidor FTP o carpeta local) y conexión por parámetros.
"""
import os
import sys
import time

# Historial de comandos con ↑/↓ (Linux/Mac; en Windows no hay readline en la stdlib)
try:
    import readline
except ImportError:
    readline = None

from .backend import BaseBackend, FTPBackend, LocalBackend, get_backend_from_env
from . import colors


def _is_escape_or_control(line):
    """Si la línea es una tecla (flechas, etc.) no enviarla al agente para no trabar."""
    if not line:
        return True
    # Secuencias ANSI (flecha arriba = \x1b[A, etc.)
    if "\x1b" in line or "\033" in line:
        return True
    # Un solo carácter de control (salvo tab, enter)
    if len(line) == 1 and ord(line[0]) < 32 and ord(line[0]) not in (9, 10, 13):
        return True
    return False


class FTPTerminalClient:
    """Puede usar un backend (FTP o local) o parámetros legacy (solo FTP)."""

    def __init__(self, backend=None, host=None, username=None, password=None, device_folder=None, port=21, base_path="", backend_factory=None):
        self._backend_factory = backend_factory  # callable(device_name) -> backend, para cambiar de dispositivo
        if backend is not None:
            self._backend = backend
            self._owns_backend = False
        else:
            self._backend = FTPBackend(
                host, username, password, device_folder or "",
                base_path=(base_path or "").strip("/"), port=port
            )
            self._owns_backend = True

    def current_device(self):
        """Nombre del dispositivo actual (para el prompt)."""
        return getattr(self._backend, "device_name", None) or getattr(self._backend, "device_folder", "?")

    def switch_device(self, device_name):
        """Cambia al dispositivo indicado. Solo si se pasó backend_factory al crear el cliente."""
        if not self._backend_factory:
            return False
        device_name = (device_name or "").strip()
        if not device_name:
            return False
        self.disconnect()
        self._backend = self._backend_factory(device_name)
        if hasattr(self._backend, "connect") and getattr(self._backend, "ftp", None) is None:
            self._backend.connect()
        return True

    def connect(self):
        if hasattr(self._backend, "connect") and getattr(self._backend, "ftp", None) is None:
            self._backend.connect()
        return self

    def send_command(self, command):
        text = command.decode("utf-8") if isinstance(command, bytes) else command
        if text and not text.endswith("\n"):
            text += "\n"
        # Evitar mostrar salida previa (out.txt viejo) para el siguiente comando
        if hasattr(self._backend, "clear_out"):
            self._backend.clear_out()
        self._backend.write_in(text)

    def read_output(self):
        return self._backend.read_out()

    def read_status(self):
        """Lee status.txt (IDLE, RUNNING, DONE). None si el backend no lo soporta."""
        if hasattr(self._backend, "read_status"):
            try:
                return self._backend.read_status()
            except Exception:
                pass
        return None

    def get_cwd(self):
        """Directorio de trabajo actual del dispositivo (para mostrar en el prompt)."""
        if hasattr(self._backend, "read_cwd"):
            try:
                return self._backend.read_cwd()
            except Exception:
                pass
        return None

    def wait_for_output(self, poll_interval=None, timeout=60.0, stable_seconds=None):
        """Espera la salida y la muestra en vivo. Devuelve (contenido, se_mostro_en_vivo).
        Opción B: espera status RUNNING (agente tomó el comando) y luego DONE (comando terminado)."""
        if poll_interval is None:
            poll_interval = float(os.environ.get("FTP_TERMINAL_POLL", "0.15"))
        if stable_seconds is None:
            stable_seconds = float(os.environ.get("FTP_TERMINAL_STABLE_SECONDS", "0.5"))
            stable_seconds = max(stable_seconds, poll_interval * 1.5, 0.2)
        deadline = time.monotonic() + timeout
        last_content = None
        last_change = time.monotonic()
        printed_len = 0
        seen_running = False
        while time.monotonic() < deadline:
            content = self.read_output()
            if content is not None:
                if len(content) > printed_len:
                    new_part = content[printed_len:]
                    print(new_part, end="", flush=True)
                    printed_len = len(content)
            status = self.read_status()
            if status == "RUNNING":
                seen_running = True
            # DONE = comando terminado. Si vimos RUNNING o si ya llegó salida (comando rápido), dar por terminado
            if status == "DONE" and (seen_running or printed_len > 0):
                return ((content if content is not None else last_content) or ""), printed_len > 0
            if content is not None and content.strip():
                if content == last_content:
                    if status is None and time.monotonic() - last_change >= stable_seconds:
                        return content, printed_len > 0
                else:
                    last_content = content
                    last_change = time.monotonic()
            else:
                last_content = content
                last_change = time.monotonic()
            time.sleep(poll_interval)
        out = last_content if last_content else "(timeout sin respuesta)"
        return out, printed_len > 0

    def disconnect(self):
        if hasattr(self._backend, "disconnect"):
            self._backend.disconnect()


def interactive_session(host=None, username=None, password=None, device_folder=None, port=21, base_path="", backend=None, backend_factory=None):
    if backend is not None:
        client = FTPTerminalClient(backend=backend, backend_factory=backend_factory)
    else:
        client = FTPTerminalClient(
            host=host, username=username, password=password,
            device_folder=device_folder, port=port, base_path=base_path
        )
    client.connect()
    label = client.current_device()
    root_info = ""
    if hasattr(client._backend, "base_path") and getattr(client._backend, "base_path", ""):
        root_info = f" base={client._backend.base_path}"
    elif hasattr(client._backend, "root_path"):
        root_info = f" root={client._backend.root_path}"
    print(f"[ Conectado → dispositivo '{label}'{root_info} ]")
    if backend_factory:
        print("  Comando 'device <nombre>' para cambiar de dispositivo (ej: device BCM026).")
    print("  Escribe 'exit' o 'quit' para salir.\n")
    colors.init()
    try:
        while True:
            try:
                cwd = client.get_cwd()
                if cwd:
                    prompt = colors.meta(f"ftp-term [{client.current_device()}] {cwd}> ")
                else:
                    prompt = colors.meta(f"ftp-term [{client.current_device()}]> ")
                line = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            # No enviar flechas/teclas como comando (evita que se trabe esperando respuesta)
            if _is_escape_or_control(line):
                continue
            if line.lower() in ("exit", "quit"):
                break
            # Cambiar de dispositivo: "device BCM026" o "switch BCM026"
            lower = line.lower()
            if (lower.startswith("device ") or lower.startswith("switch ")) and len(line) > 7:
                target = line.split(None, 1)[1].strip()
                if client.switch_device(target):
                    print(f"→ Cambiado a dispositivo '{target}'.\n")
                else:
                    print("→ Cambio de dispositivo solo disponible con FTP_TERMINAL_* en env.\n")
                continue
            client.send_command(line + "\n")
            print(colors.meta("(esperando respuesta del dispositivo...)"))
            print()
            output, streamed = client.wait_for_output()
            if line.strip().lower() in ("cls", "clear"):
                colors.clear_screen()
            else:
                if not streamed and output:
                    print(colors.colorize_timestamp_in_output(output))
                print()
                print(colors.meta(colors.SEP))
    finally:
        client.disconnect()
        print("Desconectado.")


def one_shot(host=None, username=None, password=None, device_folder=None, command=None, port=21, base_path="", backend=None):
    if backend is not None:
        client = FTPTerminalClient(backend=backend)
    else:
        client = FTPTerminalClient(
            host=host, username=username, password=password,
            device_folder=device_folder, port=port, base_path=base_path
        )
    client.connect()
    try:
        client.send_command(command + "\n")
        out, _ = client.wait_for_output()
        return out
    finally:
        client.disconnect()


def main():
    import getpass
    # Cargar .env o config.ini si existen
    try:
        from ftp_terminal.config_loader import load_config
        load_config()
    except Exception:
        pass
    # ¿Usar solo variables de entorno? (FTP_TERMINAL_ROOT fija la ruta base)
    use_env = os.environ.get("FTP_TERMINAL_ROOT") or os.environ.get("FTP_TERMINAL_HOST")
    device_from_env = os.environ.get("FTP_TERMINAL_DEVICE")
    # Dispositivo: argumento o env (ej. "python -m ftp_terminal.client BCM025")
    device_arg = sys.argv[1] if len(sys.argv) >= 2 and sys.argv[1] and not sys.argv[1].startswith("-") else None
    if use_env and (device_from_env or device_arg):
        device = device_arg or device_from_env
        backend = get_backend_from_env(device)
        args_rest = sys.argv[2:] if device_arg else sys.argv[1:]
        if args_rest and args_rest[0] == "--cmd" and len(args_rest) >= 2:
            print(one_shot(backend=backend, command=" ".join(args_rest[1:])))
        else:
            # backend_factory permite cambiar de dispositivo con "device BCM026"
            interactive_session(backend=backend, backend_factory=get_backend_from_env)
        return

    if len(sys.argv) < 4:
        print("Uso: python -m ftp_terminal.client <host> <usuario> <carpeta_dispositivo> [puerto]")
        print("     python -m ftp_terminal.client <carpeta_dispositivo>   (con FTP_TERMINAL_* en env)")
        print("     python -m ftp_terminal.client <host> <usuario> <carpeta> --cmd 'comando'")
        print("Ejemplo: python -m ftp_terminal.client ftp.miempresa.com usuario BCM025")
        sys.exit(1)
    host = sys.argv[1]
    user = sys.argv[2]
    device = sys.argv[3]
    port = 21
    base_path = (os.environ.get("FTP_TERMINAL_ROOT") or "").strip()
    args = sys.argv[4:]
    if args and args[0] == "--cmd" and len(args) >= 2:
        password = getpass.getpass(f"Contraseña FTP para {user}@{host}: ")
        cmd = " ".join(args[1:])
        print(one_shot(host, user, password, device, cmd, port, base_path))
        return
    if args and args[0].isdigit():
        port = int(args[0])
    password = getpass.getpass(f"Contraseña FTP para {user}@{host}: ")
    interactive_session(host, user, password, device, port, base_path)


if __name__ == "__main__":
    main()
