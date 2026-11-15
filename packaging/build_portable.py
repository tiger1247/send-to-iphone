"""Builds the direct-download PhoneDrop zip (for Gumroad / Lemon Squeezy).

    build\\venv\\Scripts\\python packaging\\build_portable.py

Output: build\\PhoneDrop-Windows.zip containing
    Install PhoneDrop.cmd     copies the app to %LOCALAPPDATA%\\Programs\\PhoneDrop and starts it
    Uninstall PhoneDrop.cmd   removes shortcuts, right-click menu, startup entry and the program folder
    READ ME FIRST.txt
    PhoneDrop\\               self-contained app (bundled python.org Python, PSF-signed pythonw.exe)
"""
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_msix as bm  # reuse the self-contained Python bundling

ROOT = bm.ROOT
STAGE = os.path.join(os.path.expanduser("~"), "PhoneDrop-portable")
OUT = os.path.join(ROOT, "build", "PhoneDrop-Windows.zip")
VERSION = "1.0.0"

INSTALL_CMD = r"""@echo off
setlocal
title Install PhoneDrop
set "DEST=%LOCALAPPDATA%\Programs\PhoneDrop"
echo.
echo  Installing PhoneDrop to %DEST% ...
powershell -NoProfile -Command "try { Invoke-RestMethod -Method Post http://127.0.0.1:8765/local/quit -Headers @{'X-STP-Local'='1'} -TimeoutSec 2 | Out-Null; Start-Sleep 2 } catch {}" >nul 2>&1
robocopy "%~dp0PhoneDrop" "%DEST%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo  Copy failed. Close PhoneDrop from the tray and run this again.
  pause
  exit /b 1
)
start "" "%DEST%\python\pythonw.exe" "%DEST%\app\main.py"
echo.
echo  Done! PhoneDrop is starting. Scan the QR code with your iPhone camera.
echo  If Windows Firewall asks, tick "Private networks" and click Allow.
echo.
timeout /t 8 >nul
"""

UNINSTALL_CMD = r"""@echo off
setlocal
title Uninstall PhoneDrop
set "DEST=%LOCALAPPDATA%\Programs\PhoneDrop"
powershell -NoProfile -Command "try { Invoke-RestMethod -Method Post http://127.0.0.1:8765/local/quit -Headers @{'X-STP-Local'='1'} -TimeoutSec 2 | Out-Null; Start-Sleep 2 } catch {}" >nul 2>&1
if exist "%DEST%\python\python.exe" "%DEST%\python\python.exe" "%DEST%\app\main.py" --uninstall --quiet
rd /s /q "%DEST%" 2>nul
rd /s /q "%APPDATA%\PhoneDrop" 2>nul
echo PhoneDrop has been removed. Files you received are still in Downloads\From iPhone.
timeout /t 6 >nul
"""

README = f"""PhoneDrop {VERSION} for Windows 10/11
=====================================

Send photos, videos and files between your PC and iPhone over Wi-Fi.
Nothing to install on the iPhone.

INSTALL
1. Right-click the zip > Extract All... (don't run it from inside the zip).
2. Double-click "Install PhoneDrop.cmd".
   If Windows says "Windows protected your PC", click "More info" > "Run anyway".
   (PhoneDrop is a small indie app that isn't code-signed yet.)
3. Scan the QR code with your iPhone camera and tap the link.
   In Safari: Share > Add to Home Screen, so it opens like an app.
4. If Windows Firewall asks about Python, tick "Private networks" and click Allow.

PhoneDrop starts with Windows and lives in the tray. Desktop and Start-menu
shortcuts are created on first start.

SMART APP CONTROL
If your PC has Smart App Control turned on, Windows may block this download.
In that case get PhoneDrop from the Microsoft Store instead - search "PhoneDrop".

UNINSTALL
Double-click "Uninstall PhoneDrop.cmd". Files you received stay in
Downloads\\From iPhone.

Privacy: files go directly over your own Wi-Fi; nothing is sent to the internet.
Support: https://github.com/tiger1247/send-to-iphone/issues
"""


def clear(path):
    """rmtree that survives antivirus briefly locking freshly written files."""
    import time
    for attempt in range(5):
        if not os.path.exists(path):
            return
        try:
            shutil.rmtree(path)
        except OSError:
            time.sleep(2)
    os.rename(path, f"{path}-old-{int(time.time())}")  # last resort: move it out of the way


def main():
    clear(STAGE)
    app_root = os.path.join(STAGE, "PhoneDrop")
    os.makedirs(app_root)
    print("Bundling Python runtime…")
    bm.copy_python(os.path.join(app_root, "python"))
    os.makedirs(os.path.join(app_root, "app"))
    for f in bm.APP_FILES:
        shutil.copy2(os.path.join(bm.SRC, f), os.path.join(app_root, "app", f))
    with open(os.path.join(app_root, "app", "DIRECT_EDITION"), "w") as fh:
        fh.write(VERSION)
    import compileall
    compileall.compile_dir(app_root, quiet=1, workers=0)
    for name, text in (("Install PhoneDrop.cmd", INSTALL_CMD), ("Uninstall PhoneDrop.cmd", UNINSTALL_CMD),
                       ("READ ME FIRST.txt", README)):
        with open(os.path.join(STAGE, name), "w", encoding="ascii", newline="\r\n") as fh:
            fh.write(text.replace("\r\n", "\n"))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _, files in os.walk(STAGE):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, STAGE))
    print(f"Wrote {OUT} ({os.path.getsize(OUT) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
