"""Installs (or updates / uninstalls) Send to iPhone for the current Windows user.

    python install.py              install or update, then start the app
    python install.py --uninstall  remove everything (your received files are kept)

Installs to %LOCALAPPDATA%\\Programs\\SendToiPhone and runs on Python's signed
pythonw.exe, so it works with Smart App Control turned on. No admin rights needed.
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
DEST = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "SendToiPhone")
APP = os.path.join(DEST, "app")
VENV = os.path.join(DEST, "venv")
PY = os.path.join(VENV, "Scripts", "python.exe")
PYW = os.path.join(VENV, "Scripts", "pythonw.exe")
FILES = ["main.py", "core.py", "server.py", "wininteg.py", "icon.py", "phone.html", "app.ico"]
DEPS = ["pystray==0.19.5", "pillow==13.0.0", "qrcode==8.2", "tkinterdnd2==0.7.0"]
NO_WINDOW = 0x08000000


def stop_running_copy():
    for port in (8765,):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/local/quit", data=b"",
                                         headers={"X-STP-Local": "1"}, method="POST")
            urllib.request.urlopen(req, timeout=2).read()
            print("Stopped the running copy.")
            time.sleep(2)
        except OSError:
            pass


def install():
    print(f"Installing to {DEST}")
    stop_running_copy()
    os.makedirs(APP, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(APP, f))
    if not os.path.exists(PY):
        base = getattr(sys, "_base_executable", sys.executable)
        print("Creating private Python environment…")
        subprocess.run([base, "-m", "venv", VENV], check=True)
    print("Installing libraries…")
    subprocess.run([PY, "-m", "pip", "install", "-q", "--disable-pip-version-check"] + DEPS, check=True)

    # Start Menu shortcut (the app itself sets up the right-click menu and startup entry on launch).
    code = ("import sys; sys.argv=[r'%s']; sys.path.insert(0, r'%s'); import wininteg; "
            "wininteg.launch_parts=lambda: [r'%s', r'%s']; wininteg.create_start_menu_entry(); "
            "wininteg.create_desktop_shortcut()"
            % (os.path.join(APP, "main.py"), APP, PYW, os.path.join(APP, "main.py")))
    subprocess.run([PY, "-c", code], check=True)

    subprocess.Popen([PYW, os.path.join(APP, "main.py")], cwd=APP, creationflags=NO_WINDOW, close_fds=True)
    print("\nDone! Send to iPhone is running — look for the blue phone icon in the system tray.")
    print("If Windows Firewall asks about Python, tick 'Private networks' and click Allow.")


def uninstall():
    stop_running_copy()
    if os.path.exists(PY):
        subprocess.run([PY, os.path.join(APP, "main.py"), "--uninstall"], cwd=APP)
    shutil.rmtree(DEST, ignore_errors=True)
    shutil.rmtree(os.path.join(os.environ["APPDATA"], "SendToiPhone"), ignore_errors=True)
    print("Uninstalled. Files you received are still in Downloads\\From iPhone.")


if __name__ == "__main__":
    uninstall() if "--uninstall" in sys.argv else install()
