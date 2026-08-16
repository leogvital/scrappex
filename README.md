# X Video Scraper

*[Leia em português](README.pt-BR.md)*

Local web application to search and download videos from **X (Twitter)**, **XHamster**, **XVideos**, **xFree** and **Pornhub**.

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
| XHamster/XVideos/Pornhub scraping | `requests` (direct HTTP) |
| Video download | yt-dlp |
| Frontend | React 18 + standalone Babel (zero build step) |
| Cookie storage | Netscape-format file at `/tmp/x_cookies.txt` |
| Downloaded videos | `~/Downloads/X-Videos/` |

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
| POST | `/api/search` | Search videos (first page) |
| POST | `/api/search/more` | Load next page |
| POST | `/api/preview` | Direct URL for in-browser preview |
| POST | `/api/formats` | List available formats (yt-dlp) |
| POST | `/api/download/start` | Start an async download |
| GET | `/api/download/progress/<tid>` | Download progress |
| GET | `/api/download/file/<tid>` | Serve the downloaded file |
| GET | `/api/library` | List videos in the downloads folder |
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
| `LibraryGrid` | Grid of downloaded videos |
| `PlayerModal` | Fullscreen player with seek, play/pause, next/previous, delete |

### Search history and favorites

Every successful search (any platform, including Home-feed loads) is recorded into `searchHistory`, persisted to `localStorage` under `scrapperx_search_history` — the same pattern already used for background download tracking (`scrapperx_bg_tasks`). A history entry is identified by `platform+type+query+category`; re-running the same search moves it to the top instead of duplicating, and preserves an existing favorite flag rather than replacing it with a fresh unstarred entry. Non-favorite entries are capped at `HISTORY_MAX` (30, oldest dropped first); favorites are exempt from the cap and from "Limpar histórico" (which only clears non-favorite entries).

Clicking a history entry (`runHistoryEntry`) needs to both update the visible platform/type/query/category selectors *and* fire the search immediately — but React state setters are async, so `search()` reading `platform`/`query`/etc. from its own closure would still see the *previous* values on that same call. `search()` therefore accepts an optional `overrides` object that takes precedence over current state for that one invocation, while every existing caller (the search button, `Enter` in the query field, the auto-search effect on tab change) keeps calling `search()` with no arguments and behaves exactly as before. One consequence worth knowing if touching this code: `search` is called directly as `onClick={()=>search()}`, never bare as `onClick={search}` — React would pass the click's `SyntheticEvent` as `overrides` in that case, and since events carry a real `.type` property (`"click"`), `eType` would silently become the string `"click"` instead of falling back to state.

Validated with a headless render test (jsdom + React 18, Babel-transforming the actual `index.html` script block) driving real DOM clicks/input events end-to-end: opening the empty history panel, running a search and confirming it's recorded with the right label, favoriting an entry, confirming "Limpar histórico" preserves it, and confirming clicking a history entry fires a fresh `/api/search` with the expected body.

### "Buscar em tudo" — searching every platform at once

A 6th button in the platform selector, "🌐 Tudo", switches into `searchAllMode`: a single query box searches X, xHamster, XVideos, xFree, and Pornhub with `searchAllPlatforms()`. Each platform's `/api/search` call runs **sequentially inside a `for` loop, not `Promise.all`** — this is deliberate, not an oversight. Unlike X and xFree (each with their own dedicated session dict, `_SS`/`_XF_SS`), xHamster, XVideos, and Pornhub all share one backend session slot (`_SITE_SS`) since they're plain HTTP scrapers, not Selenium; firing two of those three concurrently would have the second response's `_SITE_SS.update(...)` clobber the first one's in-flight pagination state. Running everything sequentially sidesteps the question entirely rather than special-casing which platform pairs are actually safe to parallelize.

