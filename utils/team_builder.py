"""
Team balancing logic — True Battlegrounds 6v6.
Guarantees role balance and minimises duplicate jobs per team.
"""

import random
from itertools import combinations
from collections import Counter
from typing import TypedDict

from config import TEAM_ROLES, PLAYERS_PER_TEAM


class PlayerSlot(TypedDict):
    slot_role:  str
    discord_id: str
    username:   str
    rating:     int
    sub_role:   str
    role:       str


def _rating(p: dict) -> int:
    return p.get("rating", 3000)


def _dup_count(players: list[dict]) -> int:
    subs = [p.get("sub_role", "").upper() for p in players if p.get("sub_role")]
    return sum(c - 1 for c in Counter(subs).values() if c > 1)


def _split_score(t1: list[dict], t2: list[dict]) -> float:
    dups = (_dup_count(t1) + _dup_count(t2)) * 10_000
    diff = abs(sum(_rating(p) for p in t1) - sum(_rating(p) for p in t2))
    return dups + diff


def _split_role_group(group: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a same-role group evenly, preferring no duplicate sub_roles."""
    n = len(group)
    half = n // 2
    if n == 2:
        return [group[0]], [group[1]]

    best_t1, best_t2 = group[:half], group[half:]
    best = _split_score(best_t1, best_t2)

    for combo in combinations(range(n), half):
        t1 = [group[i] for i in combo]
        t2 = [group[i] for i in range(n) if i not in combo]
        s = _split_score(t1, t2)
        if s < best:
            best = s
            best_t1, best_t2 = t1, t2

    return best_t1, best_t2


def _balance_swap(
    team1: list[dict], team2: list[dict], max_passes: int = 30
) -> tuple[list[dict], list[dict]]:
    """Minimise rating difference via same-role swaps without increasing dups."""
    for _ in range(max_passes):
        s1 = sum(_rating(p) for p in team1)
        s2 = sum(_rating(p) for p in team2)
        if abs(s1 - s2) <= 50:
            break

        best_swap = None
        best_diff = abs(s1 - s2)
        cur_dups  = _dup_count(team1) + _dup_count(team2)

        for i, p1 in enumerate(team1):
            for j, p2 in enumerate(team2):
                if p1.get("role") != p2.get("role"):
                    continue
                if p1.get("sub_role","").upper() == p2.get("sub_role","").upper():
                    continue
                new_s1 = s1 - _rating(p1) + _rating(p2)
                new_s2 = s2 - _rating(p2) + _rating(p1)
                nd     = abs(new_s1 - new_s2)
                nt1    = team1[:i] + [p2] + team1[i+1:]
                nt2    = team2[:j] + [p1] + team2[j+1:]
                if nd < best_diff and (_dup_count(nt1) + _dup_count(nt2)) <= cur_dups:
                    best_diff = nd
                    best_swap = (i, j)

        if best_swap is None:
            break
        i, j = best_swap
        team1[i], team2[j] = team2[j], team1[i]

    return team1, team2


def _fix_duplicate_jobs(
    team1: list[dict], team2: list[dict], max_passes: int = 30
) -> tuple[list[dict], list[dict]]:
    """
    Eliminate duplicate sub_roles within each team via same-role swaps.
    Preserves role balance.
    """
    for _ in range(max_passes):
        before = _dup_count(team1) + _dup_count(team2)
        if before == 0:
            break

        best_swap  = None
        best_score = before

        for i, p1 in enumerate(team1):
            for j, p2 in enumerate(team2):
                if p1.get("role") != p2.get("role"):
                    continue
                if p1.get("sub_role","").upper() == p2.get("sub_role","").upper():
                    continue
                nt1   = team1[:i] + [p2] + team1[i+1:]
                nt2   = team2[:j] + [p1] + team2[j+1:]
                after = _dup_count(nt1) + _dup_count(nt2)
                if after < best_score:
                    best_score = after
                    best_swap  = (i, j)

        if best_swap is None:
            break
        i, j = best_swap
        team1[i], team2[j] = team2[j], team1[i]

    return team1, team2


def build_teams(players: list[dict]) -> tuple[list[PlayerSlot], list[PlayerSlot]]:
    """
    Split 12 players into two balanced teams of 6.
    Role balance guaranteed. Duplicate jobs minimised.
    """
    if len(players) != 12:
        raise ValueError(f"Expected 12 players, got {len(players)}")

    players = list(players)
    random.shuffle(players)

    role_groups: dict[str, list[dict]] = {}
    for p in players:
        role_groups.setdefault(p.get("role", "ANY"), []).append(p)

    team1: list[dict] = []
    team2: list[dict] = []

    for role, group in role_groups.items():
        group.sort(key=_rating, reverse=True)
        t1h, t2h = _split_role_group(group)
        team1.extend(t1h)
        team2.extend(t2h)

    team1, team2 = _balance_swap(team1, team2)
    team1, team2 = _fix_duplicate_jobs(team1, team2)

    return _assign_slots(team1), _assign_slots(team2)


def _assign_slots(players: list[dict]) -> list[PlayerSlot]:
    slots: list[PlayerSlot | None] = [None] * len(TEAM_ROLES)
    unassigned = list(players)

    MATCH_MAP = {
        "ORB":  ["ORB"],
        "DPS":  ["DPS"],
        "UTIL": ["UTIL/UBER"],
        "ANY":  ["ANY"],
    }

    for i, slot_role in enumerate(TEAM_ROLES):
        if slots[i] is not None:
            continue
        for p in unassigned:
            if slot_role in MATCH_MAP.get(p.get("role", "ANY"), []):
                slots[i] = _make_slot(p, slot_role)
                unassigned.remove(p)
                break

    for i, slot_role in enumerate(TEAM_ROLES):
        if slots[i] is None and unassigned:
            slots[i] = _make_slot(unassigned.pop(0), slot_role)

    return [s for s in slots if s is not None]


def _make_slot(player: dict, slot_role: str) -> PlayerSlot:
    return PlayerSlot(
        slot_role  = slot_role,
        discord_id = player["discord_id"],
        username   = player["username"],
        rating     = player["rating"],
        sub_role   = player.get("sub_role", ""),
        role       = player.get("role", "ANY"),
    )


def team_rating(slots: list[PlayerSlot]) -> int:
    return sum(s["rating"] for s in slots)


def format_teams_text(t1: list[PlayerSlot], t2: list[PlayerSlot], label: str = "") -> str:
    lines = [f"**{label}**\n"] if label else []
    for tag, slots in (("Team 1", t1), ("Team 2", t2)):
        lines.append(f"**{tag}**")
        for s in slots:
            lines.append(f"`{s['slot_role']:<10} {s['rating']:>4} {s['sub_role']:<5}` @{s['username']}")
        lines.append(f"Total: {team_rating(slots)}\n")
    return "\n".join(lines)
