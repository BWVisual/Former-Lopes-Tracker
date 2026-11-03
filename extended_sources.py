"""Additional Lopes Tracker sources: NCAA D-II/D-III and optional NAIA.

NCAA helper uses the public, unofficial henrygd/ncaa-api API.
NAIA helper uses MonteHall's documented keyed game logs; availability for the
current season must be confirmed with that provider. These sources are kept
separate from the ESPN collector to make their health auditable.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

import requests

LOG = logging.getLogger("lopes")
NCAA_API = (os.getenv("NCAA_API_BASE") or "https://ncaa-api.henrygd.me").rstrip("/")
MONTEHALL_API = "https://app.montehall.com/api/leagues/public"

# These field mappings are based on NCAA's published teamBoxscore.playerStats.
# Missing fields stay missing rather than being silently filled with zeroes.
NCAA_FIELDS = [
    ("MIN", "minutesPlayed"), ("FGM", "fieldGoalsMade"), ("FGA", "fieldGoalsAttempted"),
    ("3PM", "threePointsMade"), ("3PA", "threePointsAttempted"),
    ("FTM", "freeThrowsMade"), ("FTA", "freeThrowsAttempted"),
    ("OREB", "offensiveRebounds"), ("REB", "totalRebounds"),
    ("AST", "assists"), ("STL", "steals"), ("BLK", "blockedShots"),
    ("TO", "turnovers"), ("PF", "personalFouls"), ("PTS", "points"),
]


def get_json(session: requests.Session, url: str, params=None, headers=None):
    response = session.get(url, params=params or {}, headers=headers, timeout=25)
    response.raise_for_status()
    return response.json()


def key_name(value):
    import unicodedata
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def name_matches(value, candidate):
    """Supports 'First Last' and 'Last, First' but never partial surnames."""
    if key_name(value) == key_name(candidate):
        return True
    if "," in str(value):
        family, given = value.split(",", 1)
        return key_name(given + " " + family) == key_name(candidate)
    return False


def ncaa_team_name(team):
    names = team.get("names") or {}
    return [names.get("full"), names.get("short"), team.get("nameFull"), team.get("nameShort"), team.get("name")]


def ncaa_player_stats(box: dict, gameinfo: dict, player: dict, home: bool):
    """Locate a single player's stats on the verified team (not same-name opponent)."""
    from_team = (gameinfo.get("gameinfo") or gameinfo.get("gameInfo") or gameinfo).get("teams") or []
    target_ids = {str(t.get("teamId")) for t in from_team if t.get("isHome") is home}
    team_blocks = box.get("teamBoxscore") or []
    for index, block in enumerate(team_blocks):
        bid = str(block.get("teamId", ""))
        # Some NCAA records omit ids. Do NOT assume positional order of teams.
        if bid not in target_ids:
            continue
        for stat in block.get("playerStats") or []:
            full_name = stat.get("fullName") or " ".join(filter(None, [stat.get("firstName"), stat.get("lastName")]))
            if not name_matches(full_name, player["name"]):
                continue
            if player.get("athlete_id") and str(player["athlete_id"]) != str(stat.get("id", "")):
                continue
            minutes = str(stat.get("minutesPlayed") or "").strip()
            # If the roster lists someone but no recorded minutes or other box score stats, don't alert.
            has_activity = any(str(stat.get(k, "")).strip() not in ("", "0", "0.0") for _, k in NCAA_FIELDS if k != "MIN")
            if minutes in ("0", "0:00", "00:00") or (not minutes and not has_activity):
                return None
            return [{"label": label, "value": str(stat[key])} for label, key in NCAA_FIELDS if stat.get(key) is not None and str(stat[key]).strip() != ""]
    return None


