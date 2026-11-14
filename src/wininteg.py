"""Windows integration: Explorer right-click menu, Send To, startup, self-install.

Everything is per-user (HKEY_CURRENT_USER / %APPDATA%), so no admin rights are needed.
"""
import os
import shutil
import subprocess
import sys
import winreg

from core import APP_ID, APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MENU_KEYS = [r"Software\Classes\*\shell\SendToiPhone", r"Software\Classes\Directory\shell\SendToiPhone"]
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", APP_ID)
START_MENU = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
SENDTO = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\SendTo")
NO_WINDOW = 0x08000000


def frozen():
    return getattr(sys, "frozen", False)


def launch_parts():
    """[executable, *prefix_args] that relaunch this app."""
    if frozen():
        return [sys.executable]
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return [pyw if os.path.exists(pyw) else sys.executable, os.path.abspath(sys.argv[0])]


def icon_path():
    if frozen():
        return sys.executable
    ico = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "app.ico")
    return ico if os.path.exists(ico) else launch_parts()[0]


# ---- Explorer right-click menu ------------------------------------------
def set_explorer_menu(enabled):
    for key in MENU_KEYS:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Send to iPhone")
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon_path())
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
                cmd = subprocess.list2cmdline(launch_parts() + ["--send"]) + ' "%1"'
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        else:
            for sub in (key + r"\command", key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except OSError:
                    pass
    # "Send to" submenu entry: handles multi-select in a single launch.
    lnk = os.path.join(SENDTO, "iPhone (Send to iPhone).lnk")
    if enabled:
        make_shortcut(lnk, ["--send"])
    else:
        try:
            os.remove(lnk)
        except OSError:
            pass


# ---- Start with Windows -------------------------------------------------
def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, subprocess.list2cmdline(launch_parts() + ["--tray"]))
        else:
            try:
                winreg.DeleteValue(k, APP_ID)
            except OSError:
                pass


# ---- shortcuts ----------------------------------------------------------
def make_shortcut(lnk_path, extra_args=()):
    parts = launch_parts()
    target, args = parts[0], subprocess.list2cmdline(parts[1:] + list(extra_args))

    def ps(s):
        return "'" + s.replace("'", "''") + "'"

    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + ps(lnk_path) + ");"
        "$s.TargetPath=" + ps(target) + ";$s.Arguments=" + ps(args) + ";"
        "$s.IconLocation=" + ps(icon_path() + ",0") + ";$s.WorkingDirectory=" + ps(os.path.dirname(parts[-1])) + ";$s.Description=" + ps(APP_NAME) + ";$s.Save()"
    )
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   creationflags=NO_WINDOW, check=False, timeout=30)


# ---- self-install -------------------------------------------------------
def needs_install():
    if not frozen():
        return False
    return os.path.normcase(os.path.dirname(sys.executable)) != os.path.normcase(INSTALL_DIR)


def install_and_relaunch(argv):
    """Copy the .exe to %LOCALAPPDATA%\\Programs\\SendToiPhone, add a Start Menu entry, relaunch."""
    os.makedirs(INSTALL_DIR, exist_ok=True)
    dest = os.path.join(INSTALL_DIR, "SendToiPhone.exe")
    try:
        shutil.copy2(sys.executable, dest)
    except OSError:
        return False  # installed copy is running/locked — just run from here
    subprocess.Popen([dest] + argv, creationflags=NO_WINDOW, close_fds=True)
    return True


def create_start_menu_entry():
    make_shortcut(os.path.join(START_MENU, f"{APP_NAME}.lnk"))


def desktop_dir():
    """The real Desktop folder (OneDrive can relocate it)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            return os.path.expandvars(winreg.QueryValueEx(k, "Desktop")[0])
    except OSError:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def create_desktop_shortcut():
    make_shortcut(os.path.join(desktop_dir(), f"{APP_NAME}.lnk"))


def uninstall():
    set_explorer_menu(False)
    set_startup(False)
    for lnk in (os.path.join(START_MENU, f"{APP_NAME}.lnk"), os.path.join(desktop_dir(), f"{APP_NAME}.lnk")):
        try:
            os.remove(lnk)
        except OSError:
            pass
