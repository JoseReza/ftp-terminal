#!/usr/bin/env python3
"""
Backends para FTP-Terminal: FTP (con ruta base) o sistema de archivos local.
La variable FTP_TERMINAL_ROOT apunta a la carpeta que contiene todos los dispositivos:
- Modo FTP: ruta base en el servidor (ej. "devices" → devices/BCM025/in.txt).
- Modo local: directorio en disco (ej. D:\\devices o /mnt/ftp → .../BCM025/in.txt).
"""
import io
import os
import ftplib
from urllib.parse import urlparse


FILE_IN = "in.txt"
FILE_OUT = "out.txt"
FILE_CWD = "cwd.txt"
FILE_STATUS = "status.txt"


class BaseBackend:
    """Interfaz común: leer/escribir in.txt y out.txt para un dispositivo."""

    def read_in(self):
        """Lee el contenido de in.txt. None si no existe o está vacío."""
        raise NotImplementedError

    def write_in(self, content):
        """Escribe (sobrescribe) in.txt."""
        raise NotImplementedError

    def read_out(self):
        """Lee el contenido de out.txt. None si no existe o está vacío."""
        raise NotImplementedError

    def write_out(self, content):
        """Escribe (sobrescribe) out.txt."""
        raise NotImplementedError

    def clear_in(self):
        """Limpia in.txt."""
        self.write_in("")

    def clear_out(self):
        """Limpia out.txt (para evitar leer salidas viejas)."""
        self.write_out("")

    def read_cwd(self):
        """Lee el directorio de trabajo actual del dispositivo (cwd.txt). None si no existe."""
        raise NotImplementedError

    def write_cwd(self, cwd):
        """Escribe el directorio de trabajo actual (para que el cliente lo muestre en el prompt)."""
        raise NotImplementedError

    def read_status(self):
        """Lee status.txt (IDLE, RUNNING, DONE). None si no existe o está vacío."""
        raise NotImplementedError

    def write_status(self, status):
        """Escribe status.txt. status: 'IDLE' | 'RUNNING' | 'DONE'."""
        raise NotImplementedError

    def disconnect(self):
        """Cierra conexión si aplica (FTP). En Local no hace nada."""
        pass


class LocalBackend(BaseBackend):
    """Carpeta local: puede ser un directorio en disco o espejo de un FTP montado."""

    def __init__(self, root_path, device_name):
        self.root_path = os.path.normpath(root_path)
        self.device_name = device_name.strip("/")
        self._device_dir = os.path.join(self.root_path, self.device_name)

    def _ensure_device_dir(self):
        os.makedirs(self._device_dir, exist_ok=True)

    def _path(self, filename):
        return os.path.join(self._device_dir, filename)

    def read_in(self):
        self._ensure_device_dir()
        p = self._path(FILE_IN)
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read().strip()
            return data if data else None
        except OSError:
            return None

    def write_in(self, content):
        self._ensure_device_dir()
        with open(self._path(FILE_IN), "w", encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else content.decode("utf-8"))

    def read_out(self):
        self._ensure_device_dir()
        p = self._path(FILE_OUT)
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            return data if data.strip() else None
        except OSError:
            return None

    def write_out(self, content):
        self._ensure_device_dir()
        s = content if isinstance(content, str) else content.decode("utf-8")
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        with open(self._path(FILE_OUT), "w", encoding="utf-8", newline="\n") as f:
            f.write(s)

    def read_cwd(self):
        self._ensure_device_dir()
        p = self._path(FILE_CWD)
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read().strip() or None
        except OSError:
            return None

    def write_cwd(self, cwd):
        self._ensure_device_dir()
        with open(self._path(FILE_CWD), "w", encoding="utf-8") as f:
            f.write((cwd or "").strip())

    def read_status(self):
        self._ensure_device_dir()
        p = self._path(FILE_STATUS)
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                s = f.read().strip().upper()
            return s if s in ("IDLE", "RUNNING", "DONE") else None
        except OSError:
            return None

    def write_status(self, status):
        self._ensure_device_dir()
        with open(self._path(FILE_STATUS), "w", encoding="utf-8") as f:
            f.write((status or "IDLE").strip().upper())


