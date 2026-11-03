#!/usr/bin/env python3
"""Lopes Tracker — six US basketball competitions and per-game phone alerts.

Uses unofficial ESPN endpoints. Review usage terms; expect occasional changes.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TZ = ZoneInfo("America/Phoenix")
API = "https://site.api.espn.com/apis/site/v2/sports/basketball"
LEAGUES = {
    "d1": {"espn": "mens-college-basketball", "url": "mens-college-basketball"},
    "gleague": {"espn": "nba-development", "url": "nba-development"},
    "nba": {"espn": "nba", "url": "nba"},
    "d2": {}, "d3": {}, "naia": {},
}
LEAGUE_LABELS = {
    "d1": "NCAA DIVISION I", "d2": "NCAA DIVISION II", "d3": "NCAA DIVISION III",
    "naia": "NAIA", "gleague": "NBA G LEAGUE", "nba": "NBA",
}
LOG = logging.getLogger("lopes")


def session_with_retries() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": "LopesTracker/1.0 personal basketball tracker", "Accept": "application/json"})
    return session


def get_json(session: requests.Session, endpoint: str, params: dict) -> dict:
    response = session.get(endpoint, params=params, timeout=22)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"Unexpected JSON structure at {endpoint}")
    return result


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def normalized(value) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def team_matches(team: dict, player: dict) -> bool:
    if player.get("team_id") and str(player["team_id"]) == str(team.get("id", "")):
        return True
    # Exact matching prevents e.g. San Diego from matching San Diego State.
    target = normalized(player.get("team"))
    return bool(target) and target in {
        normalized(team.get(field))
        for field in ("location", "displayName", "shortDisplayName", "name", "abbreviation")
    }


def athlete_matches(athlete: dict, player: dict) -> bool:
    if player.get("athlete_id"):
        return str(athlete.get("id", "")) == str(player["athlete_id"])
    target = normalized(player.get("name"))
    return bool(target) and target in {
        normalized(athlete.get("displayName")),
        normalized(athlete.get("fullName")),
        normalized(athlete.get("shortName")),
    }


def get_score(competitor: dict) -> str:
    score = competitor.get("score", "")
    if isinstance(score, dict):
        return str(score.get("displayValue", score.get("value", "")))
    return str(score)


def find_player_statistics(summary: dict, player: dict, team_id: str):
    """Return all reported labels + values, or None if athlete did not play.

    ESPN's boxscore has groups such as 'starters' and 'bench'; each group
    contains names/labels and a separate athletes array.
    """
    for block in summary.get("boxscore", {}).get("players", []):
        block_team = block.get("team", {})
        if str(block_team.get("id", "")) != str(team_id):
            continue
        for category in block.get("statistics", []):
            raw_labels = category.get("labels") or category.get("names") or []
            for entry in category.get("athletes", []):
                if not athlete_matches(entry.get("athlete", {}), player):
                    continue
                if entry.get("didNotPlay") is True or entry.get("did_not_play") is True:
                    return None
                if entry.get("reason") and not entry.get("stats"):
                    return None
                values = entry.get("stats") or []
                if not values:
                    return None
                labels = raw_labels if len(raw_labels) == len(values) else category.get("names", [])
                if len(labels) != len(values):
                    labels = [f"STAT {i+1}" for i in range(len(values))]
                stats = [{"label": str(label), "value": str(value)} for label, value in zip(labels, values)]
                if all(normalized(s["value"]) in ("", "dnp", "did not play", "") for s in stats):
                    return None
                return stats
    return None


def stat_value(stats: list[dict], aliases: tuple[str, ...]) -> str:
    for row in stats:
        if normalized(row["label"]) in {normalized(alias) for alias in aliases}:
            return row["value"]
    return "—"


def parse_result(league: str, event: dict, player: dict, summary: dict) -> dict | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competitors = competitions[0].get("competitors") or []
    mine = next((c for c in competitors if team_matches(c.get("team") or {}, player)), None)
    if not mine or len(competitors) < 2:
        return None
    opponents = [c for c in competitors if c is not mine]
    if not opponents:
        return None
    theirs = opponents[0]
    my_team = mine["team"]
    their_team = theirs.get("team") or {}
    stats = find_player_statistics(summary, player, str(my_team.get("id", "")))
    if not stats:
        return None
    date = event.get("date", "")
    my_score = get_score(mine)
    their_score = get_score(theirs)
    if not my_score or not their_score:
        return None
    try:
        score_diff = float(my_score) - float(their_score)
    except ValueError:
        score_diff = 0
    outcome = "W" if score_diff > 0 else "L" if score_diff < 0 else "T"
    event_id = str(event.get("id", ""))
    athlete_id = str(player.get("athlete_id") or normalized(player["name"]).replace(" ", "-"))
    url_league = LEAGUES[league]["url"]
    return {
        "id": f"{league}:{event_id}:{athlete_id}",
        "event_id": event_id,
        "date": date,
        "name": player["name"],
        "league": league,
        "team": player["team"],
        "gcu_years": player.get("gcu_years", ""),
        "opponent": their_team.get("location") or their_team.get("displayName") or "Unknown",
        "home": mine.get("homeAway") == "home",
        "score_for": my_score,
        "score_against": their_score,
        "outcome": outcome,
        "pts": stat_value(stats, ("PTS", "points")),
        "reb": stat_value(stats, ("REB", "TRB", "rebounds", "totalRebounds")),
        "ast": stat_value(stats, ("AST", "assists")),
        "stats": stats,
        "boxscore_url": f"https://www.espn.com/{url_league}/boxscore/_/gameId/{event_id}",
    }


def game_is_final(event: dict) -> bool:
    status = event.get("status", {}).get("type", {})
    return status.get("completed") is True or status.get("name") == "STATUS_FINAL"


def dates_to_check(days: int, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    local_day = now.astimezone(TZ).date()
    return [(local_day - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


def collect_results(session: requests.Session, players: list[dict], days: int) -> list[dict]:
    found = {}
    for league, settings in LEAGUES.items():
        if "espn" not in settings:
            continue
        league_players = [p for p in players if p["league"] == league]
        if not league_players:
            continue
        for date in dates_to_check(days):
            params = {"dates": date, "limit": 500}
            if league == "d1":
                params["groups"] = 50  # all D-I, not ESPN's default selected games
            try:
                scoreboard = get_json(session, f"{API}/{settings['espn']}/scoreboard", params)
            except (requests.RequestException, ValueError) as exc:
                LOG.warning("Scoreboard unavailable for %s %s: %s", league, date, exc)
                continue
            for event in scoreboard.get("events", []):
                if not game_is_final(event):
                    continue
                competition = (event.get("competitions") or [{}])[0]
                teams = [c.get("team") or {} for c in competition.get("competitors", [])]
                relevant = [p for p in league_players if any(team_matches(t, p) for t in teams)]
                if not relevant:
                    continue
                event_id = str(event.get("id", ""))
                if not event_id:
                    continue
                try:
                    summary = get_json(session, f"{API}/{settings['espn']}/summary", {"event": event_id})
                except (requests.RequestException, ValueError) as exc:
                    LOG.warning("Box score unavailable %s %s: %s", league, event_id, exc)
                    continue
                for player in relevant:
                    result = parse_result(league, event, player, summary)
                    if result:
                        found[result["id"]] = result
                        LOG.info("Found: %s — %s vs %s", player["name"], date, result["opponent"])
                time.sleep(1.1)  # courtesy; ESPN has no published rate limit
    from extended_sources import collect_ncaa_results, collect_naia_results
    date_strings = dates_to_check(days)
    for item in collect_ncaa_results(session, players, days, date_strings):
        found[item["id"]] = item
    for item in collect_naia_results(session, players, days, date_strings):
        found[item["id"]] = item
    return list(found.values())


def notification_text(game: dict) -> str:
    heading = LEAGUE_LABELS.get(game["league"], game["league"].upper())
    where = "vs." if game["home"] else "at"
    lines = [
        f"🏀 LOPES TRACKER | {heading}",
        f"{game['name']} | {game['team']}",
        f"{where} {game['opponent']} — {game['outcome']} {game['score_for']}-{game['score_against']}",
        f"{game['pts']} PTS · {game['reb']} REB · {game['ast']} AST",
        " | ".join(f"{s['label']} {s['value']}" for s in game["stats"]),
        f"Full box score: {game['boxscore_url']}",
    ]
    return "\n".join(lines)


def send_alerts(session: requests.Session, games: list[dict], notified: dict, max_age_hours: int) -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    discord = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    channels = []
    if token and chat_id:
        channels.append("telegram")
    if discord:
        channels.append("discord")
    if not channels:
        LOG.info("No notification secrets configured; dashboard will still update.")
        return 0

    now = datetime.now(timezone.utc)
    sent = 0
    for game in sorted(games, key=lambda item: item["date"]):
        try:
            age = (now - datetime.fromisoformat(game["date"].replace("Z", "+00:00"))).total_seconds() / 3600
        except ValueError:
            continue
        if age < -12 or age > max_age_hours:
            continue
        for channel in channels:
            key = f"{game['id']}:{channel}"
            if key in notified:
                continue
            message = notification_text(game)
            try:
                if channel == "telegram":
                    response = session.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
                        timeout=20,
                    )
                else:
                    response = session.post(discord, json={"content": message[:1900]}, timeout=20)
                response.raise_for_status()
                notified[key] = now.isoformat()
                sent += 1
                LOG.info("Notified %s about %s", channel, game["name"])
            except requests.RequestException as exc:
                LOG.warning("Could not notify %s about %s (%s)", channel, game["name"], type(exc).__name__)
    return sent


def validate_players(raw) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("players.json must contain a JSON list")
    players = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not str(item.get("name", "")).strip() or not str(item.get("team", "")).strip():
            raise ValueError(f"Player #{index} needs 'name' and 'team'")
        if item.get("league") not in LEAGUES:
            raise ValueError(f"Player #{index} league must be one of: d1, d2, d3, naia, gleague, nba")
        players.append(item)
    return players


def run(days: int, no_notify: bool, max_age_hours: int) -> None:
    players = validate_players(load_json(ROOT / "players.json", []))
    session = session_with_retries()
    fresh = collect_results(session, players, days)
    previous = load_json(DATA_DIR / "results.json", {}).get("games", [])
    # Retain historical entries and refresh corrected stat lines across sources.
    by_id = {r["id"]: r for r in previous}
    by_id.update({r["id"]: r for r in fresh})
    all_games = sorted(by_id.values(), key=lambda r: r.get("date", ""), reverse=True)
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tracked": [{k: p.get(k, "") for k in ("name", "league", "team", "gcu_years") } for p in players],
        "games": all_games,
        "coverage": {
            "d1": {"source": "ESPN (unofficial)", "configured": True},
            "d2": {"source": "NCAA.com via community proxy", "configured": True},
            "d3": {"source": "NCAA.com via community proxy", "configured": True},
            "naia": {"source": "MonteHall (key required; season coverage unverified)", "configured": bool(os.getenv("MONTEHALL_API_KEY", "").strip())},
            "gleague": {"source": "ESPN G League (unofficial)", "configured": True},
            "nba": {"source": "ESPN (unofficial)", "configured": True},
        },
    }
    save_json(DATA_DIR / "results.json", data)
    notified = load_json(DATA_DIR / "notified.json", {})
    sent = 0 if no_notify else send_alerts(session, fresh, notified, max_age_hours)
    save_json(DATA_DIR / "notified.json", notified)
    LOG.info("%s tracked players, %s new-window games, %s archived, %s notifications",
             len(players), len(fresh), len(all_games), sent)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update Lopes Tracker game logs and notifications")
    parser.add_argument("--days", type=int, default=3, help="Number of calendar days to check (default: 3)")
    parser.add_argument("--no-notify", action="store_true", help="Update dashboard without messaging")
    parser.add_argument("--notify-max-age-hours", type=int, default=60, help="Avoid alerts for old games (default: 60h; NCAA/NAIA timestamps may be date-only)")
    args = parser.parse_args()
    if args.days < 1 or args.days > 31:
        parser.error("--days must be between 1 and 31")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.days, args.no_notify, args.notify_max_age_hours)


if __name__ == "__main__":
    main()
