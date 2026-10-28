"""Default settings and rules.

All rules that depend on the game server (portal splinters, Super-Elite
signature, chest items, categories) live here as defaults and can be changed
in the app's settings page without touching code.
"""
import copy

APP_NAME = "Nihor2 - Loottracker"
APP_VERSION = "0.3.0"

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
        # Fallback (e.g. German client, where the signature items have other names):
        # both chests away from the splinter + Yang >= yang_confirm also counts.
        "yang_fallback": True,
        # ... and NOT in the same second as the run's splinter (that would be
        # the normal end boss).
        "yang_item": "Yang",
        "yang_confirm": 1_000_000,   # Yang drop >= this within the window confirms it
        "yang_window_s": 20,
        "yang_presence_window_s": 600,  # no Yang lines at all nearby -> "no Yang data"
        "max_before_end_s": 900,     # Super-Elite must die at most this long before the splinter
    },
    # Special items: only drops from the listed sources count (no bought/traded items).
    # Sources: "<portal>_end" = end package of that portal (same second as its splinter),
    #          "super_elite" = the Super-Elite drop package.
    # "items" are name patterns ('*' wildcard), matched against German and English names.
    "tracked": [
        {"key": "bewitchment", "de": "Begleiter Verhexen", "en": "Companion Bewitchment",
         "items": ["Companion Bewitchment", "Begleiter Verhexen"],
         "sources": ["elite_end", "super_elite"]},
        {"key": "satchel", "de": "Gürteltasche", "en": "Companion's Belt Satchel", "jackpot": True,
         "items": ["Companion*Belt Satchel", "*Gürteltasche*"],
         "sources": ["super_elite"]},
    ],
    "tracked_window_s": 2,  # tolerance around the package second (log timestamps jitter slightly)
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
    {"key": "splinter", "de": "Splitter", "en": "Splinters", "patterns": ["* Splinter", "*-Splitter", "Großer Splitter", "Mystischer Splitter"]},
    {"key": "skillbook", "de": "Fertigkeitsbücher", "en": "Skill books", "patterns": ["* Skill Book [*]", "* Lektüre [*]", "Book of *"]},
    {"key": "chest", "de": "Truhen & Kisten", "en": "Chests", "patterns": ["*Chest*", "*Truhe*", "*Kiste*"]},
    {"key": "rawdiamond", "de": "Rohdiamanten", "en": "Raw diamonds", "patterns": ["* Raw Diamond", "* Rohdiamant"]},
    {"key": "gem", "de": "Edelsteine", "en": "Gemstones", "patterns": ["* Gemstone", "Lapislazuli", "Jewel of *", "Juwel der *"]},
    {"key": "belt", "de": "Gürtel", "en": "Belts", "patterns": ["* Belt", "* Gürtel"]},
    {"key": "scroll", "de": "Schriftrollen", "en": "Scrolls", "patterns": ["* Scroll", "*schriftrolle"]},
    {"key": "shard", "de": "Scherben", "en": "Shards", "patterns": ["Shard", "* Shard"]},
    {"key": "upgrade", "de": "Verzauberung & Segen", "en": "Enchanting & blessing", "patterns": ["* Enchanting", "* Blessing", "* Smithing Hammer", "* Verzaubern"]},
]