Results stream in as each platform finishes (`setAllResults(prev => [...prev, ...tagged])` after every platform, not once at the end) rather than waiting for all 5 before showing anything. Each result is tagged with `_platform` on the way in; `VideoCard` renders a small badge from `PLATFORM_LABEL` when that field is present, and is otherwise unaffected — the card, `FormatModal`, and the download flow all only ever depended on `video.url`, never on the outer `platform` state, so mixing results from five different platforms in one grid needed no changes there. One deliberate v1 scope cut: `showCheckbox={false}` on aggregate-mode cards — bulk multi-select reads from the single-platform `checked`/`results` state, and wiring it to also work against `allResults` was left out to keep this change bounded; aggregate mode supports individual preview/download per card only.

A run is recorded into search history as one `platform:"all"` entry (not five separate ones) — `historyLabel()` and `runHistoryEntry()` both special-case it, the latter setting `searchAllMode` and calling `searchAllPlatforms(qOverride)` the same way single-platform history entries use `search(overrides)`.

Validated by extending the same headless render test: switching into aggregate mode, submitting a query, confirming exactly one `/api/search` POST fires per platform (five total, one each for x/xhamster/xvideos/xfree/pornhub), confirming results from all five render together with the correct summary count, and confirming the run collapses into a single history entry.

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
- Output: `~/Downloads/X-Videos/<title>_<id>.mp4`

### Pause, cancel, and resume

yt-dlp has no native "pause." The trick: yt-dlp's `FileDownloader._hook_progress()` calls every registered `progress_hook` with **no `try/except` around it** — any exception a hook raises propagates straight out of `extract_info()`, uncaught. `download_task()`'s hook checks a per-task `threading.Event` (`_download_control[task_id]["stop"]`) on every call; when set, it raises, and `download_task`'s own `except` blocks distinguish *why* via `_download_control[task_id]["action"]` (`"pause"` vs `"cancel"`, set by `/api/download/pause/<tid>` / `/api/download/cancel/<tid>` right before setting the event):

- **Pause** leaves the `.part` file on disk untouched. **Resume** is nothing more than calling `/api/download/start` again with the same `url`/`format_id` — since `outtmpl` (`%(title)s_%(id)s.%(ext)s`) is deterministic, yt-dlp lands on the exact same destination path, finds the existing `.part` file, and continues via HTTP Range requests using its own default resume behavior (`continuedl=True`) — no custom resume code needed at all.
- **Cancel** does the same signal, but the `except` handler removes the `.part` (and `.ytdl`, for fragmented downloads) via `_remove_partial_files()`, using the exact filename the hook last reported (`d["filename"]`) — not a directory-wide glob, so a concurrent, unrelated download's partial file is never at risk.
- Cancelling an **already-paused** task (no thread left to signal — `download_task` already returned, `_download_control[tid]` was popped in its `finally`) is handled as a distinct branch in `/api/download/cancel/<tid>`: it deletes the file recorded in `download_progress[tid]["filename"]` directly, no signaling involved.

Pause/cancel/resume controls appear everywhere download progress is shown — `FormatModal` (single download), `BulkProgressModal` (batch), and `BgTray` (background) — each managing its own polling independently but hitting the same three endpoints. `bgTasks`/`localStorage` (`scrapperx_bg_tasks`) now also persist `url`/`format_id`/`prog` per task (previously just `taskId`/`title`), which is what makes a paused download resumable even after reopening the browser.

Validated with a Python-level test that fakes `yt_dlp.YoutubeDL` to drive the hook directly (no real network): pausing mid-download preserves the `.part` file and records `url`/`format_id` for resume; cancelling mid-download removes it; cancelling an already-paused task removes it through the thread-less path; and re-invoking `download_task` with a paused task's `url`/`format_id` completes normally. Also validated end-to-end through the actual UI with the same headless render harness used for search history: starting a download, pausing it (progress bar and buttons update to a "Pausado" state), resuming it (fires a fresh `/api/download/start` and returns to "Baixando"), and cancelling it (immediately shows "Cancelado").

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
