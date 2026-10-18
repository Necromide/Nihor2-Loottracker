"""Derives portal runs and Super-Elite kills from the raw drops."""
import bisect
import threading

_rebuild_lock = threading.Lock()


def canon_of(db, name):
    row = db.conn.execute("SELECT canon FROM aliases WHERE name=?", (name,)).fetchone()
    return row[0] if row else name


def _ids(db, names):
    names = [canon_of(db, n) for n in names]
    return db.item_ids_for_canon(names)


def _in(ids):
    return "(%s)" % (",".join(str(int(i)) for i in ids) or "NULL")


def rebuild(db, settings, since_ts=None):
    """(Re)compute runs whose end is >= a cutoff derived from since_ts (None = everything)."""
    with _rebuild_lock:
        _rebuild(db, settings, since_ts)


def _rebuild(db, settings, since_ts):
    rules = settings["rules"]
    run_rules = rules["run"]
    se_rules = rules["super_elite"]
    max_dur = int(run_rules["max_duration_s"])
    idle_gap = int(run_rules["idle_gap_s"])

    with db.lock:
        conn = db.conn
        splinter_type = {}
        for p in rules["portals"]:
            for iid in _ids(db, [p["splinter"]]):
                splinter_type[iid] = p["key"]

        if since_ts is None:
            cutoff = -(2 ** 62)
        else:
            cutoff = since_ts - max_dur - 60
        prev = conn.execute("SELECT MAX(end) FROM runs WHERE end < ?", (cutoff,)).fetchone()[0]
        prev_end = prev if prev is not None else -(2 ** 62)

        conn.execute("DELETE FROM runs WHERE end >= ?", (cutoff,))
        conn.execute("UPDATE drops SET run_id=NULL WHERE ts > ? AND run_id IS NOT NULL", (prev_end,))

        # 1) run ends = splinter drops (one run per second and portal type)
        ends = []
        seen = set()
        if splinter_type:
            q = "SELECT ts, item_id FROM drops WHERE item_id IN %s AND ts > ? ORDER BY ts" % _in(splinter_type)
            for ts, iid in conn.execute(q, (prev_end,)):
                key = (ts, splinter_type[iid])
                if key not in seen:
                    seen.add(key)
                    ends.append(key)

        # 2) run starts: walk back from the splinter until an idle gap / previous run
        runs = []
        last_end = prev_end
        for end, typ in ends:
            lower = max(last_end, end - max_dur)
            start = end
            for (t,) in conn.execute(
                "SELECT DISTINCT ts FROM drops WHERE ts > ? AND ts <= ? ORDER BY ts DESC", (lower, end)
            ):
                if start - t > idle_gap:
                    break
                start = t
            runs.append([typ, start, end])
            last_end = end

        run_ids = []
        for typ, start, end in runs:
            cur = conn.execute("INSERT INTO runs(type, start, end) VALUES(?,?,?)", (typ, start, end))
            run_ids.append(cur.lastrowid)
            conn.execute("UPDATE drops SET run_id=? WHERE ts BETWEEN ? AND ?", (cur.lastrowid, start, end))

        # 3) Super-Elite: signature drop package that is NOT the run's end package
        se_portal = se_rules["portal"]
        req_ids = {}
        for n in se_rules["required"]:
            for iid in _ids(db, [n]):
                req_ids[iid] = canon_of(db, n)
        sig_ids = {}
        for n in se_rules["signature"]:
            for iid in _ids(db, [n]):
                sig_ids[iid] = canon_of(db, n)
        end_ids = {iid for iid, k in splinter_type.items() if k == se_portal}
        yang_ids = _ids(db, [se_rules["yang_item"]])
        need_req = {canon_of(db, n) for n in se_rules["required"]}
        sig_min = int(se_rules["signature_min"])

        per_sec = {}
        all_ids = list(req_ids) + list(sig_ids) + list(end_ids)
        if req_ids:
            q = "SELECT ts, item_id FROM drops WHERE item_id IN %s AND ts > ? ORDER BY ts" % _in(all_ids)
            for ts, iid in conn.execute(q, (prev_end,)):
                per_sec.setdefault(ts, set()).add(iid)

        se_runs = [(rid, r[2]) for rid, r in zip(run_ids, runs) if r[0] == se_portal]
        se_ends = [e for _, e in se_runs]
        best = {}
        w = int(se_rules["yang_window_s"])
        pw = int(se_rules["yang_presence_window_s"])
        for ts, ids in per_sec.items():
            if {req_ids[i] for i in ids if i in req_ids} != need_req:
                continue
            if ids & end_ids:
                continue  # same second as the splinter -> normal end boss
            sig_ok = len({sig_ids[i] for i in ids if i in sig_ids}) >= sig_min
            if not sig_ok and not se_rules.get("yang_fallback", False):
                continue
            k = bisect.bisect_left(se_ends, ts)
            if k >= len(se_ends) or se_ends[k] - ts > int(se_rules["max_before_end_s"]):
                continue
            rid = se_runs[k][0]
            yang = 0
            present = False
            if yang_ids:
                yang = conn.execute(
                    "SELECT MAX(qty) FROM drops WHERE item_id IN %s AND ts BETWEEN ? AND ?" % _in(yang_ids),
                    (ts - w, ts + w),
                ).fetchone()[0] or 0
                present = yang > 0 or conn.execute(
                    "SELECT 1 FROM drops WHERE item_id IN %s AND ts BETWEEN ? AND ? LIMIT 1" % _in(yang_ids),
                    (ts - pw, ts + pw),
                ).fetchone() is not None
            if not sig_ok and yang < int(se_rules["yang_confirm"]):
                continue  # fallback needs the Yang confirmation
            if yang >= int(se_rules["yang_confirm"]):
                conf = "confirmed"
            elif not present:
                conf = "no_yang_data"
            else:
                conf = "signature"
            if rid not in best or yang > best[rid][1]:
                best[rid] = (ts, yang, conf)
        for rid, (ts, yang, conf) in best.items():
            conn.execute("UPDATE runs SET se=1, se_ts=?, se_yang=?, se_conf=? WHERE id=?", (ts, yang, conf, rid))
        conn.commit()
