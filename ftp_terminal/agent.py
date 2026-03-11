#!/usr/bin/env python3
"""
Agente FTP-Terminal: corre EN EL DISPOSITIVO (Windows o Linux).
Lee comandos de in.txt (por FTP o carpeta local), los ejecuta en la shell local
y escribe la salida en out.txt.
Soporta FTP_TERMINAL_ROOT: ruta base (FTP o local) donde están las carpetas por dispositivo.
"""
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

from .backend import BaseBackend, get_backend_from_env
from . import colors

# Comandos que bloquean la terminal (editores/pagers interactivos). No se ejecutan.
BLOCKED_COMMANDS = frozenset({
    "vim", "vi", "nano", "nvim", "emacs", "ed", "ex",
    "less", "more", "most",
    "top", "htop", "btop",
    "watch", "screen", "tmux", "byobu",
    "man", "info", "pager",
    "telnet", "rlogin",
    "ftp", "sftp",
})
# Prefijos que no son el programa (ej. sudo nano -> programa = nano)
COMMAND_PREFIXES = frozenset({"sudo", "env", "stdbuf", "script", "nice", "time", "nohup"})


def _get_command_program(command):
    """Obtiene el nombre del programa (primer token relevante) del comando."""
    if not command or not command.strip():
        return None
    parts = command.strip().split()
    i = 0
    while i < len(parts):
        token = parts[i].lower()
        if token in COMMAND_PREFIXES:
            i += 1
            continue
        if token.startswith("-"):
            i += 1
            continue
        name = os.path.basename(parts[i]).lower()
        if "=" in name:
            name = name.split("=")[0]
        return name
    return None


def get_blocked_commands():
    """Lista de comandos bloqueados (base + FTP_TERMINAL_BLOCKED si está definido)."""
    extra = os.environ.get("FTP_TERMINAL_BLOCKED", "").strip()
    if not extra:
        return BLOCKED_COMMANDS
    add = {x.strip().lower() for x in extra.split(",") if x.strip()}
    return BLOCKED_COMMANDS | add


def is_command_blocked(command):
    """
    True si el comando es interactivo y bloquearía la comunicación.
    Devuelve (blocked: bool, program_name: str|None).
    """
    program = _get_command_program(command)
    if not program:
        return False, None
    blocked_set = get_blocked_commands()
    # SSH: permitir solo modo no-interactivo (si no, se cuelga esperando password/confirmación)
    if program == "ssh":
        low = command.lower()
        # Requerir BatchMode=yes para que falle rápido en vez de pedir password
        if "batchmode=yes" not in low:
            return True, program
    return (program in blocked_set, program)


def run_shell_command(command):
    """Compat: wrapper legacy. (Ya no se usa en el bucle principal)."""
    return _run_shell_command_with_cwd(command, cwd=os.getcwd())[0]


def _resolve_cd_target(current_cwd, target):
    target = (target or "").strip().strip('"')
    if not target:
        return current_cwd
    if os.path.isabs(target):
        return os.path.normpath(target)
    return os.path.normpath(os.path.join(current_cwd, target))


