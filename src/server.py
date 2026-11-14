"""Local Wi-Fi HTTP server the iPhone talks to."""
import hmac
import json
import mimetypes
import os
import re
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from core import resource_path, safe_filename, unique_path

CHUNK = 1024 * 512
COOKIE = "stp"
SIGNATURE = "send-to-iphone-ok"

mimetypes.add_type("image/heic", ".heic")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("video/mp4", ".mp4")


def make_server(store, on_received, on_clip, on_local_show, on_local_quit=lambda: None):
    page_cache = {}

    def phone_page():
        if "html" not in page_cache:
            with open(resource_path("phone.html"), "r", encoding="utf-8") as f:
                page_cache["html"] = f.read()
        return page_cache["html"]

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "SendToiPhone"

        def log_message(self, *args):
            pass

        # ---- helpers --------------------------------------------------
        def _local(self):
            return self.client_address[0] in ("127.0.0.1", "::1")

        def _query(self):
            return parse_qs(urlparse(self.path).query)

        def _authed(self):
            tok = store.token
            t = self._query().get("t", [""])[0]
            if t and hmac.compare_digest(t, tok):
                return True
            c = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE)
            ok = bool(c and hmac.compare_digest(c.value, tok))
            if ok and not self._local():
                store.last_phone_seen = time.time()
            return ok

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", headers=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj), "application/json")

        def _body(self, limit=None):
            n = int(self.headers.get("Content-Length") or 0)
            if limit and n > limit:
                raise ValueError("too large")
            return self.rfile.read(n) if n else b""

        def _denied(self):
            self._send(403, DENIED_PAGE, "text/html; charset=utf-8")

        # ---- routes ---------------------------------------------------
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/local/ping":
                return self._send(200, SIGNATURE)
            if path == "/favicon.ico":
                return self._send(204)
            if not self._authed():
                return self._denied()

            if path == "/":
                if "t" in self._query():
                    # Swap the token in the URL for a long-lived cookie, then clean the URL.
                    return self._send(302, headers={
                        "Location": "/",
                        "Set-Cookie": f"{COOKIE}={store.token}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Lax",
                    })
                return self._send(200, phone_page(), "text/html; charset=utf-8")
            if path == "/api/state":
                return self._json(store.snapshot())
            m = re.fullmatch(r"/f/([0-9a-f]+)(?:/.*)?", path)
            if m:
                if store.locked:
                    return self._send(402, LOCKED_PAGE, "text/html; charset=utf-8")
                return self._serve_file(m.group(1))
            self._send(404, "Not found")

        def do_POST(self):
            path = urlparse(self.path).path
            if path.startswith("/local/"):
                # The custom header blocks web pages open on this PC from calling us
                # (browsers can't send it cross-origin without a preflight we never answer).
                if not self._local() or self.headers.get("X-STP-Local") != "1":
                    return self._send(403, "Forbidden")
                if path == "/local/add":
                    data = json.loads(self._body(10_000_000) or b"{}")
                    store.add_paths(data.get("paths", []))
                    if data.get("show"):
                        on_local_show()
                    return self._json({"ok": True})
                if path == "/local/show":
                    on_local_show()
                    return self._json({"ok": True})
                if path == "/local/quit":
                    on_local_quit()
                    return self._json({"ok": True})
                return self._send(404, "Not found")

            if not self._authed():
                return self._denied()
            if store.locked and path in ("/api/upload", "/api/clip"):
                self.close_connection = True  # don't read a possibly huge body we're rejecting
                return self._json({"ok": False, "error": "trial_ended"}, 402)
            if path == "/api/upload":
                return self._upload()
            if path == "/api/clip":
                text = self._body(5_000_000).decode("utf-8", "replace")
                on_clip(text)
                return self._json({"ok": True})
            m = re.fullmatch(r"/api/remove/([0-9a-f]+)", path)
            if m:
                store.remove(m.group(1))
                return self._json({"ok": True})
            self._send(404, "Not found")

        # ---- file transfer --------------------------------------------
        def _serve_file(self, fid):
            entry = store.get_file(fid)
            if not entry or not os.path.isfile(entry["path"]):
                return self._send(404, "That file is no longer shared.")
            size = os.path.getsize(entry["path"])
            ctype = mimetypes.guess_type(entry["name"])[0] or "application/octet-stream"
            disp = "attachment" if self._query().get("dl") else "inline"
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            status = 200
            if rng:
                m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
                if m:
                    a, b = m.groups()
                    if a == "" and b:
                        start = max(0, size - int(b))
                    else:
                        start = int(a or 0)
                        end = min(int(b), size - 1) if b else size - 1
                    if start > end or start >= size:
                        return self._send(416, headers={"Content-Range": f"bytes */{size}"})
                    status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{quote(entry['name'])}")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            try:
                with open(entry["path"], "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(CHUNK, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (ConnectionError, OSError):
                self.close_connection = True

        def _upload(self):
            name = safe_filename(unquote(self.headers.get("X-Filename", "") or "upload"))
            total = int(self.headers.get("Content-Length") or 0)
            os.makedirs(store.inbox, exist_ok=True)
            final = unique_path(store.inbox, name)
            part = final + ".part"
            got = 0
            try:
                with open(part, "wb") as out:
                    while got < total:
                        chunk = self.rfile.read(min(CHUNK, total - got))
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
            except (ConnectionError, OSError):
                pass
            if got != total:
                try:
                    os.remove(part)
                except OSError:
                    pass
                self.close_connection = True
                return self._json({"ok": False, "error": "Upload interrupted"}, 400)
            final = unique_path(store.inbox, name)  # re-check in case of parallel uploads
            os.replace(part, final)
            on_received(final)
            self._json({"ok": True, "name": os.path.basename(final)})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False  # so a second copy can detect we're already running

        def handle_error(self, request, client_address):
            pass  # phones drop idle keep-alive connections all the time; not worth logging

    return Server((os.environ.get("STP_BIND", "0.0.0.0"), store.port), Handler)


LOCKED_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Trial ended</title>
<body style="font:17px -apple-system,system-ui,sans-serif;padding:32px;text-align:center;color:#333">
<h2>Free trial ended</h2>
<p>Buy PhoneDrop on your PC (Microsoft Store) to keep sending files.</p>
</body>"""

DENIED_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Send to iPhone</title>
<body style="font:17px -apple-system,system-ui,sans-serif;padding:32px;text-align:center;color:#333">
<h2>Link expired or not paired</h2>
<p>On your PC, open <b>Send to iPhone</b> from the tray and scan the QR code again with your iPhone camera.</p>
</body>"""
