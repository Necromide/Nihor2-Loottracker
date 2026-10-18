"""Core tests: parsing, incremental import, log rotation, run + Super-Elite detection.

Run with:  python -m unittest discover tests
"""
import os
import shutil
import tempfile
import unittest

from loottracker import analysis
from loottracker.db import Database
from loottracker.importer import Importer, parse_line
from loottracker.stats import Stats


def line(day, t, qty, item):
    return f"[{day}] [{t}]: You receive {qty} {item}.\r\n"


def elite_run(day, h, m, se=False, yang=500000):
    """A tiny elite run ending at h:m:30."""
    out = [line(day, f"{h:02d}:{m:02d}:00", 3, "Red Raw Diamond"),
           line(day, f"{h:02d}:{m:02d}:05", yang, "Yang")]
    if se:
        out += [line(day, f"{h:02d}:{m:02d}:10", 1, n) for n in
                ("Skill Book Chest [G-P]", "Skill Book Chest [M-G]", "Divine Blessing",
                 "Divine Enchanting", "Nataraja's Medallion")]
        out.append(line(day, f"{h:02d}:{m:02d}:12", 15_000_000, "Yang"))
    out += [line(day, f"{h:02d}:{m:02d}:30", 1, "Elite Splinter"),
            line(day, f"{h:02d}:{m:02d}:30", 150, "Portal Shard"),
            line(day, f"{h:02d}:{m:02d}:30", 1, "Fire Arrow Skill Book [G-P]")]
    return out


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.client = os.path.join(self.dir, "client")
        os.makedirs(os.path.join(self.client, "loot_history_archive"))
        self.active = os.path.join(self.client, "info_chat_loot.log")
        self.db = Database(os.path.join(self.dir, "t.db"))
        self.db.apply_default_aliases()
        self.imp = Importer(self.db)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.dir)

    def write(self, path, lines, mode="a"):
        with open(path, mode, encoding="utf-8", newline="") as fh:
            fh.writelines(lines)

    def sync(self):
        mts = self.imp.scan(self.client)
        if mts is not None:
            analysis.rebuild(self.db, self.db.get_settings(), mts)

    def test_parse(self):
        c = {}
        ts, q, it = parse_line("[02/10/26] [15:16:23]: You receive 3695 Yang.", c)
        self.assertEqual((q, it), (3695, "Yang"))
        self.assertEqual(ts % 86400, 15 * 3600 + 16 * 60 + 23)
        self.assertEqual(parse_line("[02/10/26] [15:16:23]: You receive 1 Skill Book Chest [G-P].", c)[2],
                         "Skill Book Chest [G-P]")
        self.assertIsNone(parse_line("   ======Friday 02/10/26=======", c))

    def test_rotation_and_runs(self):
        self.write(self.active, ["\r\n   ======Monday 12/10/26=======\r\n\r\n"] + elite_run("12/10/26", 10, 0))
        self.write(self.active, [line("12/10/26", "10:01:00", 1, "Shard")[:-2]])  # incomplete last line
        self.sync()
        n1 = self.db.conn.execute("SELECT COUNT(*) FROM drops").fetchone()[0]
        self.assertEqual(n1, 5)  # incomplete line not yet imported
        # finish line + another run with Super-Elite
        self.write(self.active, ["\r\n"] + elite_run("12/10/26", 10, 5, se=True))
        self.sync()
        # rotate: move active into archive and start a new one
        shutil.move(self.active, os.path.join(self.client, "loot_history_archive", "info_chat_loot_20261012_101000.log"))
        self.write(self.active, ["\r\n   ======Monday 12/10/26=======\r\n\r\n"] + elite_run("12/10/26", 10, 10))
        self.sync()
        self.sync()  # idempotent
        total = self.db.conn.execute("SELECT COUNT(*) FROM drops").fetchone()[0]
        self.assertEqual(total, 5 + 1 + 11 + 5)
        runs = self.db.conn.execute("SELECT type, se, se_conf FROM runs ORDER BY end").fetchall()
        self.assertEqual([tuple(r) for r in runs], [("elite", 0, None), ("elite", 1, "confirmed"), ("elite", 0, None)])

    def test_report_filters_and_sessions(self):
        self.write(self.active, elite_run("12/10/26", 10, 0) + elite_run("12/10/26", 10, 5, se=True))
        self.sync()
        st = Stats(self.db)
        s = self.db.get_settings()
        r = st.report({}, s)
        self.assertEqual(r["portals"]["elite"]["runs"], 2)
        self.assertEqual(r["super_elite"]["count"], 1)
        items = {x["item"] for x in r["portals"]["elite"]["items"]}
        self.assertNotIn("Fire Arrow Skill Book [G-P]", items)  # chest contents hidden by default
        r = st.report({"chest": "only"}, s)
        self.assertEqual({x["item"] for x in r["portals"]["elite"]["items"]}, {"Fire Arrow Skill Book [G-P]"})
        # live session covering only the second run's last 20 s
        base = self.db.conn.execute("SELECT MAX(end) FROM runs").fetchone()[0]
        self.db.conn.execute("INSERT INTO sessions(id, name, created) VALUES(1, 'x', ?)", (base - 20,))
        self.db.conn.execute("INSERT INTO segments(session_id, start, end) VALUES(1, ?, ?)", (base - 20, base))
        r = st.report({"sessions": [1]}, s)
        self.assertEqual(r["portals"]["elite"]["runs"], 1)  # run counts (splinter inside window)
        self.assertEqual(r["yang_total"], 15_000_000)      # but only drops inside the window
        self.assertEqual(r["super_elite"]["count"], 1)

    def test_german_client(self):
        d = "12/10/26"
        de = [line(d, "10:00:00", 3, "Roter Rohdiamant"),
              line(d, "10:00:10", 1, "Lektüre Truhe [G-P]"), line(d, "10:00:10", 1, "Lektüre Truhe [M-G]"),
              line(d, "10:00:11", 15_000_000, "Yang"),
              line(d, "10:00:30", 1, "Elite-Splitter"), line(d, "10:00:30", 150, "Portalscherbe"),
              line(d, "10:02:00", 1, "Roter Rohdiamant"), line(d, "10:02:30", 1, "Großer Splitter"),
              line(d, "10:04:00", 1, "Roter Rohdiamant"), line(d, "10:04:30", 1, "Mystischer Splitter")]
        en = elite_run(d, 10, 10)  # same player later on an English client
        self.write(self.active, de + en)
        self.sync()
        runs = self.db.conn.execute("SELECT type, se, se_conf FROM runs ORDER BY end").fetchall()
        self.assertEqual([tuple(r) for r in runs], [("elite", 1, "confirmed"), ("greater", 0, None),
                                                    ("mystic", 0, None), ("elite", 0, None)])
        r = Stats(self.db).report({}, self.db.get_settings())
        red = [x for x in r["portals"]["elite"]["items"] if x["item"] == "Red Raw Diamond"][0]
        self.assertEqual(red["runs"], 2)  # German and English name counted as one item


if __name__ == "__main__":
    unittest.main()
