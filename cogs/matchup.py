"""
Matchup cog — the heart of the bot.

Slash commands
--------------
/shuffle       – start a 6v6 from 12 @mentions
/quickshuffle  – open a form to type/paste all 12 players at once
/testmatch     – generate a matchup with built-in fake players

Interactive buttons (on the matchup embed)
------------------------------------------
  Select Winner   – modal to pick Team 1 or Team 2
  Mods            – show match details (mod only)
  Lock Shuffling  – prevent reshuffling (mod/admin)
  Reshuffle       – re-randomise teams (if not locked)
"""

import asyncio
import io
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config import TOTAL_PLAYERS, PLAYERS_PER_TEAM, COLOUR_TEAM1, COLOUR_TEAM2, COLOUR_NEUTRAL
from utils.database import (
    get_player, get_players_bulk, get_player_by_username, upsert_player,
    create_match, get_match, set_match_winner, lock_match,
    # apply_match_result, calc_points,  # Phase 2: points system
)
from utils.team_builder import build_teams, team_rating
from utils.image_gen import generate_matchup_image


# ── Persistent state (in-memory, keyed by message_id) ─────────────────────────
# Each entry: { match_id, team1, team2, label, locked, players }
_active_matches: dict[int, dict] = {}

SLOT_ROLES = ["ORB", "ORB", "DPS", "DPS", "UTIL/UBER", "ANY"]


async def _load_match_from_message(interaction: discord.Interaction) -> dict | None:
    """
    Extract match_id from the embed footer, load the match from DB,
    and reconstruct team slot dicts from stored player IDs.
    Returns match_data dict or None (after sending an ephemeral error).
    """
    try:
        footer_text = interaction.message.embeds[0].footer.text  # "Match ID: 42"
        match_id = int(footer_text.split("Match ID:")[-1].strip())
    except (IndexError, ValueError, AttributeError):
        await interaction.response.send_message(
            "❌ Could not read match ID from this message.", ephemeral=True
        )
        return None

    match = await get_match(match_id)
    if not match:
        await interaction.response.send_message(
            f"❌ Match `{match_id}` not found in the database.", ephemeral=True
        )
        return None

    all_ids = match["team1_ids"] + match["team2_ids"]
    players  = await get_players_bulk(all_ids)
    p_map    = {p["discord_id"]: p for p in players}

    def make_slots(ids: list[str]) -> list[dict]:
        slots = []
        for i, pid in enumerate(ids):
            p = p_map.get(pid, {
                "discord_id": pid, "username": pid,
                "rating": 3000, "role": "ANY", "sub_role": "SA",
            })
            slots.append({
                "discord_id": p["discord_id"],
                "username":   p["username"],
                "rating":     p["rating"],
                "role":       p["role"],
                "sub_role":   p["sub_role"],
                "slot_role":  SLOT_ROLES[i] if i < len(SLOT_ROLES) else "ANY",
            })
        return slots

    team1 = make_slots(match["team1_ids"])
    team2 = make_slots(match["team2_ids"])
    return {
        "match_id": match_id,
        "team1":    team1,
        "team2":    team2,
        "label":    match["game_label"],
        "players":  team1 + team2,
    }


# ── Helper: build and send a matchup message ──────────────────────────────────