# German client name -> English name. Applied automatically so that runs and
# statistics work for German clients and for players who switched languages.
# Bump DEFAULT_ALIASES_VERSION when adding entries (they are then applied once more).
DEFAULT_ALIASES_VERSION = 2
DEFAULT_ALIASES = {
    # portals
    "Elite-Splitter": "Elite Splinter",
    "Mystischer Splitter": "Mystic Splinter",
    "Großer Splitter": "Greater Splinter",
    # Super-Elite package
    "Lektüre Truhe [G-P]": "Skill Book Chest [G-P]",
    "Lektüre Truhe [M-G]": "Skill Book Chest [M-G]",
    "Göttlicher Segen": "Divine Blessing",
    "Göttliches Verzaubern": "Divine Enchanting",
    "Natarajas Medaillon": "Nataraja's Medallion",
    "Begleiter Verhexen": "Companion Bewitchment",
    "Begleiter Siegel": "Companion Seal",
    "Begleiter Serum [50-250]": "Companion Serum [50-250]",
    "Begleiter Serum [250-500]": "Companion Serum [250-500]",
    "Begleiter Serum [500-750]": "Companion Serum [500-750]",
    "Gegenstand verhexen": "Bewitch Item",
    "Gegenstand segnen": "Blessing Item",
    "Außergewöhnliche blaue Flamme": "Exceptional Blue Flame",
    "Außergewöhnliche rote Flamme": "Exceptional Red Flame",
    "Blauer Edelstein": "Blue Gemstone",
    "Grüner Edelstein": "Green Gemstone",
    # common drops (derived from logs where the client language was switched)
    "Bruchstück": "Shard",
    "Sturmkristallsplitter": "Storm Crystal Shard",
    "Energiesplitter": "Energy Fragment",
    "Grauer Rohdiamant": "Gray Raw Diamond",
    "Violetter Rohdiamant": "Violet Raw Diamond",
    "Roter Rohdiamant": "Red Raw Diamond",
    "Grüner Rohdiamant": "Green Raw Diamond",
    "Gelber Rohdiamant": "Yellow Raw Diamond",
    "Blauer Rohdiamant": "Blue Raw Diamond",
    "Juwel der Missgunst": "Jewel of Spite",
    "Juwel der Weisheit": "Jewel of Wisdom",
    "Juwel der Niedertracht": "Jewel of Malice",
    "Verbessertes Verzaubern": "Improved Enchanting",
    "Sagenhaftes Verzaubern": "Fabled Enchanting",
    "Segensschriftrolle": "Blessing Scroll",
    "Grüner Tasman": "Green Tasman",
    "Blauer Tasman": "Blue Tasman",
    "Violetter Tasman": "Violett Tasman",
    "Gräten": "Fishbones",
    "Stück eines Eulenpasses [L]": "Piece of an Owl Pass [L]",
    "Stück eines Eulenpasses [R]": "Piece of an Owl Pass [R]",
    "Seelenkristallerz": "Soul Crystal Ore",
    "Geiststein Lava": "Lava Spirit Stone",
    "Grüner Meteor": "Green Meteor",
    "Blauer Meteor": "Blue Meteor",
    "Roter Meteor": "Red Meteor",
    "Grüner Meteorstaub": "Green Meteordust",
    "Blauer Meteorstaub": "Blue Meteordust",
    "Roter Meteorstaub": "Red Meteor Dust",
    "Trank der Hast": "Potion of Haste",
    "Rubinerz": "Ruby Ore",
    "Grüner Trank (G)": "Green Potion(L)",
    "Weiße Perle": "White Pearl",
    "Blutrote Perle": "Blood-Red Pearl",
    "Blaue Perle": "Blue Pearl",
    "Stumpfe Eulenkralle": "Dull Owl Claw",
    "Zerbrochenes Porzellan": "Broken Porcelain",
    "Prächtige Feder": "Magnificent Feather",
    "Steinstück": "Piece of Stone",
    "Rostige Degenklinge": "Rusty Blade",
    "Schatulle der Geiststeine": "Casket of Spirit Stones",
    "Kakiblüte": "Kaki Blossom",
    "Schmückende Haarnadel": "Ornamental Hairpin",
    "Seelenstein+": "Soul Stone+",
    "Mondlicht-Schatztruhe": "Moonlight Treasure Chest",
    "Stück kaputte Rüstung": "Piece of Broken Armor",
    "Stück Edelstein": "Piece of Gem",
    "Blatt": "Leaf",
    "Splitter eines legendären Seelensteins [1]": "Shard of a Legendary Soul Stone [1]",
    "Splitter eines legendären Seelensteins [2]": "Shard of a Legendary Soul Stone [2]",
    "Splitter eines legendären Seelensteins [3]": "Shard of a Legendary Soul Stone [3]",
}

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
