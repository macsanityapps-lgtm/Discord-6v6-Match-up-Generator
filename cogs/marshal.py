"""
Marshal cog — blind ban & composition submission for LAN tournaments.

Problem solved
--------------
The old way: marshal counts 3-2-1 in chat and both teams paste at the same time.
Delay / lag means one team can see the other's input before they finish typing
and change their answer on the fly.

New way
-------
Both teams click their private button → a modal pops up (visible only to them)
→ they type and submit → bot holds both answers → **reveals both at the same time
only after both teams have submitted**.

Slash commands
--------------
/marshal setup    team1 team2  – create a new match session
/marshal startban             – open the ban-submission phase
/marshal startcomp            – open the composition-submission phase
/marshal status               – show current phase + who has submitted
/marshal reset                – cancel the current phase (keep match)
/marshal endmatch             – clear everything
"""

from __future__ import annotations

from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

# ─── Match state ──────────────────────────────────────────────────────────────

class MatchState:
    def __init__(self, channel_id: int, team1: str, team2: str):
        self.channel_id = channel_id
        self.team1 = team1
        self.team2 = team2
        self.phase: str = "idle"          # idle | ban | comp

        # Ban phase
        self.team1_ban:  Optional[str] = None
        self.team2_ban:  Optional[str] = None

        # Composition phase
        self.team1_comp: Optional[str] = None
        self.team2_comp: Optional[str] = None

        # The live status embed (updated while teams submit)
        self.phase_message: Optional[discord.Message] = None

    def reset_phase(self) -> None:
        self.phase = "idle"
        self.team1_ban = self.team2_ban = None
        self.team1_comp = self.team2_comp = None
        self.phase_message = None


# Keyed by guild ID
_states: Dict[int, MatchState] = {}


def _tick(done: bool) -> str:
    return "✅" if done else "⏳"

# ─── Modals ───────────────────────────────────────────────────────────────────

class BanModal(Modal):
    banned = TextInput(
        label="Banned Job(s)",
        placeholder="e.g.  White Mage, Black Mage",
        style=discord.TextStyle.short,
        max_length=300,
    )

    def __init__(self, state: MatchState, team: int):
        team_name = state.team1 if team == 1 else state.team2
        super().__init__(title=f"🚫  Ban Submission — {team_name}")
        self.state = state
        self.team  = team

    async def on_submit(self, interaction: discord.Interaction):
        value = self.banned.value.strip()
        if self.team == 1:
            self.state.team1_ban = value
        else:
            self.state.team2_ban = value

        await interaction.response.send_message(
            "✅  **Your ban is locked in!**  Waiting for the other team…",
            ephemeral=True,
        )
        await _refresh_ban_embed(self.state)

        if self.state.team1_ban and self.state.team2_ban:
            await _reveal_bans(interaction.guild, self.state)