async def _send_matchup(
    interaction_or_channel,
    players: list[dict],
    label: str,
    is_followup: bool = False,
) -> None:
    """Core routine used by /shuffle and Reshuffle button."""
    team1_slots, team2_slots = build_teams(players)

    # Save to DB
    match_id = await create_match(
        label,
        [s["discord_id"] for s in team1_slots],
        [s["discord_id"] for s in team2_slots],
    )

    # Generate image
    img_bytes = generate_matchup_image(team1_slots, team2_slots, title=label)
    file = discord.File(io.BytesIO(img_bytes), filename="matchup.png")

    # Build embed
    embed = discord.Embed(
        title=f"{label}",
        description=f"**Game Mode:** Shuffle",
        colour=COLOUR_NEUTRAL,
        timestamp=datetime.utcnow(),
    )
    embed.set_image(url="attachment://matchup.png")
    embed.set_footer(text=f"Match ID: {match_id}")

    # Build view
    view = MatchupView(
        match_id=match_id,
        team1=team1_slots,
        team2=team2_slots,
        players=players,
        label=label,
    )

    if is_followup:
        msg = await interaction_or_channel.followup.send(
            embed=embed, file=file, view=view
        )
    else:
        await interaction_or_channel.response.send_message(
            embed=embed, file=file, view=view
        )
        msg = await interaction_or_channel.original_response()

    # Store in active matches cache
    _active_matches[msg.id] = {
        "match_id": match_id,
        "team1":    team1_slots,
        "team2":    team2_slots,
        "label":    label,
        "locked":   False,
        "players":  players,
        "message":  msg,
    }


# ── Modal: select winner ───────────────────────────────────────────────────────

class SelectWinnerModal(discord.ui.Modal, title="Select Match Winner"):
    winner_input = discord.ui.TextInput(
        label='Winning team (type "1" or "2")',
        placeholder="1",
        min_length=1,
        max_length=1,
    )

    def __init__(self, match_data: dict):
        super().__init__()
        self.match_data = match_data

    async def on_submit(self, interaction: discord.Interaction):
        val = self.winner_input.value.strip()
        if val not in ("1", "2"):
            await interaction.response.send_message(
                '❌ Enter "1" or "2".', ephemeral=True
            )
            return

        winner       = int(val)
        match_id     = self.match_data["match_id"]
        winning_team = self.match_data[f"team{winner}"]
        losing_team  = self.match_data[f"team{3 - winner}"]

        await set_match_winner(match_id, winner)

        # ── Winner embed ───────────────────────────────────────────────────────
        winner_colour = COLOUR_TEAM1 if winner == 1 else COLOUR_TEAM2
        embed = discord.Embed(
            title=f"🏆 Team {winner} Wins!",
            description=f"Match `{self.match_data['label']}` has concluded.",
            colour=winner_colour,
        )

        win_lines = "\n".join(
            f"`{s['slot_role']:<9}` **{s['username']}**"
            for s in winning_team
        )
        lose_lines = "\n".join(
            f"`{s['slot_role']:<9}` {s['username']}"
            for s in losing_team
        )
        embed.add_field(name="🥇 Winners", value=win_lines,  inline=True)
        embed.add_field(name="💀 Losers",  value=lose_lines, inline=True)
        embed.set_footer(text=f"Match ID: {match_id}")

        await interaction.response.send_message(embed=embed)
        self.match_data["locked"] = True


# ── Modal: edit players ───────────────────────────────────────────────────────