class FTPBackend(BaseBackend):
    """FTP con ruta base: la carpeta del dispositivo es base_path/device_name."""

    def __init__(self, host, username, password, device_name, base_path="", port=21, use_passive=True):
        self.host = host
        self.username = username
        self.password = password
        self.device_name = device_name.strip("/")
        # Normalizar base: sin barra final, sin barra inicial para cwd
        self.base_path = (base_path or "").strip("/").replace("\\", "/")
        self.port = port
        self.use_passive = use_passive
        self.ftp = None

    def _device_folder(self):
        if self.base_path:
            return f"{self.base_path}/{self.device_name}"
        return self.device_name

    def connect(self):
        self.ftp = ftplib.FTP(timeout=30)
        self.ftp.connect(self.host, self.port)
        self.ftp.login(self.username, self.password)
        self.ftp.set_pasv(self.use_passive)
        self._ensure_device_folder()
        return self

    def _ensure_device_folder(self):
        folder = self._device_folder()
        parts = [p for p in folder.split("/") if p]
        for i in range(len(parts)):
            sub = "/".join(parts[: i + 1])
            try:
                self.ftp.cwd(sub)
            except ftplib.error_perm:
                try:
                    self.ftp.mkd(parts[i])
                except ftplib.error_perm:
                    pass
                try:
                    self.ftp.cwd(sub)
                except ftplib.error_perm:
                    pass
        return self

    def _cwd_device(self):
        self.ftp.cwd(self._device_folder())

    def read_in(self):
        self._cwd_device()
        try:
            bio = io.BytesIO()
            self.ftp.retrbinary(f"RETR {FILE_IN}", bio.write)
            data = bio.getvalue().decode("utf-8", errors="replace").strip()
            return data if data else None
        except ftplib.error_perm as e:
            if "550" in str(e):
                return None
            raise

    def write_in(self, content):
        self._cwd_device()
        raw = content.encode("utf-8") if isinstance(content, str) else content
        self.ftp.storbinary(f"STOR {FILE_IN}", io.BytesIO(raw))

    def read_out(self):
        self._cwd_device()
        try:
            bio = io.BytesIO()
            self.ftp.retrbinary(f"RETR {FILE_OUT}", bio.write)
            data = bio.getvalue().decode("utf-8", errors="replace")
            return data if data.strip() else None
        except ftplib.error_perm as e:
            if "550" in str(e):
                return None
            raise

    def write_out(self, content):
        self._cwd_device()
        raw = (content or "").encode("utf-8")
        self.ftp.storbinary(f"STOR {FILE_OUT}", io.BytesIO(raw))

    def read_cwd(self):
        self._cwd_device()
        try:
            bio = io.BytesIO()
            self.ftp.retrbinary(f"RETR {FILE_CWD}", bio.write)
            return bio.getvalue().decode("utf-8", errors="replace").strip() or None
        except ftplib.error_perm as e:
            if "550" in str(e):
                return None
            raise

    def write_cwd(self, cwd):
        self._cwd_device()
        self.ftp.storbinary(f"STOR {FILE_CWD}", io.BytesIO((cwd or "").strip().encode("utf-8")))

    def read_status(self):
        self._cwd_device()
        try:
            bio = io.BytesIO()
            self.ftp.retrbinary(f"RETR {FILE_STATUS}", bio.write)
            s = bio.getvalue().decode("utf-8", errors="replace").strip().upper()
            return s if s in ("IDLE", "RUNNING", "DONE") else None
        except ftplib.error_perm as e:
            if "550" in str(e):
                return None
            raise

    def write_status(self, status):
        self._cwd_device()
        raw = ((status or "IDLE").strip().upper()).encode("utf-8")
        self.ftp.storbinary(f"STOR {FILE_STATUS}", io.BytesIO(raw))

    def disconnect(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                pass
            self.ftp = None


def _is_local_root(path):
    """True si path parece una ruta local (existe como dir o es absoluta típica)."""
    if not path or not path.strip():
        return False
    path = path.strip()
    if os.path.isabs(path):
        return True
    # Windows: C:\, D:\, etc.
    if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
        return True
    # Ruta relativa que existe como directorio
    return os.path.isdir(path)


def _parse_ftp_root(root):
    """
    Si root es una URL (contiene ://), extrae host, port, user, password, base_path.
    Devuelve dict o None si no es URL. Ej: ftp://user:pass@host:21/devices → modo FTP.
    """
    if not root or "://" not in root:
        return None
    u = urlparse(root)
    if (u.scheme or "").lower() != "ftp":
        return None
    host = (u.hostname or "").strip()
    if not host:
        return None
    port = int(u.port) if u.port else 21
    base_path = (u.path or "").strip("/").replace("\\", "/")
    username = (u.username or "").strip() or os.environ.get("FTP_TERMINAL_USER") or ""
    password = (u.password or "").strip() if u.password is not None else (os.environ.get("FTP_TERMINAL_PASS") or "")
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "base_path": base_path,
    }


