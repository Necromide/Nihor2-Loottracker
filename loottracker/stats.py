"""Statistics for the dashboard, all driven by one filter object.

Filter keys (all optional):
  from, to          naive local timestamps (seconds) – inclusive range
  portals           list of portal keys, e.g. ["elite", "mystic"]
  se                "all" | "with" | "without"   (runs with / without Super-Elite)
  se_conf           "all" | "confirmed"          (which Super-Elites count)
  sessions          list of live-session ids (only their active time windows count)
  chest             "exclude" | "include" | "only"   chest contents
  outside           "exclude" | "include" | "only"   drops outside portal runs
  weekdays          list of 0..6 (Mon..Sun)
  hour_from, hour_to  0..23 (wraps over midnight if from > to)
  category          category key
  search            substring of the item name
"""
import bisect
import calendar
import math
import statistics
import time

from .analysis import canon_of
from .db import match_any


def now_ts():
    return calendar.timegm(time.localtime())


def wilson(k, n, z=1.96):
    if n <= 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def _weekday(ts):
    return time.gmtime(ts).tm_wday


def _hour(ts):
    return time.gmtime(ts).tm_hour


def _hour_ok(h, hf, ht):
    if hf is None or ht is None:
        return True
    if hf <= ht:
        return hf <= h <= ht
    return h >= hf or h <= ht


