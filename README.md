# X Video Scraper

*[Leia em português](README.pt-BR.md)*

Local web application to search and download videos from **X (Twitter)**, **XHamster**, **XVideos**, **xFree**, **Pornhub**, **XNXX**, **TNAFlix** and **RedTube**.

> See [ROADMAP.md](ROADMAP.md) for what's already done and what's planned next.

## Architecture Overview

```
scrapperx/
├── app.py               # Flask backend (REST API)
├── index.html            # React frontend (SPA, no build step)
├── setup.sh              # Linux/Mac — installs dependencies
├── start.sh              # Linux/Mac — starts the server (foreground, Gunicorn)
├── restart.sh             # Linux/Mac — restarts in background, with log
├── setup_windows.bat      # Windows — installs dependencies
├── start_windows.bat      # Windows — starts the server (foreground, Waitress)
├── restart_windows.bat    # Windows — restarts in background, with log
└── venv/                 # Python virtual environment
```

The backend serves both the API (`/api/*`) and the frontend (`/`) in the same process — no separate server.

---

## Stack

| Layer | Technology |
|---|---|
| Server | Flask 3 + Gunicorn (1 worker, `gthread`, 4 threads, 600 s timeout) — **Linux/Mac**. On **Windows**, Gunicorn doesn't run (it uses `fork()`, which doesn't exist there); Waitress is used instead, with `--threads 4` for the same reason |
| X and xFree scraping | Selenium + headless Chrome (WebDriver Manager) |
| XHamster/XVideos/Pornhub/XNXX scraping | `requests` (direct HTTP) |
| Video download | yt-dlp |
| Frontend | React 18 + standalone Babel (zero build step) |
| Cookie storage | Netscape-format file at `/tmp/x_cookies.txt` |
| Downloaded videos | `~/Downloads/X-Videos/` by default — configurable, see [Download Folder](#download-folder) |

**Why `gthread` + `--threads 4`**: Gunicorn's default `sync` worker processes **one request at a time** — while a slow search is in progress (Selenium scrolling on X/xFree, for example), no other request is even accepted, including `/api/download/start`. That's exactly what caused downloads to hang when clicked while more videos were auto-loading. `gthread` keeps a single process (preserving the in-memory global state — `_SS`, `_XF_SS`, `_SITE_SS`, `download_progress` — which isn't shareable across processes without an external store like Redis) but processes up to 4 requests in parallel within it, since most of the work here is I/O (waiting on Selenium, waiting on HTTP responses) and releases the GIL during those waits.

---

## Installation and Setup

Pick the section for your OS. Both use the same `app.py`/`index.html` — only the setup/start scripts differ.

### 🐧 Linux (Ubuntu/Debian) — step by step

**1. Prerequisites:**
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Google Chrome (needed for Selenium-based scraping — X and xFree)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable
```

**2. Get the project** (if you don't already have the `scrapperx/` folder):
```bash
git clone https://github.com/leogvital/scrappex.git scrapperx
cd scrapperx
```

**3. Install dependencies** (creates `venv/` and installs everything inside it — doesn't touch the system Python):
```bash
bash setup.sh
```

**4. Configure the app login** (see the [App Login](#app-login) section below):
```bash
cp .env.local.example .env.local
# edit .env.local and set SCRAPPERX_APP_USER / SCRAPPERX_APP_PASS
```

**5. Start:**
```bash
# Foreground (stays attached to the terminal, Ctrl+C to stop) — good for watching logs/debugging
bash start.sh

# OR background (keeps running after closing the terminal) — good for everyday use
bash restart.sh
# Logs: tail -f /tmp/scrapperx.log
```

**6. Open**: [http://localhost:5000](http://localhost:5000)

**Requirements:**
- Python 3.10+
- Google Chrome installed (for Selenium-based scraping of X and xFree)
- `python3-venv` (included in step 1 above)

**If running under systemd** (a unit like `/etc/systemd/system/scrapperx.service` with `ExecStart=.../start.sh` and `Restart=always`): don't run `restart.sh` by hand once that unit exists and is enabled. `restart.sh` only knows about whatever's bound to port 5000 at the moment it runs — it has no idea a systemd unit is also trying to manage that same process, so the two fight over the port (systemd's `Restart=always` respawning `start.sh` the instant `restart.sh` kills the old one, `restart.sh`'s own fresh gunicorn then failing to bind because the systemd-spawned one got there first, `curl`'s health check in `restart.sh` still passing against *that* one and reporting success even though nothing changed). Restart with `sudo systemctl restart scrapperx.service` instead — `restart.sh`/`start.sh` remain what that unit's `ExecStart` actually runs under the hood, so they're still the right thing to read to understand *how* the server starts, just not the right *command* to run directly once systemd owns the process.

---

### 🪟 Windows — step by step

**1. Install Python:**
- Download from [python.org/downloads](https://www.python.org/downloads/) (3.10 or newer)
- On the installer screen, check **"Add python.exe to PATH"** before clicking Install — this is easy to miss, and without it the `.bat` scripts won't find Python
- Confirm by opening **Command Prompt** (`cmd`) and running `python --version`

**2. Install Google Chrome:**
- Download and install from [google.com/chrome](https://www.google.com/chrome/) (needed for Selenium-based scraping of X and xFree — `webdriver-manager` downloads the matching `chromedriver` automatically, you just need Chrome itself installed)

**3. Get the project** (if you don't already have the `scrapperx/` folder):
- Via Git: `git clone https://github.com/leogvital/scrappex.git scrapperx`
- Or download the repository `.zip` and extract it to a folder

**4. Install dependencies** — open **Command Prompt** inside the `scrapperx` folder (click the Explorer address bar, type `cmd`, press Enter) and run:
```bat
setup_windows.bat
```
This creates `venv\` and installs everything inside it (doesn't touch the system Python).

**5. Configure the app login** (see the [App Login](#app-login) section below) — copy `.env.local.example` to `.env.local` and edit the `SCRAPPERX_APP_USER`/`SCRAPPERX_APP_PASS` values in a text editor.

**6. Start:**
```bat
REM Foreground (stays attached to the window, close it to stop) — good for watching logs/debugging
start_windows.bat

REM OR background (keeps running after closing this terminal) — good for everyday use
restart_windows.bat
REM Logs: %TEMP%\scrapperx.log
```

**7. Open**: [http://localhost:5000](http://localhost:5000)

**Requirements:**
- Python 3.10+ with "Add to PATH" checked during install
- Google Chrome installed
- Windows 10/11 (the `.bat` scripts use built-in `netstat`/`taskkill`/PowerShell, nothing extra to install)

**Differences from Linux**: on Windows the server runs via **Waitress** instead of **Gunicorn** (Gunicorn depends on `fork()`, which doesn't exist on Windows) — same idea, equivalent result. Automatic Chrome/Edge cookie extraction also works differently under the hood (Windows uses DPAPI for decryption; Linux uses a fixed key or the keyring via `secretstorage`), but that's already handled automatically by `yt-dlp` as a fallback — nothing extra to do.

> **Alternative**: if you'd rather run the exact same commands as Linux on Windows, install **WSL2** (`wsl --install` in an administrator PowerShell) with Ubuntu, then follow the 🐧 Linux section above from inside WSL.

**Note on `--no-control-socket`**: `start.sh`/`restart.sh` pass this flag to Gunicorn 26+ to disable the *control socket* (an admin feature used only by `gunicornc`, which this project doesn't use). Without it, Gunicorn tries to create `$XDG_RUNTIME_DIR/gunicorn.ctl` — if that variable leaked from a previous root session (common when switching users with `su user -c '...'` without the `-`, or `sudo -u user` without resetting the environment), it tries to write to `/run/user/0/` and fails with `PermissionError`. The HTTP server itself still comes up fine despite this error (only the control socket fails), but `--no-control-socket` eliminates the whole class of problem.

---

## App Login

The whole app sits behind its own login screen (independent from the X cookies below), with username and password configured via environment variable — **not** hardcoded in the source (the repository is public):

```bash
# 1. Copy the template
cp .env.local.example .env.local

# 2. Edit .env.local and set:
SCRAPPERX_APP_USER=admin
SCRAPPERX_APP_PASS=your-password-here
```

`.env.local` is in `.gitignore` — it stays only on your machine/server; `start.sh`/`restart.sh` (and the Windows `.bat` files) load these variables automatically before starting the server. Without `.env.local` (or without `SCRAPPERX_APP_PASS` set), login is blocked for everyone — the backend warns about this in the log on startup.

- Backend (`app.py`): `before_request` blocks any `/api/*` route (except `/api/auth/app-login`, `/api/auth/app-status` and `/api/health`) while `session["app_logged_in"]` isn't set.
- **Persistent session**: `app.secret_key` is generated once and saved to `.flask_secret_key` (permission `600`) — loaded from that file on every subsequent start, so restarting the server does **not** log anyone out. On login, `session.permanent = True` + `PERMANENT_SESSION_LIFETIME = 30 days` make the cookie survive closing the browser (without this it would be a session cookie, wiped on close). If `.flask_secret_key` gets recreated by a different system user (a different owner than the server process), loading it fails with `PermissionError` on boot — delete the file so the current process recreates it with the right owner.
- **X login also survives restarts**: on boot, if `x_cookies.txt` already exists, the backend runs `validate_cookies()` automatically and restores `session_state["logged_in"]` — without this, even with valid X cookies intact on disk, a restart would force the X auth screen again every time.
- Endpoints: `POST /api/auth/app-login`, `POST /api/auth/app-logout`, `GET /api/auth/app-status`.
- Frontend (`index.html`): `Root` gates rendering before `App` — shows `AppLoginScreen` if not authenticated, otherwise renders `App` with a floating "🔒 Sair" (Log out) button in the bottom-left corner.
- **Rate limited**: `/api/auth/app-login` allows `_LOGIN_RATE_LIMIT` (5) failed attempts per IP within `_LOGIN_RATE_WINDOW` (300s), then returns `429` — including for the *correct* password, until the window clears — with a "wait Xs" message the frontend already surfaces via the existing `err` state (no frontend changes needed; `fetch` doesn't throw on a 429, so `d.error` from the JSON body renders exactly like a wrong-password message). Tracked in-memory only (`_LOGIN_ATTEMPTS`, a plain dict — no Redis) since `--workers 1` means there's no cross-process state to synchronize anyway, and losing the counter on a restart is harmless here, not a security hole. A successful login clears that IP's failure history immediately. `_login_rate_limited()` prunes attempts older than the window as a side effect of every check, so both the per-IP list and the dict itself (once a key's list empties) stay naturally bounded — no separate cleanup job. Validated with 7 cases: the 5th attempt still succeeds and the 6th is blocked (off-by-one is deliberate — the window fills on attempts 1-5, so the check on attempt 6 is the first to see `len >= 5`), a blocked IP can't get through even with the right password, a different IP is unaffected, a correct login clears the history, a fresh 5 failures are required to re-trigger after a reset, and attempts outside the time window are pruned and stop counting.

---

## Authentication

Access to X requires valid session cookies. Three methods available:

### 1. Auto-detection (recommended for Linux)
Detects and imports cookies directly from Chrome, Firefox or Edge's SQLite database.
- Chrome on Linux doesn't encrypt cookies by default
- Automatic fallback via yt-dlp if direct reading fails

### 2. Via yt-dlp
Uses yt-dlp's native extractor, which handles the system keyring's encryption.
Supports: Chrome, Firefox, Edge, Opera, Brave.
> Close the browser before using this method.

### 3. Paste cookies manually
Paste the JSON exported by the [Cookie-Editor](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) extension, or Netscape-format text.

After importing, cookies are validated via a `POST` to a `media/upload.json` INIT call (`total_bytes=1`) — the same endpoint tweet publishing actually uses.

> **Historical note**: until 2026-08, validation used `GET /i/api/1.1/account/verify_credentials.json`. That endpoint started always returning `404 {"message":"Sorry, that page does not exist","code":34}` — including for genuinely valid cookies (confirmed: the same cookies worked fine against the `media/upload.json` INIT call). In other words, it's no longer a reliable signal of an expired session — X discontinued the endpoint itself for this kind of auth. This caused a false logout: `session_state["logged_in"]` would get stuck at `False` (or worse, stuck at a previous `True` — `/api/auth/validate` only *flipped the flag on* on success, never *off* on failure) even with working cookies, and the user would see raw X API errors (`"Failed to authenticate. API Error: 401 OAuth access token has expired."`) instead of the re-auth screen. Swapping the validation endpoint fixed both issues.

---

## Search Features

### X (Twitter) — via Selenium
| Mode | Description |
|---|---|
| For You | Main feed (`/home`) — starts automatically when the tab is clicked |
| Following | "Following" feed (clicks the tab via Selenium) — starts automatically |
| Keyword | Search with `filter:videos` |
| Hashtag | Hashtag page with video filter |
| User | Profile's `/media` tab |

Selenium keeps **one persistent Chrome session** across pagination — the driver isn't restarted on every "Load more", avoiding re-scrolling and duplicates. The session expires after 600 s of inactivity or 60 scrolls.

**Infinite auto-scroll:** upon reaching 700 px from the bottom of the page, new results load automatically (no button click), mimicking X's native navigation.

**Clickable username/hashtags on each card**: `_parse_tweet_object` now also pulls `hashtags` from the tweet's own `entities.hashtags` (a structured list X already attaches to the tweet, not a regex over the text — avoids false positives from a `#` inside a URL/mention) alongside the existing `uploader_id`/`duration`/etc. fields. `VideoCard` uses `hashtags !== undefined` (present, possibly empty) as the signal "this is an X result" — platform isn't otherwise threaded down to that component, and that check works the same whether the card came from a single-platform X search or a "buscar em tudo" aggregate result. When it's an X card, `@uploader_id` becomes a link to `x.com/<user>/media` and each `#hashtag` becomes a link to `x.com/hashtag/<tag>?...&f=video` — the exact same URLs the app's own in-app User/Hashtag search types already navigate to (see the table above), each opening in a new tab (`target="_blank"`, with `e.stopPropagation()` so clicking one doesn't also trigger the card's own play-preview handler). Other platforms' cards are unaffected — no `hashtags` field, so the username stays plain, non-clickable text exactly as before.

**Thumbnail extraction hardened against X's DOM, in two rounds**. A user-submitted screenshot showed several blank `For You` cards (no thumbnail image at all, not a broken-image icon) — round 1 found `_extract_video_thumbnail`'s most reliable tier (reading `<video poster>`) only looked inside `[data-testid="videoPlayer"]`/`[data-testid="videoComponent"]`, missing `[data-testid="animatedMediaPlayer"]` (the container X uses for GIFs, which are real `<video poster>` elements underneath too) — fixed, but didn't fully resolve the report. Round 2 made the extraction considerably more defensive instead of enumerating more specific container names one at a time:
- **Tier 0** is now a plain `video` selector scanning the whole article for *any* `<video poster>`, independent of whichever specific `data-testid` X currently wraps it in — the exact kind of container-name assumption that broke once already (X's own frontend changes its DOM fairly often, and this class of bug is easy to reintroduce by only patching the one container name a particular report happens to surface).
- Every img-based tier now resolves through `_img_url()`, which checks `data-src`/`data-image-url`/the first `srcset` candidate before falling back to `src` — a tweet's preview image can be genuinely lazy-loaded, with `src` sitting on a blank placeholder (a `data:` URI, confirmed via a local fixture) until an attribute swap happens, so reading `src` directly on those misses the real URL entirely.

Verified mechanically against local HTML fixtures (no live X session was available in the environment doing this work, so this couldn't be confirmed against the real site directly): tier 0 correctly finds a `<video poster>` under a container name it has no specific knowledge of, and `_img_url()` correctly prefers `data-src` over a blank-placeholder `src`.

**Round 3 — the real root cause turned out to be unrelated to extraction.** The user reported the blank cards persisted unchanged after rounds 1 and 2 deployed. A temporary on-screen debug overlay (`DEBUG thumb=... err=...`, since removed) confirmed `video.thumbnail` was never actually empty — every blank card had a valid `pbs.twimg.com` URL, but the `<img>` fired `onError` anyway. A direct server-side fetch of one of the exact failing URLs, no auth or `Referer` header, returned `200` with `Access-Control-Allow-Origin: *` — so unlike RedTube's `pix-cdn77` case, the CDN itself isn't hotlink-blocking these. That points at something on the *client's own connection* blocking `twimg.com` (carrier/DNS/ad-blocker content filtering — common for domains known to host NSFW media) rather than anything wrong in the scraping. Fix: the same proxy pattern already used for RedTube. `_tw_thumb_url()` routes every X thumbnail (both the Selenium `_ss_parse` path and the API-based `_parse_tweet_object` path) through `GET /api/thumb-proxy?url=...`, whose SSRF allowlist now accepts `twimg.com`/`*.twimg.com` alongside the existing `*.rdtcdn.com` suffix check — the client's browser never talks to `twimg.com` directly, sidestepping whichever layer was actually blocking it.

### XHamster and XVideos — via HTTP
Direct HTML page scraping, no headless browser. Two tabs — Home and Search — plus an orientation category (❤️ Straight / 🏳️‍🌈 Gay / 🏳️‍⚧️ Trans), using the same simple URL-prefix scheme on both sites:

| Category | Prefix (XHamster and XVideos) |
|---|---|
| ❤️ Straight | *(none)* |
| 🏳️‍🌈 Gay | `/gay` |
| 🏳️‍⚧️ Trans | `/shemale` |

- **XHamster**: both Home (`{prefix}?page=N`) and Search (`{prefix}/search/{query}?page=N`) use the same embedded JSON blob (`window.initials`) — Search keeps items in `searchResult.videoThumbProps`, Home in `layoutPage.videoListProps.videoThumbProps`. `_scrape_xhamster` tries both paths.
- **XVideos**: Search (`{prefix}/?k=...&p=N`) paginates normally, but **Home doesn't paginate** — `{prefix}/` always returns the same featured set regardless of `page`/`p` (confirmed by testing directly over HTTP, outside the app). Because of this, XVideos Home always reports `has_more=false` — no "load more" — and the UI shows a notice about it.
- Sorting (Search only): relevance, newest, views, top rated, longest
- Duration filter (client-side): short (<10 min), medium (10–30 min), long (>30 min)

### xFree — Selenium (home and search)
Scrapes xfree.com (Vue.js/Nuxt SSR) via headless Chrome, for both Home and Search.

- **Why Selenium for everything**: neither xfree.com's Home nor its Search paginate reliably over plain HTTP — content loads via client-side infinite scroll, calling an internal JSON endpoint (`/api/2/search?...&offset=N`) protected by Cloudflare that blocks direct HTTP requests (404). The Gay/Trans categories (`/gay`, `/trans`) are additionally blocked by a bot-specific Cloudflare challenge that only a real browser can pass. So everything — Home and Search, across all 4 categories — opens a headless Chrome session (`_XF_SS`, analogous to X's `_SS`) and simulates scrolling (`_xf_scroll_down`) until it accumulates `page_size` new items, with ID-based dedup (`seen_ids`).
- **Category (Straight / Gay / Trans / All)**: the category is Vuex state on the site (not a query param), set by actually navigating to its dedicated route — `/`, `/gay`, `/trans`, `/all`. So the session always starts with `driver.get()` on the chosen category's route; for search, the query is typed into the page's own search box (`input[name=q]`) and submitted with Enter, preserving the already-loaded category state (navigating straight to a `/search?q=...` URL resets that state back to "Straight").
- Video links carry a category-specific suffix — `/video?id=` (straight/all), `/video-gay?id=`, `/video-trans?id=` — preserved by the parser (`_parse_xfree_blocks`) to keep the playback URL correct.
- No server-side sort support (sorting is client-side in Vue.js)

### Pornhub (pt.pornhub.com) — via HTTP
Direct HTML page scraping, no headless browser (`_scrape_pornhub`). Two tabs — Home and Search — plus an orientation category:

| Category | Site vertical (Home) | Keyword search |
|---|---|---|
| ❤️ Straight | `/` | `/video/search?search=...` |
| 🏳️‍🌈 Gay | `/gayporn` | `/gay/video/search?search=...` |
| 🏳️‍🌈 Sapphic | `/lesbian` | `/lesbian/video/search?search=...` |
| 🏳️‍⚧️ Trans | `/transgender` | **no dedicated endpoint** |

- **Home** doesn't require a query — it loads the featured videos for the selected category's vertical (the same URL used as Trans's search fallback).
- Gay and Sapphic are the site's own "verticals" (same domain, SSR HTML already filtered by orientation) with a dedicated search endpoint — they work over plain HTTP, no blocking.
- Trans has no keyword-search endpoint on the site — the category browses `/transgender`'s featured feed for both Home and Search, and **ignores the typed text** in Search, warning the user in the UI (an info message when "Trans" is selected).
- Pagination via `?page=N`, the same for every category and for Home/Search.
- **Cross-page dedup**: Pornhub's category pagination repeats a few promoted items across consecutive pages (confirmed directly over HTTP, outside the app). Because of this, `_SITE_SS` (also used by XHamster/XVideos) gained a `seen_ids` set that filters out already-seen IDs before returning each page.
- **Thumbnail**: Home/trending cards use a different attribute (`data-mediumthumb`) than search cards (`data-image`) — `_scrape_pornhub` tries both before falling back to the `<img>`'s plain `src`, otherwise several previews would show up blank on Home.

### XNXX (www.xnxx.com) — via HTTP
Direct HTML page scraping, no headless browser (`_scrape_xnxx`). Two tabs — Home and Search — plus a category, all funneled through the same `/search/...` path (unlike Pornhub's per-orientation subdomains/paths):

| Category | Browse (Home) | Keyword search |
|---|---|---|
| ❤️ Straight | `/search/straight` | `/search/<query>` |
| 🏳️‍🌈 Gay | `/search/gay` | `/search/gay/<query>` |
| 🏳️‍🌈 Sapphic | `/search/lesbian` | **no dedicated endpoint** |
| 🏳️‍⚧️ Trans | `/search/shemale` | `/search/shemale/<query>` |

- **Category as a path segment, not a subdomain**: Gay and Trans are recognized "orientation filter" segments the search endpoint understands — prepending `gay` or `shemale` before the query narrows results to that orientation. "Sapphic" maps to the `lesbian` *tag* instead, which the site only recognizes as a lone segment — combining it with a second query segment gets silently dropped (the site falls back to a plain, unfiltered search on the query alone), confirmed by testing directly against the site outside the app.
- **Sapphic ignores the typed query** for the same reason Pornhub's Trans does: no combinable keyword-search endpoint exists, so Search browses the `lesbian` tag's feed and warns the user in the UI instead of silently losing the category filter.
- Pagination is 1-based via an extra trailing segment (`/search/<query>/2`, `/search/gay/2`, etc.), the same for every category and for Home/Search.
- **Card selector matters**: the page mixes real video cards (`class="thumb-block  with-uploader"`) with decorative/suggestion placeholder blocks (`class="thumb-block thumb-cat"`, no video data) — `_scrape_xnxx` matches on the more specific `with-uploader` class specifically to skip those; matching the bare `thumb-block` class would parse zero real results on Home/category pages, where placeholders can outnumber (or on some pages, entirely replace) actual cards.
- **Views use pt-BR number formatting** (comma as decimal separator, e.g. `12,7M`) unlike Pornhub's English formatting (`1.1M`) — `_parse_xnxx_views` handles this separately from `_parse_pornhub_views`.
- **Sort and duration are further combinable segments** — confirmed against the live site: `/search/gay/hits/10min+/<query>` chains orientation + sort + duration + query together in one request, in that order, for both Home and Search. `sort` maps to `hits` (most viewed) / `month` / `year` / `random`; `duration` maps to `0-10min` / `10-20min` / `20min+`. Sapphic is the one exception — being a lone tag (see above), it drops *any* second segment, sort/duration included, not just a query, so both selects are disabled in the UI when it's chosen.
- **Not double-filtered**: since XNXX already filters duration server-side with its own bands (`medium` = 10-20min here, vs. xHamster/XVideos' shared client-side filter using 10-30min for the same label), `search_site_page` skips its generic post-fetch duration filter entirely for `xnxx`/`tnaflix` — running both would silently drop results the site had already correctly returned (e.g. a 29-minute video correctly placed in XNXX's "Longo" bucket would get cut by the generic filter's `>30min` threshold for "long").
- **Fixed: duplicate "Ordenar por"/"Duração" selects on screen for XNXX and TNAFlix**. A separate, generic block (`siteSort`/`siteDuration`, meant for "xHamster and XVideos only" per its own comment) was gated by `platform!=="x"&&platform!=="xfree"` — broad enough to also render for Pornhub, XNXX, and TNAFlix, none of which that comment meant to include. For XNXX/TNAFlix specifically, this meant their dedicated sort/duration selects (above) rendered *alongside* this second, redundant pair — two visually identical-looking "Ordenar por"/"Duração" selects stacked on the page. Tightened the condition to `platform==="xhamster"||platform==="xvideos"`, matching the comment's actual intent.

### TNAFlix (www.tnaflix.com) — via HTTP
Direct HTML page scraping, no headless browser (`_scrape_tnaflix`). Two tabs — Home and Search — plus a category:

| Category | Browse (Home) | Keyword search |
|---|---|---|
| ❤️ Straight | homepage (`/`) | `/search?what=<query>` |
| 🏳️‍🌈 Gay | `/gay-porn` | **no dedicated endpoint** |
| 🏳️‍🌈 Sapphic | `/lesbian-porn` | **no dedicated endpoint** |
| 🏳️‍⚧️ Trans | `/shemale-porn` | **no dedicated endpoint** |

- **No category+keyword combination at all**, unlike XNXX (where 2 of 3 non-default categories combine with a query) or Pornhub (where only Trans lacks it) — confirmed against the live site: `/<tag>/search?what=...` 404s, and the search box rendered on every category page still posts to the same site-wide `/search`. So here, **any** non-straight category always browses its tag page and ignores whatever was typed, not just one edge case.
- **Home/category pages don't paginate at all** — confirmed directly against the site: the homepage and every `/<tag>-porn` page return byte-for-byte the same 60 cards on `?page=2` as `?page=1`. Only straight keyword search (`/search?what=...`) actually paginates with new results per page. `search_task_start`'s route forces `has_more=False` whenever `not q or category != "straight"`, mirroring the same fix already in place for XVideos' non-paginating category landing page.
- **Card selector**: each result is a `<div data-vid="...">` wrapper — split directly on that attribute rather than a generic content class, since the id is already sitting right there in the marker being matched on.
- **Views use English dot-decimal formatting** (e.g. `33.2K`) — same as Pornhub, so `_scrape_tnaflix` reuses `_parse_pornhub_views` instead of a third near-identical parser.
- **Sort and duration exist, but only apply to Home/category browsing** — confirmed against the live site: the search results page renders the exact same "Duration"/"Uploaded" dropdowns as a category page, but `?d=`/`?u=` have zero effect there (identical result IDs with or without them on the same `what=` query); only a Home/category request actually honors `?d=` (its sort is a path segment instead — `featured`/`new`/`toprated` on the homepage vs. `featured`/`most-recent`/`top-rated` on a `/<tag>-porn` page, two different slug sets for the same three options). So the frontend only shows the sort/duration selects while the Home tab is active, and `search()` doesn't send them at all for a keyword search.

### RedTube (www.redtube.com) — via HTTP
Direct HTML page scraping, no headless browser (`_scrape_redtube`). Two tabs — Home and Search — plus a category:

| Category | Browse (Home) | Keyword search |
|---|---|---|
| ❤️ Straight | homepage (`/`) | `/?search=<query>` |
| 🏳️‍🌈 Gay | `/gay` | `/gay?search=<query>` |
| 🏳️‍🌈 Sapphic | `/redtube/lesbian` | **no dedicated endpoint** |
| 🏳️‍⚧️ Trans | `/redtube/transgender` | **no dedicated endpoint** |

- **Straight and Gay genuinely combine with a query** — confirmed against the live site: 0-1 shared video IDs between two different search terms under the same category, for both. Sapphic and Trans are tag-only pages — a typed query is silently dropped (100% identical results regardless of the term), same limitation as Pornhub's Trans/XNXX's Sapphic.
- **Sort (`relevance`/`new`/`top`/`mostviewed`/`longest`) and the `min_duration`/`max_duration` range filter (in minutes) only reliably combine with Straight** — confirmed against the live site that most sort values silently fall back to plain `/gay` when combined with Gay (only `/top/gay` survives as a distinct URL) and that `min_duration`/`max_duration` barely narrows Gay results at all (55 of 65 ids still shared with the unfiltered page). Rather than offer selects that quietly no-op or barely do anything for Gay/Sapphic/Trans, both are shown in the UI only while the category is Straight.
- **Card selector**: the `<li>` wrapper's own `id` prefix differs by page template (`tags_videos_<id>` on search results, `browse_<id>` on Home/category listings, confirmed against both live) — splitting on either alone misses the other template entirely. `class="js-pop thumbnail-card` is identical across both and appears exactly once per real card, so `_scrape_redtube` splits on that instead; `data-video-id` itself isn't a safe split marker since it appears twice per card (once on the `<li>`, once on the nested `<a>`).
- **Views use English dot-decimal formatting** (e.g. `123K`) — same as Pornhub/TNAFlix, so `_scrape_redtube` reuses `_parse_pornhub_views`.
- **Some thumbnails need a server-side proxy**: certain videos only have a dynamic, generated-from-a-video-frame thumbnail served from `pix-cdn77.rdtcdn.com`, instead of the older static `ei-ph.rdtcdn.com` jpg. Confirmed against the site: the exact same `pix-cdn77` URL returns `200` with a `Referer: https://www.redtube.com/` header and `403` without one — a browser's own `<img>` request, loading the thumbnail directly from our page, never sends that header, so those specific videos showed up with a broken preview image. `GET /api/thumb-proxy?url=<thumb_url>` fetches the image server-side with the right header and streams it back; `_rt_thumb_url()` only routes `pix-cdn77` URLs through it (also unescaping the `&amp;` HTML entity `data-o_thumb` carries around its `validto` param, which breaks the query string if passed through raw) — `ei-ph.rdtcdn.com` thumbnails already load fine with no header and are left as plain URLs, skipping the extra hop. The proxy itself allowlists by hostname *suffix* (`.rdtcdn.com`), not substring, to avoid being usable as an open SSRF relay for an arbitrary URL.

---

## Background Search

A fresh search — especially X/xFree via Selenium, or "buscar em tudo" running all 8 platforms one after another — can take anywhere from a few seconds to well over a minute. That used to mean the whole wait lived inside one blocking `fetch()` on the client; if the tab got backgrounded (phone screen locks, user switches app), mobile browsers throttle or fully suspend JS and networking, and the in-flight request either stalls indefinitely or gets dropped outright, losing the search. Same fix as [background downloads](#video-download): the actual work moves into a server-side thread that keeps running regardless of what the client tab does.

`/api/search/start` and `/api/search/start_all` kick off the real work in a background thread and return a `task_id` immediately; the client polls `GET /api/search/task/<tid>` every 1.5s until it reports `"complete"` or `"error"`. The `task_id` is persisted to `localStorage` (`scrapperx_search_task` / `scrapperx_search_all_task`) while a search is in flight, and a mount-time effect in `App` checks for one and resumes polling if found — closing the tab, or the OS killing a backgrounded one outright, and reopening later reconnects to a search that kept running server-side the entire time, with results ready as soon as it finishes. `/api/search` itself is untouched and still works exactly as before for a synchronous call — nothing was removed, only added.

**Reusing the existing view instead of duplicating it**: `_call_search_view(body)` invokes the existing `search()` Flask view function via `app.test_request_context(...)`, which synthesizes a real request/app context so `request.json` etc. work normally inside — then `app.make_response()` normalizes whatever the view returned (a bare `Response`, or a `(body, status)` tuple, exactly like Flask's own dispatcher would for a real HTTP request) into a consistent `(status_code, dict)` pair. This reuses every branch of the existing search logic (xfree/xhamster/xvideos/pornhub/X, retry logic, session bookkeeping) verbatim from a background thread, rather than re-implementing any of it for async execution.

**The aggregate case moved server-side entirely**, not just wrapped: `_run_aggregate_search_task()` loops through all 8 platforms sequentially *inside the background thread*, calling `_call_search_view()` for each and accumulating tagged results, per-platform `search_id`s, and per-platform `has_more` into the task's state as it goes — mirroring exactly what the old client-side `for` loop used to do, just moved off the tab. This mattered specifically because a client-side `await`-based loop is JS running in the tab, which is exactly what gets suspended when a mobile browser backgrounds it; keeping the loop client-side while only the individual `/api/search` calls became async would have defeated the whole point for the slowest, most-likely-to-be-left-running search mode. A platform that errors doesn't abort the run — the loop just moves on to the next one, same tolerance the old client-side version had.

**Deliberately out of scope**: `/api/search/more` (pagination / "load more") stays synchronous. It's typically fast (one page, not a fresh multi-scroll gather) and triggered by explicit engagement (scrolling near the bottom, or clicking a button) while the user is already looking at results on screen — a different situation from "I started a search and want to walk away," which is what this feature targets.

Finished tasks are swept by the existing watchdog (`_watchdog_sweep`, every 120s) once older than `_SEARCH_TASK_MAX_AGE` (1 hour), the same pattern already used for idle Selenium sessions and orphaned chromedriver processes, so `_search_tasks` doesn't grow unbounded over a long server uptime.

Validated at three levels: a Python test using Flask's test client confirming a background task completes with the right results, an unknown task_id returns `not_found` rather than crashing, the aggregate task accumulates results while tolerating individual platform failures, per-platform `search_id`/`has_more` end up correctly recorded for later "load more", and the watchdog sweep prunes old finished tasks; a headless render test confirming the client starts a task (not a direct search call), persists and clears the `localStorage` entry at the right moments, and populates the UI once polling detects completion, for both single-platform and aggregate search; and a dedicated resume scenario — `localStorage` pre-populated with a pending task *before* the app even mounts, confirming it immediately shows "buscando" on reconnect, stays in that state across polls while the (mocked) task is still running, and renders results once it completes, exactly as if the search had run in the foreground the whole time.

---

## REST API

| Method | Route | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/auth/app-login` | App login (configured username/password) |
| POST | `/api/auth/app-logout` | App logout |
| GET | `/api/auth/app-status` | App login session state |
| GET | `/api/session` | Current session state (requires app login) |
| POST | `/api/auth/auto-import` | Import cookies from the browser |
| POST | `/api/auth/yt-dlp-browser` | Import cookies via yt-dlp |
| POST | `/api/auth/paste-cookies` | Import pasted cookies |
| POST | `/api/auth/validate` | Validate active cookies |
| POST | `/api/upload/init` | Start chunked upload (Twitter INIT) |
| POST | `/api/upload/chunk` | Send a 5 MB segment (Twitter APPEND) |
| POST | `/api/upload/finalize` | Finalize upload and wait for processing |
| POST | `/api/tweet/create` | Publish a tweet with text and/or video |
| POST | `/api/auth/logout` | End session and delete cookies |
| POST | `/api/search` | Search videos (first page), synchronous |
| POST | `/api/search/more` | Load next page, synchronous |
| POST | `/api/search/start` | Start a single-platform search as a background task |
| POST | `/api/search/start_all` | Start a "buscar em tudo" (all 8 platforms) search as a background task |
| GET | `/api/search/task/<tid>` | Poll a background search task's status/results |
| GET | `/api/history` | List search history/favorites (server-side, SQLite) |
| POST | `/api/history` | Record a search into history (dedups by platform+type+query+category) |
| POST | `/api/history/<id>/favorite` | Toggle an entry's favorite flag |
| DELETE | `/api/history/<id>` | Remove one history entry |
| POST | `/api/history/clear` | Clear non-favorite history entries |
| POST | `/api/preview` | Direct URL for in-browser preview |
| POST | `/api/formats` | List available formats (yt-dlp) |
| POST | `/api/download/start` | Start an async download |
| GET | `/api/download/progress/<tid>` | Download progress |
| POST | `/api/download/pause/<tid>` | Pause a running download |
| POST | `/api/download/cancel/<tid>` | Cancel a running or paused download |
| GET | `/api/download/file/<tid>` | Serve the downloaded file |
| GET | `/api/settings/download-dir` | Current download folder, plus the default one |
| POST | `/api/settings/download-dir` | Change the download folder (validates it exists/is writable) |
| GET | `/api/library` | List videos in the downloads folder, plus free disk space |
| GET | `/api/library/video/<name>` | Serve a library video (streaming) |
| POST | `/api/library/delete` | Delete a video from the library |

---

## Frontend (React SPA)

The entire interface lives in `index.html` as inline JSX compiled by Babel in the browser — no `npm build`. Main components:

| Component | Purpose |
|---|---|
| `Root` | App login gate — decides between `AppLoginScreen` and `App` |
| `AppLoginScreen` | App login screen (configured username/password) |
| `AuthScreen` | Login screen with the 3 X cookie-import tabs |
| `VideoCard` | Result card with embedded preview and selection checkbox |
| `FormatModal` | Quality selection and download progress modal |
| `BulkActionBar` | Fixed bulk-download bar (multi-selection) |
| `BulkProgressModal` | Modal with simultaneous progress for several downloads |
| `BgTray` | Floating pill for background downloads |
| `PostModal` | Modal for composing and publishing a tweet with video (chunked upload with real progress) |
| `LibraryGrid` | Grid of downloaded videos, with the disk-usage bar |
| `LibraryCard` | One library grid item — hover-to-play preview via local streaming |
| `LibraryModal` | "Meus Vídeos" as a modal over the search page (wraps `LibraryGrid`) |
| `DiskUsageBar` | Free/used space bar for the folder backing `DOWNLOAD_DIR` |
| `HistoryModal` | Search history/favorites as a modal — filter by platform/searched term, paginated |
| `DownloadDirModal` | Modal to change the download folder (free-text path, no native picker) |
| `PlayerModal` | Fullscreen player with seek, play/pause, next/previous, delete |

### Search history and favorites

Every successful search (any platform, including Home-feed loads) is recorded into `searchHistory`, persisted **server-side** in `search_history.db` (SQLite, next to `app.py` — same rationale/pattern as `download_history.db`: not under `tempfile.gettempdir()`, so it survives reboots and OS `/tmp` cleanups) via the `/api/history*` endpoints. This used to live only in the browser's `localStorage` (`scrapperx_search_history`); moving it server-side means the admin user's history/favorites are now shared across browsers/devices and survive a browser data wipe, instead of being tied to one browser profile. A history entry is identified by `platform+type+query+category`; re-running the same search moves it to the top (server-side `ts` bump) instead of duplicating, and preserves an existing favorite flag rather than replacing it with a fresh unstarred entry. Non-favorite entries are capped at `HISTORY_MAX` (30, oldest dropped first, enforced server-side in `_prune_search_history`); favorites are exempt from the cap and from "Limpar histórico" (which only clears non-favorite entries). The frontend no longer computes dedup/cap logic itself — every `/api/history*` call returns the full, current list, and the client just renders it.

Clicking a history entry (`runHistoryEntry`) needs to both update the visible platform/type/query/category selectors *and* fire the search immediately — but React state setters are async, so `search()` reading `platform`/`query`/etc. from its own closure would still see the *previous* values on that same call. `search()` therefore accepts an optional `overrides` object that takes precedence over current state for that one invocation, while every existing caller (the search button, `Enter` in the query field, the auto-search effect on tab change) keeps calling `search()` with no arguments and behaves exactly as before. One consequence worth knowing if touching this code: `search` is called directly as `onClick={()=>search()}`, never bare as `onClick={search}` — React would pass the click's `SyntheticEvent` as `overrides` in that case, and since events carry a real `.type` property (`"click"`), `eType` would silently become the string `"click"` instead of falling back to state.

Validated with a Python test using Flask's test client: adding an entry, re-adding the same platform+type+query+category (dedup — count stays at 1, `ts` bumps), favoriting, "Limpar histórico" preserving the favorite, and deleting an entry.

**History as a modal, with filtering and pagination**: the history panel used to render inline above the search form, only while on the "search" tab (`Meus Vídeos` used to be a whole separate page/`view`, so the two couldn't be open together anyway). Both are now modals (`HistoryModal`/`LibraryModal`) layered over the search page like `FormatModal`/`PostModal` already were, so the search state underneath stays mounted and the "Meus Vídeos" button no longer needs a `view` toggle at all — clicking it just opens the modal. `HistoryModal` adds two client-side filters — a text input matching against `historyLabel(h)` (the same label already shown per entry, so filtering by typed query text and by platform name both work through one field) and a platform `<select>` built from `PLATFORM_LABEL` — plus pagination at `HISTORY_PAGE_SIZE` (10) entries per page. No new backend endpoint was needed for this: `search_history.db` is already capped at `HISTORY_MAX` (30) non-favorites server-side, so the full list `GET /api/history` returns is small enough to filter/paginate entirely client-side; only the current page's rows exist in the DOM at once, the same practical effect a server-paginated endpoint would give here.

Validated end-to-end with a headless Playwright run against a live Flask instance seeded with 15 history entries across two platforms: the panel opens as an overlay (not inline) with the search page still visible/interactive behind it, pagination reads "Página 1 de 2" for the full unfiltered list, filtering down to one platform (~7-8 entries) drops back to a single page with no pagination controls shown, and clicking an entry closes the modal. Also caught and fixed during that same pass: `DownloadDirModal` was rendered as a descendant of the sticky header (which has `backdropFilter`) instead of at `App`'s top level alongside the other modals — an element with `backdrop-filter` establishes a new containing block for `position:fixed` descendants, so the modal's overlay was being confined to the header's own ~56px bounding box instead of the viewport. All modals (`HistoryModal`/`LibraryModal` included) are now rendered at the same top level as `FormatModal`/`PostModal`/`PlayerModal`, never inside the header.

### "Buscar em tudo" — searching every platform at once

A 6th button in the platform selector, "🌐 Tudo", switches into `searchAllMode`: a single query box searches X, xHamster, XVideos, xFree, Pornhub, and XNXX with `searchAllPlatforms()`. Each platform's `/api/search` call runs **sequentially inside a `for` loop, not `Promise.all`** — this is deliberate, not an oversight. Unlike X and xFree (each with their own dedicated session dict, `_SS`/`_XF_SS`), xHamster, XVideos, Pornhub, and XNXX are plain HTTP scrapers sharing the `_SITE_SS` machinery; firing two of those concurrently would have the second response's session update clobber the first one's in-flight pagination state mid-write. Running everything sequentially sidesteps that race entirely rather than special-casing which platform pairs are actually safe to parallelize.

Results stream in as each platform finishes (`setAllResults(prev => [...prev, ...tagged])` after every platform, not once at the end) rather than waiting for all 6 before showing anything. Each result is tagged with `_platform` on the way in; `VideoCard` renders a small badge from `PLATFORM_LABEL` when that field is present, and is otherwise unaffected — the card, `FormatModal`, and the download flow all only ever depended on `video.url`, never on the outer `platform` state, so mixing results from five different platforms in one grid needed no changes there.

**Per-platform "load more"**: `allSearchIds`/`allHasMore`/`allLoadingMore` track each platform's own `search_id` and pagination state independently, and `loadMoreAllPlatform(platform)` calls `/api/search/more` with that specific platform's `search_id`. This only became reliable once `_SITE_SS` on the backend changed from one shared dict to a dict keyed by site (`_SITE_SS["xhamster"]`, `_SITE_SS["xvideos"]`, `_SITE_SS["pornhub"]`), each looked up by matching `search_id` instead of assumed to be "whichever site searched most recently." With the old single shared slot, two of the three site platforms would *always* have an already-evicted session by the time the aggregate search finished (whichever ran before the last one in the sequential loop), making their "load more" permanently broken rather than just occasionally racy — this wasn't visible before "buscar em tudo" existed, since only one platform's results were ever on screen at a time.

**Bulk select in aggregate mode**: a separate `checkedAll` Set from the single-platform `checked`, keyed by `` `${platform}-${id}` `` rather than the bare video id — ids aren't guaranteed unique across five unrelated sites, so a composite key avoids one platform's selection accidentally toggling a same-id item from another. `VideoCard` gained an optional `checkKey` prop (falls back to `video.id`) so the same component serves both modes without duplication. `startBulkDownloadAll()` reuses the exact same `bulkTasks`/`BulkProgressModal` pipeline as single-platform bulk download — it only needs `url`/`title`/`uploader`/`fmt` per item, which aggregate results already carry regardless of source platform.

A run is recorded into search history as one `platform:"all"` entry (not five separate ones) — `historyLabel()` and `runHistoryEntry()` both special-case it, the latter setting `searchAllMode` and calling `searchAllPlatforms(qOverride)` the same way single-platform history entries use `search(overrides)`.

Validated by extending the same headless render test: switching into aggregate mode, submitting a query, confirming exactly one `/api/search` POST fires per platform (five total, one each for x/xhamster/xvideos/xfree/pornhub), confirming results from all five render together with the correct summary count, confirming the run collapses into a single history entry, confirming a platform-specific "load more" button fetches and appends more results then disappears once that platform is exhausted, and confirming selecting all aggregate results and bulk-downloading starts one `/api/download/start` call per item.

### Light theme

Every color in the app was originally a hardcoded hex literal inline in `style={{...}}` objects — no CSS classes, no theme system, ~1700 lines. Rewriting each one to read from a JS theme object would mean touching (and risking) hundreds of individual style blocks, and would force a full re-render of the tree on every toggle. Instead, only the **neutral palette** (11 tokens: page/card/input/selected/hover/placeholder backgrounds, 2 border shades, 3 text shades) became CSS custom properties — defined once in a `:root`/`html[data-theme="light"]` block in the `<style>` tag — and every occurrence of those specific hex values elsewhere in the file was mechanically replaced with the matching `var(--token)` string. Toggling the theme is just flipping one HTML attribute (`document.documentElement.setAttribute("data-theme", ...)`); the browser's own CSS cascade updates every inline style referencing a token instantly, with zero React re-render.

Accent/semantic colors (the brand blue, danger red, success green, warning yellow) and their translucent tinted variants (`rgba(29,155,240,.15)` and friends) were deliberately left untouched in both themes — same approach X/Twitter's own official light and dark themes use: blue is blue regardless of theme, only the neutrals flip. `PlayerModal` (the fullscreen video player) was excluded from the substitution entirely and keeps its literal dark colors — a "cinema mode" surface conventionally stays dark even in light-themed apps, and its overlaid controls (scrubber, delete button) are styled specifically for legibility against a black backdrop.

The theme choice persists to `localStorage` (`scrapperx_theme`); state lives in `Root` (above `App`) so it also applies to the login/loading screens rendered before `App` ever mounts, not just the main UI. A tiny inline `<script>` runs before React loads and applies `data-theme="light"` early if that's the stored choice, avoiding a flash of dark on first paint for light-theme users — `Root`'s own `useEffect` then normalizes the attribute on every mount regardless.

Contrast was checked programmatically (WCAG relative-luminance formula) rather than eyeballed, since this environment has no way to visually render a browser: primary text is 18.5:1 against the card background and 16.6:1 against the page background (WCAG AAA), secondary text is 6.2:1/5.6:1 (AA), well above the 4.5:1 minimum for body text. Validated end-to-end with the same headless render harness: the toggle switches `data-theme` and persists the choice to `localStorage`, and switching back restores dark.

---

## Video Download

- **Single download**: pick a specific format (quality, codec, estimated size) via yt-dlp
- **Batch download**: starts all of them in parallel, shows individual progress
- **Background**: closing the modal during a download lets the task keep running, shown in the `BgTray`
- **Survives closing the browser**: the download runs in a `threading.Thread` on the server process (`download_task` in `app.py`), fully decoupled from the HTTP connection — closing the tab/browser doesn't interrupt it. What was missing was the *frontend* remembering which tasks were in progress: `bgRef`/`bgTasks` are now mirrored to `localStorage` (`scrapperx_bg_tasks`) on every progress update, and a `useEffect` on `App`'s mount reads that list back and resumes polling — reopening the browser reconnects to the real progress. If the *server* restarts mid-download (not just the browser), the in-memory progress (`download_progress`) is lost; the UI detects this (a `not_found` response) and marks the task as an error instead of polling forever.
- Supported formats: `best`, up to 1080p, up to 720p, up to 480p
- Output: `<DOWNLOAD_DIR>/<title>_<id>.mp4` — `~/Downloads/X-Videos/` by default, but configurable (see below)

### Download Folder

`DOWNLOAD_DIR` used to be a constant computed once at import time; it's now a module-level global that can be changed at runtime and persists across restarts — via `.download_dir`, a plain text file next to `app.py`, read on boot the same way `.flask_secret_key` is (falling back to the default `~/Downloads/X-Videos` — and creating it — if nothing was ever saved, or if the saved path isn't usable right now, e.g. a USB drive that's unplugged at boot).

- `GET /api/settings/download-dir` returns the current folder plus the default one (so the UI has something to offer as a "reset" option without hardcoding it a second time on the frontend).
- `POST /api/settings/download-dir` with `{"path": "..."}` validates the new folder — `os.makedirs(path, exist_ok=True)` (creates it if missing, catching a mounted-but-read-only or a genuinely invalid path as an `OSError`), confirms it's actually a directory, and confirms `os.access(path, os.W_OK)` — before reassigning the `DOWNLOAD_DIR` global and persisting the choice. Any of those checks failing returns a specific error message instead of a generic failure.
- **Reassigning the global is enough** — every consumer (`download_task`'s thread arg, `/api/library`, the disk-usage `disk` field, `_library_path`) reads `DOWNLOAD_DIR` as a plain global lookup at call time, not at import time, so nothing else needed to change to make the switch take effect immediately for anything started *after* the change.
- **Doesn't move anything**: switching folders only changes where new downloads land and what the Library/disk-usage bar look at — files already sitting in the old folder stay exactly where they are, they just stop showing up in "Meus Vídeos" until you switch back.
- Frontend: the download-folder path in the header (previously just static text) is now a button — clicking it opens `DownloadDirModal`, a free-text path input (not a native folder picker, since the server may be headless with no desktop of its own to browse from) with a "usar padrão" shortcut and the same not-a-move warning inline.

### Pause, cancel, and resume

yt-dlp has no native "pause." The trick: yt-dlp's `FileDownloader._hook_progress()` calls every registered `progress_hook` with **no `try/except` around it** — any exception a hook raises propagates straight out of `extract_info()`, uncaught. `download_task()`'s hook checks a per-task `threading.Event` (`_download_control[task_id]["stop"]`) on every call; when set, it raises, and `download_task`'s own `except` blocks distinguish *why* via `_download_control[task_id]["action"]` (`"pause"` vs `"cancel"`, set by `/api/download/pause/<tid>` / `/api/download/cancel/<tid>` right before setting the event):

- **Pause** leaves the `.part` file on disk untouched. **Resume** is nothing more than calling `/api/download/start` again with the same `url`/`format_id` — since `outtmpl` (`%(title)s_%(id)s.%(ext)s`) is deterministic, yt-dlp lands on the exact same destination path, finds the existing `.part` file, and continues via HTTP Range requests using its own default resume behavior (`continuedl=True`) — no custom resume code needed at all.
- **Cancel** does the same signal, but the `except` handler removes the `.part` (and `.ytdl`, for fragmented downloads) via `_remove_partial_files()`, using the exact filename the hook last reported (`d["filename"]`) — not a directory-wide glob, so a concurrent, unrelated download's partial file is never at risk.
- Cancelling an **already-paused** task (no thread left to signal — `download_task` already returned, `_download_control[tid]` was popped in its `finally`) is handled as a distinct branch in `/api/download/cancel/<tid>`: it deletes the file recorded in `download_progress[tid]["filename"]` directly, no signaling involved.

Pause/cancel/resume controls appear everywhere download progress is shown — `FormatModal` (single download), `BulkProgressModal` (batch), and `BgTray` (background) — each managing its own polling independently but hitting the same three endpoints. `bgTasks`/`localStorage` (`scrapperx_bg_tasks`) now also persist `url`/`format_id`/`prog` per task (previously just `taskId`/`title`), which is what makes a paused download resumable even after reopening the browser.

Validated with a Python-level test that fakes `yt_dlp.YoutubeDL` to drive the hook directly (no real network): pausing mid-download preserves the `.part` file and records `url`/`format_id` for resume; cancelling mid-download removes it; cancelling an already-paused task removes it through the thread-less path; and re-invoking `download_task` with a paused task's `url`/`format_id` completes normally. Also validated end-to-end through the actual UI with the same headless render harness used for search history: starting a download, pausing it (progress bar and buttons update to a "Pausado" state), resuming it (fires a fresh `/api/download/start` and returns to "Baixando"), and cancelling it (immediately shows "Cancelado").

### Duplicate-download history (survives deleting the file)

`download_history.db` (SQLite, next to `app.py` — deliberately *not* under `tempfile.gettempdir()`, since the whole point is remembering a video was already downloaded long after the file itself was deleted, which rules out anywhere that gets wiped by a reboot or an OS `/tmp` cleanup; see the disk-leak fix in `ROADMAP.md` for why that's not hypothetical here) records every completed download by URL, along with its title, filename, and size. It's an append-only history (not one row per URL) rather than a single dedup table, so downloading the same URL again later — including a second time after deleting the first copy — stays fully recorded rather than silently overwriting the earlier entry.

`/api/download/start` checks this history by URL before doing anything; if there's a match, it returns `{"already_downloaded": true, "info": {...}}` instead of starting a new download, unless the request explicitly includes `"force": true`. Nothing is auto-blocked forever — `FormatModal` shows the recorded title/size/date and a "Baixar mesmo assim" button that retries the same call with `force:true`; `BulkProgressModal` does the same per-item (identified by array index rather than `taskId`, since an unstarted "already downloaded" item has no task yet — several could otherwise collide on a `null` key). Search results are also flagged: `_mark_downloaded(results)` runs a single batched `WHERE url IN (...)` query (not one lookup per result) at every point `/api/search`/`/api/search/more` returns results, adding `already_downloaded: bool` to each item — `VideoCard` shows a small "✓ Já baixado" badge when set. Since `/api/search/start_all` reuses the same `search()` view internally (see [Background Search](#background-search)), aggregate results get the same flag automatically, with no extra code.

`download_task()` records history on completion — after confirming the file exists on disk, it reads the real size with `os.path.getsize()` and inserts `(url, title, filename, filesize_bytes, downloaded_at)`. A fresh `sqlite3.connect()` per call (not one shared connection) is the standard-safe pattern here, since gunicorn runs 4 request threads (`--worker-class gthread`) and sqlite3 connections aren't safe to share across threads by default.

Validated with a Python test covering: a recorded download is found by URL lookup and persists independent of whether the file still exists on disk; a URL with no history returns `None`/starts normally; the batched bulk lookup used for marking search results returns exactly the matching URLs; `/api/download/start` blocks a known duplicate by default and proceeds with `force:true`; and `download_task`'s actual completion path (with a faked `yt_dlp.YoutubeDL`, no real network) records the real title and file size. Also validated through the UI: a search result shows the "já baixado" badge, opening the download modal and starting a download shows the warning with the recorded size instead of downloading, and "Baixar mesmo assim" retries with `force:true` and proceeds normally.

### Library preview

Each card in "Meus Vídeos" used to show only a static play icon on a blank background — no indication at all of which video it was without opening it. `LibraryCard` now renders a `<video preload="metadata">` pointed directly at `/api/library/video/<name>` (the same range-request-capable streaming endpoint the fullscreen `PlayerModal` already used) — `preload="metadata"` alone makes the browser display the first frame as a static thumbnail without downloading the whole file, even before any interaction, and hovering plays it (muted, looped) for a real live preview. Unlike `VideoCard`'s remote-preview flow, which needs a `POST /api/preview` round-trip to resolve a playable URL for a video hosted on someone else's site, a library item's own file already *is* the direct playable URL, so there's no extra request involved at all.

Validated with a headless render test (jsdom doesn't implement real media decoding, so `HTMLMediaElement.prototype.play`/`pause` are spied on rather than exercised for real): each library card renders a `<video>` pointed at the correct streaming URL, hovering a card calls `.play()`, and un-hovering calls `.pause()`.

### Free disk space in the Library

`GET /api/library` now also returns a `disk` field — `shutil.disk_usage(DOWNLOAD_DIR)` converted to GB (total/used/free) plus a `free_pct` — computed for whichever filesystem actually backs `DOWNLOAD_DIR`, not the server's root filesystem, so it stays correct even if downloads live on a separate mount (an external drive, a bind-mounted volume, etc.). `DiskUsageBar` renders it as a small usage bar above the video grid in "Meus Vídeos" — shown on the loading/empty states too, not just once there are videos, since low free space is exactly the kind of thing worth seeing before you've downloaded anything. The bar turns amber under 20% free and red under 10%, as an early low-space warning.

### Pornhub needs TLS impersonation
yt-dlp's native Pornhub extractor gets `403 Forbidden` when downloading the video page — it's a TLS *fingerprint* block (JA3/JA4), not an HTTP-header block (confirmed: the same headers via plain `requests` work fine; only yt-dlp's network stack gets blocked). The fix is making yt-dlp mimic a real Chrome TLS handshake via `curl_cffi`:
- `setup.sh` installs `curl_cffi` (pinned to `>=0.10,<0.15` — v0.15 breaks the API that yt-dlp `2026.03.17` expects)
- `build_ydl_opts(extra, url)` detects `pornhub.com` URLs and injects `impersonate=ImpersonateTarget.from_str("chrome")` (yt-dlp's Python API requires the `ImpersonateTarget` object, unlike the CLI's `--impersonate chrome` which accepts a plain string)
- Applies to `/api/formats`, `/api/download/start` and `/api/preview`

---

## Selenium Session Flow

```
POST /api/search
  └─ _ss_close()           # closes any previous session
  └─ _ss_driver()          # creates headless Chrome
  └─ _ss_inject_cookies()  # injects cookies via CDP
  └─ navigates to the URL
  └─ _ss_fetch_page()      # parses visible articles, scrolls if needed
  └─ stores the driver in _SS{}

POST /api/search/more
  └─ checks _SS["id"] and timeout
  └─ _ss_fetch_page()      # continues where it left off
```

xFree's Home and Search use the same session pattern (no cookies, no X involved):

```
POST /api/search  (platform=xfree, category=straight|gay|trans|all)
  └─ _xf_close()           # closes any previous session
  └─ _ss_driver()          # creates headless Chrome (reused from X)
  └─ navigates to /, /gay, /trans or /all      # sets the category (Vuex state)
  └─ if there's a query: types it into the page's own input[name=q] and presses Enter
  └─ _xf_fetch_page()      # parses visible wall__item cards, scrolls if needed
  └─ stores the driver in _XF_SS{}

POST /api/search/more
  └─ checks _XF_SS["id"] and timeout
  └─ _xf_fetch_page()      # continues where it left off
```

The session is closed automatically via `atexit` when the server stops.

### Robust cleanup of stuck processes (`_hard_kill_driver`)

When a session's Chrome/chromedriver crashes on its own (`tab crashed`, `Connection refused` in `_ss_fetch_page`/`_xf_fetch_page`), `driver.quit()` doesn't help — it needs a working WebDriver connection to ask Chrome to close, and that's exactly the connection that's broken. Left untreated, the entire process tree (chromedriver + Chrome + zygote/gpu/renderer) is orphaned and keeps running forever — **~1-1.5 GB of RAM per stuck session** (a ~15h-old orphaned session was found consuming server memory to the point of nearly exhausting swap).

`_ss_close()`/`_xf_close()` now call `_hard_kill_driver()`, which:
1. Tries `driver.quit()` normally (best effort)
2. Kills the chromedriver process directly by PID (`drv.service.process.pid`)
3. Scans **every** process on the system for that session's unique `--user-data-dir` (tagged onto `drv._user_data_dir` at creation, in `_ss_driver()`) and kills any process whose cmdline contains that path

Step 3 exists because a parent→child walk (`psutil.Process(pid).children()`) **doesn't work** once chromedriver is already dead: its children get reparented away immediately (out of the dead chromedriver's tree), so asking "what are this PID's children" after the crash finds nothing — confirmed by simulating the crash and testing it (0 of 9 orphaned processes killed via the walk; 9 of 9 killed via the `--user-data-dir` scan). It doesn't use `killpg` — chromedriver shares Gunicorn's own process group, and killing the group would take the server down with it.

### Automatic retry on transient browser crashes

The same `tab crashed`/`Connection refused` errors above don't just leak processes — without retry, they also surface as a raw Python exception straight to the user for whatever they were doing when Chrome died. `_x_open_session()`/`_xf_open_session()` (X and xFree respectively) factor the "create a Chrome session, log in / pick a category, wait for content" flow out of the route handlers so it can be reused by:

- **A fresh search** (`/api/search`): wrapped in a loop of up to `_BROWSER_RETRY_ATTEMPTS` (2) attempts — on a transient failure, the dead session is cleaned up (`_ss_close()`/`_xf_close()`, which now also runs `_hard_kill_driver()`) and the whole flow retries from scratch with a new Chrome instance.
- **"Load more"** (`/api/search/more`): a crash mid-scroll can't just retry the same call (the driver is gone), so instead it **reopens** a session for the same search (same URL/type for X; same category/query for xFree) and resumes — `seen_ids` and `scroll_count` are carried over into the new session first, so the resumed fetch naturally skips everything already shown instead of returning duplicates.

`_is_transient_browser_error()` matches the exception message against known crash signatures (`connection refused`, `tab crashed`, `errno 5`, `invalid session id`, etc.) — only these get retried; a `TimeoutException` from Selenium genuinely finding no results (or X asking to log in again) raises `_NoResultsError` instead and is never retried, since retrying wouldn't change that outcome. Validated by monkeypatching `_xf_open_session`/`_x_open_session`/`_ss_fetch_page`/`_xf_fetch_page` to fail once with the exact error strings seen in production, confirming: the retry fires exactly once, non-transient errors fail immediately without retrying, and a "load more" resume correctly preserves `seen_ids`/`category`/`query` (or `url`/`type` for X) across the reopened session.

`_x_open_session()`/`_xf_open_session()` themselves used to leak the driver they create on any failure that wasn't the one `TimeoutException` path they explicitly handled — a crash mid-open (e.g. `invalid session id: session deleted as the browser has closed the connection`, seen live in production) meant the caller's own `driver` variable never got assigned, so the caller's usual `if driver: driver.quit()` cleanup was a no-op, and the orphaned `chromedriver` process stuck around (until the watchdog below eventually reaped it, up to 15 min later). Both functions now wrap their whole body in `try/except Exception: driver.quit(); raise`, so any failure during session setup quits the driver immediately, before the exception ever reaches the caller.

This box is the user's own desktop, not a dedicated server — VSCode, a personal Chrome window, MariaDB, and the desktop shell are all competing for the same RAM as scrapperx's headless Chrome sessions, and swap was seen sitting completely full. Under that kind of pressure, `tab crashed` can happen on both the first attempt *and* the immediate retry, seconds apart — real production logs showed exactly that (X and xFree both crashing on attempt 2/2 within the same minute). Two changes address it: `_BROWSER_RETRY_ATTEMPTS` went from 2 to 3, and every retry (fresh search and "load more" resume alike) now does `time.sleep(2)` first, giving a momentary memory/CPU spike a chance to pass before spinning up another Chrome instance.

A flat 2s backoff still wasn't enough for a longer dip: production logs later showed three separate searches (X, X again, xFree) all exhausting 3 attempts within a ~40s window before recovering on their own, and a personal Chrome tab was found pinning ~32% CPU continuously for 3.6h in the background — real, sustained contention, not a one-off blip. The backoff is now escalating (3s → 6s → 9s between attempts) and `_BROWSER_RETRY_ATTEMPTS` went from 3 to 4, giving up to ~25-30s of total retry window to ride out a longer dip before giving up.

### Self-heal: worker restart after retries are fully exhausted

Even with 4 escalating attempts, sustained contention can still exhaust all of them — at that point `_self_heal_restart()` does one more thing beyond just surfacing the error: it sends `SIGTERM` to the worker process itself (`os.kill(os.getpid(), signal.SIGTERM)`). This is exactly the mechanism gunicorn's own `--max-requests` worker recycling uses internally, so it's standard, well-supported behavior, not a hack — the worker finishes any in-flight response, exits, and gunicorn's arbiter (a separate, always-alive process — confirmed via `ps`: arbiter and worker are parent/child) immediately spawns a fresh one to replace it. The app runs under a `systemd` unit (`Type=simple`, `Restart=always`) that tracks the *arbiter's* PID via `start.sh`'s `exec gunicorn ...`, not the worker's — so this is fully transparent to systemd, which never even notices a worker-level restart happened.

Skipped entirely if a download is in progress (`download_progress` has any entry with `status == "downloading"`) — `download_task()` runs as a background thread inside this same worker process and would be killed along with it. Before restarting, it also runs `_ss_close()`, `_xf_close()`, and `_watchdog_sweep()` for a best-effort cleanup of any tracked session or orphaned chromedriver.

**Important caveat**: this does not fix the actual root cause of contention-driven crashes (e.g. another process on the host hogging CPU) — restarting scrapperx's own worker has no effect on an unrelated Chrome tab or VSCode process. It only guarantees scrapperx's own internal state gets a clean slate faster than the watchdog sweep (up to 120s later) would, right after a crash pattern strong enough to exhaust every retry. Validated by monkeypatching `os.kill` and toggling `download_progress`: confirmed the restart is skipped while a download is active, and proceeds (calling `os.kill` with `SIGTERM`) when none is.

### Critical fix: every Chrome session was leaking its profile directory on disk

While investigating why crashes kept happening even after all of the above, `/tmp` was found completely full (7.3 GB, 100% used). Root cause: `_ss_driver()` creates a unique `tempfile.mkdtemp()` directory as each session's `--user-data-dir`, but **no cleanup path ever deleted it** — not `_ss_close()`, not `_hard_kill_driver()`, not the watchdog. Chrome only auto-cleans a profile directory it creates itself; one supplied via `--user-data-dir` is never touched. Every single search this app has ever run leaked one of these directories permanently — found ~27 leftover ones (2 MB–870 MB each) once `/tmp` was inspected directly. With the disk full, any *new* Chrome session fails to write its profile and crashes immediately — this is very likely the actual (or at least a major) cause of the "tab crashed" pattern chased through the sections above, not purely external CPU contention.

Fixed at every level: `_hard_kill_driver()` now `shutil.rmtree()`s the tagged `--user-data-dir` after killing the process tree; the watchdog's orphan sweep extracts and removes the `--user-data-dir` from each orphaned chromedriver's child Chrome process before moving on; every remaining ad-hoc `driver.quit()` in the `/api/search` failure-cleanup paths was replaced with `_hard_kill_driver()` so it also cleans up the directory instead of just quitting the WebDriver session. Also removed `_selenium_search()`/`search_x_videos()` — a second, dead X-search code path (unreferenced by any active route) that built its own `--user-data-dir` inline and leaked it completely outside `_hard_kill_driver`'s reach. Validated with three tests: `_hard_kill_driver` removes a tagged directory, a simulated crash inside `_x_open_session` leaves nothing behind, and the watchdog's orphan sweep cleans up a real spawned process carrying a `--user-data-dir` argument.

### Background watchdog for sessions the reactive cleanup can't reach

Retry and `_hard_kill_driver` both only run when a request handler actually notices something's wrong — neither helps if no new request ever comes in for the dead session. Two real gaps:

- A user starts a search, then just closes the tab without ever calling "load more" again — that Chrome session would otherwise idle forever; nothing reactively checks `_SS_TIMEOUT`/`_XF_SS_TIMEOUT` unless a *new* request happens to reference that session ID.
- The server process itself gets killed (`kill -9`, OOM) — the next process's `_SS`/`_XF_SS` start out empty, with no idea the old chromedriver/Chrome tree even exists. This is exactly the ~15h/~1.5GB leak that motivated `_hard_kill_driver` in the first place, just from a different trigger (the tracking state itself being lost, not a crash `_ss_close()` gets called for).

`_watchdog_sweep()` runs in a daemon thread (`_watchdog_loop`, every `_WATCHDOG_INTERVAL` = 120s, started once at module import) and does two independent things: closes `_SS`/`_XF_SS` if tracked but idle past their timeout (same `_ss_close()`/`_xf_close()` used everywhere else), and separately scans **every** `chromedriver` process on the system — killing (with its children) any one that isn't backing a currently-tracked session and has been running longer than `_WATCHDOG_ORPHAN_AGE` (900s, generously past how long real navigation ever takes, so nothing legitimate is ever "untracked" for that long). Validated against real spawned `chromedriver` processes: a tracked one survived a sweep with the orphan-age check forced to trigger on everything, an untracked one didn't — and in the same run it also caught and killed a genuinely orphaned `chromedriver` left over from earlier testing, confirming the scan works against real leaks, not just the synthetic case.

### Periodic X cookie revalidation

Before this, `session_state["logged_in"]` was only (re)checked at server boot and when the user manually clicked "Validar" — if the X session expired while the server just kept running (the common case, since restarts are infrequent), the app kept believing it was logged in until an actual search or upload hit a raw X API error (this is what caused the earlier `"Failed to authenticate. API Error: 401 OAuth access token has expired."` incident reaching the user instead of the re-auth screen).

`_cookie_revalidate_check()` reruns the same `validate_cookies()` used at boot/"Validar" and syncs `session_state["logged_in"]` to the result either direction, called every `_COOKIE_REVALIDATE_INTERVAL` (1800s / 30 min — cookies don't expire fast enough to justify hitting X's API more often) by its own daemon thread (`_cookie_revalidate_loop`), independent of the process watchdog above so a slow cookie check can never delay it. No-ops if there's no cookies file yet, and swallows network errors without touching the existing state (a transient failure to *check* isn't evidence the session is actually invalid). Validated with 4 cases: no cookies file (no-op), session expired (flips `True → False`), session valid again (flips `False → True`), and a network error during the check (doesn't crash, leaves state untouched).

### Alerting when a scraper silently stops returning results

An exception (network error, HTML parse error, Selenium crash) already surfaces immediately as an error message to the user — that's not a gap. The dangerous case is *silent*: the request "succeeds" (200 OK, no exception) but the parser extracts nothing, because the target site changed its HTML/JSON shape out from under a brittle selector or dict key path. A single zero-result search is normal (a rare query, a momentarily empty page); several of them **in a row on an endpoint that should reliably have content** is the actual signal something broke.

`_record_scraper_outcome(platform, got_results, context)` tracks a per-platform consecutive-zero-result streak in `_SCRAPER_HEALTH`, called from every fresh-search code path in `/api/search` (not `/api/search/more` — pagination has its own "finished"/"has_more" semantics that would just add noise here). Any call with `got_results=True` resets that platform's streak to 0. Deliberately scoped to **home/category-browse calls only, not keyword searches** — a narrow keyword can legitimately return zero on a fully-working parser, but a category landing page or an active account's own feed should always have content:

- **xHamster / XVideos / Pornhub**: only recorded when `query` is empty (home/category browsing).
- **X**: only recorded for `type in ("home", "following")`, and explicitly excludes the "X solicitou login" case from `_NoResultsError` — that's an auth problem, not evidence the tweet-parsing logic broke.
- **xFree**: every `_NoResultsError` counts — xFree has no login wall, so a category page rendering with zero `.wall__item` elements has no legitimate explanation other than something being broken.

Once a platform's streak reaches `_SCRAPER_ZERO_ALERT_THRESHOLD` (5), it logs one clearly-tagged `[PARSER-ALERT]` line (easy to `grep` out of the logs) — then stays quiet until the streak grows by another `_SCRAPER_ZERO_ALERT_REPEAT` (10) failures before alerting again, so a scraper that stays broken for hours doesn't flood the log on every single call but also isn't forgotten. The message deliberately doesn't over-claim a single diagnosis ("parser broke" vs. "site is down") — both produce the same symptom from here, and the alert's job is just to flag "go look," not to guess which.

Validated with 6 cases: no alert below the threshold, exactly one alert fires the instant the streak hits 5, no repeat alert between 5 and 15, a repeat alert fires exactly at 15, a success resets the streak so a later failure run needs a fresh 5 to re-alert, and platforms are tracked fully independently of each other.
