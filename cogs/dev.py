"""
Dev / testing cog.

Commands
--------
/mockdata   – seed 16 fake players and simulate several matches
/cleardata  – wipe all mock/test data (players whose ID starts with mock_ or test_)
"""

import discord
from discord import app_commands
from discord.ext import commands

from datetime import datetime, timezone

from utils.database import (
    upsert_player, apply_match_result,
    create_match, set_match_winner, DB_PATH,
)
import aiosqlite

# ── Mock player pool ──────────────────────────────────────────────────────────
# 16 players across all role types with varied ratings

MOCK_PLAYERS = [
    # ORB
    {"discord_id": "mock_001", "username": "Tongtong",    "rating": 3200, "role": "ORB",  "sub_role": "LMX"},
    {"discord_id": "mock_002", "username": "Choel",       "rating": 3100, "role": "ORB",  "sub_role": "MR"},
    {"discord_id": "mock_003", "username": "Hawi",        "rating": 3050, "role": "ORB",  "sub_role": "MR"},
    {"discord_id": "mock_004", "username": "SilentArrow", "rating": 2950, "role": "ORB",  "sub_role": "LMX"},
    # DPS
    {"discord_id": "mock_005", "username": "Barabas",     "rating": 3150, "role": "DPS",  "sub_role": "KF"},
    {"discord_id": "mock_006", "username": "Seth",        "rating": 3000, "role": "DPS",  "sub_role": "KF"},
    {"discord_id": "mock_007", "username": "Boris",       "rating": 2900, "role": "DPS",  "sub_role": "AIS"},
    {"discord_id": "mock_008", "username": "Tomioka",     "rating": 2850, "role": "DPS",  "sub_role": "FR"},
    {"discord_id": "mock_009", "username": "Mafee",       "rating": 3080, "role": "DPS",  "sub_role": "AI"},
    {"discord_id": "mock_010", "username": "TROXZ",       "rating": 3020, "role": "DPS",  "sub_role": "KA"},
    {"discord_id": "mock_011", "username": "JeFeDnZ",     "rating": 2980, "role": "DPS",  "sub_role": "AIS"},
    {"discord_id": "mock_012", "username": "Nero",        "rating": 2920, "role": "DPS",  "sub_role": "JM"},
    # UTIL/UBER
    {"discord_id": "mock_013", "username": "PontakPilot", "rating": 3000, "role": "UTIL", "sub_role": "SB"},
    {"discord_id": "mock_014", "username": "LaSaP",       "rating": 2960, "role": "UTIL", "sub_role": "NL"},
    # ANY
    {"discord_id": "mock_015", "username": "Spotted",     "rating": 3100, "role": "ANY",  "sub_role": "JM"},
    {"discord_id": "mock_016", "username": "DaneBell",    "rating": 2880, "role": "ANY",  "sub_role": "FR"},
]

# ── Simulated matches (team indices into MOCK_PLAYERS, winner = 1 or 2) ──────
# Each match uses exactly 12 of the 16 players.

MOCK_MATCHES = [
    {
        "label":   "Mock Match G1",
        "team1":   [0, 1, 4, 8,  12, 14],   # strong ORBs + mixed
        "team2":   [2, 3, 5, 9,  13, 15],
        "winner":  1,   # Team 1 wins (slightly stronger → moderate points)
    },
    {
        "label":   "Mock Match G2",
        "team1":   [0, 2, 6, 10, 13, 15],
        "team2":   [1, 3, 4, 8,  12, 14],
        "winner":  2,   # Team 2 wins (slight upset)
    },
    {
        "label":   "Mock Match G3",
        "team1":   [0, 3, 5, 11, 12, 15],
        "team2":   [1, 2, 6, 9,  13, 14],
        "winner":  1,
    },
    {
        "label":   "Mock Match G4",
        "team1":   [2, 3, 7, 11, 14, 15],   # underdog team
        "team2":   [0, 1, 4, 8,  12, 13],   # favourites
        "winner":  1,   # upset win for team1
    },
    {
        "label":   "Mock Match G5",
        "team1":   [0, 1, 4, 9,  12, 15],
        "team2":   [2, 3, 6, 10, 13, 14],
        "winner":  2,
    },
    {
        "label":   "Mock Match G6",
        "team1":   [1, 3, 5, 8,  13, 15],
        "team2":   [0, 2, 7, 11, 12, 14],
        "winner":  1,
    },
]


def _make_slot(player: dict, slot_role: str) -> dict:
    return {
        "discord_id": player["discord_id"],
        "username":   player["username"],
        "rating":     player["rating"],
        "sub_role":   player["sub_role"],
        "slot_role":  slot_role,
        "role":       player["role"],
    }


def _build_slots(indices: list[int]) -> list[dict]:
    """Assign slot roles to a list of player indices."""
    slot_order = ["ORB", "ORB", "DPS", "DPS", "UTIL/UBER", "ANY"]
    players = [MOCK_PLAYERS[i] for i in indices]

    slots  = [None] * 6
    used   = [False] * 6
    role_map = {
        "ORB":  "ORB",
        "DPS":  "DPS",
        "UTIL": "UTIL/UBER",
        "ANY":  "ANY",
    }

    for slot_i, slot_role in enumerate(slot_order):
        for p_i, p in enumerate(players):
            if used[p_i]:
                continue
            if role_map.get(p["role"]) == slot_role:
                slots[slot_i] = _make_slot(p, slot_role)
                used[p_i] = True
                break

    # Fill remaining
    leftover = [players[i] for i in range(6) if not used[i]]
    for slot_i, slot_role in enumerate(slot_order):
        if slots[slot_i] is None and leftover:
            slots[slot_i] = _make_slot(leftover.pop(0), slot_role)

    return [s for s in slots if s is not None]


