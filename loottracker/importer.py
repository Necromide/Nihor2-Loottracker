"""Reads the client's loot logs incrementally.

Files are identified by their first two drop lines, not by name. When the
client rotates `info_chat_loot.log` into `loot_history_archive/`, the archived
file has the same identity and is simply continued from the stored offset, so
nothing is counted twice.
"""
import calendar
import hashlib
import os
import threading
import time

from . import config

PREFIX = "You receive "


def _day_epoch(cache, d):
    v = cache.get(d)
    if v is None:
        dd, mm, yy = int(d[0:2]), int(d[3:5]), int(d[6:8])
        v = calendar.timegm((2000 + yy, mm, dd, 0, 0, 0, 0, 0, 0))
        cache[d] = v
    return v


def parse_line(line, cache):
    """'[02/10/26] [15:16:23]: You receive 3695 Yang.' -> (ts, qty, item) or None.

    Timestamps are naive local time stored as if UTC (seconds).
    """
    if len(line) < 36 or line[0] != "[" or line[9:11] != "] " or line[20:23] != "]: ":
        return None
    rest = line[23:]
    if not rest.startswith(PREFIX):
        return None
    rest = rest[len(PREFIX):].rstrip()
    sp = rest.find(" ")
    if sp <= 0:
        return None
    try:
        qty = int(rest[:sp])
        t = line[12:20]
        ts = _day_epoch(cache, line[1:9]) + int(t[0:2]) * 3600 + int(t[3:5]) * 60 + int(t[6:8])
    except ValueError:
        return None
    item = rest[sp + 1:]
    if item.endswith("."):
        item = item[:-1]
    if not item:
        return None
    return ts, qty, item


def _decode(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252", errors="replace")


def file_ident(path):
    """Identity from the first two complete drop lines, or None if not yet available."""
    found = []
    cache = {}
    with open(path, "rb") as fh:
        for raw in fh:
            if not raw.endswith(b"\n"):
                break
            line = _decode(raw).strip()
            if parse_line(line, cache):
                found.append(line)
                if len(found) == 2:
                    return hashlib.sha1("\n".join(found).encode("utf-8")).hexdigest()
            if fh.tell() > 1_000_000:
                break
    return None


class Importer:
    def __init__(self, db, on_new_data=None):
        self.db = db
        self.on_new_data = on_new_data
        self.status = {"state": "idle", "file": None, "files_done": 0, "files_total": 0, "lines": 0, "error": None}
        self._stop = threading.Event()
        self._thread = None

    # ---- single file ----------------------------------------------------
    def import_file(self, path, display_name=None):
        """Import new complete lines of `path`. Returns (new_rows, min_ts)."""
        ident = file_ident(path)
        if ident is None:
            return 0, None
        db = self.db
        with db.lock:
            row = db.conn.execute("SELECT id, offset, lines FROM files WHERE ident=?", (ident,)).fetchone()
            if row is None:
                cur = db.conn.execute(
                    "INSERT INTO files(ident, name, path) VALUES(?, ?, ?)",
                    (ident, display_name or os.path.basename(path), path),
                )
                file_id, offset, line_no = cur.lastrowid, 0, 0
            else:
                file_id, offset, line_no = row["id"], row["offset"], row["lines"]
        size = os.path.getsize(path)
        if size <= offset:
            return 0, None
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
        cut = data.rfind(b"\n")
        if cut < 0:
            return 0, None
        data = data[: cut + 1]
        new_offset = offset + len(data)
        cache = {}
        batch = []
        min_ts = max_ts = None
        for raw in data.split(b"\n")[:-1]:
            line_no += 1
            p = parse_line(_decode(raw).strip(), cache)
            if p is None:
                continue
            ts, qty, item = p
            batch.append((ts, qty, item, line_no))
            if min_ts is None or ts < min_ts:
                min_ts = ts
            if max_ts is None or ts > max_ts:
                max_ts = ts
        with db.lock:
            rows = [(ts, qty, db.item_id(item), file_id, ln) for ts, qty, item, ln in batch]
            db.conn.executemany(
                "INSERT OR IGNORE INTO drops(ts, qty, item_id, file_id, line_no) VALUES(?,?,?,?,?)", rows
            )
            db.conn.execute(
                "UPDATE files SET offset=?, lines=?, path=?, "
                "first_ts=COALESCE(MIN(first_ts, ?), ?), last_ts=COALESCE(MAX(last_ts, ?), ?) WHERE id=?",
                (new_offset, line_no, path, min_ts, min_ts, max_ts, max_ts, file_id),
            )
            db.conn.commit()
        self.status["lines"] += len(batch)
        return len(batch), min_ts

    # ---- client folder --------------------------------------------------
    def client_files(self, client_path):
        files = []
        arch = os.path.join(client_path, config.ARCHIVE_DIR)
        if os.path.isdir(arch):
            for n in sorted(os.listdir(arch)):
                if n.lower().endswith(".log"):
                    files.append(os.path.join(arch, n))
        active = os.path.join(client_path, config.ACTIVE_LOG)
        if os.path.isfile(active):
            files.append(active)
        return files

    def scan(self, client_path):
        """Import everything new from the client folder. Returns min new ts or None."""
        files = self.client_files(client_path)
        self.status.update(files_total=len(files), files_done=0)
        overall_min = None
        for f in files:
            self.status["file"] = os.path.basename(f)
            try:
                n, mts = self.import_file(f)
            except OSError as e:  # file locked/rotating – try again next round
                self.status["error"] = str(e)
                continue
            if mts is not None and (overall_min is None or mts < overall_min):
                overall_min = mts
            self.status["files_done"] += 1
        return overall_min

    # ---- background loop -------------------------------------------------
    def start(self, get_client_path, interval=1.0):
        def loop():
            first = True
            while not self._stop.is_set():
                path = get_client_path()
                if path and os.path.isdir(path):
                    self.status["state"] = "importing" if first else "watching"
                    try:
                        mts = self.scan(path)
                        if mts is not None and self.on_new_data:
                            if first:
                                self.status["state"] = "analysing"
                            self.on_new_data(mts)
                        self.status["error"] = None
                    except Exception as e:  # keep the watcher alive
                        self.status["error"] = repr(e)
                    first = False
                    self.status["state"] = "watching"
                else:
                    self.status["state"] = "no_client_path"
                    first = True
                self._stop.wait(interval)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
