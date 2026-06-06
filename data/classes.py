"""
═══════════════════════════════════════════════════════════════
  TRUE BATTLEGROUNDS — CLASS REFERENCE

  HOW TO EDIT:
  - Add a new class: copy any existing entry, change the code/icon/name
  - Change an icon: update the "icon" field with the filename from data/icons/
  - Move a class to a different role: change its "role" field
  - Disable a class: set "enabled": False

  ROLE VALUES: "ORB"  |  "DPS"  |  "UTIL"  |  "ANY"
═══════════════════════════════════════════════════════════════
"""

CLASSES: list[dict] = [

    # ──────────────────────────────────────────────────────────
    # 🔮 ORB — Orbital roles
    # ──────────────────────────────────────────────────────────
    {"code": "LMX",     "name": "Lui Maoxing",         "role": "ORB",  "icon": "icon_75_5.png", "enabled": True},
    {"code": "MR",      "name": "Morroc",              "role": "ORB",  "icon": "icon_76_5.png", "enabled": True},
    {"code": "HL",      "name": "Hela",                "role": "ORB",  "icon": "icon_64_5.png", "enabled": True},
    {"code": "SA",      "name": "Saint",               "role": "ORB",  "icon": "icon_5_5.png",  "enabled": True},
    {"code": "NL",      "name": "Nameless",            "role": "ORB",  "icon": "icon_78_5.png", "enabled": True},
    {"code": "NH",      "name": "Nidhogg",             "role": "ORB",  "icon": "icon_61_5.png", "enabled": True},
    {"code": "OS",      "name": "Oscar",               "role": "ORB",  "icon": "icon_82_5.png", "enabled": True},


    # ──────────────────────────────────────────────────────────
    # 🛡️ UTIL — Utility / Uber roles
    # ──────────────────────────────────────────────────────────
    {"code": "JM",      "name": "Jormungandr",         "role": "UTIL", "icon": "icon_67_5.png", "enabled": True},
    {"code": "AIS",     "name": "Ais Wallenstein",     "role": "UTIL", "icon": "icon_81_5.png", "enabled": True},
    {"code": "SB",      "name": "Soul Binder",         "role": "UTIL", "icon": "icon_18_5.png", "enabled": True},
    {"code": "CM",      "name": "Cannon Master",       "role": "UTIL", "icon": "icon_11_5.png", "enabled": True},
    {"code": "PD",      "name": "Paladin",             "role": "UTIL", "icon": "icon_9_5.png",  "enabled": True},
    {"code": "SW",      "name": "Spirit Whisperer",    "role": "UTIL", "icon": "icon_15_5.png", "enabled": True},
    {"code": "VALK",    "name": "Valkyrie",            "role": "UTIL", "icon": "icon_66_5.png", "enabled": True},
    {"code": "TK",      "name": "Apocalypse",          "role": "UTIL", "icon": "icon_19_5.png", "enabled": True},
    {"code": "HG",      "name": "Hollgrehenn",         "role": "UTIL", "icon": "icon_65_5.png", "enabled": True},
    {"code": "TH",      "name": "Thanatos",            "role": "UTIL", "icon": "icon_60_5.png", "enabled": True},
    {"code": "MR",      "name": "Morroc",              "role": "UTIL", "icon": "icon_76_5.png", "enabled": True},
    {"code": "HL",      "name": "Hela",                "role": "UTIL", "icon": "icon_64_5.png", "enabled": True},
    {"code": "NH",      "name": "Nidhogg",             "role": "UTIL", "icon": "icon_61_5.png", "enabled": True},
    {"code": "OS",      "name": "Oscar",               "role": "UTIL", "icon": "icon_82_5.png", "enabled": True},
    {"code": "AAU",     "name": "Ancient Artifact User","role": "DPS", "icon": "icon_69_5.png", "enabled": True},

    # ──────────────────────────────────────────────────────────
    # ⚔️ DPS — Damage roles
    # ──────────────────────────────────────────────────────────
    {"code": "ELI",     "name": "Elliana",             "role": "DPS",  "icon": "icon_74_5.png", "enabled": True},
    {"code": "AIS",     "name": "Ais Wallenstein",     "role": "DPS",  "icon": "icon_81_5.png", "enabled": True},
    {"code": "KF",      "name": "Kafra",               "role": "DPS",  "icon": "icon_79_5.png", "enabled": True},
    {"code": "JM",      "name": "Jormungandr",         "role": "DPS",  "icon": "icon_67_5.png", "enabled": True},
    {"code": "FR",      "name": "Fenrir",              "role": "DPS",  "icon": "icon_71_5.png", "enabled": True},
    {"code": "KH",      "name": "Khalitzburg",         "role": "DPS",  "icon": "icon_72_5.png", "enabled": True},
    {"code": "NL",      "name": "Nameless",            "role": "DPS",  "icon": "icon_78_5.png", "enabled": True},
    {"code": "SBX",     "name": "Blade Soul",          "role": "DPS",  "icon": "icon_3_5.png",  "enabled": True},
    {"code": "SH",      "name": "Stellar Hunter",      "role": "DPS",  "icon": "icon_4_5.png",  "enabled": True},
    {"code": "SR",      "name": "Sara Alin",           "role": "DPS",  "icon": "icon_73_5.png", "enabled": True},
    {"code": "TR",      "name": "Thor",                "role": "DPS",  "icon": "icon_70_5.png", "enabled": True},
    {"code": "HR",      "name": "Heinrich",            "role": "DPS",  "icon": "icon_68_5.png", "enabled": True},
    {"code": "BELL",    "name": "Bell",                "role": "UTIL", "icon": "icon_80_5.png", "enabled": True},

    # ──────────────────────────────────────────────────────────
    # ⭐ ANY — Flexible / CC builds
    # ──────────────────────────────────────────────────────────
    # ANY players can fill DPS, UTIL, or CC build slots.
    # Add icon/code here if you want class icons for flex players.

    {"code": "RM",      "name": "Runemaster",          "role": "ORB",  "icon": "icon_1_5.png",  "enabled": True},
    {"code": "AM",      "name": "Arcane Master",       "role": "ORB",  "icon": "icon_2_5.png",  "enabled": True},
    {"code": "LB",      "name": "Lightbringer",        "role": "ORB",  "icon": "icon_6_5.png",  "enabled": True},
    {"code": "NOGU",    "name": "Novice Guardian",     "role": "ORB",  "icon": "icon_15_0.png", "enabled": True},
    {"code": "Genos",   "name": "Shadow Genos",        "role": "ORB",  "icon": "icon_63_5.png", "enabled": True},
    {"code": "Saitama", "name": "Shadow Saitama",      "role": "ORB",  "icon": "icon_62_5.png",  "enabled": True},
    {"code": "OS",      "name": "Oscar",               "role": "UTIL", "icon": "icon_82_5.png", "enabled": True},
    {"code": "AAU",     "name": "Ancient Artifact User","role": "DPS", "icon": "icon_69_5.png", "enabled": True},
    {"code": "NJ",      "name": "Yamata",              "role": "DPS",  "icon": "icon_16_5.png", "enabled": True},
    {"code": "TYRANT",  "name": "Tyrant",              "role": "DPS",  "icon": "icon_17_5.png", "enabled": True},
    {"code": "RONIN",   "name": "Inferno Armor",       "role": "DPS",  "icon": "icon_20_5.png", "enabled": True},

]


# ══════════════════════════════════════════════════════════════
#  AUTO-GENERATED LOOKUPS  (do not edit below this line)
#  These are built from the CLASSES list above.
# ══════════════════════════════════════════════════════════════

def _build_icon_map() -> dict[str, str]:
    """code → icon filename (last definition wins for duplicates)."""
    return {
        c["code"].upper(): c["icon"]
        for c in CLASSES
        if c.get("enabled", True) and c.get("icon")
    }


def _build_valid_sub_roles() -> list[str]:
    """Unique list of all enabled class codes."""
    seen = set()
    result = []
    for c in CLASSES:
        if not c.get("enabled", True):
            continue
        code = c["code"].upper()
        if code not in seen:
            seen.add(code)
            result.append(code)
    return sorted(result)


def _build_role_classes() -> dict[str, list[dict]]:
    """role → list of class entries for that role."""
    result: dict[str, list[dict]] = {}
    for c in CLASSES:
        if not c.get("enabled", True):
            continue
        role = c["role"]
        result.setdefault(role, []).append(c)
    return result


# Ready-to-use exports
ICON_MAP        = _build_icon_map()
VALID_SUB_ROLES = _build_valid_sub_roles()
ROLE_CLASSES    = _build_role_classes()
