"""Default settings and rules.

All rules that depend on the game server (portal splinters, Super-Elite
signature, chest items, categories) live here as defaults and can be changed
in the app's settings page without touching code.
"""
import copy

APP_NAME = "Nihor2 - Loottracker"
APP_VERSION = "0.1.1"

DEFAULT_RULES = {
    # Every portal run ends with exactly one splinter drop.
    "portals": [
        {"key": "elite", "splinter": "Elite Splinter"},
        {"key": "mystic", "splinter": "Mystic Splinter"},
        {"key": "greater", "splinter": "Greater Splinter"},
    ],
    "run": {
        # A run starts with the first drop after the previous splinter, but a
        # pause longer than this (seconds) without drops starts the run later.
        "idle_gap_s": 300,
        # Runs are never considered longer than this (seconds).
        "max_duration_s": 1800,
    },
    "super_elite": {
        "portal": "elite",
        # All of these must drop in the same second ...
        "required": ["Skill Book Chest [G-P]", "Skill Book Chest [M-G]"],
        # ... together with at least `signature_min` of these ...
        "signature": ["Divine Blessing", "Divine Enchanting", "Nataraja's Medallion"],
        "signature_min": 2,
        # ... and NOT in the same second as the run's splinter (that would be
        # the normal end boss).
        "yang_item": "Yang",
        "yang_confirm": 1_000_000,   # Yang drop >= this within the window confirms it
        "yang_window_s": 20,
        "yang_presence_window_s": 600,  # no Yang lines at all nearby -> "no Yang data"
        "max_before_end_s": 900,     # Super-Elite must die at most this long before the splinter
    },
}

# Items that only come out of chests. '*' is the only wildcard.
DEFAULT_CHEST_PATTERNS = [
    "* Skill Book [G-P]",
    "* Skill Book [M-G]",
    "* Lektüre [G-P]",
    "* Lektüre [M-G]",
]

# Item categories for filtering. First matching category wins.
DEFAULT_CATEGORIES = [
    {"key": "yang", "de": "Yang", "en": "Yang", "patterns": ["Yang"]},
    {"key": "splinter", "de": "Splitter", "en": "Splinters", "patterns": ["* Splinter"]},
    {"key": "skillbook", "de": "Fertigkeitsbücher", "en": "Skill books", "patterns": ["* Skill Book [*]", "* Lektüre [*]", "Book of *"]},
    {"key": "chest", "de": "Truhen & Kisten", "en": "Chests", "patterns": ["*Chest*", "*Truhe*", "*Kiste*"]},
    {"key": "rawdiamond", "de": "Rohdiamanten", "en": "Raw diamonds", "patterns": ["* Raw Diamond"]},
    {"key": "gem", "de": "Edelsteine", "en": "Gemstones", "patterns": ["* Gemstone", "Lapislazuli", "Jewel of *"]},
    {"key": "belt", "de": "Gürtel", "en": "Belts", "patterns": ["* Belt"]},
    {"key": "scroll", "de": "Schriftrollen", "en": "Scrolls", "patterns": ["* Scroll"]},
    {"key": "shard", "de": "Scherben", "en": "Shards", "patterns": ["Shard", "* Shard"]},
    {"key": "upgrade", "de": "Verzauberung & Segen", "en": "Enchanting & blessing", "patterns": ["* Enchanting", "* Blessing", "* Smithing Hammer"]},
]

DEFAULT_SETTINGS = {
    "language": "de",
    "client_path": "",
    "rules": DEFAULT_RULES,
    "chest_patterns": DEFAULT_CHEST_PATTERNS,
    "categories": DEFAULT_CATEGORIES,
}

ACTIVE_LOG = "info_chat_loot.log"
ARCHIVE_DIR = "loot_history_archive"


def defaults():
    return copy.deepcopy(DEFAULT_SETTINGS)
