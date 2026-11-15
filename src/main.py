"""Send to iPhone — tray app that moves files between this PC and an iPhone over Wi-Fi.

Usage:
  SendToiPhone.exe                 open the window (starting the app if needed)
  SendToiPhone.exe --tray          start hidden in the tray (used at Windows startup)
  SendToiPhone.exe --send <paths>  share files/folders with the phone (Explorer menu)
  SendToiPhone.exe --uninstall     remove the right-click menu, startup entry and shortcut
"""
import ctypes
import json
import os
import queue
import sys
import threading
import time
import urllib.request

import core
import wininteg
from core import APP_NAME, Store, human_size


# ---------------------------------------------------------------- single instance
def configured_port():
    try:
        with open(core.CONFIG_PATH, "r", encoding="utf-8") as f:
            return int(json.load(f).get("port") or core.DEFAULT_PORT)
    except (OSError, ValueError):
        return core.DEFAULT_PORT


def forward_to_running(paths, show, text=""):
    """If a copy is already running, hand it our work and return True."""
    base = f"http://127.0.0.1:{configured_port()}"
    try:
        with urllib.request.urlopen(base + "/local/ping", timeout=0.6) as r:
            if r.read() != b"send-to-iphone-ok":
                return False
        req = urllib.request.Request(
            base + "/local/add", data=json.dumps({"paths": paths, "show": show, "text": text}).encode(),
            headers={"X-STP-Local": "1", "Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
        return True
    except OSError:
        return False


def parse_args(argv):
    # The Store package starts us as "pythonw -m main ..."; drop those bits if they show up.
    argv = [a for a in argv if a not in ("-m", "main", "-E", "-s")]
    paths = [a for a in argv if not a.startswith("--")]
    return paths, ("--tray" in argv), ("--send" in argv)


# ---------------------------------------------------------------- the app
class App:
    def __init__(self, store, show_window):
        import pystray
        import qrcode
        from PIL import ImageTk
        from tkinter import ttk
        import tkinter as tk
        from tkinterdnd2 import DND_FILES, TkinterDnD
        from icon import make_icon

        self.tk, self.ttk, self.ImageTk, self.qrcode, self.pystray = tk, ttk, ImageTk, qrcode, pystray
        self.store = store
        self.q = queue.Queue()
        self.last_url = None
        self.was_connected = False

        self.root = TkinterDnD.Tk()
        self.root.title(APP_NAME)
        self.scale = self.root.winfo_fpixels("1i") / 96.0
        self.icon_img = make_icon(64)
        self.icon_img_on = make_icon(64, badge=True)
        self._tk_icon = ImageTk.PhotoImage(make_icon(32))
        self.root.iconphoto(True, self._tk_icon)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.minsize(int(700 * self.scale), int(440 * self.scale))
        self._build_ui(DND_FILES)

        import storeapi
        self.storeapi = storeapi
        self.lic = storeapi.LicenseWatcher(store, lambda l: self.call(self.on_license, l))

        self.tray = pystray.Icon(core.APP_ID, self.icon_img, APP_NAME, menu=self._tray_menu())
        self.tray.run_detached()

        def first_checks():
            self.lic.refresh(force=True)
            if core.PACKAGED:
                self.store.startup = storeapi.startup_enabled()
                self.tray.update_menu()
        threading.Thread(target=first_checks, daemon=True).start()

        store.listeners.append(lambda ev, p: self.call(self.on_store_event, ev, p))
        self.root.after(100, self._pump)
        self.root.after(500, self._tick)
        self.refresh()
        if show_window:
            self.show()
        else:
            self.root.withdraw()

    # ---- thread hand-off -------------------------------------------------
    def call(self, fn, *args):
        self.q.put((fn, args))

    def _pump(self):
        try:
            while True:
                fn, args = self.q.get_nowait()
                try:
                    fn(*args)
                except Exception as e:  # keep the UI alive no matter what
                    print("ui error:", e, file=sys.stderr)
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _tick(self):
        connected = self.store.phone_connected()
        if connected != self.was_connected:
            self.was_connected = connected
            self.tray.icon = self.icon_img_on if connected else self.icon_img
            self.tray.title = f"{APP_NAME} — {'iPhone connected' if connected else 'waiting for iPhone'}"
        self._update_status()
        if self.root.state() != "withdrawn":
            self._update_qr()
        threading.Thread(target=self.lic.refresh, daemon=True).start()  # cheap: rate-limited inside
        self.root.after(2000, self._tick)

    def on_license(self, lic):
        if lic.state == "full":
            self.banner.pack_forget()
        else:
            if lic.state == "trial":
                d = lic.days_left
                text = f"Free trial: {d} day{'s' if d != 1 else ''} left." if d else "Free trial: last day."
                self.banner.configure(bg="#eef5ff"); self.banner_label.configure(bg="#eef5ff", fg="#0a3d8f")
            else:
                text = "Your free trial has ended. Buy PhoneDrop to keep sending files."
                self.banner.configure(bg="#fff4e5"); self.banner_label.configure(bg="#fff4e5", fg="#7a4b00")
                self.show()
            self.banner_label.configure(text=text)
            self.banner.pack(side="top", fill="x", before=self.outer)
        self.tray.update_menu()
        self.refresh()

    # ---- UI ----------------------------------------------------------------
    def _build_ui(self, DND_FILES):
        tk, ttk, S = self.tk, self.ttk, self.scale
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        font = ("Segoe UI", 10)
        style.configure(".", font=font)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 13))
        style.configure("Muted.TLabel", foreground="#6e6e73")
        style.configure("Ok.TLabel", foreground="#1f8a3b", font=("Segoe UI Semibold", 10))
        style.configure("Wait.TLabel", foreground="#b25000", font=("Segoe UI Semibold", 10))
        style.configure("Treeview", rowheight=int(26 * S))

        # Trial / purchase banner (hidden unless the Store build is on a trial).
        self.banner = tk.Frame(self.root, bg="#eef5ff", padx=int(16 * S), pady=int(8 * S))
        self.banner_label = tk.Label(self.banner, text="", bg="#eef5ff", font=("Segoe UI Semibold", 10))
        self.banner_label.pack(side="left")
        ttk.Button(self.banner, text="Buy PhoneDrop", command=lambda: self.storeapi.open_store_page()).pack(side="right")

        outer = ttk.Frame(self.root, padding=int(16 * S))
        outer.pack(fill="both", expand=True)
        self.outer = outer
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # left: pairing
        left = ttk.Frame(outer)
        left.grid(row=0, column=0, sticky="ns", padx=(0, int(18 * S)))
        ttk.Label(left, text="Scan with your iPhone camera", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Then tap the link. Bookmark it or use\nShare → Add to Home Screen to keep it.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(2, 8))
        self.qr_label = tk.Label(left, bg="white", bd=0)
        self.qr_label.pack(anchor="w")
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(left, textvariable=self.url_var, state="readonly", width=34)
        url_entry.pack(anchor="w", fill="x", pady=(8, 4))
        row = ttk.Frame(left)
        row.pack(anchor="w", fill="x")
        ttk.Button(row, text="Copy link", command=self.copy_link).pack(side="left")
        ttk.Button(row, text="New link", command=self.new_link).pack(side="left", padx=6)
        self.status = ttk.Label(left, text="", style="Wait.TLabel")
        self.status.pack(anchor="w", pady=(12, 0))
        ttk.Label(left, text="PC and iPhone must be on the same Wi-Fi.", style="Muted.TLabel").pack(anchor="w")

        # right: sending
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        ttk.Label(right, text="Send to iPhone", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        drop = tk.Canvas(right, height=int(96 * S), bg="#eef5ff", highlightthickness=0, cursor="hand2")
        drop.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        self.drop = drop

        def draw_drop(_e=None, hot=False):
            drop.delete("all")
            w, h = drop.winfo_width(), drop.winfo_height()
            drop.configure(bg="#d6e8ff" if hot else "#eef5ff")
            drop.create_rectangle(4, 4, w - 4, h - 4, outline="#0a84ff", dash=(6, 4), width=2)
            drop.create_text(w / 2, h / 2 - 9 * S, text="Drop files or folders here",
                             font=("Segoe UI Semibold", 12), fill="#0a5bd8")
            drop.create_text(w / 2, h / 2 + 13 * S, text="or click to choose files", font=("Segoe UI", 9), fill="#4a6fa5")

        self._draw_drop = draw_drop
        drop.bind("<Configure>", draw_drop)
        drop.bind("<Button-1>", lambda e: self.add_files())
        drop.drop_target_register(DND_FILES)
        drop.dnd_bind("<<DropEnter>>", lambda e: (draw_drop(hot=True), e.action)[1])
        drop.dnd_bind("<<DropLeave>>", lambda e: (draw_drop(), e.action)[1])
        drop.dnd_bind("<<Drop>>", self.on_drop)
        # The whole window accepts drops too.
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.on_drop)

        tree_frame = ttk.Frame(right)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=("size", "added"), show="headings", selectmode="extended")
        self.tree.heading("#0", text="")
        self.tree["columns"] = ("name", "size", "added")
        for col, text, w, anchor in (("name", "Shared with iPhone", 260, "w"), ("size", "Size", 80, "e"),
                                     ("added", "Added", 80, "e")):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=int(w * S), anchor=anchor, stretch=(col == "name"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

        btns = ttk.Frame(right)
        btns.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="Add files…", command=self.add_files).pack(side="left")
        ttk.Button(btns, text="Add folder…", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(btns, text="Remove", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="Clear all", command=self.store.clear).pack(side="left", padx=6)

        bottom = ttk.Frame(right)
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(bottom, text="Send PC clipboard to iPhone", command=self.send_clipboard).pack(side="left")
        ttk.Button(bottom, text="Open received files", command=self.open_inbox).pack(side="right")
        self.note = ttk.Label(right, text="", style="Muted.TLabel")
        self.note.grid(row=5, column=0, sticky="w", pady=(6, 0))

    def _tray_menu(self):
        Item, Menu = self.pystray.MenuItem, self.pystray.Menu
        return Menu(
            Item("Open Send to iPhone", lambda: self.call(self.show), default=True),
            Item("Send clipboard text to iPhone", lambda: self.call(self.send_clipboard)),
            Item("Open received files", lambda: self.call(self.open_inbox)),
            Menu.SEPARATOR,
            Item("Buy PhoneDrop…", lambda: self.storeapi.open_store_page(),
                 visible=lambda i: self.lic.license.state != "full"),
            Item("Start with Windows", lambda: self.call(self.toggle_startup), checked=lambda i: self.store.startup),
            Item("Show in right-click menu", lambda: self.call(self.toggle_menu),
                 checked=lambda i: self.store.explorer_menu, visible=not core.PACKAGED),
            Menu.SEPARATOR,
            Item("Quit", lambda: self.call(self.quit)),
        )

    # ---- refresh -----------------------------------------------------------
    def _update_qr(self):
        url = self.store.url()
        if url == self.last_url:
            return
        self.last_url = url
        self.url_var.set(url)
        qr = self.qrcode.QRCode(border=2, box_size=10)
        qr.add_data(url)
        qr.make(fit=True)
        size = int(230 * self.scale)
        img = qr.make_image(fill_color="black", back_color="white").get_image().convert("RGB")
        from PIL import Image
        self._qr_photo = self.ImageTk.PhotoImage(img.resize((size, size), Image.NEAREST))
        self.qr_label.configure(image=self._qr_photo)

    def _update_status(self):
        if self.store.phone_connected():
            self.status.configure(text="● iPhone connected", style="Ok.TLabel")
        else:
            self.status.configure(text="○ Waiting for iPhone…", style="Wait.TLabel")

    def refresh(self):
        self._update_qr()
        self._update_status()
        self.tree.delete(*self.tree.get_children())
        for f in self.store.snapshot()["files"]:
            added = time.strftime("%H:%M", time.localtime(f["added"]))
            if time.time() - f["added"] > 86400:
                added = time.strftime("%d %b", time.localtime(f["added"]))
            self.tree.insert("", "end", iid=f["id"], values=(f["name"], human_size(f["size"]), added))

    def on_store_event(self, ev, payload):
        self.refresh()
        if ev == "added" and self.root.state() == "withdrawn":
            names = ", ".join(e["name"] for e in payload[:3]) + (" …" if len(payload) > 3 else "")
            if self.store.phone_connected():
                self.notify("Ready on your iPhone", names)
            else:
                self.notify("Shared — open the page on your iPhone", names)
        elif ev == "zipping":
            self.note.configure(text=f"Zipping folder “{payload}”…")
        elif ev == "error":
            self.note.configure(text=payload)
            self.notify("Problem", payload)
        if ev == "added":
            self.note.configure(text="")
        if ev == "token":
            self.last_url = None
            self._update_qr()

    # ---- actions -------------------------------------------------------------
    def show(self):
        self.last_url = None
        self.refresh()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def hide(self):
        self.root.withdraw()
        if not getattr(self, "_hid_once", False):
            self._hid_once = True
            self.notify(APP_NAME, "Still running in the tray. Right-click any file → Send to iPhone.")

    def notify(self, title, msg):
        try:
            self.tray.notify(msg[:250], title[:60])
        except Exception:
            pass

    def on_drop(self, event):
        self._draw_drop()
        paths = self.root.tk.splitlist(event.data)
        self.store.add_paths(paths)
        return event.action

    def add_files(self):
        from tkinter import filedialog
        paths = filedialog.askopenfilenames(parent=self.root, title="Choose files to send to iPhone")
        if paths:
            self.store.add_paths(paths)

    def add_folder(self):
        from tkinter import filedialog
        p = filedialog.askdirectory(parent=self.root, title="Choose a folder (it will be sent as a .zip)")
        if p:
            self.store.add_paths([p])

    def remove_selected(self):
        for fid in self.tree.selection():
            self.store.remove(fid)

    def copy_link(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.store.url())
        self.note.configure(text="Link copied.")

    def new_link(self):
        from tkinter import messagebox
        if messagebox.askyesno(APP_NAME, "Make a new pairing link?\n\nYour iPhone will need to scan the new "
                                         "QR code, and the old link stops working.", parent=self.root):
            self.store.rotate_token()

    def send_clipboard(self):
        try:
            text = self.root.clipboard_get()
        except self.tk.TclError:
            text = ""
        if not text.strip():
            self.notify(APP_NAME, "The PC clipboard has no text to send.")
            return
        self.store.set_clip_for_phone(text)
        self.notify("Clipboard sent", "It's in the Clipboard section on your iPhone page.")

    def got_clip_from_phone(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # keeps the clipboard content after we return
        preview = text.strip().replace("\n", " ")
        self.notify("Copied from iPhone", preview[:120] + ("…" if len(preview) > 120 else ""))

    def got_file_from_phone(self, path):
        now = time.time()
        # Collapse a burst of uploads into one notification.
        self._recv = [t for t in getattr(self, "_recv", []) if now - t < 6] + [now]
        n = len(self._recv)
        self.notify("Received from iPhone" if n == 1 else f"Received {n} files from iPhone",
                    os.path.basename(path) + f"\nSaved in {self.store.inbox}")

    def open_inbox(self):
        os.makedirs(self.store.inbox, exist_ok=True)
        os.startfile(self.store.inbox)

    def toggle_startup(self):
        want = not self.store.startup
        if core.PACKAGED:
            def work():  # the Store API is async and may open Settings; keep the UI responsive
                self.store.startup = wininteg.set_startup(want)
                self.tray.update_menu()
            threading.Thread(target=work, daemon=True).start()
            return
        self.store.startup = want
        wininteg.set_startup(want)
        self.store.save()
        self.tray.update_menu()

    def toggle_menu(self):
        self.store.explorer_menu = not self.store.explorer_menu
        threading.Thread(target=wininteg.set_explorer_menu, args=(self.store.explorer_menu,), daemon=True).start()
        self.store.save()
        self.tray.update_menu()

    def quit(self):
        self.tray.stop()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        self.root.destroy()

    def run(self, server):
        self.server = server
        self.root.mainloop()


# ---------------------------------------------------------------- entry point
def main():
    argv = sys.argv[1:]
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    if not core.PACKAGED:  # packaged apps already have their own taskbar identity
        try:  # own taskbar identity/icon instead of being grouped as "Python"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SendToiPhone.App")
        except Exception:
            pass

    if "--uninstall" in argv:
        wininteg.uninstall()
        if "--quiet" in argv:
            return
        ctypes.windll.user32.MessageBoxW(0, "Removed the right-click menu, startup entry and Start Menu shortcut.\n"
                                            "You can now delete the program folder.", APP_NAME, 0x40)
        return

    paths, tray_only, sending = parse_args(argv)
    import storeapi
    tray_only = tray_only or storeapi.launched_at_startup()
    shared_text = ""
    share = storeapi.take_share()  # launched from Windows' Share menu?
    if share:
        paths, shared_text = paths + share[0], share[1]
        sending = True
    show = not tray_only and not sending

    if forward_to_running(paths, show, shared_text):
        return

    if wininteg.needs_install() and "--portable" not in argv and not core.PACKAGED:
        if wininteg.install_and_relaunch(argv):
            return

    store = Store()

    from server import make_server
    app_ref = {}

    def ui(fn_name, *a):
        app = app_ref.get("app")
        if app:
            app.call(getattr(app, fn_name), *a)

    server = None
    for attempt in range(12):
        try:
            server = make_server(
                store,
                on_received=lambda p: ui("got_file_from_phone", p),
                on_clip=lambda t: ui("got_clip_from_phone", t),
                on_local_show=lambda: ui("show"),
                on_local_quit=lambda: ui("quit"),
            )
            break
        except OSError:
            # Another copy may be starting at the same moment (multi-select in Explorer).
            time.sleep(0.5)
            if forward_to_running(paths, show, shared_text):
                return
    if server is None:
        ctypes.windll.user32.MessageBoxW(
            0, f"Port {store.port} is already in use by another program.\n"
               f"Change \"port\" in {core.CONFIG_PATH} and start again.", APP_NAME, 0x10)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Keep Windows integration pointing at wherever this copy lives.
    def integrate():
        try:
            wininteg.set_startup(store.startup)
            if store.explorer_menu:
                wininteg.set_explorer_menu(True)
            if store.first_run and (wininteg.frozen() or core.DIRECT):
                wininteg.create_start_menu_entry()
                if core.DIRECT:
                    wininteg.create_desktop_shortcut()
        except Exception as e:
            print("integration error:", e, file=sys.stderr)
    if "--no-integrate" not in argv and not core.PACKAGED:
        threading.Thread(target=integrate, daemon=True).start()

    store.add_paths(paths)
    if shared_text:
        store.set_clip_for_phone(shared_text)
    app = App(store, show_window=show or store.first_run or (sending and not store.phone_connected()))
    app_ref["app"] = app
    try:
        app.run(server)
    finally:
        server.server_close()
        core.cleanup_temp()


if __name__ == "__main__":
    main()
