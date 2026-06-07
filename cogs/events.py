"""
Events cog — track how many games each player plays during an event.

All commands live under the /event group:
  /event create     – [Mod] create a named event with a date range
  /event delete     – [Mod] delete an event
  /event list       – list all events
  /event breakdown  – per-player game count for a named event
  /event daily      – per-player game count for today (or any date)
  /event range      – per-player game count for a custom date range
"""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import EVENTS_CHANNEL_ID
from utils.database import (
    create_event,
    get_event,
    list_events,
    delete_event,
    get_player_game_counts,
    get_daily_game_counts,
)

COLOUR_EVENT = 0x7C3AED   # purple


async def _check_channel(interaction: discord.Interaction) -> bool:
    if EVENTS_CHANNEL_ID is None:
        return True
    if interaction.channel_id != EVENTS_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ Event commands can only be used in <#{EVENTS_CHANNEL_ID}>.",
            ephemeral=True,
        )
        return False
    return True


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _parse_date(raw: str) -> str | None:
    try:
        datetime.strptime(raw.strip(), "%Y-%m-%d")
        return raw.strip()
    except ValueError:
        return None


def _build_breakdown_embed(title: str, subtitle: str, rows: list[dict]) -> discord.Embed:
    embed = discord.Embed(title=title, description=subtitle, colour=COLOUR_EVENT)

    if not rows:
        embed.add_field(name="No games found", value="No matches were played in this period.", inline=False)
        return embed

    medals = ["🥇", "🥈", "🥉"] + ["▪️"] * max(0, len(rows) - 3)
    lines  = []
    for i, r in enumerate(rows):
        total   = r["wins"] + r["losses"]
        wr      = f"{r['wins']/total*100:.0f}%" if total else "—%"
        pending = r["game_count"] - (r["wins"] + r["losses"])
        pending_str = f"  *(+{pending} pending)*" if pending else ""
        lines.append(
            f"{medals[i]} **{r['username']}** — "
            f"**{r['game_count']}** games  "
            f"`W{r['wins']}/L{r['losses']}` ({wr}){pending_str}"
        )

    chunk, chunks = [], []
    for line in lines:
        chunk.append(line)
        if len("\n".join(chunk)) > 900:
            chunks.append("\n".join(chunk[:-1]))
            chunk = [line]
    chunks.append("\n".join(chunk))

    for idx, block in enumerate(chunks):
        embed.add_field(name="📊 Game Count" if idx == 0 else "​", value=block, inline=False)

    embed.set_footer(text=f"{len(rows)} players  •  avg {sum(r['game_count'] for r in rows) // (len(rows) or 1)} games each")
    return embed


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    event = app_commands.Group(name="event", description="Tournament event commands")

    # ── /event create ─────────────────────────────────────────────────────────

    @event.command(name="create", description="[Mod] Create a named event with a date range.")
    @app_commands.describe(
        name       = "Event name (e.g. 'Week 1 Tournament').",
        start_date = "Start date — YYYY-MM-DD.",
        end_date   = "End date — YYYY-MM-DD (inclusive).",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def event_create(
        self,
        interaction: discord.Interaction,
        name: str,
        start_date: str,
        end_date: str,
    ):
        if not await _check_channel(interaction):
            return
        start = _parse_date(start_date)
        end   = _parse_date(end_date)

        if not start:
            await interaction.response.send_message("❌ Invalid `start_date`. Use **YYYY-MM-DD**.", ephemeral=True)
            return
        if not end:
            await interaction.response.send_message("❌ Invalid `end_date`. Use **YYYY-MM-DD**.", ephemeral=True)
            return
        if end < start:
            await interaction.response.send_message("❌ `end_date` must be on or after `start_date`.", ephemeral=True)
            return

        event_id = await create_event(name.strip(), start, end)

        embed = discord.Embed(title="✅ Event Created", colour=COLOUR_EVENT)
        embed.add_field(name="Event", value=name.strip(), inline=False)
        embed.add_field(name="ID",    value=str(event_id), inline=True)
        embed.add_field(name="Start", value=start,         inline=True)
        embed.add_field(name="End",   value=end,           inline=True)
        embed.set_footer(text=f"Use /event breakdown event_id:{event_id} to view game counts")
        await interaction.response.send_message(embed=embed)

    # ── /event delete ─────────────────────────────────────────────────────────

    @event.command(name="delete", description="[Mod] Delete an event by ID.")
    @app_commands.describe(event_id="The numeric ID of the event to delete.")
    @app_commands.default_permissions(manage_guild=True)
    async def event_delete(self, interaction: discord.Interaction, event_id: int):
        if not await _check_channel(interaction):
            return
        deleted = await delete_event(event_id)
        if deleted:
            await interaction.response.send_message(f"✅ Event `{event_id}` deleted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Event `{event_id}` not found.", ephemeral=True)

    # ── /event list ───────────────────────────────────────────────────────────

    @event.command(name="list", description="List the 10 most recent events.")
    async def event_list(self, interaction: discord.Interaction):
        if not await _check_channel(interaction):
            return
        events = await list_events(10)
        if not events:
            await interaction.response.send_message(
                "No events yet. Mods can use `/event create` to add one.", ephemeral=True
            )
            return

        today = _today_utc()
        lines = []
        for e in events:
            if today < e["start_date"]:   status = "📅 Upcoming"
            elif today > e["end_date"]:   status = "✅ Ended"
            else:                         status = "🟢 Active"
            lines.append(
                f"`ID {e['event_id']}` **{e['name']}** — "
                f"{e['start_date']} → {e['end_date']}  {status}"
            )

        embed = discord.Embed(title="📋 Events", description="\n".join(lines), colour=COLOUR_EVENT)
        await interaction.response.send_message(embed=embed)

    # ── /event breakdown ──────────────────────────────────────────────────────

    @event.command(name="breakdown", description="Per-player game count for a specific event.")
    @app_commands.describe(event_id="The numeric ID of the event (see /event list).")
    async def event_breakdown(self, interaction: discord.Interaction, event_id: int):
        if not await _check_channel(interaction):
            return
        await interaction.response.defer()

        ev = await get_event(event_id)
        if not ev:
            await interaction.followup.send(
                f"❌ Event `{event_id}` not found. Use `/event list` to see all events.", ephemeral=True
            )
            return

        rows  = await get_player_game_counts(ev["start_date"], ev["end_date"])
        embed = _build_breakdown_embed(
            title    = f"🎮 {ev['name']} — Game Breakdown",
            subtitle = f"📅 {ev['start_date']} → {ev['end_date']}",
            rows     = rows,
        )
        embed.set_footer(text=f"Event ID: {event_id}  •  {len(rows)} players participated")
        await interaction.followup.send(embed=embed)

    # ── /event daily ──────────────────────────────────────────────────────────

    @event.command(name="daily", description="Per-player game count for today (or a specific date).")
    @app_commands.describe(date="Date in YYYY-MM-DD format. Defaults to today.")
    async def event_daily(self, interaction: discord.Interaction, date: str | None = None):
        if not await _check_channel(interaction):
            return
        await interaction.response.defer()

        if date is not None:
            target = _parse_date(date)
            if not target:
                await interaction.followup.send("❌ Invalid date. Use **YYYY-MM-DD** format.", ephemeral=True)
                return
        else:
            target = _today_utc()

        rows  = await get_daily_game_counts(target)
        embed = _build_breakdown_embed(
            title    = "📅 Daily Game Breakdown",
            subtitle = f"Date: **{target}**",
            rows     = rows,
        )
        await interaction.followup.send(embed=embed)

    # ── /event range ──────────────────────────────────────────────────────────

    @event.command(name="range", description="Per-player game count for a custom date range.")
    @app_commands.describe(
        start_date = "Start date — YYYY-MM-DD.",
        end_date   = "End date — YYYY-MM-DD (inclusive). Defaults to today.",
    )
    async def event_range(
        self,
        interaction: discord.Interaction,
        start_date: str,
        end_date: str | None = None,
    ):
        if not await _check_channel(interaction):
            return
        await interaction.response.defer()

        start = _parse_date(start_date)
        if not start:
            await interaction.followup.send("❌ Invalid `start_date`. Use **YYYY-MM-DD**.", ephemeral=True)
            return

        end = _parse_date(end_date) if end_date else _today_utc()
        if not end:
            await interaction.followup.send("❌ Invalid `end_date`. Use **YYYY-MM-DD**.", ephemeral=True)
            return
        if end < start:
            await interaction.followup.send("❌ `end_date` must be on or after `start_date`.", ephemeral=True)
            return

        rows  = await get_player_game_counts(start, end)
        embed = _build_breakdown_embed(
            title    = "📊 Game Count Breakdown",
            subtitle = f"📅 {start} → {end}",
            rows     = rows,
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