class CompModal(Modal):
    composition = TextInput(
        label="Team Composition",
        placeholder=(
            "Player 1: Warrior\n"
            "Player 2: White Mage\n"
            "Player 3: Black Mage\n"
            "Player 4: Monk\n"
            "Player 5: Dragoon\n"
            "Player 6: Bard"
        ),
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    def __init__(self, state: MatchState, team: int):
        team_name = state.team1 if team == 1 else state.team2
        super().__init__(title=f"⚔️  Comp Submission — {team_name}")
        self.state = state
        self.team  = team

    async def on_submit(self, interaction: discord.Interaction):
        value = self.composition.value.strip()
        if self.team == 1:
            self.state.team1_comp = value
        else:
            self.state.team2_comp = value

        await interaction.response.send_message(
            "✅  **Your composition is locked in!**  Waiting for the other team…",
            ephemeral=True,
        )
        await _refresh_comp_embed(self.state)

        if self.state.team1_comp and self.state.team2_comp:
            await _reveal_comps(interaction.guild, self.state)

# ─── Views (button rows) ──────────────────────────────────────────────────────

class BanView(View):
    def __init__(self, state: MatchState):
        super().__init__(timeout=None)
        self.state = state

        b1 = Button(label=f"Submit Ban — {state.team1}", style=discord.ButtonStyle.danger,  row=0)
        b2 = Button(label=f"Submit Ban — {state.team2}", style=discord.ButtonStyle.primary, row=0)

        async def cb1(interaction: discord.Interaction):
            if self.state.team1_ban:
                await interaction.response.send_message(
                    f"⛔  **{self.state.team1}** has already submitted a ban.", ephemeral=True
                )
                return
            await interaction.response.send_modal(BanModal(self.state, 1))

        async def cb2(interaction: discord.Interaction):
            if self.state.team2_ban:
                await interaction.response.send_message(
                    f"⛔  **{self.state.team2}** has already submitted a ban.", ephemeral=True
                )
                return
            await interaction.response.send_modal(BanModal(self.state, 2))

        b1.callback = cb1
        b2.callback = cb2
        self.add_item(b1)
        self.add_item(b2)


class CompView(View):
    def __init__(self, state: MatchState):
        super().__init__(timeout=None)
        self.state = state

        b1 = Button(label=f"Submit Comp — {state.team1}", style=discord.ButtonStyle.danger,  row=0)
        b2 = Button(label=f"Submit Comp — {state.team2}", style=discord.ButtonStyle.primary, row=0)

        async def cb1(interaction: discord.Interaction):
            if self.state.team1_comp:
                await interaction.response.send_message(
                    f"⛔  **{self.state.team1}** has already submitted a comp.", ephemeral=True
                )
                return
            await interaction.response.send_modal(CompModal(self.state, 1))

        async def cb2(interaction: discord.Interaction):
            if self.state.team2_comp:
                await interaction.response.send_message(
                    f"⛔  **{self.state.team2}** has already submitted a comp.", ephemeral=True
                )
                return
            await interaction.response.send_modal(CompModal(self.state, 2))

        b1.callback = cb1
        b2.callback = cb2
        self.add_item(b1)
        self.add_item(b2)

# ─── Live-embed helpers ───────────────────────────────────────────────────────

async def _refresh_ban_embed(state: MatchState) -> None:
    if not state.phase_message:
        return
    embed = discord.Embed(title="🚫  Ban Phase", color=0xF0A500)
    embed.add_field(
        name=f"{_tick(bool(state.team1_ban))}  {state.team1}",
        value="Submitted" if state.team1_ban else "Waiting…",
        inline=True,
    )
    embed.add_field(
        name=f"{_tick(bool(state.team2_ban))}  {state.team2}",
        value="Submitted" if state.team2_ban else "Waiting…",
        inline=True,
    )
    embed.set_footer(text="Bans are hidden until both teams submit.")
    try:
        await state.phase_message.edit(embed=embed)
    except discord.HTTPException:
        pass


async def _refresh_comp_embed(state: MatchState) -> None:
    if not state.phase_message:
        return
    embed = discord.Embed(title="⚔️  Composition Phase", color=0x3498DB)
    embed.add_field(
        name=f"{_tick(bool(state.team1_comp))}  {state.team1}",
        value="Submitted" if state.team1_comp else "Waiting…",
        inline=True,
    )
    embed.add_field(
        name=f"{_tick(bool(state.team2_comp))}  {state.team2}",
        value="Submitted" if state.team2_comp else "Waiting…",
        inline=True,
    )
    embed.set_footer(text="Compositions are hidden until both teams submit.")
    try:
        await state.phase_message.edit(embed=embed)
    except discord.HTTPException:
        pass

# ─── Reveal helpers ───────────────────────────────────────────────────────────

async def _reveal_bans(guild: discord.Guild, state: MatchState) -> None:
    channel = guild.get_channel(state.channel_id)
    if not channel:
        return

    state.phase = "idle"

    # Mark status message as done and remove buttons
    if state.phase_message:
        try:
            done = discord.Embed(title="🚫  Ban Phase — Complete", color=0xF0A500)
            done.add_field(name=f"✅  {state.team1}", value="Submitted", inline=True)
            done.add_field(name=f"✅  {state.team2}", value="Submitted", inline=True)
            await state.phase_message.edit(embed=done, view=None)
        except discord.HTTPException:
            pass

    reveal = discord.Embed(
        title="🚫  Ban Reveal",
        description="Both teams have submitted — bans are now public!",
        color=0xE74C3C,
    )
    reveal.add_field(
        name=f"🔴  {state.team1} bans:",
        value=f"```\n{state.team1_ban}\n```",
        inline=False,
    )
    reveal.add_field(
        name=f"🔵  {state.team2} bans:",
        value=f"```\n{state.team2_ban}\n```",
        inline=False,
    )
    await channel.send(embed=reveal)


async def _reveal_comps(guild: discord.Guild, state: MatchState) -> None:
    channel = guild.get_channel(state.channel_id)
    if not channel:
        return

    state.phase = "idle"

    if state.phase_message:
        try:
            done = discord.Embed(title="⚔️  Composition Phase — Complete", color=0x3498DB)
            done.add_field(name=f"✅  {state.team1}", value="Submitted", inline=True)
            done.add_field(name=f"✅  {state.team2}", value="Submitted", inline=True)
            await state.phase_message.edit(embed=done, view=None)
        except discord.HTTPException:
            pass

    reveal = discord.Embed(
        title="⚔️  Composition Reveal",
        description="Both teams have submitted — compositions are now public!",
        color=0x2ECC71,
    )
    reveal.add_field(
        name=f"🔴  {state.team1}:",
        value=f"```\n{state.team1_comp}\n```",
        inline=False,
    )
    reveal.add_field(
        name=f"🔵  {state.team2}:",
        value=f"```\n{state.team2_comp}\n```",
        inline=False,
    )
    await channel.send(embed=reveal)

# ─── Cog ──────────────────────────────────────────────────────────────────────

class MarshalCog(commands.Cog):
    """Blind ban and composition submission for tournament matches."""

    marshal = app_commands.Group(
        name="marshal",
        description="Tournament marshal commands for ban and composition phases",
    )

    # /marshal setup -----------------------------------------------------------
    @marshal.command(name="setup", description="Create a new match session")
    @app_commands.describe(team1="Name of Team 1", team2="Name of Team 2")
    async def marshal_setup(
        self, interaction: discord.Interaction, team1: str, team2: str
    ):
        state = MatchState(interaction.channel_id, team1, team2)
        _states[interaction.guild_id] = state

        embed = discord.Embed(
            title="🏆  Match Created",
            description="Use **/marshal startban** or **/marshal startcomp** to begin.",
            color=0xF1C40F,
        )
        embed.add_field(name="🔴  Team 1", value=team1, inline=True)
        embed.add_field(name="🔵  Team 2", value=team2, inline=True)
        await interaction.response.send_message(embed=embed)

    # /marshal startban --------------------------------------------------------
    @marshal.command(name="startban", description="Open the ban submission phase")
    async def marshal_startban(self, interaction: discord.Interaction):
        state = _states.get(interaction.guild_id)
        if not state:
            await interaction.response.send_message(
                "❌  No match set up. Run **/marshal setup** first.", ephemeral=True
            )
            return
        if state.phase != "idle":
            await interaction.response.send_message(
                f"❌  A **{state.phase}** phase is already running. "
                "Use **/marshal reset** to cancel it first.",
                ephemeral=True,
            )
            return

        state.phase = "ban"
        state.team1_ban = state.team2_ban = None
        state.channel_id = interaction.channel_id

        embed = discord.Embed(
            title="🚫  Ban Phase",
            description=(
                "Each team clicks **their** button to submit their ban privately.\n"
                "**Bans are hidden until both teams have submitted.**"
            ),
            color=0xF0A500,
        )
        embed.add_field(name=f"⏳  {state.team1}", value="Waiting…", inline=True)
        embed.add_field(name=f"⏳  {state.team2}", value="Waiting…", inline=True)
        embed.set_footer(text="The modal is private — only the submitter can see what they type.")

        view = BanView(state)
        await interaction.response.send_message(embed=embed, view=view)
        state.phase_message = await interaction.original_response()

    # /marshal startcomp -------------------------------------------------------
    @marshal.command(name="startcomp", description="Open the composition submission phase")
    async def marshal_startcomp(self, interaction: discord.Interaction):
        state = _states.get(interaction.guild_id)
        if not state:
            await interaction.response.send_message(
                "❌  No match set up. Run **/marshal setup** first.", ephemeral=True
            )
            return
        if state.phase != "idle":
            await interaction.response.send_message(
                f"❌  A **{state.phase}** phase is already running. "
                "Use **/marshal reset** to cancel it first.",
                ephemeral=True,
            )
            return

        state.phase = "comp"
        state.team1_comp = state.team2_comp = None
        state.channel_id = interaction.channel_id

        embed = discord.Embed(
            title="⚔️  Composition Phase",
            description=(
                "Each team clicks **their** button to submit their composition privately.\n"
                "**Compositions are hidden until both teams have submitted.**"
            ),
            color=0x3498DB,
        )
        embed.add_field(name=f"⏳  {state.team1}", value="Waiting…", inline=True)
        embed.add_field(name=f"⏳  {state.team2}", value="Waiting…", inline=True)
        embed.set_footer(text="The modal is private — only the submitter can see what they type.")

        view = CompView(state)
        await interaction.response.send_message(embed=embed, view=view)
        state.phase_message = await interaction.original_response()

    # /marshal status ----------------------------------------------------------
    @marshal.command(name="status", description="Show current match and phase status")
    async def marshal_status(self, interaction: discord.Interaction):
        state = _states.get(interaction.guild_id)
        if not state:
            await interaction.response.send_message("❌  No match set up.", ephemeral=True)
            return

        embed = discord.Embed(title="📊  Marshal Status", color=0xF1C40F)
        embed.add_field(name="🔴  Team 1", value=state.team1, inline=True)
        embed.add_field(name="🔵  Team 2", value=state.team2, inline=True)
        embed.add_field(
            name="Current Phase",
            value=state.phase.capitalize() if state.phase != "idle" else "Idle",
            inline=False,
        )

        if state.phase == "ban":
            embed.add_field(
                name="Ban Submissions",
                value=(
                    f"{_tick(bool(state.team1_ban))}  {state.team1}\n"
                    f"{_tick(bool(state.team2_ban))}  {state.team2}"
                ),
                inline=False,
            )
        elif state.phase == "comp":
            embed.add_field(
                name="Composition Submissions",
                value=(
                    f"{_tick(bool(state.team1_comp))}  {state.team1}\n"
                    f"{_tick(bool(state.team2_comp))}  {state.team2}"
                ),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /marshal reset -----------------------------------------------------------
    @marshal.command(name="reset", description="Cancel the active phase (match stays active)")
    async def marshal_reset(self, interaction: discord.Interaction):
        state = _states.get(interaction.guild_id)
        if not state:
            await interaction.response.send_message("❌  No match to reset.", ephemeral=True)
            return

        old = state.phase
        state.reset_phase()

        await interaction.response.send_message(
            f"🔄  Phase cancelled. *(was: **{old}**)*\n"
            f"Match still active: **{state.team1}** vs **{state.team2}**"
        )

    # /marshal endmatch --------------------------------------------------------
    @marshal.command(name="endmatch", description="End the match and clear all data")
    async def marshal_endmatch(self, interaction: discord.Interaction):
        _states.pop(interaction.guild_id, None)
        embed = discord.Embed(
            title="🏁  Match Ended",
            description="All data cleared. Run **/marshal setup** to start a new match.",
            color=0x95A5A6,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MarshalCog())
