"""Local HTTP server: JSON API + static dashboard (bound to 127.0.0.1 only)."""
import json
import mimetypes
import os
import re
import sys
import threading
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import analysis, config
from .db import Database
from .importer import Importer
from .sessions import Sessions
from .stats import Stats


def resource_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(base, "loottracker", "web")
    return os.path.join(base, "web")


class App:
    def __init__(self, data_dir, client_path=None):
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.db = Database(os.path.join(data_dir, "loottracker.db"))
        if client_path:
            self.db.set_setting("client_path", client_path)
        self.stats = Stats(self.db)
        self.sessions = Sessions(self.db)
        self.analysing = False
        self.importer = Importer(self.db, on_new_data=self.on_new_data)

    def settings(self):
        return self.db.get_settings()

    def on_new_data(self, min_ts):
        analysis.rebuild(self.db, self.settings(), min_ts)

    def full_rebuild_async(self):
        def run():
            self.analysing = True
            try:
                analysis.rebuild(self.db, self.settings(), None)
            finally:
                self.analysing = False
        threading.Thread(target=run, daemon=True).start()

    def start(self):
        self.importer.start(lambda: self.settings().get("client_path"))


def pick_folder():
    """Native folder dialog on the local machine (the server runs on the user's PC)."""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title=config.APP_NAME)
        root.destroy()
        return path or None
    except Exception:
        return None


_INVISIBLE = dict.fromkeys(map(ord, "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"), None)


def normalize_path(path):
    """Clean up pasted paths: quotes ("Copy as path"), invisible Unicode marks, the log file itself."""
    if not path:
        return ""
    p = str(path).translate(_INVISIBLE).strip().strip('"').strip("'").strip()
    p = os.path.expandvars(os.path.expanduser(p))
    if p.lower().endswith(config.ACTIVE_LOG):
        p = os.path.dirname(p)
    return os.path.normpath(p) if p else ""


def check_client_path(path):
    path = normalize_path(path)
    if not path:
        return {"ok": False, "reason": "empty", "path": path}
    if not os.path.isdir(path):
        return {"ok": False, "reason": "not_found", "path": path}
    has_active = os.path.isfile(os.path.join(path, config.ACTIVE_LOG))
    has_archive = os.path.isdir(os.path.join(path, config.ARCHIVE_DIR))
    return {"ok": has_active or has_archive, "active": has_active, "archive": has_archive, "path": path,
            "reason": None if (has_active or has_archive) else "no_logs"}


def detect_client_paths():
    """Look for client folders (containing info_chat_loot.log) in the usual places."""
    roots = []
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    roots += [exe_dir, os.path.dirname(exe_dir)]
    home = os.path.expanduser("~")
    for sub in ("Downloads", "Desktop", "Documents", "Games", "OneDrive\\Desktop", ""):
        roots.append(os.path.join(home, sub) if sub else home)
    for drive in "CDEFG":
        for sub in ("", "Games", "Spiele", "Program Files", "Program Files (x86)"):
            roots.append(f"{drive}:\\{sub}")
    found, seen = [], set()
    for r in roots:
        try:
            if not os.path.isdir(r):
                continue
            cands = [r] + [os.path.join(r, n) for n in os.listdir(r)]
        except OSError:
            continue
        for c in cands:
            key = os.path.normcase(c)
            if key in seen:
                continue
            seen.add(key)
            try:
                if os.path.isfile(os.path.join(c, config.ACTIVE_LOG)):
                    found.append(c)
            except OSError:
                pass
        if len(found) >= 5:
            break
    return found