class EditPlayersModal(discord.ui.Modal, title="Edit Players — replace any line to swap"):

    player_list = discord.ui.TextInput(
        label="Players (role name sub_role — one per line)",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=2000,
    )

    label_input = discord.ui.TextInput(
        label="Match label (optional)",
        required=False,
        max_length=60,
    )

    def __init__(self, view: "MatchupView", original_message: discord.Message):
        super().__init__()
        self._view    = view
        self._message = original_message
        # Pre-fill current roster — edit any line to replace that player
        lines = []
        for i, p in enumerate(view.players, 1):
            role     = p.get("role", "ANY")
            name     = p.get("username", f"Player{i}")
            sub_role = p.get("sub_role", "SA")
            lines.append(f"{i} {role} {name} {sub_role}")
        self.player_list.default = "\n".join(lines)
        self.label_input.default = view.label

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        players, errors = _parse_player_list(self.player_list.value)

        if errors:
            msg = "**Fix these lines before shuffling:**\n" + "\n".join(errors)
            await interaction.followup.send(msg, ephemeral=True)
            return

        if len(players) != TOTAL_PLAYERS:
            await interaction.followup.send(
                f"❌ Got **{len(players)} players** — need exactly **{TOTAL_PLAYERS}**.\n"
                f"Check for blank lines or duplicates.",
                ephemeral=True,
            )
            return

        players = await _resolve_players(players)
        label   = self.label_input.value.strip() or self._view.label

        # Build new teams and update the ORIGINAL message in place
        team1_slots, team2_slots = build_teams(players)
        new_match_id = await create_match(
            label,
            [s["discord_id"] for s in team1_slots],
            [s["discord_id"] for s in team2_slots],
        )

        img_bytes = generate_matchup_image(team1_slots, team2_slots, title=label)
        file  = discord.File(io.BytesIO(img_bytes), filename="matchup.png")
        embed = discord.Embed(
            title=label,
            description="**Game Mode:** Shuffle  *(edited)*",
            colour=COLOUR_NEUTRAL,
            timestamp=datetime.utcnow(),
        )
        embed.set_image(url="attachment://matchup.png")
        embed.set_footer(text=f"Match ID: {new_match_id}")

        new_view = MatchupView(
            match_id=new_match_id,
            team1=team1_slots,
            team2=team2_slots,
            players=players,
            label=label,
        )

        await self._message.edit(embed=embed, attachments=[file], view=new_view)


# ── Button view ────────────────────────────────────────────────────────────────

