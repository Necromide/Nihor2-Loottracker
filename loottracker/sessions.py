"""Live-tracker sessions: a session is a list of active time windows."""
from .stats import now_ts


class Sessions:
    def __init__(self, db):
        self.db = db

    def _q(self, sql, params=()):
        return self.db.conn.execute(sql, params)

    def active(self):
        with self.db.lock:
            r = self._q("SELECT * FROM sessions WHERE ended IS NULL ORDER BY id DESC LIMIT 1").fetchone()
            return self._full(r) if r else None

    def _full(self, r):
        s = dict(r)
        segs = [dict(x) for x in self._q("SELECT start, end FROM segments WHERE session_id=? ORDER BY start", (s["id"],))]
        now = now_ts()
        s["segments"] = segs
        s["running"] = bool(segs) and segs[-1]["end"] is None and s["ended"] is None
        s["active_seconds"] = sum((x["end"] if x["end"] is not None else now) - x["start"] for x in segs)
        s["first"] = segs[0]["start"] if segs else s["created"]
        s["last"] = (segs[-1]["end"] or now) if segs else s["created"]
        return s

    def list(self):
        with self.db.lock:
            return [self._full(r) for r in self._q("SELECT * FROM sessions ORDER BY id DESC")]

    def start(self, name=None):
        with self.db.lock:
            act = self.active()
            if act:
                return act
            now = now_ts()
            n = self._q("SELECT COUNT(*) FROM sessions").fetchone()[0] + 1
            cur = self._q("INSERT INTO sessions(name, created) VALUES(?, ?)", (name or f"Session {n}", now))
            self._q("INSERT INTO segments(session_id, start) VALUES(?, ?)", (cur.lastrowid, now))
            self.db.conn.commit()
            return self.active()

    def pause(self):
        with self.db.lock:
            act = self.active()
            if act and act["running"]:
                self._q("UPDATE segments SET end=? WHERE session_id=? AND end IS NULL", (now_ts(), act["id"]))
                self.db.conn.commit()
            return self.active()

    def resume(self):
        with self.db.lock:
            act = self.active()
            if act and not act["running"]:
                self._q("INSERT INTO segments(session_id, start) VALUES(?, ?)", (act["id"], now_ts()))
                self.db.conn.commit()
            return self.active()

    def stop(self):
        with self.db.lock:
            act = self.active()
            if act:
                now = now_ts()
                self._q("UPDATE segments SET end=? WHERE session_id=? AND end IS NULL", (now, act["id"]))
                self._q("UPDATE sessions SET ended=? WHERE id=?", (now, act["id"]))
                self.db.conn.commit()
            return None

    def rename(self, sid, name):
        with self.db.lock:
            self._q("UPDATE sessions SET name=? WHERE id=?", (name, int(sid)))
            self.db.conn.commit()

    def delete(self, sid):
        with self.db.lock:
            self._q("DELETE FROM segments WHERE session_id=?", (int(sid),))
            self._q("DELETE FROM sessions WHERE id=?", (int(sid),))
            self.db.conn.commit()
