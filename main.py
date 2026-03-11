#!/usr/bin/env python3
r"""
Punto de entrada único: terminal (cliente) y agente.

  python main.py                    → agente + terminal a la vez (todo en uno)
  python main.py agent              → solo agente en este equipo
  python main.py client             → solo terminal (dispositivo desde FTP_TERMINAL_DEVICE)
  python main.py client BCM025       → terminal conectada al dispositivo BCM025
  python main.py client BCM025 --cmd "dir"

Configuración: .env o config.ini (root y device). root sin "://" = local, con "://" = FTP.
"""
import sys
import os
import threading

# Cargar configuración una sola vez
try:
    from ftp_terminal.config_loader import load_config
    load_config()
except Exception:
    pass


def run_agent(stop_event=None):
    """Ejecuta el agente. Si stop_event (threading.Event) está definido, el bucle termina al hacer set()."""
    from ftp_terminal.agent import FTPTerminalAgent
    from ftp_terminal.backend import get_backend_from_env
    root = (os.environ.get("FTP_TERMINAL_ROOT") or "").strip()
    device = os.environ.get("FTP_TERMINAL_DEVICE") or ""
    if not root or not device:
        print("Definir FTP_TERMINAL_ROOT y FTP_TERMINAL_DEVICE (config.ini o .env).")
        print("  root = ruta local (D:/devices) o URL FTP (ftp://user:pass@host:21/devices)")
        sys.exit(1)
    try:
        backend = get_backend_from_env()
    except (TimeoutError, OSError, ConnectionError) as e:
        print("Error al conectar por FTP:", e)
        print("Para modo local usa en root una ruta sin ://  (ej. D:/devices).")
        sys.exit(1)
    agent = FTPTerminalAgent(backend=backend)
    agent.run_loop(
        poll_interval=float(os.environ.get("FTP_TERMINAL_POLL", "2")),
        stop_event=stop_event,
    )


def run_client(argv=None):
    """argv: lista de argumentos para el cliente (ej. [BCM025] o [BCM025, --cmd, dir])."""
    from ftp_terminal.client import main as client_main
    if argv is not None:
        sys.argv = [sys.argv[0]] + list(argv)
    client_main()


def run_both(client_args=None):
    """Agente en segundo plano + terminal en primer plano. Al salir de la terminal se detiene el agente.
    client_args: argumentos para el cliente (ej. [BCM025] para conectar a ese dispositivo)."""
    stop = threading.Event()
    agent_thread = threading.Thread(target=run_agent, args=(stop,), daemon=False)
    agent_thread.start()
    try:
        run_client(client_args or [])
    finally:
        stop.set()
        agent_thread.join(timeout=3.0)


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        print()
        print("Comandos:  agent | client [dispositivo] [--cmd 'comando']")
        print("          (sin argumentos: agente + terminal a la vez)")
        sys.exit(0)
    if not args:
        run_both()
        return
    sub = args[0].lower()
    rest = args[1:]
    if sub == "agent":
        run_agent()
    elif sub in ("client", "terminal", "term"):
        run_client(rest)
    elif sub in ("both", "all", "run"):
        run_both()
    else:
        # Primer arg no es comando: todo en uno, primer arg = dispositivo para la terminal
        run_both(args)


if __name__ == "__main__":
    main()