def make_handler(app):
    web = resource_dir()

    class Handler(BaseHTTPRequestHandler):
        server_version = "Loottracker"

        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def _jbody(self):
            b = self._body()
            return json.loads(b.decode("utf-8")) if b else {}

        def _local_only(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def do_GET(self):
            if not self._local_only():
                return self._json({"error": "forbidden"}, 403)
            path = self.path.split("?")[0]
            qs = {}
            if "?" in self.path:
                for kv in self.path.split("?", 1)[1].split("&"):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        qs[k] = v
            if path.startswith("/api/"):
                return self.api_get(path[5:], qs)
            if path == "/":
                path = "/index.html"
            fp = os.path.normpath(os.path.join(web, path.lstrip("/")))
            if not fp.startswith(web) or not os.path.isfile(fp):
                self.send_error(404)
                return
            with open(fp, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self._local_only():
                return self._json({"error": "forbidden"}, 403)
            path = self.path.split("?")[0]
            if not path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            try:
                return self.api_post(path[5:])
            except Exception as e:
                return self._json({"error": repr(e)}, 500)

        # ---- GET ---------------------------------------------------------
        def api_get(self, name, qs):
            s = app.settings()
            if name == "status":
                st = dict(app.importer.status)
                if app.analysing:
                    st["state"] = "analysing"
                return self._json({
                    "app": config.APP_NAME, "version": config.APP_VERSION,
                    "importer": st, "language": s["language"], "client_path": s["client_path"],
                    "client_check": check_client_path(s["client_path"]),
                    "portals": [p["key"] for p in s["rules"]["portals"]],
                    "categories": s["categories"], "live": app.sessions.active(),
                })
            if name == "settings":
                return self._json(s)
            if name == "items":
                return self._json(app.stats.items_catalog(s))
            if name == "aliases":
                return self._json(app.db.aliases())
            if name == "sessions":
                return self._json(app.sessions.list())
            if name == "recent":
                since = qs.get("since")
                return self._json(app.stats.recent(s, int(qs.get("limit", 40)), int(since) if since else None))
            m = re.fullmatch(r"run/(\d+)", name)
            if m:
                d = app.stats.run_detail(int(m.group(1)), s)
                return self._json(d if d else {"error": "not found"}, 200 if d else 404)
            return self._json({"error": "not found"}, 404)

        # ---- POST --------------------------------------------------------
        def api_post(self, name):
            s = app.settings()
            if name == "report":
                return self._json(app.stats.report(self._jbody(), s))
            if name == "runs":
                b = self._jbody()
                return self._json(app.stats.runs_page(b.get("filter", {}), s, int(b.get("offset", 0)),
                                                      int(b.get("limit", 100))))
            if name == "settings":
                b = self._jbody()
                rebuild = False
                if "client_path" in b:
                    b["client_path"] = normalize_path(b["client_path"])
                for key in ("language", "client_path", "rules", "chest_patterns", "categories"):
                    if key in b:
                        app.db.set_setting(key, b[key])
                        rebuild = rebuild or key == "rules"
                if rebuild:
                    app.full_rebuild_async()
                return self._json(app.settings())
            if name == "reset_setting":
                key = self._jbody().get("key")
                if key in ("rules", "chest_patterns", "categories"):
                    app.db.conn.execute("DELETE FROM settings WHERE key=?", (key,))
                    app.db.conn.commit()
                    if key == "rules":
                        app.full_rebuild_async()
                return self._json(app.settings())
            if name == "check_path":
                return self._json(check_client_path(self._jbody().get("path")))
            if name == "detect_paths":
                return self._json({"paths": detect_client_paths()})
            if name == "pick_folder":
                return self._json({"path": pick_folder()})
            if name == "alias":
                b = self._jbody()
                app.db.set_alias(b["name"], b.get("canon"))
                app.full_rebuild_async()
                return self._json({"ok": True})
            if name == "price":
                b = self._jbody()
                app.db.set_price(b["item"], b.get("price"))
                return self._json({"ok": True})
            if name == "rebuild":
                app.full_rebuild_async()
                return self._json({"ok": True})
            if name == "import":
                fname = os.path.basename(unquote(self.headers.get("X-Filename") or "import.log")) or "import.log"
                data = self._body()
                d = os.path.join(app.data_dir, "imports")
                os.makedirs(d, exist_ok=True)
                fp = os.path.join(d, fname)
                i = 1
                while os.path.exists(fp):
                    fp = os.path.join(d, f"{i}_{fname}"); i += 1
                with open(fp, "wb") as fh:
                    fh.write(data)
                n, mts = app.importer.import_file(fp, fname)
                if n == 0:
                    os.remove(fp)
                if mts is not None:
                    analysis.rebuild(app.db, s, mts)
                return self._json({"ok": True, "new_drops": n})
            if name.startswith("session/"):
                act = name.split("/", 1)[1]
                b = self._jbody()
                if act == "start":
                    return self._json(app.sessions.start(b.get("name")))
                if act == "pause":
                    return self._json(app.sessions.pause())
                if act == "resume":
                    return self._json(app.sessions.resume())
                if act == "stop":
                    return self._json(app.sessions.stop())
                if act == "rename":
                    app.sessions.rename(b["id"], b["name"])
                    return self._json({"ok": True})
                if act == "delete":
                    app.sessions.delete(b["id"])
                    return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)

    return Handler


def serve(app, port):
    for p in [port] + list(range(port + 1, port + 20)):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), make_handler(app))
            return httpd, p
        except OSError:
            continue
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    return httpd, httpd.server_address[1]
