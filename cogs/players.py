"""
Player management cog.

Slash commands
--------------
/register          – register yourself (or update your info)
/setrating         – admin: set any player's rating
/setrole           – set your main role
/setsubrole        – set your sub-role / class tag
/playerinfo        – view a player's profile + per-role stats
/leaderboard       – overall top 10 by points
/roleleaderboard   – top 10 for a specific role/position
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import VALID_ROLES, MIN_RATING, MAX_RATING
from data.classes import VALID_SUB_ROLES
from utils.database import (
    upsert_player, get_player, get_leaderboard,
    get_role_stats,
)

# All roles that can appear in a match slot (for the role leaderboard choices)
SLOT_ROLES = ["ORB", "DPS", "DPS", "UTIL/ANY"]


class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /register ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="register",
        description="Register yourself for 6v6 matchups (or update your info).",
    )
    @app_commands.describe(
        rating  = f"Your MMR / rating ({MIN_RATING}–{MAX_RATING}). Default: 3000.",
        role    = "Your main role (ORB, DPS, UTIL, ANY).",
        subrole = "Your class tag shown on the matchup card (e.g. SA, LMX, AIS …).",
    )
    async def register(
        self,
        interaction: discord.Interaction,
        rating:  int  = 3000,
        role:    str  = "ANY",
        subrole: str  = "SA",
    ):
        role    = role.upper()
        subrole = subrole.upper()

        if role not in VALID_ROLES:
            await interaction.response.send_message(
                f"❌ Invalid role `{role}`. Choose from: {', '.join(VALID_ROLES)}",
                ephemeral=True,
            )
            return

        if subrole not in VALID_SUB_ROLES:
            await interaction.response.send_message(
                f"❌ Invalid sub-role `{subrole}`. Choose from: {', '.join(VALID_SUB_ROLES)}",
                ephemeral=True,
            )
            return

        if not (MIN_RATING <= rating <= MAX_RATING):
            await interaction.response.send_message(
                f"❌ Rating must be between {MIN_RATING} and {MAX_RATING}.",
                ephemeral=True,
            )
            return

        player = await upsert_player(
            discord_id=str(interaction.user.id),
            username=interaction.user.display_name,
            rating=rating,
            role=role,
            sub_role=subrole,
        )

        embed = discord.Embed(title="✅ Registered!", colour=0x4ADE80)
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="Rating",   value=str(player["rating"]),  inline=True)
        embed.add_field(name="Role",     value=player["role"],          inline=True)
        embed.add_field(name="Sub-Role", value=player["sub_role"],      inline=True)
        embed.add_field(name="Points",   value=str(player["points"]),   inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /setrating (admin) ────────────────────────────────────────────────────

    @app_commands.command(
        name="setrating",
        description="[Mod] Set a player's MMR rating.",
    )
    @app_commands.describe(
        member = "The Discord member to update.",
        rating = "New rating value.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setrating(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        rating: int,
    ):
        if not (MIN_RATING <= rating <= MAX_RATING):
            await interaction.response.send_message(
                f"❌ Rating must be between {MIN_RATING} and {MAX_RATING}.",
                ephemeral=True,
            )
            return
        await upsert_player(
            discord_id=str(member.id),
            username=member.display_name,
            rating=rating,
        )
        await interaction.response.send_message(
            f"✅ Set **{member.display_name}**'s rating to **{rating}**.",
            ephemeral=True,
        )

    # ── /setrole ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="setrole",
        description="Update your main role for matchup balancing.",
    )
    @app_commands.describe(role="Your main role.")
    @app_commands.choices(role=[
        app_commands.Choice(name=r, value=r) for r in VALID_ROLES
    ])
    async def setrole(self, interaction: discord.Interaction, role: str):
        await upsert_player(
            discord_id=str(interaction.user.id),
            username=interaction.user.display_name,
            role=role.upper(),
        )
        await interaction.response.send_message(
            f"✅ Role updated to **{role.upper()}**.", ephemeral=True
        )

    # ── /setsubrole ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="setsubrole",
        description="Update your class tag shown on the matchup card (e.g. KF, LMX, JM, SB …).",
    )
    @app_commands.describe(subrole="Your class code. e.g. KF, LMX, JM, SB, ELI, VALK …")
    async def setsubrole(self, interaction: discord.Interaction, subrole: str):
        code = subrole.strip().upper()

        if code not in [s.upper() for s in VALID_SUB_ROLES]:
            valid_list = ", ".join(sorted(VALID_SUB_ROLES))
            await interaction.response.send_message(
                f"❌ Unknown class code `{code}`.\nValid codes: {valid_list}",
                ephemeral=True,
            )
            return

        await upsert_player(
            discord_id=str(interaction.user.id),
            username=interaction.user.display_name,
            sub_role=code,
        )
        await interaction.response.send_message(
            f"✅ Sub-role updated to **{code}**.", ephemeral=True
        )

    # ── /playerinfo ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="playerinfo",
        description="View a player's profile, overall stats, and per-role breakdown.",
    )
    @app_commands.describe(member="The player to look up. Defaults to yourself.")
    async def playerinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ):
        target = member or interaction.user
        player = await get_player(str(target.id))

        if not player:
            await interaction.response.send_message(
                f"❌ **{target.display_name}** isn't registered yet.",
                ephemeral=True,
            )
            return

        total   = player["wins"] + player["losses"]
        winrate = f"{player['wins'] / total * 100:.1f}%" if total else "—"

        # Rank label by points
        pts = player["points"]
        if pts >= 2000:   rank = "💎 Diamond"
        elif pts >= 1500: rank = "🥇 Gold"
        elif pts >= 1200: rank = "🥈 Silver"
        elif pts >= 900:  rank = "🥉 Bronze"
        else:             rank = "🪨 Iron"

        embed = discord.Embed(
            title=f"🎮 {target.display_name}",
            colour=0x4A90E8,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Rank",     value=rank,              inline=True)
        embed.add_field(name="Points",   value=f"**{pts}** pts",  inline=True)
        embed.add_field(name="Rating",   value=str(player["rating"]), inline=True)
        embed.add_field(name="Role",     value=player["role"],    inline=True)
        embed.add_field(name="Wins",     value=str(player["wins"]),   inline=True)
        embed.add_field(name="Losses",   value=str(player["losses"]), inline=True)
        embed.add_field(name="Win Rate", value=winrate,           inline=True)

        # Per-role breakdown
        role_rows = await get_role_stats(str(target.id))
        if role_rows:
            lines = []
            for r in role_rows:
                t = r["wins"] + r["losses"]
                wr = f"{r['wins']/t*100:.0f}%" if t else "—"
                lines.append(
                    f"`{r['role']:<10}` W {r['wins']} / L {r['losses']} "
                    f"({wr})  **{r['points']} pts**"
                )
            embed.add_field(
                name="📊 Per-Role Stats",
                value="\n".join(lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="leaderboard",
        description="Overall top 10 players ranked by points.",
    )
    async def leaderboard(self, interaction: discord.Interaction):
        rows = await get_leaderboard(10)
        if not rows:
            await interaction.response.send_message(
                "No players registered yet. Use `/register` to get started!",
                ephemeral=True,
            )
            return

        medals = ["🥇", "🥈", "🥉"] + ["▪️"] * 7
        lines  = []
        for i, p in enumerate(rows):
            total = p["wins"] + p["losses"]
            wr    = f"{p['wins']/total*100:.0f}%" if total else "—%"
            lines.append(
                f"{medals[i]} **{p['username']}** — **{p['points']} pts**  "
                f"`{p['role']}`  W{p['wins']}/L{p['losses']} ({wr})"
            )

        embed = discord.Embed(
            title="🏆 True Battlegrounds — Overall Leaderboard",
            description="\n".join(lines),
            colour=0xF5A623,
        )
        embed.set_footer(text="Points: Win +12~35  |  Loss −5~18  (varies by match result)")
        await interaction.response.send_message(embed=embed)

    # ── /roleleaderboard ──────────────────────────────────────────────────────

    @app_commands.command(
        name="roleleaderboard",
        description="Top 10 players for a specific role/position.",
    )
    @app_commands.describe(role="The role slot to rank.")
    @app_commands.choices(role=[
        app_commands.Choice(name="ORB",       value="ORB"),
        app_commands.Choice(name="DPS",       value="DPS"),
        app_commands.Choice(name="UTIL/UBER", value="UTIL/UBER"),
        app_commands.Choice(name="ANY",       value="ANY"),
    ])
    async def roleleaderboard(self, interaction: discord.Interaction, role: str):
        rows = await get_leaderboard(10, role=role)
        if not rows:
            await interaction.response.send_message(
                f"No stats yet for **{role}**. Play some matches first!",
                ephemeral=True,
            )
            return

        medals = ["🥇", "🥈", "🥉"] + ["▪️"] * 7
        lines  = []
        for i, r in enumerate(rows):
            total = r["wins"] + r["losses"]
            wr    = f"{r['wins']/total*100:.0f}%" if total else "—%"
            lines.append(
                f"{medals[i]} **{r['username']}** — **{r['points']} pts**  "
                f"W{r['wins']}/L{r['losses']} ({wr})"
            )

        role_icons = {
            "ORB":       "🔮",
            "DPS":       "⚔️",
            "UTIL/UBER": "🛡️",
            "ANY":       "🎯",
        }
        icon = role_icons.get(role, "🎮")

        embed = discord.Embed(
            title=f"{icon} {role} Leaderboard — True Battlegrounds",
            description="\n".join(lines),
            colour=0x4A90E8,
        )
        embed.set_footer(text="Stats tracked per role slot played in each match")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