def parse_ncaa_result(league: str, entry: dict, player: dict, box: dict, gameinfo: dict):
    """Convert one NCAA scoreboard game to the common Lopes Tracker result."""
    game = entry.get("game", entry)
    if str(game.get("gameState", "")).strip().lower() not in ("final", "f"):
        return None
    home = game.get("home") or {}
    away = game.get("away") or {}
    mine_home = any(key_name(n) == key_name(player["team"]) for n in ncaa_team_name(home) if n)
    mine_away = any(key_name(n) == key_name(player["team"]) for n in ncaa_team_name(away) if n)
    if mine_home == mine_away:  # do not guess when team identity is ambiguous
        return None
    mine = home if mine_home else away
    rival = away if mine_home else home
    stats = ncaa_player_stats(box, gameinfo, player, mine_home)
    if not stats:
        return None
    own_score = str(mine.get("score", ""))
    their_score = str(rival.get("score", ""))
    if not own_score.isdigit() or not their_score.isdigit():
        return None
    event_id = str(game.get("gameID") or game.get("id") or "")
    if not event_id.isdigit():
        return None
    # startTimeEpoch is UTC; use this for notification windows when available.
    epoch = game.get("startTimeEpoch")
    date = None
    try:
        if epoch is not None and str(epoch).isdigit():
            timestamp = int(epoch)
            date = datetime.fromtimestamp(timestamp / (1000 if timestamp > 1e11 else 1), timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        pass
    if not date:
        day = str(game.get("startDate") or "")
        try:
            date = datetime.strptime(day[:10], "%Y-%m-%d").replace(hour=22, tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    stats_map = {s["label"]: s["value"] for s in stats}
    return {
        "id": f"{league}:{event_id}:{player.get('athlete_id') or key_name(player['name']).replace(' ','-')}",
        "event_id": event_id, "date": date, "name": player["name"], "league": league,
        "team": player["team"], "gcu_years": player.get("gcu_years", ""),
        "opponent": next((n for n in ncaa_team_name(rival) if n), "Unknown"),
        "home": mine_home, "score_for": own_score, "score_against": their_score,
        "outcome": "W" if int(own_score) > int(their_score) else "L" if int(own_score) < int(their_score) else "T",
        "pts": stats_map.get("PTS", "—"), "reb": stats_map.get("REB", "—"),
        "ast": stats_map.get("AST", "—"), "stats": stats,
        "boxscore_url": f"https://www.ncaa.com/game/{event_id}/boxscore", "source": "NCAA.com",
    }


def collect_ncaa_results(session, players, days, date_strings):
    from time import sleep
    results = {}
    for league in ("d2", "d3"):
        selected = [p for p in players if p["league"] == league]
        if not selected:
            continue
        for yyyymmdd in date_strings:
            day = f"{yyyymmdd[:4]}/{yyyymmdd[4:6]}/{yyyymmdd[6:]}"
            url = f"{NCAA_API}/scoreboard/basketball-men/{league}/{day}/all-conf"
            try:
                scoreboard = get_json(session, url)
            except (requests.RequestException, ValueError) as exc:
                LOG.warning("NCAA %s scoreboard unavailable %s: %s", league, day, exc)
                continue
            for entry in scoreboard.get("games", []):
                game = entry.get("game") or {}
                if str(game.get("gameState", "")).lower() not in ("final", "f"):
                    continue
                teams = [game.get("home") or {}, game.get("away") or {}]
                relevant = [p for p in selected if any(any(key_name(n) == key_name(p["team"]) for n in ncaa_team_name(t) if n) for t in teams)]
                if not relevant:
                    continue
                event_id = str(game.get("gameID", ""))
                if not event_id.isdigit():
                    continue
                try:
                    info = get_json(session, f"{NCAA_API}/game/{event_id}")
                    box = get_json(session, f"{NCAA_API}/game/{event_id}/boxscore")
                except (requests.RequestException, ValueError) as exc:
                    LOG.warning("NCAA %s box unavailable for %s: %s", league, event_id, exc)
                    continue
                for p in relevant:
                    result = parse_ncaa_result(league, entry, p, box, info)
                    if result:
                        results[result["id"]] = result
                sleep(0.5)
    return list(results.values())


def collect_naia_results(session, players, days, date_strings):
    """NAIA optional MonteHall connector; current-season coverage not guaranteed.

    Uses a per-player gamelog, never league-wide scraping. Responses vary by
    provider data tier: unknown/missing fields must not generate guessed scores.
    """
    naia = [p for p in players if p["league"] == "naia"]
    if not naia:
        return []
    key = os.getenv("MONTEHALL_API_KEY", "").strip()
    if not key:
        LOG.warning("NAIA watchlist has %s players, but MONTEHALL_API_KEY isn't configured. No automatic NAIA alerts.", len(naia))
        return []
    results = []
    # Gamelog service must actually contain the current season, and include
    # player, opponent, final score and game date to qualify for push alerts.
    from datetime import datetime, timedelta
    today = datetime.strptime(date_strings[0], "%Y%m%d").date()
    after = (today - timedelta(days=days + 1)).isoformat()
    for p in naia:
        try:
            url = f"{MONTEHALL_API}/naia/players/{quote(p['name'], safe='')}/gamelog"
            payload = get_json(session, url, {"season": today.year + (today.month >= 7), "gender": "mens", "team": p["team"], "after": after, "limit": 100}, headers={"X-API-Key": key})
        except (requests.RequestException, ValueError) as exc:
            LOG.warning("NAIA gamelog not available for %s: %s", p["name"], exc)
            continue
        # The shape of the keyed provider response needs verifying against a
        # real issued key. Strictly accept records with all the required data.
        if not isinstance(payload, dict):
            LOG.warning("NAIA response for %s was not a JSON object; skipped", p["name"])
            continue
        rows = payload.get("games") or payload.get("gamelog") or payload.get("rows") or []
        if isinstance(rows, dict):
            rows = rows.get("games", [])
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get("game_date") or not row.get("opponent"):
                continue
            if not key_name(row.get("team", p["team"])) == key_name(p["team"]):
                continue
            my_points = row.get("team_points") or row.get("team_score")
            their_points = row.get("opponent_points") or row.get("opponent_score")
            game_id = row.get("game_id") or row.get("canonical_game_id")
            if any(v is None or str(v).strip() == "" for v in (my_points, their_points, game_id)):
                continue
            try:
                own = int(my_points)
                rival = int(their_points)
                game_date = datetime.fromisoformat(str(row["game_date"])[:10]).replace(hour=22, tzinfo=timezone.utc).isoformat()
            except (TypeError, ValueError):
                continue
            if not (after < game_date[:10] <= today.isoformat()):
                continue
            field_map = [("MIN", "minutes_played"), ("FGM", "fgm"), ("FGA", "fga"), ("3PM", "fgm_3"),
                         ("3PA", "fga_3"), ("FTM", "ftm"), ("FTA", "fta"), ("OREB", "offensive_rebounds"),
                         ("DREB", "defensive_rebounds"), ("REB", "rebounds"), ("AST", "assists"),
                         ("STL", "steals"), ("BLK", "blocks"), ("TO", "turnovers"), ("PF", "fouls"), ("PTS", "points")]
            stats = [{"label": label, "value": str(row[k])} for label, k in field_map if row.get(k) is not None]
            if not stats:
                continue
            results.append({
                "id": f"naia:{game_id}:{key_name(p['name']).replace(' ','-')}",
                "event_id": str(game_id), "date": game_date, "name": p["name"], "league": "naia",
                "team": p["team"], "gcu_years": p.get("gcu_years", ""),
                "opponent": row["opponent"], "home": str(row.get("home", "")).lower() in ("true", "1", "home"),
                "score_for": str(own), "score_against": str(rival),
                "outcome": "W" if own > rival else "L" if own < rival else "T",
                "pts": str(row.get("points", "—")), "reb": str(row.get("rebounds", "—")),
                "ast": str(row.get("assists", "—")), "stats": stats,
                "boxscore_url": str(row.get("boxscore_url") or "https://sport-stats.mynaia.org/"), "source": "MonteHall / NAIA",
            })
    return results
