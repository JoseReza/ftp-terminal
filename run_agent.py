#!/usr/bin/env python3
r"""Atajo para el agente. Equivalente a:  python main.py agent"""
import sys
import os

try:
    from ftp_terminal.config_loader import load_config
    load_config()
except Exception:
    pass

# Redirigir a main.py agent
if __name__ == "__main__":
    sys.argv = [sys.argv[0], "agent"]
    from main import main
    main()
