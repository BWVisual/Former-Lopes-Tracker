# Lopes Tracker 🏀 — College transfers + NBA/G League

A mobile-friendly dashboard and **individual phone alerts after each completed game** for former GCU men's basketball players. Every alert contains the player's current team, opponent, final score, W/L, the **full available box-score line**, and a source link. **One alert per player per game**; two former Lopes playing on the same night generate two alerts. Players who did not play (DNP) are excluded when the source identifies them.

## Exactly six included competitions

| Competition | Connector | Readiness |
|---|---|---|
| NCAA Division I | ESPN men's college basketball (`groups=50`) | Coded; unofficial feed; requires live testing |
| NCAA Division II | NCAA.com via [henrygd/ncaa-api](https://github.com/henrygd/ncaa-api) | Coded; requires live testing; occasional missing box scores possible |
| NCAA Division III | NCAA.com via [henrygd/ncaa-api](https://github.com/henrygd/ncaa-api) | Coded; requires live testing; occasional missing box scores possible |
| NAIA | Optional [MonteHall NAIA data API](https://montehall.com/docs/ncaa-api) | **Not turnkey**: an API key and live current-season coverage validation are required. Without them, **no NAIA automatic alerts**. |
| NBA G League | ESPN `nba-development` feed | Coded; unofficial feed; requires live testing |
| NBA | ESPN `nba` feed | Coded; unofficial feed; requires live testing |

**No international leagues.** The sources are not universal/guaranteed: a missing box score can cause a missed alert. The NAIA provider publicly documents detailed 2025–26 game data, but its current 2026–27 availability is unverified. Never treat an empty dashboard as proof someone did not play. For editorial use, check the original box score before publishing.

**State of this project:** It is a runnable, tested **starter**, not a deployed or independently live-verified notification service. Source parsing and duplicate alerts were tested offline with representative data fixtures; no paid credentials or real Telegram destination are included. No roster auto-discovery is provided; the editable `players.json` begins with four verified 2026–27 D-I transfers, and you must add other former Lopes to monitor them.

## Get individual alerts on your phone (Telegram recommended)

1. Install **Telegram** on your iPhone/Android and enable its push notifications.
2. Open Telegram and message **@BotFather**. Send `/newbot` and follow its instructions to get a **bot token**.
3. Open the bot you created, press **Start**, and send `hi`.
4. In your **own browser**, open `https://api.telegram.org/botYOUR_TOKEN/getUpdates` with your secret token inserted. Look for `result[].message.chat.id` (the private chat ID). Keep **both** the token and chat ID private. Don't put them in source code or screenshots.
5. In your GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**. Add exactly `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as separate repository secrets.
6. Run the updater through **Actions → Refresh Lopes Tracker → Run workflow**. After a tracked player appears in a completed game and the source provides a box score, you should get **one individual Telegram notification**. Make sure the chat is not muted.

Optional test *on your computer*, with environment variables set locally:

```bash
python test_phone_notification.py
```

It sends **one test message** without changing the game log. It won't run during the scheduled updater. **Do not post your bot credentials in chat or include them in GitHub files.**

Discord can also be configured via an optional `DISCORD_WEBHOOK_URL` secret, but Telegram is the simplest choice for phone notifications.

**Timing:** GitHub Actions checks roughly every 30 minutes; scheduling may be delayed, and a game must be marked final with valid player stats before an alert is sent. This is not guaranteed instant push at the final horn. Once delivered for that player/game/channel, the persistent `data/notified.json` ledger prevents duplicate alerts; corrected statistics are still refreshed on the website.

## Publish the website and schedule checks

1. Create a new GitHub repository, e.g. `lopes-tracker`.
2. Upload the **contents of the extracted project folder** into its `main` branch. Include the hidden `.github/workflows/update.yml` file.
3. Under **Settings → Actions → General → Workflow permissions**, grant **Read and write permissions** if your repository allows it. The workflow requests `contents: write` so it can commit refreshed results.
4. Under **Actions**, manually run **Refresh Lopes Tracker** for the first sync.
5. Under **Settings → Pages → Build and deployment**, choose **Deploy from a branch**, `main`, `/ (root)`. The site will normally be `https://YOUR-GITHUB-USERNAME.github.io/lopes-tracker/`.
6. Visit the site and check the updated timestamp and monitored players. On mobile, add the site to your home screen if desired (this does **not** itself enable browser push—Telegram delivers the push notifications).

The GitHub workflow is not a perfectly reliable real-time scheduler. For guaranteed low-latency delivery, migrate it to an always-running host/queue with a supported/licensed feed.

## Add more GCU alumni — essential for "every" former player

Edit `players.json`. **All six** allowed league codes are exactly `d1`, `d2`, `d3`, `naia`, `gleague`, and `nba`. Example only—**replace the fictional record**, don't mistake it for a confirmed alumnus:

```json
{
  "name": "Example Former Lope",
  "league": "d2",
  "team": "Example University",
  "gcu_years": "2023–25",
  "athlete_id": ""
}
```

Use the player's **current** team and the name used by the source. The NCAA lower-division parser matches exact official team names to avoid mixing up similar schools. For ESPN-sourced leagues, a verified `team_id` and `athlete_id` can help prevent ambiguous matches. If a player changes teams during the season, update the record: past games remain stored on the dashboard, but the same player at multiple clubs requires careful identity mapping. Don't add international or unrelated competitions; the validation rejects them.

The initial watchlist has four 2026–27 D-I transfers. You can add previous departures in those six competitions. **It does not automatically discover all historical GCU players or all transfers.**

## What it checks and stores

- Every scheduled run looks back three Phoenix calendar dates (configurable with `--days` up to 31).
- ESPN: only final games featuring a current tracked team; full reported box-score labels are retained.
- NCAA D-II and D-III: the NCAA.com men's scoreboard and per-game data, mapping `teamBoxscore.playerStats` to the same format. If team identity is ambiguous or the box score is incomplete, it skips the alert rather than inventing a line.
- NAIA: only attempts a **per-player**, keyed game-log lookup when the secret `MONTEHALL_API_KEY` exists. This integration's exact current-season payload and update timeliness must be verified with a real account before relying on it. Until then it is **experimental and not considered functioning**.
- `data/results.json` holds historical appearances and current tracked players; `data/notified.json` holds a dedupe key for every player/game/channel.
- Telegram or Discord gets a unique message per verified final player appearance, not a batch digest.

The default message looks like this (**illustrative numbers only**):

> 🏀 LOPES TRACKER | NCAA DIVISION II  
> Example Former Lope | Example University  
> vs. Example State — W 82–76  
> 17 PTS · 7 REB · 4 AST  
> MIN 29 | FGM 6 | FGA 12 | 3PM 2 | 3PA 5 | FTM 3 | FTA 4 | REB 7 | AST 4 | STL 1 | BLK 1 | TO 2 | PF 3 | PTS 17  
> Full box score: [source URL]

## NAIA: one key outstanding

The NAIA has partnered with **PrestoSports** for official statistical reporting. Unlike D-I, D-II, D-III, the G League, and NBA, we have not yet validated an accessible current-season box-score source end-to-end. The [`MonteHall` API](https://montehall.com/docs/ncaa-api) has documented NAIA per-player game logs and requires an **issued API key**; price and live current-season completeness are not publicly established. If you have an issued key, add it as a GitHub Actions secret called `MONTEHALL_API_KEY` and compare an actual returned log against the documented fields before relying on alerts. The app displays a warning when a NAIA player is on the watchlist without this secret. Until this provider is verified, there is **no reliable automatic NAIA alert coverage**. A missing game should be treated as unknown, not a confirmed DNP.

## Run and test locally

```bash
python3 -m venv .venv
source .venv/bin/activate          # On Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python tracker.py --days 3 --no-notify
python -m http.server 8000
```

Open `http://localhost:8000`. The optional `NCAA_API_BASE` environment variable points at a self-hosted copy of [henrygd/ncaa-api](https://github.com/henrygd/ncaa-api); otherwise it uses its public demonstration service. To use a different NCAA API base in GitHub Actions, create an **Actions variable** named `NCAA_API_BASE`.

## Failure / limitations

- **No games:** Make sure the watchlist includes that player and the current team exactly matches the source. For a past game use `python tracker.py --days 14 --no-notify`; old games aren't pushed to your phone after the 60-hour notification age cutoff by default.
- **Missing D-II/D-III box score:** NCAA subroutes occasionally fail or omit athlete data. The tracker refuses to fill in a phantom stat line.
- **NAIA player but no alerts:** This requires an issued key and validated 2026–27 NAIA coverage, not just adding the player to `players.json`.
- **No Telegram alert:** Start the bot chat, unmute notifications, set both secrets, check the GitHub Actions log, and remember that DNPs produce no alerts.
- **Workflow delayed/missed:** This can happen with GitHub scheduled Actions. Use a stronger task runner when you need stricter delivery timing.
- **API changes/terms:** ESPN endpoints are undocumented; NCAA.com is accessed through an unofficial open-source proxy; the NAIA keyed provider is separate. Review each provider's terms and permission before scaling collection.

**Unofficial personal/editorial project; not affiliated with GCU, ESPN, NCAA, NBA, or NAIA.**