def _run_shell_command_with_cwd(command, cwd, stream_callback=None):
    """
    Ejecuta un comando en la shell local con cwd persistente.
    Devuelve (output, new_cwd).
    Si stream_callback(text) está definido, se llama con la salida acumulada en vivo.
    """
    command = (command or "").strip()
    if not command:
        return "", cwd, False
    # Aliases útiles: permitir comandos tipo Linux en Windows
    is_win = sys.platform.startswith("win") or os.name == "nt"
    if is_win:
        stripped = command.strip()
        low = stripped.lower()
        if low == "ls":
            command = "dir"
        elif low == "pwd":
            return cwd, cwd, False
        elif low.startswith("cat "):
            command = "type " + stripped[4:]
    else:
        if command.strip().lower() == "pwd":
            return cwd, cwd, False
    # cd persistente
    low = command.strip().lower()
    if low == "cd" or low.startswith("cd "):
        parts = command.split(maxsplit=1)
        target = parts[1] if len(parts) > 1 else ""
        new_cwd = _resolve_cd_target(cwd, target)
        if os.path.isdir(new_cwd):
            return "", new_cwd, False
        return f"No existe el directorio: {new_cwd}", cwd, False

    blocked, program = is_command_blocked(command)
    if blocked:
        if program == "ssh":
            return (
                "[Comando bloqueado] 'ssh' requiere modo no-interactivo.\n"
                "Usa llaves SSH y agrega: -o BatchMode=yes\n"
                "Ejemplo: ssh -o BatchMode=yes usuario@host \"uname -a\""
            ), cwd, False
        return (
            f"[Comando bloqueado] '{program}' es interactivo y dejaría la sesión colgada.\n"
            "Usa alternativas: cat/type para ver archivos, head/tail para ver porciones, grep para buscar."
        ), cwd, False

    # Capturar en binario para evitar UnicodeDecodeError con archivos .exe u otros binarios
    MAX_OUTPUT_BYTES = 100 * 1024  # 100 KB máximo para no saturar
    CMD_TIMEOUT = float(os.environ.get("FTP_TERMINAL_CMD_TIMEOUT", "30"))

    def safe_decode(data):
        if data is None:
            return ""
        n = len(data)
        if n > MAX_OUTPUT_BYTES:
            data = data[:MAX_OUTPUT_BYTES]
            suffix = f"\n... (salida truncada, {n} bytes en total)"
        else:
            suffix = ""
        # En Windows, cmd usa la página de códigos de consola (p. ej. cp850); en Linux, utf-8
        encoding = "cp850" if is_win else "utf-8"
        text = data.decode(encoding, errors="replace").strip() + suffix
        # Un solo tipo de salto de línea para que no se vean dobles espacios
        return text.replace("\r\n", "\n").replace("\r", "\n")

    encoding = "cp850" if is_win else "utf-8"

    def run_streaming():
        """Ejecuta con Popen y va llamando stream_callback con la salida acumulada."""
        accumulated = []
        accumulated_len = 0
        lock = threading.Lock()
        encoding_stream = os.environ.get("FTP_TERMINAL_ENCODING") or encoding

        if is_win:
            proc = subprocess.Popen(
                ["cmd", "/c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                shell=False,
            )
        else:
            proc = subprocess.Popen(
                ["sh", "-c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
            )

        def reader():
            nonlocal accumulated_len
            try:
                for raw in iter(proc.stdout.readline, b""):
                    if accumulated_len >= MAX_OUTPUT_BYTES:
                        continue
                    piece = raw.decode(encoding_stream, errors="replace")
                    piece = piece.replace("\r\n", "\n").replace("\r", "\n")
                    with lock:
                        accumulated.append(piece)
                        accumulated_len += len(raw)
                        if accumulated_len > MAX_OUTPUT_BYTES:
                            accumulated.append("\n... (salida truncada)\n")
                        text = "".join(accumulated)
                    stream_callback(text)
            except (BrokenPipeError, ValueError):
                pass

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        try:
            proc.wait(timeout=CMD_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            with lock:
                text = "".join(accumulated)
            stream_callback(text + f"\n[timeout] El comando excedió {CMD_TIMEOUT}s.")
            return (text + f"\n[timeout] El comando excedió {CMD_TIMEOUT}s.", cwd, True)
        reader_thread.join(timeout=1.0)
        with lock:
            out = "".join(accumulated)
        return (out, cwd, True)  # True = ya escrito vía stream_callback

    if stream_callback is not None:
        out, cwd, _ = run_streaming()
        return (out, cwd, True)  # ya escrito vía callback

    if is_win:
        try:
            proc = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True,
                timeout=CMD_TIMEOUT,
                shell=False,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired as e:
            out = getattr(e, "stdout", None) or b""
            err = getattr(e, "stderr", None) or b""
            out = out[:MAX_OUTPUT_BYTES]
            err = err[:MAX_OUTPUT_BYTES]
            return (
                f"{safe_decode(out)}\n{safe_decode(err)}\n[timeout] El comando excedió {CMD_TIMEOUT}s.",
                cwd,
                False,
            )
    else:
        try:
            proc = subprocess.run(
                ["sh", "-c", command],
                capture_output=True,
                timeout=CMD_TIMEOUT,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired as e:
            out = getattr(e, "stdout", None) or b""
            err = getattr(e, "stderr", None) or b""
            out = out[:MAX_OUTPUT_BYTES]
            err = err[:MAX_OUTPUT_BYTES]
            return (
                f"{safe_decode(out)}\n{safe_decode(err)}\n[timeout] El comando excedió {CMD_TIMEOUT}s.",
                cwd,
                False,
            )

    out = safe_decode(proc.stdout)
    err = safe_decode(proc.stderr)
    if out and err:
        return out + "\n" + err, cwd, False
    return (out or err), cwd, False


class FTPTerminalAgent:
    """Puede usar un backend (FTP o local) o parámetros legacy (solo FTP)."""

    def __init__(self, backend=None, host=None, username=None, password=None, device_folder=None, port=21, base_path=""):
        if backend is not None:
            self._backend = backend
            self._owns_backend = False
        else:
            from .backend import FTPBackend
            self._backend = FTPBackend(
                host, username, password, device_folder or "",
                base_path=(base_path or "").strip("/"), port=port
            )
            self._owns_backend = True

    def connect(self):
        if hasattr(self._backend, "connect") and self._backend.ftp is None:
            self._backend.connect()
        return self

    def read_command(self):
        return self._backend.read_in()

    def write_output(self, text):
        self._backend.write_out(text)

    def clear_input(self):
        self._backend.clear_in()

    def write_status(self, status):
        """Escribe status.txt (IDLE, RUNNING, DONE) para Opción B del protocolo."""
        if hasattr(self._backend, "write_status"):
            try:
                self._backend.write_status(status)
            except Exception:
                pass

    def run_loop(self, poll_interval=2.0, stop_event=None):
        """Bucle principal: lee in.txt, ejecuta, escribe out.txt, limpia in.txt.
        Si stop_event (threading.Event) está definido, el bucle termina cuando se hace set()."""
        label = getattr(self._backend, "device_name", None) or getattr(self._backend, "device_folder", "?")
        root_info = ""
        if hasattr(self._backend, "base_path") and getattr(self._backend, "base_path", ""):
            root_info = f" (base: {self._backend.base_path})"
        elif hasattr(self._backend, "root_path"):
            root_info = f" (root: {self._backend.root_path})"
        colors.init()
        print(f"Agente FTP-Terminal → {label}{root_info}. Poll cada {poll_interval}s. Ctrl+C para salir.")
        last_command = None
        current_cwd = os.getcwd()
        if hasattr(self._backend, "write_cwd"):
            try:
                self._backend.write_cwd(current_cwd)
            except Exception:
                pass
        self.write_status("IDLE")
        while True:
            if stop_event and stop_event.is_set():
                break
            try:
                cmd = self.read_command()
                if cmd and cmd != last_command:
                    self.write_status("RUNNING")
                    last_command = cmd
                    print(colors.meta(f"[Ejecutando] {cmd[:60]}{'...' if len(cmd) > 60 else ''}"))
                    print()
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    def on_stream(text):
                        self.write_output(f"[{ts}] {text}")

                    output, current_cwd, already_wrote = _run_shell_command_with_cwd(
                        cmd, cwd=current_cwd, stream_callback=on_stream
                    )
                    if not already_wrote:
                        text = (output or "").strip() or current_cwd
                        self.write_output(f"[{ts}] {text}")
                    self.clear_input()
                    self.write_status("DONE")
                    if hasattr(self._backend, "write_cwd"):
                        try:
                            self._backend.write_cwd(current_cwd)
                        except Exception:
                            pass
                    last_command = None
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.write_output(f"[{ts}] Error en agente: {e}")
            time.sleep(poll_interval)


def main():
    if len(sys.argv) >= 5:
        # Legacy: host usuario contraseña carpeta_dispositivo [puerto]
        host, user, password, device = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        port = int(sys.argv[5]) if len(sys.argv) > 5 else 21
        base_path = (os.environ.get("FTP_TERMINAL_ROOT") or "").strip()
        from .backend import FTPBackend
        backend = FTPBackend(host, user, password, device, base_path=base_path, port=port)
        backend.connect()
        agent = FTPTerminalAgent(backend=backend)
    else:
        # Desde variables de entorno (incluye FTP_TERMINAL_ROOT y opcionalmente modo local)
        backend = get_backend_from_env()
        agent = FTPTerminalAgent(backend=backend)
    agent.run_loop(poll_interval=float(os.environ.get("FTP_TERMINAL_POLL", "2")))


if __name__ == "__main__":
    main()
