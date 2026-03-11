#!/usr/bin/env python3
"""
Carga configuración desde .env o config.ini y la aplica a os.environ (FTP_TERMINAL_*).
Así no hace falta definir las variables a mano; las lee del archivo si existe.
Las variables ya definidas en el sistema tienen prioridad (no se sobrescriben).
"""
import os
import sys


# Mapeo nombre en config.ini -> variable de entorno
CONFIG_KEYS = {
    "host": "FTP_TERMINAL_HOST",
    "user": "FTP_TERMINAL_USER",
    "username": "FTP_TERMINAL_USER",
    "password": "FTP_TERMINAL_PASS",
    "pass": "FTP_TERMINAL_PASS",
    "root": "FTP_TERMINAL_ROOT",
    "base_path": "FTP_TERMINAL_ROOT",
    "device": "FTP_TERMINAL_DEVICE",
    "port": "FTP_TERMINAL_PORT",
    "poll": "FTP_TERMINAL_POLL",
    "stable_seconds": "FTP_TERMINAL_STABLE_SECONDS",
    "use_local": "FTP_TERMINAL_USE_LOCAL",
    "ftp": "FTP_TERMINAL_FTP",
    "enable_ftp": "FTP_TERMINAL_FTP",
}


def _find_config_dirs():
    """Carpetas donde buscar .env / config.ini: cwd y raíz del proyecto."""
    dirs = [os.getcwd()]
    # Raíz del proyecto (donde está run_agent.py o el paquete ftp_terminal)
    try:
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        parent = os.path.dirname(pkg_dir)
        if parent not in dirs:
            dirs.append(parent)
    except Exception:
        pass
    return dirs


def _load_dotenv(path):
    """Carga un .env y actualiza os.environ (solo si la clave no existe)."""
    if not os.path.isfile(path):
        return False
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"')
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("\\'", "'")
            if key and key not in os.environ:
                os.environ[key] = value
    return True


def _load_ini(path):
    """Carga config.ini [ftp_terminal] y actualiza os.environ con FTP_TERMINAL_*."""
    if not os.path.isfile(path):
        return False
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(path, encoding="utf-8")
        if "ftp_terminal" not in cfg:
            return True
        section = cfg["ftp_terminal"]
        for ini_key, env_key in CONFIG_KEYS.items():
            if ini_key in section and env_key not in os.environ:
                os.environ[env_key] = section[ini_key].strip()
        return True
    except Exception:
        return False


def load_config():
    """
    Busca .env o config.ini en el directorio actual y en la raíz del proyecto,
    y rellena os.environ con FTP_TERMINAL_* (solo las que no estén ya definidas).
    """
    for dirpath in _find_config_dirs():
        env_path = os.path.join(dirpath, ".env")
        ini_path = os.path.join(dirpath, "config.ini")
        if _load_dotenv(env_path):
            return
        if _load_ini(ini_path):
            return