class Dev(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /mockdata ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="mockdata",
        description="Seed 16 mock players and simulate 6 matches to populate all leaderboards.",
    )
    async def mockdata(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # 1. Upsert all mock players
        for p in MOCK_PLAYERS:
            await upsert_player(
                discord_id=p["discord_id"],
                username=p["username"],
                rating=p["rating"],
                role=p["role"],
                sub_role=p["sub_role"],
            )

        # 2. Simulate each match
        results_log = []
        for m in MOCK_MATCHES:
            t1_slots = _build_slots(m["team1"])
            t2_slots = _build_slots(m["team2"])
            match_id = await create_match(
                m["label"],
                [s["discord_id"] for s in t1_slots],
                [s["discord_id"] for s in t2_slots],
            )
            await set_match_winner(match_id, m["winner"])

            winning = t1_slots if m["winner"] == 1 else t2_slots
            losing  = t2_slots if m["winner"] == 1 else t1_slots
            changes = await apply_match_result(winning, losing)

            w_avg = sum(s["rating"] for s in winning) / len(winning)
            l_avg = sum(s["rating"] for s in losing)  / len(losing)
            diff  = w_avg - l_avg
            mtype = (
                "⚡ Upset"    if diff < -50 else
                "💪 Sl. Upset" if diff < 0  else
                "⚔️ Close"   if diff <= 50 else
                "👑 Dominant"
            )
            results_log.append(f"`{m['label']}` — Team {m['winner']} wins  {mtype}")

        # 3. Summary embed
        embed = discord.Embed(
            title="✅ Mock Data Loaded",
            colour=0x4ADE80,
        )
        embed.add_field(
            name=f"👥 {len(MOCK_PLAYERS)} Players Created",
            value=(
                "**ORB:** Tongtong, Choel, Hawi, SilentArrow\n"
                "**PHYS DPS:** Barabas, Seth, Boris, Tomioka\n"
                "**MAGIC DPS:** Mafee, TROXZ, JeFeDnZ, Nero\n"
                "**UTIL/ANY:** PontakPilot, LaSaP, Spotted, DaneBell"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"🎮 {len(MOCK_MATCHES)} Matches Simulated",
            value="\n".join(results_log),
            inline=False,
        )
        embed.add_field(
            name="📊 Now try these commands",
            value=(
                "`/leaderboard` — overall standings\n"
                "`/roleleaderboard role:ORB` — ORB rankings\n"
                "`/roleleaderboard role:PHYS DPS` — DPS rankings\n"
                "`/roleleaderboard role:MAGIC DPS` — Magic rankings\n"
                "`/roleleaderboard role:UTIL/ANY` — Util rankings\n"
                "`/playerinfo` — your profile (register first)"
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /cleardata ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="cleardata",
        description="[Admin] Remove all mock and test data from the database.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def cleardata(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        async with aiosqlite.connect(DB_PATH) as db:
            # Remove mock_ and test_ players
            await db.execute(
                "DELETE FROM role_stats WHERE discord_id LIKE 'mock_%' OR discord_id LIKE 'test_%' OR discord_id LIKE 'quick_%'"
            )
            await db.execute(
                "DELETE FROM players WHERE discord_id LIKE 'mock_%' OR discord_id LIKE 'test_%' OR discord_id LIKE 'quick_%'"
            )
            await db.execute(
                "DELETE FROM matches WHERE game_label LIKE 'Mock%' OR game_label LIKE 'TEST%'"
            )
            await db.commit()

        await interaction.followup.send(
            "🗑️ All mock and test data cleared.", ephemeral=True
        )


    # ── /deletematches ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="deletematches",
        description="[Mod] Delete all match records for a specific date. Defaults to today.",
    )
    @app_commands.describe(
        date    = "Date to clear in YYYY-MM-DD format. Defaults to today (UTC).",
        confirm = "Set to True to actually delete. Leave False to preview only.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def deletematches(
        self,
        interaction: discord.Interaction,
        date: str | None = None,
        confirm: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        target = date.strip() if date else datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Validate date format
        try:
            datetime.strptime(target, "%Y-%m-%d")
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid date format. Use **YYYY-MM-DD** (e.g. `2025-06-04`).",
                ephemeral=True,
            )
            return

        # Fetch matches for that date
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT match_id, game_label, winner FROM matches WHERE DATE(created_at) = ?",
                (target,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await interaction.followup.send(
                f"ℹ️ No match records found for **{target}**.",
                ephemeral=True,
            )
            return

        total    = len(rows)
        finished = sum(1 for r in rows if r["winner"] is not None)
        pending  = total - finished

        lines = []
        for r in rows:
            status = f"✅ Team {r['winner']} won" if r["winner"] else "⏳ No winner"
            lines.append(f"`ID {r['match_id']}` {r['game_label']} — {status}")

        embed = discord.Embed(
            title=f"🗑️ Matches on {target}",
            description="\n".join(lines),
            colour=0xEF4444,
        )
        embed.add_field(name="Total",    value=str(total),    inline=True)
        embed.add_field(name="Finished", value=str(finished), inline=True)
        embed.add_field(name="Pending",  value=str(pending),  inline=True)

        if not confirm:
            embed.set_footer(text="This is a preview. Run again with confirm:True to delete.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Confirmed — delete
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM matches WHERE DATE(created_at) = ?", (target,)
            )
            await db.commit()

        embed.set_footer(text=f"✅ {total} record(s) permanently deleted.")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dev(bot))