def get_backend_from_env(device_name=None):
    """
    Crea el backend desde variables de entorno.
    device_name: opcional; si no se pasa, se usa FTP_TERMINAL_DEVICE.
    """
    device = device_name or os.environ.get("FTP_TERMINAL_DEVICE") or ""
    return backend_from_env(device)


def backend_from_env(device_name):
    """
    Crea el backend según FTP_TERMINAL_ROOT (una sola variable):
    - Si contiene "://" (ej. ftp://user:pass@host:21/devices) → modo FTP, online.
    - Si no (ej. D:/devices o /mnt/devices) → modo local, carpeta en disco.
    Compatible con el formato antiguo: host/user/pass/ftp por separado.
    """
    root = (os.environ.get("FTP_TERMINAL_ROOT") or "").strip()
    device = device_name or os.environ.get("FTP_TERMINAL_DEVICE") or ""
    if not device:
        raise ValueError("Se necesita nombre de dispositivo (FTP_TERMINAL_DEVICE o argumento).")

    # Una sola URL/dirección: "://" → FTP, si no → local
    parsed = _parse_ftp_root(root)
    if parsed:
        backend = FTPBackend(
            parsed["host"],
            parsed["username"],
            parsed["password"],
            device,
            base_path=parsed["base_path"] or "",
            port=parsed["port"],
        )
        backend.connect()
        return backend

    # Formato antiguo: host + root por separado
    use_local = (os.environ.get("FTP_TERMINAL_USE_LOCAL") or "").strip().lower() in ("1", "true", "yes", "on")
    ftp_val = (os.environ.get("FTP_TERMINAL_FTP") or "true").strip().lower()
    ftp_enabled = ftp_val not in ("0", "false", "no", "off")
    host = os.environ.get("FTP_TERMINAL_HOST")
    if host and ftp_enabled and not use_local:
        user = os.environ.get("FTP_TERMINAL_USER") or ""
        password = os.environ.get("FTP_TERMINAL_PASS") or ""
        port = int(os.environ.get("FTP_TERMINAL_PORT", "21"))
        backend = FTPBackend(host, user, password, device, base_path=root or "", port=port)
        backend.connect()
        return backend

    # Modo local: root = ruta en disco
    if not root:
        raise ValueError(
            "Definir FTP_TERMINAL_ROOT: ruta local (D:/devices) o URL FTP (ftp://user:pass@host/devices)."
        )
    if not _is_local_root(root) and not os.path.isabs(root):
        expanded = os.path.abspath(root)
        if os.path.isdir(expanded):
            root = expanded
    return LocalBackend(root, device)
