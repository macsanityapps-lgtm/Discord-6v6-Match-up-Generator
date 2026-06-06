"""
Bot-wide configuration constants.
Edit these values to customise the bot for your server.
"""

# ── Roles ────────────────────────────────────────────────────────────────────
# Exactly 6 role slots per team — order matters for display
TEAM_ROLES = ["ORB", "ORB", "DPS", "DPS", "UTIL/UBER", "ANY"]

# Allowed values when a player sets their role
VALID_ROLES = ["ORB", "DPS", "UTIL", "ANY"]


# ── Ratings ──────────────────────────────────────────────────────────────────
DEFAULT_RATING  = 3000
MIN_RATING      = 1000
MAX_RATING      = 5000

# ── Match ────────────────────────────────────────────────────────────────────
PLAYERS_PER_TEAM = 6
TOTAL_PLAYERS    = PLAYERS_PER_TEAM * 2   # 12

# ── Colours (used by both image gen and Discord embeds) ──────────────────────
COLOUR_TEAM1    = 0xF5B942   # gold
COLOUR_TEAM2    = 0x7C3AED   # purple
COLOUR_NEUTRAL  = 0xF5A623   # gold/orange

# ── Image dimensions ─────────────────────────────────────────────────────────
IMG_WIDTH   = 900
IMG_HEIGHT  = 520

# ── Game branding ─────────────────────────────────────────────────────────────
GAME_NAME   = "True Battlegrounds"
BOT_NAME    = "True Battlegrounds Shuffle Bot"

# ── Channel restrictions ──────────────────────────────────────────────────────
# Set to your channel's ID (right-click channel → Copy ID).
# Commands in that group will only work in that channel.
# Set to None to allow the commands anywhere.
EVENTS_CHANNEL_ID: int | None = 1512013971203559584

# ── Class definitions ─────────────────────────────────────────────────────────
# Edit data/classes.py to add/change classes & icons.
try:
    from data.classes import ICON_MAP as SUB_ROLE_ICONS, VALID_SUB_ROLES, ROLE_CLASSES
except ImportError:
    SUB_ROLE_ICONS  = {}
    VALID_SUB_ROLES = []
    ROLE_CLASSES    = {}
