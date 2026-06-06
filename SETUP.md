# True Battlegrounds 6v6 Shuffle Bot — Setup Guide

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create your bot token
1. Go to https://discord.com/developers/applications
2. Click **New Application** → name it (e.g. "IMPT Shuffle Bot")
3. Go to **Bot** tab → click **Reset Token** → copy the token
4. Under **Privileged Gateway Intents**, enable:
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`
6. Copy the generated URL and open it in your browser to invite the bot to your server

### 3. Configure the bot
```bash
cp .env.example .env
```
Edit `.env` and paste your token:
```
DISCORD_TOKEN=your_token_here
```

### 4. Run the bot
```bash
python bot.py
```
Slash commands sync automatically on first start. It may take up to 1 hour for them to appear globally (instant in your server if you use `guild_ids`).

---

## Commands

### Player Management
| Command | Description |
|---------|-------------|
| `/register` | Register yourself with rating, role, sub-role |
| `/setrole` | Update your main role |
| `/setsubrole` | Update your class tag (shown on the card) |
| `/playerinfo [@player]` | View a player's profile & stats |
| `/leaderboard` | Top 10 players by rating |
| `/setrating @player <rating>` | **[Mod]** Set any player's rating |

### Matchup
| Command | Description |
|---------|-------------|
| `/shuffle players:@p1 @p2 … @p12` | Create a 6v6 from 12 mentions |
| `/queue` | Join matchmaking queue (auto-shuffles at 12) |
| `/leavequeue` | Leave the queue |
| `/queuelist` | See who's in the queue |

### Match Buttons
| Button | Description |
|--------|-------------|
| 🏅 Select Winner | Report which team won |
| 🛡️ Mods | View full match details (ephemeral) |
| 🔒 Lock Shuffling | **[Mod]** Prevent reshuffles |
| 🔀 Reshuffle | Re-randomise teams |

---

## Roles Reference
Each team has exactly 6 slots in this order:

| Slot | Register as | Description |
|------|-------------|-------------|
| ORB (×2) | `ORB` | Orbital role |
| UTIL/ANY (×2) | `UTIL` or `ANY` | Utility or flexible |
| PHYS DPS | `PHYS DPS` | Physical damage dealer |
| MAGIC DPS | `MAGIC DPS` | Magic damage dealer |

## Sub-Role (Class) Tags
`SA` `CH` `AI` `KA` `JM` `NL` `RK` `AB` `SN` `WL`

---

## Custom Fonts (Optional)
Place `bold.ttf` and `regular.ttf` inside the `assets/fonts/` folder to use a custom font on the matchup card. Without these files, the bot falls back to PIL's built-in font.

Recommended: **Exo 2** or **Rajdhani** from Google Fonts — both fit the ROM aesthetic.

---

## File Structure
```
├── bot.py              Main entry point
├── config.py           Bot-wide settings (roles, ratings, colours)
├── requirements.txt    Python dependencies
├── .env                Your secret token (DO NOT commit)
├── cogs/
│   ├── players.py      Player management commands
│   └── matchup.py      Shuffle + queue commands + buttons
├── utils/
│   ├── database.py     SQLite async database layer
│   ├── team_builder.py Team balancing logic
│   └── image_gen.py    Matchup card image generator
├── assets/
│   └── fonts/          Optional: bold.ttf, regular.ttf
└── data/
    └── shuffle.db      Auto-created SQLite database
```
