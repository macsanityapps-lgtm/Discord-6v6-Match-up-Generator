"""
Async SQLite database layer.
Tables:
  players    – registered players with rating, role, sub_role, points
  role_stats – per-role win/loss/points breakdown for each player
  matches    – match history with winner tracking
  events     – named events with a date range for game count tracking
"""

import json
import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "shuffle.db"


async def init_db() -> None:
    """Create tables if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                discord_id    TEXT PRIMARY KEY,
                username      TEXT NOT NULL,
                rating        INTEGER NOT NULL DEFAULT 3000,
                role          TEXT NOT NULL DEFAULT 'ANY',
                sub_role      TEXT NOT NULL DEFAULT 'SA',
                wins          INTEGER NOT NULL DEFAULT 0,
                losses        INTEGER NOT NULL DEFAULT 0,
                points        INTEGER NOT NULL DEFAULT 1000,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS role_stats (
                discord_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                wins        INTEGER NOT NULL DEFAULT 0,
                losses      INTEGER NOT NULL DEFAULT 0,
                points      INTEGER NOT NULL DEFAULT 1000,
                PRIMARY KEY (discord_id, role)
            );

            CREATE TABLE IF NOT EXISTS matches (
                match_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                game_label  TEXT NOT NULL,
                team1_ids   TEXT NOT NULL,
                team2_ids   TEXT NOT NULL,
                winner      INTEGER,
                locked      INTEGER NOT NULL DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                start_date  TEXT NOT NULL,
                end_date    TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Migrate: add points column if upgrading from old DB
        try:
            await db.execute("ALTER TABLE players ADD COLUMN points INTEGER NOT NULL DEFAULT 1000")
            await db.commit()
        except Exception:
            pass


# ── Points calculation ────────────────────────────────────────────────────────

def calc_points(
    winner_avg: float,
    loser_avg: float,
) -> tuple[int, int]:
    """
    Return (win_pts, loss_pts) based on the rating difference.

    Inspired by LoL / Valorant ranked:
      - Upset win  (weaker team wins)  → bigger reward, smaller penalty
      - Even match                     → standard
      - Dominant win (stronger wins)   → smaller reward, bigger penalty
    """
    diff = winner_avg - loser_avg   # positive = winner was stronger

    if diff < -50:          # upset: winner was 50+ below loser
        return 35, -5
    elif diff < 0:          # slight upset
        return 28, -8
    elif diff <= 50:        # close match
        return 20, -12
    elif diff <= 150:       # moderate favourite
        return 15, -15
    else:                   # heavy favourite
        return 12, -18


# ── Player helpers ────────────────────────────────────────────────────────────

async def upsert_player(
    discord_id: str,
    username: str,
    rating: int | None = None,
    role: str | None = None,
    sub_role: str | None = None,
) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE discord_id = ?", (discord_id,)
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            updates = {"username": username}
            if rating   is not None: updates["rating"]   = rating
            if role     is not None: updates["role"]     = role
            if sub_role is not None: updates["sub_role"] = sub_role
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [discord_id]
            await db.execute(
                f"UPDATE players SET {set_clause} WHERE discord_id = ?", values
            )
        else:
            await db.execute(
                """INSERT INTO players (discord_id, username, rating, role, sub_role, points)
                   VALUES (?, ?, ?, ?, ?, 1000)""",
                (discord_id, username, rating or 3000, role or "ANY", sub_role or "SA"),
            )
        await db.commit()
        async with db.execute(
            "SELECT * FROM players WHERE discord_id = ?", (discord_id,)
        ) as cur:
            return dict(await cur.fetchone())


async def get_player(discord_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE discord_id = ?", (discord_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_player_by_username(username: str) -> dict | None:
    """Find a player by username (case-insensitive). Returns first match."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE LOWER(username) = LOWER(?)", (username,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_players_bulk(discord_ids: list[str]) -> list[dict]:
    if not discord_ids:
        return []
    placeholders = ", ".join("?" * len(discord_ids))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT * FROM players WHERE discord_id IN ({placeholders})",
            discord_ids,
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_leaderboard(limit: int = 10, role: str | None = None) -> list[dict]:
    """
    Top players by points.
    If role is given, pull from role_stats joined with players.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if role:
            async with db.execute(
                """
                SELECT p.username, p.role, rs.role AS slot_role,
                       rs.wins, rs.losses, rs.points
                FROM role_stats rs
                JOIN players p ON p.discord_id = rs.discord_id
                WHERE rs.role = ?
                ORDER BY rs.points DESC
                LIMIT ?
                """,
                (role, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM players ORDER BY points DESC LIMIT ?", (limit,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


async def get_role_stats(discord_id: str) -> list[dict]:
    """All role_stats rows for a player."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM role_stats WHERE discord_id = ? ORDER BY points DESC",
            (discord_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def apply_match_result(
    winner_slots: list[dict],
    loser_slots:  list[dict],
) -> dict[str, int]:
    """
    Award / deduct points for all players in a finished match.
    Returns a dict of {discord_id: points_change}.
    """
    winner_avg = sum(s["rating"] for s in winner_slots) / len(winner_slots)
    loser_avg  = sum(s["rating"] for s in loser_slots)  / len(loser_slots)
    win_pts, loss_pts = calc_points(winner_avg, loser_avg)

    changes: dict[str, int] = {}

    async with aiosqlite.connect(DB_PATH) as db:
        for slot in winner_slots:
            did  = slot["discord_id"]
            role = slot["slot_role"]
            await db.execute(
                "UPDATE players SET wins = wins+1, points = MAX(0, points+?) WHERE discord_id=?",
                (win_pts, did),
            )
            await db.execute(
                """INSERT INTO role_stats (discord_id, role, wins, losses, points)
                   VALUES (?, ?, 1, 0, ?)
                   ON CONFLICT(discord_id, role) DO UPDATE SET
                     wins   = wins + 1,
                     points = MAX(0, points + ?)""",
                (did, role, 1000 + win_pts, win_pts),
            )
            changes[did] = win_pts

        for slot in loser_slots:
            did  = slot["discord_id"]
            role = slot["slot_role"]
            await db.execute(
                "UPDATE players SET losses = losses+1, points = MAX(0, points+?) WHERE discord_id=?",
                (loss_pts, did),
            )
            await db.execute(
                """INSERT INTO role_stats (discord_id, role, wins, losses, points)
                   VALUES (?, ?, 0, 1, ?)
                   ON CONFLICT(discord_id, role) DO UPDATE SET
                     losses = losses + 1,
                     points = MAX(0, points + ?)""",
                (did, role, 1000 + loss_pts, loss_pts),
            )
            changes[did] = loss_pts

        await db.commit()

    return changes


# ── Match helpers ─────────────────────────────────────────────────────────────

async def create_match(
    game_label: str,
    team1_ids: list[str],
    team2_ids: list[str],
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO matches (game_label, team1_ids, team2_ids) VALUES (?, ?, ?)",
            (game_label, json.dumps(team1_ids), json.dumps(team2_ids)),
        )
        await db.commit()
        return cur.lastrowid


async def get_match(match_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM matches WHERE match_id = ?", (match_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
            d["team1_ids"] = json.loads(d["team1_ids"])
            d["team2_ids"] = json.loads(d["team2_ids"])
            return d


async def set_match_winner(match_id: int, winner: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE matches SET winner = ?, locked = 1 WHERE match_id = ?",
            (winner, match_id),
        )
        await db.commit()


async def lock_match(match_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE matches SET locked = 1 WHERE match_id = ?", (match_id,)
        )
        await db.commit()


# ── Event helpers ─────────────────────────────────────────────────────────────

async def create_event(name: str, start_date: str, end_date: str) -> int:
    """Create a named event. Dates are ISO strings YYYY-MM-DD. Returns event_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO events (name, start_date, end_date) VALUES (?, ?, ?)",
            (name, start_date, end_date),
        )
        await db.commit()
        return cur.lastrowid


async def get_event(event_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_events(limit: int = 10) -> list[dict]:
    """Return most recent events."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM events ORDER BY event_id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_event(event_id: int) -> bool:
    """Delete an event by ID. Returns True if a row was deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM events WHERE event_id = ?", (event_id,)
        )
        await db.commit()
        return cur.rowcount > 0


# ── Game-count helpers ────────────────────────────────────────────────────────

async def get_player_game_counts(
    start_date: str,
    end_date: str,
) -> list[dict]:
    """
    Count how many games each player appeared in between start_date and
    end_date (inclusive, YYYY-MM-DD).

    Only matches with a declared winner are counted. Reshuffled/edited
    matches never have a winner set, so they are automatically excluded —
    no double-counting possible.

    Returns list sorted by game_count DESC:
        [{"discord_id", "username", "game_count", "wins", "losses"}, ...]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT match_id, team1_ids, team2_ids, winner
            FROM matches
            WHERE DATE(created_at) BETWEEN ? AND ?
              AND winner IS NOT NULL
            """,
            (start_date, end_date),
        ) as cur:
            match_rows = await cur.fetchall()

    # Tally games, wins, losses per discord_id
    counts: dict[str, dict] = {}   # discord_id → {game_count, wins, losses}

    for row in match_rows:
        team1 = json.loads(row["team1_ids"])
        team2 = json.loads(row["team2_ids"])
        winner = row["winner"]  # 1, 2, or None

        for pid in team1:
            entry = counts.setdefault(pid, {"game_count": 0, "wins": 0, "losses": 0})
            entry["game_count"] += 1
            if winner == 1:
                entry["wins"] += 1
            elif winner == 2:
                entry["losses"] += 1

        for pid in team2:
            entry = counts.setdefault(pid, {"game_count": 0, "wins": 0, "losses": 0})
            entry["game_count"] += 1
            if winner == 2:
                entry["wins"] += 1
            elif winner == 1:
                entry["losses"] += 1

    if not counts:
        return []

    # Fetch usernames in one query
    placeholders = ", ".join("?" * len(counts))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT discord_id, username FROM players WHERE discord_id IN ({placeholders})",
            list(counts.keys()),
        ) as cur:
            name_map = {r["discord_id"]: r["username"] for r in await cur.fetchall()}

    result = []
    for pid, s in counts.items():
        result.append({
            "discord_id": pid,
            "username":   name_map.get(pid, pid),
            "game_count": s["game_count"],
            "wins":       s["wins"],
            "losses":     s["losses"],
        })
    result.sort(key=lambda x: x["game_count"], reverse=True)
    return result


async def get_daily_game_counts(date: str) -> list[dict]:
    """Shorthand for get_player_game_counts for a single day."""
    return await get_player_game_counts(date, date)
