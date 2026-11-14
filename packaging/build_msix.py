"""Builds the PhoneDrop MSIX for the Microsoft Store.

    build\\venv\\Scripts\\python packaging\\build_msix.py                 dev build (local test identity)
    build\\venv\\Scripts\\python packaging\\build_msix.py --store store.json   Store build

store.json (values from Partner Center → your app → Product identity):
    {"identity_name": "12345YourName.PhoneDrop",
     "publisher": "CN=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
     "publisher_display": "Your Name",
     "version": "1.0.0.0"}

The package bundles a private copy of the installed (python.org, PSF-signed) Python plus
the libraries from build\\venv, so it needs no Python on the user's PC. Output:
    %USERPROFILE%\\PhoneDrop-build\\layout\\   loose files (Add-AppxPackage -Register for testing)
    build\\PhoneDrop.msix  the file you upload to Partner Center (the Store signs it)
"""
import argparse
import compileall
import glob
import json
import os
import shutil
import subprocess
import sys
import sysconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
BUILD = os.path.join(ROOT, "build")
# Built outside OneDrive (syncing locks thousands of small files mid-build) and outside AppData
# (sandboxed/packaged tools get AppData redirected, which Windows' installer can't see).
LAYOUT = os.path.join(os.path.expanduser("~"), "PhoneDrop-build", "layout")
VENV_SITE = os.path.join(BUILD, "venv", "Lib", "site-packages")
sys.path.insert(0, SRC)

APP_FILES = ["main.py", "core.py", "server.py", "wininteg.py", "storeapi.py", "icon.py", "phone.html", "app.ico"]

STDLIB_SKIP = {"test", "idlelib", "turtledemo", "ensurepip", "venv", "site-packages", "__pycache__",
               "pydoc_data", "lib2to3", "tkinter/test", "unittest/test"}
SITE_SKIP = ("pip", "setuptools", "_distutils_hack", "distutils-precedence.pth", "__pycache__")


def find_makeappx():
    hits = glob.glob(os.path.join(BUILD, "tools", "sdk", "bin", "*", "x64", "makeappx.exe"))
    if not hits:
        sys.exit("makeappx.exe not found under build\\tools - download Microsoft.Windows.SDK.BuildTools first.")
    return sorted(hits)[-1]


def copy_python(dest):
    base = sys.base_prefix  # the real python.org install behind build\venv
    os.makedirs(dest)
    for f in ("python.exe", "pythonw.exe", "python3.dll", f"python{sys.version_info.major}{sys.version_info.minor}.dll",
              "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        if os.path.exists(os.path.join(base, f)):
            shutil.copy2(os.path.join(base, f), dest)
    shutil.copytree(os.path.join(base, "DLLs"), os.path.join(dest, "DLLs"))
    shutil.copytree(os.path.join(base, "tcl"), os.path.join(dest, "tcl"),
                    ignore=shutil.ignore_patterns("demos", "*.lib", "__pycache__"))

    lib_src = os.path.join(base, "Lib")

    def ignore_stdlib(d, names):
        rel = os.path.relpath(d, lib_src).replace("\\", "/")
        return [n for n in names if n in STDLIB_SKIP or f"{rel}/{n}".lstrip("./") in STDLIB_SKIP]

    shutil.copytree(lib_src, os.path.join(dest, "Lib"), ignore=ignore_stdlib)

    site = os.path.join(dest, "Lib", "site-packages")
    os.makedirs(site)
    for name in os.listdir(VENV_SITE):
        if name.startswith(SITE_SKIP):
            continue
        s = os.path.join(VENV_SITE, name)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(site, name), ignore=shutil.ignore_patterns("tests", "__pycache__"))
        else:
            shutil.copy2(s, os.path.join(site, name))

    # A ._pth file makes this Python fully self-contained: it ignores the PC's own Python,
    # PYTHONPATH and registry settings, and finds our app folder.
    ver = f"{sys.version_info.major}{sys.version_info.minor}"
    with open(os.path.join(dest, f"python{ver}._pth"), "w") as f:
        f.write("Lib\nDLLs\nLib\\site-packages\n..\\app\nimport site\n")


def make_assets(dest):
    from PIL import Image
    from icon import make_icon
    os.makedirs(dest)
    for name, size in (("Square44x44Logo", 44), ("Square150x150Logo", 150), ("StoreLogo", 50)):
        make_icon(size * 2).resize((size, size), Image.LANCZOS).save(os.path.join(dest, name + ".png"))
    wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
    ic = make_icon(120)
    wide.paste(ic, ((310 - 120) // 2, 15), ic)
    wide.save(os.path.join(dest, "Wide310x150Logo.png"))


def write_manifest(cfg):
    with open(os.path.join(ROOT, "packaging", "AppxManifest.xml"), encoding="utf-8") as f:
        xml = f.read()
    for key, val in (("IDENTITY_NAME", cfg["identity_name"]), ("PUBLISHER", cfg["publisher"]),
                     ("PUBLISHER_DISPLAY", cfg["publisher_display"]), ("VERSION", cfg["version"]),
                     ("DISPLAY_NAME", cfg["display_name"])):
        xml = xml.replace("{{" + key + "}}", val)
    assert "{{" not in xml, "unfilled placeholder in manifest"
    with open(os.path.join(LAYOUT, "AppxManifest.xml"), "w", encoding="utf-8") as f:
        f.write(xml)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", help="JSON file with Partner Center identity values")
    ap.add_argument("--no-pack", action="store_true", help="only build the loose layout")
    args = ap.parse_args()

    cfg = {"identity_name": "PhoneDrop.Dev", "publisher": "CN=PhoneDropDev",
           "publisher_display": "PhoneDrop (dev build)", "display_name": "PhoneDrop", "version": "1.0.0.0"}
    if args.store:
        with open(args.store, encoding="utf-8") as f:
            cfg.update(json.load(f))

    if os.path.exists(LAYOUT):
        shutil.rmtree(LAYOUT)
    os.makedirs(LAYOUT)
    print("Copying Python runtime…")
    copy_python(os.path.join(LAYOUT, "python"))
    print("Copying app…")
    os.makedirs(os.path.join(LAYOUT, "app"))
    for f in APP_FILES:
        shutil.copy2(os.path.join(SRC, f), os.path.join(LAYOUT, "app", f))
    make_assets(os.path.join(LAYOUT, "Assets"))
    write_manifest(cfg)

    # The install folder is read-only, so ship pre-compiled bytecode (hash-based: never re-checked).
    print("Pre-compiling…")
    compileall.compile_dir(LAYOUT, quiet=1, workers=0,
                           invalidation_mode=compileall.py_compile.PycInvalidationMode.UNCHECKED_HASH)

    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(LAYOUT) for f in fs)
    print(f"Layout ready: {LAYOUT} ({size / 1e6:.0f} MB)")

    if not args.no_pack:
        out = os.path.join(BUILD, "PhoneDrop.msix")
        subprocess.run([find_makeappx(), "pack", "/d", LAYOUT, "/p", out, "/o"], check=True,
                       stdout=subprocess.DEVNULL)
        print(f"Package: {out} ({os.path.getsize(out) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