class MatchupView(discord.ui.View):
    def __init__(
        self,
        match_id: int = 0,
        team1: list[dict] | None = None,
        team2: list[dict] | None = None,
        players: list[dict] | None = None,
        label: str = "",
    ):
        super().__init__(timeout=None)
        self.match_id = match_id
        self.team1    = team1 or []
        self.team2    = team2 or []
        self.players  = players or []
        self.label    = label

    # ── Select Winner ──────────────────────────────────────────────────────────

    @discord.ui.button(
        label="🏅 Select Winner",
        style=discord.ButtonStyle.success,
        custom_id="matchup:select_winner",
        row=0,
    )
    async def select_winner(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Use in-memory data if available, else load from DB
        if self.match_id and self.team1:
            data = {
                "match_id": self.match_id,
                "team1":    self.team1,
                "team2":    self.team2,
                "label":    self.label,
                "players":  self.players,
            }
        else:
            data = await _load_match_from_message(interaction)
            if data is None:
                return
        await interaction.response.send_modal(SelectWinnerModal(data))

    @discord.ui.button(
        label="🔀 Reshuffle",
        style=discord.ButtonStyle.primary,
        custom_id="matchup:reshuffle",
        row=0,
    )
    async def reshuffle(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Load from DB if in-memory state is gone (bot restarted)
        if not self.players:
            data = await _load_match_from_message(interaction)
            if data is None:
                return
            self.match_id = data["match_id"]
            self.team1    = data["team1"]
            self.team2    = data["team2"]
            self.players  = data["players"]
            self.label    = data["label"]

        await interaction.response.defer()
        try:
            team1_slots, team2_slots = build_teams(self.players)

            new_match_id = await create_match(
                self.label,
                [s["discord_id"] for s in team1_slots],
                [s["discord_id"] for s in team2_slots],
            )
            self.match_id = new_match_id
            self.team1    = team1_slots
            self.team2    = team2_slots

            img_bytes = generate_matchup_image(team1_slots, team2_slots, title=self.label)
            file  = discord.File(io.BytesIO(img_bytes), filename="matchup.png")
            embed = discord.Embed(
                title=self.label,
                description="**Game Mode:** Shuffle  *(reshuffled)*",
                colour=COLOUR_NEUTRAL,
                timestamp=datetime.utcnow(),
            )
            embed.set_image(url="attachment://matchup.png")
            embed.set_footer(text=f"Match ID: {new_match_id}")

            await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
        except Exception as e:
            await interaction.followup.send(f"❌ Reshuffle failed: {e}", ephemeral=True)

    @discord.ui.button(
        label="✏️ Edit",
        style=discord.ButtonStyle.secondary,
        custom_id="matchup:edit_players",
        row=0,
    )
    async def edit_players(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Load from DB if in-memory state is gone (bot restarted)
        if not self.players:
            data = await _load_match_from_message(interaction)
            if data is None:
                return
            self.match_id = data["match_id"]
            self.team1    = data["team1"]
            self.team2    = data["team2"]
            self.players  = data["players"]
            self.label    = data["label"]
        await interaction.response.send_modal(
            EditPlayersModal(self, interaction.message)
        )


# ── Quick-input player list parser ────────────────────────────────────────────

# Maps what the user types → internal role key
_ROLE_ALIASES = {
    # ORB
    "orb":       "ORB",
    # DPS (all variants map to DPS)
    "dps":       "DPS",
    "pdps":      "DPS",
    "mdps":      "DPS",
    "phys":      "DPS",
    "magic":     "DPS",
    "physdps":   "DPS",
    "magicdps":  "DPS",
    # UTIL / UBER
    "uty":       "UTIL",
    "util":      "UTIL",
    "utility":   "UTIL",
    "uber":      "UTIL",
    "uty/uber":  "UTIL",
    "utyuber":   "UTIL",
    "util/uber": "UTIL",
    # ANY
    "any":       "ANY",
}


def _parse_player_list(text: str) -> tuple[list[dict], list[str]]:
    """
    Parse a pasted player list into player dicts.

    Accepted line format (number prefix is optional):
        [#] <role> <name> <sub_role>

    If a player name matches an existing DB entry (mock or real),
    their saved rating and ID are reused so points accumulate correctly.

    Returns (players, errors).  DB lookup happens in on_submit (async).
    """
    players: list[dict] = []
    errors:  list[str]  = []

    for raw in text.strip().splitlines():
        line = raw.strip()
        if not line:
            continue

        tokens = line.split()

        # Strip optional leading number
        if tokens and tokens[0].rstrip(".").isdigit():
            tokens = tokens[1:]

        if len(tokens) < 3:
            errors.append(f"❌ `{raw}` — need: role  name  sub_role")
            continue

        role_raw = tokens[0].lower().replace(" ", "")
        # Last token = sub_role, everything between role and last token = name
        # This handles multi-word names like "chrollo (zzea)" correctly
        sub_role = tokens[-1].upper()
        name     = " ".join(tokens[1:-1])  # everything between role and sub_role

        if not name:
            errors.append(f"❌ `{raw}` — need: role  name  sub_role")
            continue

        role = _ROLE_ALIASES.get(role_raw)
        if role is None:
            errors.append(
                f"❌ `{raw}` — unknown role `{tokens[0]}`. "
                f"Use: orb / dps / pdps / mdps / uty / uty/uber / any"
            )
            continue

        players.append({
            "discord_id": f"quick_{name.lower().replace(' ', '_')}",
            "username":   name,
            "rating":     3000,
            "role":       role,
            "sub_role":   sub_role,
        })

    return players, errors


async def _resolve_players(players: list[dict]) -> list[dict]:
    """
    For each parsed player, check the DB by username.
    If found, use their real discord_id and rating so stats accumulate.
    If not found, upsert a new quick_ entry.
    """
    resolved = []
    for p in players:
        existing = await get_player_by_username(p["username"])
        if existing:
            resolved.append({
                "discord_id": existing["discord_id"],
                "username":   existing["username"],
                "rating":     existing["rating"],
                "role":       p["role"],
                "sub_role":   p["sub_role"],
            })
        else:
            # Create a new quick_ player
            new_p = await upsert_player(
                discord_id=p["discord_id"],
                username=p["username"],
                role=p["role"],
                sub_role=p["sub_role"],
            )
            resolved.append({
                "discord_id": new_p["discord_id"],
                "username":   new_p["username"],
                "rating":     new_p["rating"],
                "role":       p["role"],
                "sub_role":   p["sub_role"],
            })
    return resolved


# ── Quick-shuffle modal ────────────────────────────────────────────────────────

class QuickShuffleModal(discord.ui.Modal, title="Quick Shuffle — Enter 12 Players"):

    player_list = discord.ui.TextInput(
        label="Players (role name sub_role — one per line)",
        style=discord.TextStyle.paragraph,
        placeholder="1 Orb awie lmx\n2 Orb jer LMX\n3 DPS MrBrown Jm\n4 UTY tomioka nl",
        min_length=10,
        max_length=2000,
    )

    label_input = discord.ui.TextInput(
        label="Match label (optional)",
        placeholder="e.g. True Battlegrounds G1",
        required=False,
        max_length=60,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        players, errors = _parse_player_list(self.player_list.value)

        if errors:
            msg = "**Fix these lines before shuffling:**\n" + "\n".join(errors)
            await interaction.followup.send(msg, ephemeral=True)
            return

        if len(players) != TOTAL_PLAYERS:
            await interaction.followup.send(
                f"❌ Got **{len(players)} players** — need exactly **{TOTAL_PLAYERS}**.\n"
                f"Check for blank lines or duplicates.",
                ephemeral=True,
            )
            return

        # Resolve names → DB entries (reuses mock/real players if name matches)
        players = await _resolve_players(players)

        label = (
            self.label_input.value.strip()
            or f"True Battlegrounds G1  {datetime.utcnow().strftime('%m/%d')}"
        )

        await _send_matchup(interaction, players, label, is_followup=True)


# ── Matchup cog ────────────────────────────────────────────────────────────────

class Matchup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Player pool waiting for a match  {guild_id: [player_dict, ...]}
        self._queue: dict[int, list[dict]] = {}

    # ── /shuffle ───────────────────────────────────────────────────────────────

    @app_commands.command(
        name="shuffle",
        description="Generate a balanced 6v6 matchup. Mention exactly 12 registered players.",
    )
    @app_commands.describe(
        players="Mention all 12 players separated by spaces, e.g. @Alice @Bob …",
        label="Optional match label (default: MP* G1 <date>).",
    )
    async def shuffle(
        self,
        interaction: discord.Interaction,
        players: str,
        label: str | None = None,
    ):
        await interaction.response.defer()

        # Parse mentions
        member_ids: list[int] = []
        for token in players.split():
            token = token.strip("<@!>")
            if token.isdigit():
                member_ids.append(int(token))

        member_ids = list(dict.fromkeys(member_ids))   # deduplicate

        if len(member_ids) != TOTAL_PLAYERS:
            await interaction.followup.send(
                f"❌ Please mention exactly **{TOTAL_PLAYERS} unique players** "
                f"(got {len(member_ids)}).\n"
                f"Usage: `/shuffle players:@p1 @p2 … @p12`",
                ephemeral=True,
            )
            return

        # Fetch from DB
        player_rows = await get_players_bulk([str(mid) for mid in member_ids])
        found_ids = {p["discord_id"] for p in player_rows}

        # For unregistered players, create a default entry on the fly
        for mid in member_ids:
            if str(mid) not in found_ids:
                member = interaction.guild.get_member(mid)
                if not member:
                    try:
                        member = await interaction.guild.fetch_member(mid)
                    except discord.NotFound:
                        pass
                name = member.display_name if member else str(mid)
                p = await upsert_player(str(mid), name)
                player_rows.append(p)

        if label is None:
            label = f"True Battlegrounds G1  {datetime.utcnow().strftime('%m/%d')}"

        await _send_matchup(interaction, player_rows, label, is_followup=True)

    # ── /quickshuffle ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="quickshuffle",
        description="Open a form to type all 12 players (role, name, sub-role) and generate a matchup.",
    )
    async def quickshuffle(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(QuickShuffleModal())
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to open form: {e}", ephemeral=True
            )

    # ── /testmatch ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="testmatch",
        description="Generate a matchup using 12 built-in fake players (for testing).",
    )
    async def testmatch(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            label = f"TEST G1  {datetime.utcnow().strftime('%m/%d')}"
            await _send_matchup(interaction, TEST_PLAYERS, label, is_followup=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error generating matchup: {e}")

    # ── /queue group ───────────────────────────────────────────────────────────

    queue_group = app_commands.Group(
        name="queue",
        description="Matchmaking queue commands",
    )

    @queue_group.command(name="join", description="Join the matchmaking queue. 12 players = auto-shuffle.")
    async def queue_join(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if gid not in self._queue:
            self._queue[gid] = []

        uid = str(interaction.user.id)
        if any(p["discord_id"] == uid for p in self._queue[gid]):
            await interaction.response.send_message(
                "⚠️ You're already in the queue.", ephemeral=True
            )
            return

        player = await get_player(uid)
        if not player:
            player = await upsert_player(uid, interaction.user.display_name)

        self._queue[gid].append(player)
        count = len(self._queue[gid])

        await interaction.response.send_message(
            f"✅ **{interaction.user.display_name}** joined the queue. "
            f"({count}/{TOTAL_PLAYERS})",
        )

        if count == TOTAL_PLAYERS:
            players = self._queue.pop(gid)
            label = f"True Battlegrounds G1  {datetime.utcnow().strftime('%m/%d')}"
            await interaction.channel.send("🎮 Queue full! Starting match…")
            await _send_channel(interaction.channel, players, label)

    @queue_group.command(name="leave", description="Leave the matchmaking queue.")
    async def queue_leave(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        uid = str(interaction.user.id)
        queue = self._queue.get(gid, [])
        before = len(queue)
        self._queue[gid] = [p for p in queue if p["discord_id"] != uid]
        if len(self._queue[gid]) < before:
            await interaction.response.send_message(
                f"✅ Removed from queue. ({len(self._queue[gid])}/{TOTAL_PLAYERS})",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "⚠️ You weren't in the queue.", ephemeral=True
            )

    @queue_group.command(name="list", description="See who's currently in the queue.")
    async def queue_list(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        queue = self._queue.get(gid, [])
        if not queue:
            await interaction.response.send_message(
                "Queue is empty. Use `/queue join` to join!", ephemeral=True
            )
            return

        lines = [f"{i+1}. @{p['username']}  ({p['rating']} MMR)"
                 for i, p in enumerate(queue)]
        embed = discord.Embed(
            title=f"🎮 Queue  ({len(queue)}/{TOTAL_PLAYERS})",
            description="\n".join(lines),
            colour=COLOUR_NEUTRAL,
        )
        await interaction.response.send_message(embed=embed)

    # \u2500\u2500 /setwinner \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

    @app_commands.command(
        name="setwinner",
        description="[Mod] Manually set the winner for a match by its ID.",
    )
    @app_commands.describe(
        match_id = "The Match ID shown in the embed footer.",
        winner   = "Winning team: 1 or 2.",
    )
    @app_commands.choices(winner=[
        app_commands.Choice(name="Team 1", value=1),
        app_commands.Choice(name="Team 2", value=2),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def setwinner(
        self,
        interaction: discord.Interaction,
        match_id: int,
        winner: int,
    ):
        await interaction.response.defer(ephemeral=True)

        match = await get_match(match_id)
        if not match:
            await interaction.followup.send(
                f"\u274c Match `{match_id}` not found.", ephemeral=True
            )
            return

        if match.get("winner") is not None:
            await interaction.followup.send(
                f"\u26a0\ufe0f Match `{match_id}` already has Team {match['winner']} as winner.",
                ephemeral=True,
            )
            return

        await set_match_winner(match_id, winner)

        all_ids  = match["team1_ids"] + match["team2_ids"]
        players  = await get_players_bulk(all_ids)
        p_map    = {p["discord_id"]: p for p in players}
        slot_roles = ["ORB", "ORB", "DPS", "DPS", "UTIL/UBER", "ANY"]

        def make_slots(ids):
            return [
                {
                    "username":  p_map.get(pid, {"username": pid})["username"],
                    "slot_role": slot_roles[i] if i < len(slot_roles) else "ANY",
                }
                for i, pid in enumerate(ids)
            ]

        winning = make_slots(match[f"team{winner}_ids"])
        losing  = make_slots(match[f"team{3 - winner}_ids"])

        winner_colour = COLOUR_TEAM1 if winner == 1 else COLOUR_TEAM2
        embed = discord.Embed(
            title=f"\U0001f3c6 Team {winner} Wins!",
            description=f"Match `{match['game_label']}` result set manually.",
            colour=winner_colour,
        )
        win_lines  = "\n".join(f"`{s['slot_role']:<9}` **{s['username']}**" for s in winning)
        lose_lines = "\n".join(f"`{s['slot_role']:<9}` {s['username']}" for s in losing)
        embed.add_field(name="\U0001f947 Winners", value=win_lines,  inline=True)
        embed.add_field(name="\U0001f480 Losers",  value=lose_lines, inline=True)
        embed.set_footer(text=f"Match ID: {match_id}  \u2022  Set by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=False)


async def _send_channel(channel, players, label):
    team1_slots, team2_slots = build_teams(players)
    match_id = await create_match(
        label,
        [s["discord_id"] for s in team1_slots],
        [s["discord_id"] for s in team2_slots],
    )
    img_bytes = generate_matchup_image(team1_slots, team2_slots, title=label)
    file = discord.File(io.BytesIO(img_bytes), filename="matchup.png")
    embed = discord.Embed(
        title=label, description="**Game Mode:** Shuffle",
        colour=COLOUR_NEUTRAL, timestamp=datetime.utcnow(),
    )
    embed.set_image(url="attachment://matchup.png")
    embed.set_footer(text=f"Match ID: {match_id}")
    view = MatchupView(match_id=match_id, team1=team1_slots, team2=team2_slots,
                       players=players, label=label)
    await channel.send(embed=embed, file=file, view=view)


TEST_PLAYERS = [
    {"discord_id": "test_001", "username": "Berz",     "rating": 3200, "role": "ORB",  "sub_role": "SA"},
    {"discord_id": "test_002", "username": "merpmerp", "rating": 3100, "role": "ORB",  "sub_role": "LMX"},
    {"discord_id": "test_003", "username": "Mafee",    "rating": 3050, "role": "DPS",  "sub_role": "AI"},
    {"discord_id": "test_004", "username": "TROXZ",    "rating": 3000, "role": "DPS",  "sub_role": "KA"},
    {"discord_id": "test_005", "username": "Sham",     "rating": 2980, "role": "UTIL", "sub_role": "JM"},
    {"discord_id": "test_006", "username": "XxGridxX", "rating": 2950, "role": "ANY",  "sub_role": "NL"},
    {"discord_id": "test_007", "username": "Lovent",   "rating": 3150, "role": "ORB",  "sub_role": "SA"},
    {"discord_id": "test_008", "username": "AwiE",     "rating": 3080, "role": "ORB",  "sub_role": "LMX"},
    {"discord_id": "test_009", "username": "BORIS",    "rating": 3020, "role": "DPS",  "sub_role": "AIS"},
    {"discord_id": "test_010", "username": "Knackss",  "rating": 2990, "role": "DPS",  "sub_role": "KA"},
    {"discord_id": "test_011", "username": "Azh",      "rating": 2960, "role": "UTIL", "sub_role": "JM"},
    {"discord_id": "test_012", "username": "LaSaP",    "rating": 3096, "role": "ANY",  "sub_role": "NL"},
]


async def setup(bot):
    await bot.add_cog(Matchup(bot))
