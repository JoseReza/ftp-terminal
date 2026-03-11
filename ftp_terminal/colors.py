#!/usr/bin/env python3
"""ANSI: color para metadata (prompt, esperando, ejecutando, timestamp)."""
import re
import sys

# Cyan para metadata
META = "\033[36m"
RESET = "\033[0m"


def _enable_windows_ansi():
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        kernel32.SetConsoleMode(handle, 7)
    except Exception:
        pass


def init():
    """Activa colores ANSI (útil en Windows)."""
    _enable_windows_ansi()


def clear_screen():
    """Limpia la pantalla de la terminal (ANSI)."""
    print("\033[2J\033[H", end="")


def meta(s):
    """Envuelve el texto con color metadata (cyan)."""
    return f"{META}{s}{RESET}"


# Línea sutil para separar la salida del comando
SEP = "────────────────────────────────────────"


def colorize_timestamp_in_output(text):
    """Pinta solo el timestamp [YYYY-MM-DD HH:MM:SS] al inicio de la salida."""
    if not text or META in text:
        return text
    match = re.match(r"^(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\])", text)
    if match:
        return meta(match.group(1)) + text[match.end() :]
    return text