class Stats:
    def __init__(self, db):
        self.db = db
        self._quality_cache = ("init", None)

    # ---- helpers --------------------------------------------------------
    def segments(self, session_ids):
        if not session_ids:
            return None
        q = "SELECT start, end FROM segments WHERE session_id IN (%s)" % ",".join(str(int(i)) for i in session_ids)
        now = now_ts()
        return [(s, e if e is not None else now) for s, e in self.db.conn.execute(q)]

    def item_info(self, settings):
        """canon name -> {chest, category} for all known items."""
        cats = settings["categories"]
        chest_p = settings["chest_patterns"]
        info = {}
        for (canon,) in self.db.conn.execute("SELECT DISTINCT canon FROM items"):
            cat = None
            for c in cats:
                if match_any(canon, c["patterns"]):
                    cat = c["key"]
                    break
            info[canon] = {"chest": match_any(canon, chest_p), "category": cat}
        return info

    def _drop_where(self, f, settings, info, segs, alias="d"):
        """SQL WHERE fragments + params for drop-level filters."""
        w, p = [], []
        if f.get("from") is not None:
            w.append(f"{alias}.ts >= ?"); p.append(int(f["from"]))
        if f.get("to") is not None:
            w.append(f"{alias}.ts <= ?"); p.append(int(f["to"]))
        if segs is not None:
            if not segs:
                w.append("0")
            else:
                w.append("(" + " OR ".join(f"{alias}.ts BETWEEN ? AND ?" for _ in segs) + ")")
                for s, e in segs:
                    p += [s, e]
        wd = f.get("weekdays")
        if wd and len(wd) < 7:
            # sqlite %w: 0=Sunday; ours: 0=Monday
            sq = [str((int(x) + 1) % 7) for x in wd]
            w.append(f"strftime('%w', {alias}.ts, 'unixepoch') IN ({','.join(repr(s) for s in sq)})")
        hf, ht = f.get("hour_from"), f.get("hour_to")
        if hf is not None and ht is not None and not (int(hf) == 0 and int(ht) == 23):
            hexpr = f"CAST(strftime('%H', {alias}.ts, 'unixepoch') AS INTEGER)"
            if int(hf) <= int(ht):
                w.append(f"{hexpr} BETWEEN ? AND ?"); p += [int(hf), int(ht)]
            else:
                w.append(f"({hexpr} >= ? OR {hexpr} <= ?)"); p += [int(hf), int(ht)]
        # item-level filters -> list of allowed canon names
        chest = f.get("chest", "exclude")
        cat = f.get("category")
        search = (f.get("search") or "").strip().lower()
        allowed = None
        if chest != "include" or cat or search:
            allowed = []
            for name, inf in info.items():
                if chest == "exclude" and inf["chest"]:
                    continue
                if chest == "only" and not inf["chest"]:
                    continue
                if cat and inf["category"] != cat:
                    continue
                if search and search not in name.lower():
                    continue
                allowed.append(name)
        return w, p, allowed

    def _with_allowed(self, sql_where, params, allowed):
        if allowed is None:
            return sql_where, params
        if not allowed:
            return sql_where + ["0"], params
        self.db.conn.execute("CREATE TEMP TABLE IF NOT EXISTS sel_items(name TEXT PRIMARY KEY)")
        self.db.conn.execute("DELETE FROM sel_items")
        self.db.conn.executemany("INSERT OR IGNORE INTO sel_items(name) VALUES(?)", [(a,) for a in allowed])
        return sql_where + ["i.canon IN (SELECT name FROM sel_items)"], params

    def select_runs(self, f, settings, segs):
        portals = f.get("portals") or [p["key"] for p in settings["rules"]["portals"]]
        q = "SELECT id, type, start, end, se, se_ts, se_yang, se_conf FROM runs WHERE type IN (%s)" % ",".join(
            "?" * len(portals))
        params = list(portals)
        if f.get("from") is not None:
            q += " AND end >= ?"; params.append(int(f["from"]))
        if f.get("to") is not None:
            q += " AND end <= ?"; params.append(int(f["to"]))
        q += " ORDER BY end"
        se_f = f.get("se", "all")
        conf_f = f.get("se_conf", "all")
        wd = f.get("weekdays")
        wd = set(int(x) for x in wd) if wd and len(wd) < 7 else None
        hf, ht = f.get("hour_from"), f.get("hour_to")
        hf = int(hf) if hf is not None else None
        ht = int(ht) if ht is not None else None
        out = []
        for r in self.db.conn.execute(q, params):
            r = dict(r)
            counts = bool(r["se"]) and (conf_f == "all" or r["se_conf"] == "confirmed")
            r["se_counted"] = counts
            if se_f == "with" and not counts:
                continue
            if se_f == "without" and counts:
                continue
            if wd is not None and _weekday(r["end"]) not in wd:
                continue
            if not _hour_ok(_hour(r["end"]), hf, ht):
                continue
            if segs is not None and not any(s <= r["end"] <= e for s, e in segs):
                continue
            out.append(r)
        return out

    # ---- main report ----------------------------------------------------
    def report(self, f, settings):
        db = self.db
        with db.lock:
            return self._report(f, settings)

    def _report(self, f, settings):
        conn = self.db.conn
        info = self.item_info(settings)
        prices = self.db.prices()
        segs = self.segments(f.get("sessions"))
        runs = self.select_runs(f, settings, segs)
        portal_keys = [p["key"] for p in settings["rules"]["portals"]]
        outside = f.get("outside", "exclude")

        # selected runs -> temp table
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS sel_runs(id INTEGER PRIMARY KEY, type TEXT, end INTEGER)")
        conn.execute("DELETE FROM sel_runs")
        conn.executemany("INSERT INTO sel_runs(id, type, end) VALUES(?,?,?)",
                         [(r["id"], r["type"], r["end"]) for r in runs] if outside != "only" else [])

        where, params, allowed = self._drop_where(f, settings, info, segs)
        where, params = self._with_allowed(where, params, allowed)
        wsql = (" AND " + " AND ".join(where)) if where else ""

        # per-portal item stats
        by_type = {k: {} for k in portal_keys}
        q = ("SELECT s.type, i.canon, COUNT(DISTINCT d.run_id), SUM(d.qty), MAX(d.ts), MAX(s.end) "
             "FROM drops d JOIN sel_runs s ON s.id = d.run_id JOIN items i ON i.id = d.item_id "
             "WHERE 1" + wsql + " GROUP BY s.type, i.canon")
        for typ, canon, nruns, qty, last_ts, last_run_end in conn.execute(q, params):
            by_type.setdefault(typ, {})[canon] = (nruns, qty, last_ts, last_run_end)

        # outside portal runs
        outside_items = {}
        if outside != "exclude":
            q = ("SELECT i.canon, COUNT(*), SUM(d.qty), MAX(d.ts) FROM drops d JOIN items i ON i.id = d.item_id "
                 "WHERE d.run_id IS NULL" + wsql + " GROUP BY i.canon")
            for canon, n, qty, last_ts in conn.execute(q, params):
                outside_items[canon] = (n, qty, last_ts)

        runs_by_type = {k: [r for r in runs if r["type"] == k] for k in portal_keys}
        ends_by_type = {k: [r["end"] for r in v] for k, v in runs_by_type.items()}

        def item_row(canon, nruns, qty, last_ts, total_runs, ends, last_run_end):
            lo, hi = wilson(nruns, total_runs)
            since = None
            if ends and last_run_end is not None:
                since = len(ends) - bisect.bisect_right(ends, last_run_end)
            price = prices.get(canon)
            return {
                "item": canon, "runs": nruns, "qty": qty, "last": last_ts,
                "rate": nruns / total_runs if total_runs else None, "ci_lo": lo, "ci_hi": hi,
                "avg_qty": qty / total_runs if total_runs else None,
                "since": since, "chest": info.get(canon, {}).get("chest", False),
                "category": info.get(canon, {}).get("category"),
                "price": price, "value": price * qty if price is not None else None,
            }

        portals_out = {}
        for k in portal_keys:
            n = len(runs_by_type[k])
            rows = [item_row(c, *v[:3], n, ends_by_type[k], v[3]) for c, v in by_type.get(k, {}).items()]
            rows.sort(key=lambda r: (-r["runs"], -r["qty"]))
            durs = [r["end"] - r["start"] for r in runs_by_type[k]]
            portals_out[k] = {
                "runs": n,
                "median_duration": statistics.median(durs) if durs else None,
                "items": rows,
            }

        out_rows = []
        for c, (n, qty, last_ts) in outside_items.items():
            price = prices.get(c)
            out_rows.append({"item": c, "count": n, "qty": qty, "last": last_ts,
                             "chest": info.get(c, {}).get("chest", False),
                             "category": info.get(c, {}).get("category"),
                             "price": price, "value": price * qty if price is not None else None})
        out_rows.sort(key=lambda r: -r["count"])

        # combined item table (all selected portals + optional outside)
        combined = {}
        for k in portal_keys:
            for c, (nruns, qty, last_ts, _) in by_type.get(k, {}).items():
                e = combined.setdefault(c, {"item": c, "qty": 0, "last": None, "portal_qty": 0, "outside_qty": 0})
                e["qty"] += qty; e["portal_qty"] += qty
                e["last"] = max(e["last"] or 0, last_ts)
        for c, (n, qty, last_ts) in outside_items.items():
            e = combined.setdefault(c, {"item": c, "qty": 0, "last": None, "portal_qty": 0, "outside_qty": 0})
            e["qty"] += qty; e["outside_qty"] += qty
            e["last"] = max(e["last"] or 0, last_ts)
        total_value = 0
        for c, e in combined.items():
            e["price"] = prices.get(c)
            e["value"] = e["price"] * e["qty"] if e["price"] is not None else None
            e["chest"] = info.get(c, {}).get("chest", False)
            e["category"] = info.get(c, {}).get("category")
            if e["value"]:
                total_value += e["value"]
        combined_rows = sorted(combined.values(), key=lambda r: -r["qty"])

        yang_name = canon_of(self.db, settings["rules"]["super_elite"]["yang_item"])
        yang_total = combined.get(yang_name, {}).get("qty", 0)

        # Super-Elite
        se_portal = settings["rules"]["super_elite"]["portal"]
        se_runs = runs_by_type.get(se_portal, [])
        se_list = [r for r in se_runs if r["se_counted"]]
        n_se_runs = len(se_runs)
        k_se = len(se_list)
        lo, hi = wilson(k_se, n_se_runs)
        streaks, cur = [], 0
        for r in se_runs:
            if r["se_counted"]:
                streaks.append(cur); cur = 0
            else:
                cur += 1
        longest = max(streaks + [cur]) if se_runs else 0
        p = k_se / n_se_runs if n_se_runs else 0
        se_out = {
            "portal": se_portal, "runs": n_se_runs, "count": k_se,
            "rate": p if n_se_runs else None, "ci_lo": lo, "ci_hi": hi,
            "by_conf": {c: sum(1 for r in se_list if r["se_conf"] == c)
                        for c in ("confirmed", "signature", "no_yang_data")},
            "current_streak": cur, "longest_streak": longest,
            "p_longest": (1 - p) ** longest if p else None,
            "avg_gap": (sum(streaks) / len(streaks) + 1) if streaks else None,
            "list": [{"run_id": r["id"], "ts": r["se_ts"], "yang": r["se_yang"], "conf": r["se_conf"],
                      "run_end": r["end"]} for r in reversed(se_list)],
        }

        # daily series
        days = {}
        for r in runs:
            d = r["end"] // 86400 * 86400
            e = days.setdefault(d, {k: 0 for k in portal_keys})
            e[r["type"]] = e.get(r["type"], 0) + 1
            if r["se_counted"]:
                e["se"] = e.get("se", 0) + 1
        yang_days = {}
        yang_ids = self.db.item_ids_for_canon([yang_name])
        if yang_ids and (allowed is None or yang_name in allowed):
            scope = []
            if outside == "exclude":
                scope.append("d.run_id IN (SELECT id FROM sel_runs)")
            elif outside == "only":
                scope.append("d.run_id IS NULL")
            else:
                scope.append("(d.run_id IN (SELECT id FROM sel_runs) OR d.run_id IS NULL)")
            yw = [w for w in where if not w.startswith("i.canon")]
            q = ("SELECT d.ts / 86400 * 86400 AS day, SUM(d.qty) FROM drops d WHERE d.item_id IN (%s) AND "
                 % ",".join(str(i) for i in yang_ids)) + " AND ".join(scope + yw) + " GROUP BY day"
            for day, s in conn.execute(q, params[:len(params)]):
                yang_days[day] = s
        series = []
        for d in sorted(set(days) | set(yang_days)):
            e = days.get(d, {})
            series.append({"day": d, **{k: e.get(k, 0) for k in portal_keys}, "se": e.get("se", 0),
                           "yang": yang_days.get(d, 0)})

        total_runs = len(runs)
        span = None
        if runs:
            run_time = sum(r["end"] - r["start"] for r in runs)
            span = {"first": runs[0]["end"], "last": runs[-1]["end"], "run_time": run_time}

        return {
            "runs_total": total_runs,
            "span": span,
            "portals": portals_out,
            "outside": out_rows,
            "items": combined_rows,
            "yang_total": yang_total,
            "value_total": total_value,
            "super_elite": se_out,
            "series": series,
            "quality": self.quality(settings),
        }

    # ---- data quality ---------------------------------------------------
    def quality(self, settings):
        conn = self.db.conn
        n = conn.execute("SELECT MAX(id) FROM drops").fetchone()[0]
        if self._quality_cache[0] == n:
            return self._quality_cache[1]
        yang_name = canon_of(self.db, settings["rules"]["super_elite"]["yang_item"])
        yang_ids = self.db.item_ids_for_canon([yang_name]) or [-1]
        rows = conn.execute(
            "SELECT ts / 86400 AS day, COUNT(*), SUM(item_id IN (%s)) FROM drops GROUP BY day ORDER BY day"
            % ",".join(str(i) for i in yang_ids)
        ).fetchall()
        gaps = []
        cur = None
        for day, cnt, ycnt in rows:
            if cnt >= 50 and not ycnt:
                if cur and day - cur[1] <= 3:
                    cur[1] = day
                else:
                    cur = [day, day]
                    gaps.append(cur)
        first = conn.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM drops").fetchone()
        files = [dict(r) for r in conn.execute(
            "SELECT name, lines, first_ts, last_ts FROM files ORDER BY first_ts")]
        res = {
            "yang_gaps": [{"from": a * 86400, "to": b * 86400 + 86399} for a, b in gaps],
            "first_ts": first[0], "last_ts": first[1], "drops": first[2], "files": files,
        }
        self._quality_cache = (n, res)
        return res

    # ---- runs list / details --------------------------------------------
    def runs_page(self, f, settings, offset=0, limit=100):
        with self.db.lock:
            segs = self.segments(f.get("sessions"))
            runs = self.select_runs(f, settings, segs)
            runs.reverse()
            page = runs[offset: offset + limit]
            ids = [r["id"] for r in page]
            counts = {}
            if ids:
                q = ("SELECT run_id, COUNT(*), SUM(CASE WHEN item_id IN (%s) THEN qty ELSE 0 END) FROM drops "
                     "WHERE run_id IN (%s) GROUP BY run_id") % (
                    ",".join(str(i) for i in (self.db.item_ids_for_canon(
                        [canon_of(self.db, settings["rules"]["super_elite"]["yang_item"])]) or [-1])),
                    ",".join(str(i) for i in ids))
                for rid, n, y in self.db.conn.execute(q):
                    counts[rid] = (n, y)
            for r in page:
                r["drops"], r["yang"] = counts.get(r["id"], (0, 0))
                r["duration"] = r["end"] - r["start"]
            return {"total": len(runs), "runs": page}

    def run_detail(self, run_id, settings):
        with self.db.lock:
            info = self.item_info(settings)
            r = self.db.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if not r:
                return None
            drops = [{"ts": ts, "qty": q, "item": c, "chest": info.get(c, {}).get("chest", False)}
                     for ts, q, c in self.db.conn.execute(
                    "SELECT d.ts, d.qty, i.canon FROM drops d JOIN items i ON i.id=d.item_id "
                    "WHERE d.run_id=? ORDER BY d.ts, d.id", (run_id,))]
            return {"run": dict(r), "drops": drops}

    def recent(self, settings, limit=40, since=None):
        with self.db.lock:
            info = self.item_info(settings)
            q = ("SELECT d.ts, d.qty, i.canon, r.type FROM drops d JOIN items i ON i.id=d.item_id "
                 "LEFT JOIN runs r ON r.id=d.run_id ")
            params = []
            if since is not None:
                q += "WHERE d.ts >= ? "
                params.append(int(since))
            q += "ORDER BY d.ts DESC, d.id DESC LIMIT ?"
            params.append(int(limit))
            return [{"ts": ts, "qty": qn, "item": c, "portal": t, "chest": info.get(c, {}).get("chest", False)}
                    for ts, qn, c, t in self.db.conn.execute(q, params)]

    def items_catalog(self, settings):
        with self.db.lock:
            info = self.item_info(settings)
            prices = self.db.prices()
            rows = self.db.conn.execute(
                "SELECT i.canon, GROUP_CONCAT(DISTINCT i.name), COUNT(d.id), MIN(d.ts), MAX(d.ts) "
                "FROM items i LEFT JOIN drops d ON d.item_id=i.id GROUP BY i.canon ORDER BY COUNT(d.id) DESC"
            ).fetchall()
            return [{"item": c, "names": (names or "").split(","), "drops": n, "first": a, "last": b,
                     "chest": info.get(c, {}).get("chest", False), "category": info.get(c, {}).get("category"),
                     "price": prices.get(c)} for c, names, n, a, b in rows]
