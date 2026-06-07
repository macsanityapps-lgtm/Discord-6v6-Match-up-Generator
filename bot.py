"""
ROM 6v6 Shuffle Bot  –  Main entry point
-----------------------------------------
Run with:  python bot.py
"""

import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# ── Intents ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class ShuffleBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        """Load cogs and sync slash commands."""
        from utils.database import init_db
        await init_db()
        log.info("Database initialised.")

        for cog in ("cogs.players", "cogs.matchup", "cogs.dev", "cogs.events", "cogs.marshal"):
            await self.load_extension(cog)
            log.info("Loaded cog: %s", cog)

        # Register persistent view so buttons on old messages survive bot restarts
        from cogs.matchup import MatchupView
        self.add_view(MatchupView())

        # Sync to specific guild instantly (if GUILD_ID set), else sync globally
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synced to guild %s (instant).", guild_id)
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally (may take up to 1 hour).")

    async def on_ready(self):
        log.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="True Battlegrounds 🎮",
            )
        )

    async def on_message(self, message: discord.Message):
        """Handle !sync command directly from message."""
        if message.author.bot:
            return

        if message.content.strip().lower() == "!ping":
            await message.channel.send("🏓 Pong! Bot is alive.")
            return

        if message.content.strip().lower() == "!sync":
            # Allow anyone with manage_guild OR the bot owner
            is_owner = await self.is_owner(message.author)
            has_perm = (
                message.guild
                and message.channel.permissions_for(message.author).manage_guild
            )
            if not (is_owner or has_perm):
                await message.channel.send("❌ You need **Manage Server** permission to sync.")
                return

            guild_id = os.getenv("GUILD_ID")
            try:
                if guild_id:
                    guild = discord.Object(id=int(guild_id))
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    await message.channel.send(
                        f"✅ Synced **{len(synced)} commands** to this server instantly."
                    )
                    log.info("Manual sync: %d commands → guild %s.", len(synced), guild_id)
                else:
                    synced = await self.tree.sync()
                    await message.channel.send(
                        f"✅ Synced **{len(synced)} commands** globally (may take up to 1 hour)."
                    )
                    log.info("Manual sync: %d commands globally.", len(synced))
            except Exception as e:
                await message.channel.send(f"❌ Sync failed: {e}")
                log.error("Sync error: %s", e)

        # Don't pass !sync/!ping to the prefix command processor (avoids CommandNotFound noise)
        if not message.content.strip().lower().startswith(("!sync", "!ping")):
            await self.process_commands(message)


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN not set. Add it to your .env file."
        )

    async with ShuffleBot() as bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
