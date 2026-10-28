"""SQLite storage."""
import json
import re
import sqlite3
import threading

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    ident TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    path TEXT,
    offset INTEGER NOT NULL DEFAULT 0,
    lines INTEGER NOT NULL DEFAULT 0,
    first_ts INTEGER,
    last_ts INTEGER
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    canon TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (name TEXT PRIMARY KEY, canon TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (item TEXT PRIMARY KEY, price INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS drops (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    run_id INTEGER,
    UNIQUE (file_id, line_no)
);
CREATE INDEX IF NOT EXISTS drops_ts ON drops(ts);
CREATE INDEX IF NOT EXISTS drops_run ON drops(run_id);
CREATE INDEX IF NOT EXISTS drops_item_ts ON drops(item_id, ts);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    start INTEGER NOT NULL,
    end INTEGER NOT NULL,
    se INTEGER NOT NULL DEFAULT 0,
    se_ts INTEGER,
    se_yang INTEGER,
    se_conf TEXT
);
CREATE INDEX IF NOT EXISTS runs_end ON runs(end);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created INTEGER NOT NULL,
    ended INTEGER
);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    start INTEGER NOT NULL,
    end INTEGER
);
"""


def glob_to_regex(pattern):
    """'*' is the only wildcard; everything else (incl. [ ]) is literal."""
    parts = [re.escape(p) for p in pattern.split("*")]
    return re.compile("^" + ".*".join(parts) + "$", re.IGNORECASE)


def match_any(name, patterns):
    return any(glob_to_regex(p).match(name) for p in patterns)


class Database:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self._item_cache = {}
        for row in self.conn.execute("SELECT id, name FROM items"):
            self._item_cache[row["name"]] = row["id"]

    # ---- settings -------------------------------------------------------
    def get_settings(self):
        s = config.defaults()
        with self.lock:
            for row in self.conn.execute("SELECT key, value FROM settings"):
                v = json.loads(row["value"])
                if row["key"] == "rules" and isinstance(v, dict):
                    v = {**s["rules"], **v}  # new rule sections from updates stay available
                s[row["key"]] = v
        return s

    def set_setting(self, key, value):
        with self.lock:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
            self.conn.commit()

    # ---- items ----------------------------------------------------------
    def item_id(self, name):
        iid = self._item_cache.get(name)
        if iid is None:
            canon = self.conn.execute("SELECT canon FROM aliases WHERE name=?", (name,)).fetchone()
            cur = self.conn.execute(
                "INSERT INTO items(name, canon) VALUES(?, ?)", (name, canon[0] if canon else name)
            )
            iid = cur.lastrowid
            self._item_cache[name] = iid
        return iid

    def set_alias(self, name, canon):
        with self.lock:
            if not canon or canon == name:
                self.conn.execute("DELETE FROM aliases WHERE name=?", (name,))
                self.conn.execute("UPDATE items SET canon=name WHERE name=?", (name,))
            else:
                # Avoid chains: whatever pointed to `name` now points to `canon`.
                self.conn.execute("UPDATE aliases SET canon=? WHERE canon=?", (canon, name))
                self.conn.execute("UPDATE items SET canon=? WHERE canon=?", (canon, name))
                self.conn.execute(
                    "INSERT INTO aliases(name, canon) VALUES(?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET canon=excluded.canon",
                    (name, canon),
                )
                self.conn.execute("UPDATE items SET canon=? WHERE name=?", (canon, name))
            self.conn.commit()

    def aliases(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT name, canon FROM aliases ORDER BY canon, name")]

    def item_ids_for_canon(self, names):
        names = list(names)
        if not names:
            return []
        q = "SELECT id FROM items WHERE canon IN (%s)" % ",".join("?" * len(names))
        with self.lock:
            return [r[0] for r in self.conn.execute(q, names)]

    def apply_default_aliases(self):
        """Insert built-in DE->EN aliases once per DEFAULT_ALIASES_VERSION. Returns True if anything changed."""
        done = self.get_settings().get("default_aliases_version", 0)
        if done >= config.DEFAULT_ALIASES_VERSION:
            return False
        changed = False
        with self.lock:
            for name, canon in config.DEFAULT_ALIASES.items():
                if self.conn.execute("SELECT 1 FROM aliases WHERE name=?", (name,)).fetchone():
                    continue  # user already decided something for this name
                self.set_alias(name, canon)
                changed = True
        self.set_setting("default_aliases_version", config.DEFAULT_ALIASES_VERSION)
        return changed

    # ---- prices ---------------------------------------------------------
    def prices(self):
        with self.lock:
            return {r["item"]: r["price"] for r in self.conn.execute("SELECT item, price FROM prices")}

    def set_price(self, item, price):
        with self.lock:
            if price is None or price == "":
                self.conn.execute("DELETE FROM prices WHERE item=?", (item,))
            else:
                self.conn.execute(
                    "INSERT INTO prices(item, price) VALUES(?, ?) "
                    "ON CONFLICT(item) DO UPDATE SET price=excluded.price",
                    (item, int(price)),
                )
            self.conn.commit()
