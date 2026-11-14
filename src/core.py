"""Shared state, settings and helpers for Send to iPhone."""
import json
import os
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import zipfile

APP_NAME = "Send to iPhone"
APP_ID = "SendToiPhone"
DEFAULT_PORT = 8765

APPDATA_DIR = os.environ.get("STP_DATA_DIR") or os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_ID)
CONFIG_PATH = os.path.join(APPDATA_DIR, "config.json")
TEMP_DIR = os.path.join(tempfile.gettempdir(), APP_ID)


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def default_inbox():
    return os.path.join(os.path.expanduser("~"), "Downloads", "From iPhone")


def local_ip():
    """Best guess at this PC's LAN address (no packets are actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def safe_filename(name):
    name = os.path.basename(name.replace("\\", "/")).strip()
    bad = '<>:"/\\|?*' + "".join(chr(i) for i in range(32))
    name = "".join("_" if c in bad else c for c in name).strip(" .")
    return name or f"file-{int(time.time())}"


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    path = os.path.join(folder, name)
    i = 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return path


class Store:
    """Thread-safe app state: settings, files shared to the phone, clipboard."""

    def __init__(self):
        os.makedirs(APPDATA_DIR, exist_ok=True)
        os.makedirs(TEMP_DIR, exist_ok=True)
        self.lock = threading.RLock()
        self.version = 0
        self.listeners = []
        self.clip = {"text": "", "ts": 0}
        self.last_phone_seen = 0.0
        cfg = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            pass
        self.token = cfg.get("token") or secrets.token_urlsafe(18)
        self.port = int(cfg.get("port") or DEFAULT_PORT)
        self.inbox = cfg.get("inbox") or default_inbox()
        self.explorer_menu = cfg.get("explorer_menu", True)
        self.startup = cfg.get("startup", True)
        self.first_run = not cfg
        self.files = [f for f in cfg.get("files", []) if os.path.isfile(f.get("path", ""))]
        self.save()

    # ---- persistence -------------------------------------------------
    def save(self):
        with self.lock:
            data = {
                "token": self.token, "port": self.port, "inbox": self.inbox,
                "explorer_menu": self.explorer_menu, "startup": self.startup,
                "files": self.files,
            }
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, CONFIG_PATH)

    def changed(self, event="state", payload=None):
        with self.lock:
            self.version += 1
        self.save()
        for cb in list(self.listeners):
            try:
                cb(event, payload)
            except Exception:
                pass

    # ---- shared files ------------------------------------------------
    def add_paths(self, paths):
        """Share files/folders with the phone. Folders are zipped in the background."""
        added = []
        for p in paths:
            p = os.path.abspath(p.strip('"'))
            if os.path.isdir(p):
                threading.Thread(target=self._add_folder, args=(p,), daemon=True).start()
            elif os.path.isfile(p):
                added.append(self._add_file(p, temp=False, notify=False))
        if added:
            self.changed("added", added)
        return added

    def _add_file(self, path, temp, notify=True, name=None):
        entry = {
            "id": uuid.uuid4().hex[:12],
            "name": name or os.path.basename(path),
            "path": path,
            "size": os.path.getsize(path),
            "added": time.time(),
            "temp": temp,
        }
        with self.lock:
            # Re-sharing the same file moves it to the top instead of duplicating.
            self.files = [f for f in self.files if f["path"] != path]
            self.files.insert(0, entry)
        if notify:
            self.changed("added", [entry])
        return entry

    def _add_folder(self, folder):
        name = os.path.basename(folder.rstrip("\\/")) or "folder"
        self.changed("zipping", name)
        out = unique_path(TEMP_DIR, name + ".zip")
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
                for root, _dirs, fnames in os.walk(folder):
                    for fn in fnames:
                        full = os.path.join(root, fn)
                        try:
                            z.write(full, os.path.relpath(full, os.path.dirname(folder)))
                        except OSError:
                            pass
            self._add_file(out, temp=True, name=name + ".zip")
        except OSError as e:
            self.changed("error", f"Couldn't zip {name}: {e}")

    def get_file(self, fid):
        with self.lock:
            for f in self.files:
                if f["id"] == fid:
                    return dict(f)
        return None

    def remove(self, fid):
        with self.lock:
            gone = [f for f in self.files if f["id"] == fid]
            self.files = [f for f in self.files if f["id"] != fid]
        for f in gone:
            if f.get("temp"):
                try:
                    os.remove(f["path"])
                except OSError:
                    pass
        if gone:
            self.changed()

    def clear(self):
        with self.lock:
            ids = [f["id"] for f in self.files]
        for fid in ids:
            self.remove(fid)

    def snapshot(self):
        with self.lock:
            files = [f for f in self.files if os.path.isfile(f["path"])]
            return {
                "v": self.version,
                "files": [{k: f[k] for k in ("id", "name", "size", "added")} for f in files],
                "clip": dict(self.clip),
                "pc": socket.gethostname(),
            }

    # ---- clipboard / misc ---------------------------------------------
    def set_clip_for_phone(self, text):
        with self.lock:
            self.clip = {"text": text, "ts": time.time()}
        self.changed("clip_to_phone", text)

    def rotate_token(self):
        with self.lock:
            self.token = secrets.token_urlsafe(18)
        self.changed("token")

    def url(self):
        return f"http://{local_ip()}:{self.port}/?t={self.token}"

    def phone_connected(self):
        return time.time() - self.last_phone_seen < 8


def cleanup_temp():
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
