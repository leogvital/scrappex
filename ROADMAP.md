# Roadmap — X Video Scraper

*[Leia em português](ROADMAP.pt-BR.md)*

Project status and next steps. Kept alongside [README.md](README.md) (which documents *how* each thing works — this file documents *what* already exists and *what's missing*).

---

## ✅ Done

### Platforms
| Site | Search | Home | Category | Mechanism |
|---|---|---|---|---|
| X (Twitter) | Keyword, hashtag, user | For You, Following | — | Selenium |
| XHamster | ✓ | ✓ | Straight/Gay/Trans | HTTP |
| XVideos | ✓ | ✓ (no pagination — site limitation) | Straight/Gay/Trans | HTTP |
| xFree | ✓ | ✓ | Straight/Gay/Trans/All | Selenium (Cloudflare bypass) |
| Pornhub | ✓ (Trans has no keyword search — site limitation) | ✓ | Straight/Gay/Sapphic/Trans | HTTP + `curl_cffi` (TLS impersonation) |
| XNXX | ✓ (Sapphic has no keyword search — site limitation) | ✓ | Straight/Gay/Sapphic/Trans | HTTP |
| TNAFlix | ✓ (Straight only — other categories have no keyword search, site limitation) | ✓ (no pagination — site limitation) | Straight/Gay/Sapphic/Trans | HTTP |

### Account and session
- App login with username/password configurable via `.env.local` (outside the repository — see `.env.local.example`), persistent session — survives closing the browser (30-day cookie) and restarting the server (secret key saved to disk)
- Rate limit on `/api/auth/app-login` — 5 wrong attempts per IP every 5 minutes, then blocks (even the correct password) with a "wait Xs" message; in-memory only (no Redis — `--workers 1` already has no state to sync across processes), resets on a restart, but that's harmless here. A correct login clears that IP's failure history immediately
- X login (cookies) automatically revalidated on server boot
- Publishing a tweet with video (chunked upload with real progress)
- Windows compatibility (Waitress instead of Gunicorn, `.bat` scripts equivalent to the `.sh` ones)

### Downloads
- Single and batch download, with format/quality selection via yt-dlp
- Background downloads survive closing the browser (resumed via `localStorage` on reopen)
- Local library with player, deletion, and streaming
- **Preview on library cards** — each card used to show only a static play icon on an empty background, no indication at all of which video it was. Now uses `<video preload="metadata">` pointed at the local stream (`/api/library/video/<name>`, already supports range requests), so the browser shows the first frame as a static thumbnail even without interaction; hovering plays the real video (muted, looped) for a real preview. Unlike the search-result preview (`VideoCard`, which needs a POST to `/api/preview` to resolve a remote URL), a library item already IS the local file, so there's no round-trip at all
- **Persistent download history, survives deleting the file** — `download_history.db` (SQLite, next to `app.py`, not in `/tmp` — the goal is remembering long after, not just for the current session) records every completed download by search+URL+title+size. `/api/download/start` checks this history by URL before starting; if there's already a record, it returns the info (title, size, date) instead of downloading again, and only proceeds with an explicit `force:true` from the user — clicking "Baixar mesmo assim" after seeing the warning. Search results also get a "✓ Já baixado" badge when the URL is already in the history. Since it's a history (not one row per URL), downloading the same URL again after deciding "download anyway" also gets recorded, without losing the previous record
- **Free disk space in the Library** — `/api/library` also returns `shutil.disk_usage(DOWNLOAD_DIR)` in GB; `DiskUsageBar` shows this as a small bar above the "Meus Vídeos" grid (turns amber under 20% free, red under 10%)
- **Configurable download folder** — `DOWNLOAD_DIR` stopped being fixed and became a global that can change at runtime (persisted to `.download_dir`, next to `app.py`), so downloads can be pointed at a USB drive or any other folder instead of the default `~/Downloads/X-Videos`. `POST /api/settings/download-dir` validates (creates it if missing, confirms it's a folder, confirms write permission) before switching. Clicking the path shown in the header opens the change modal. Switching folders doesn't move already-downloaded videos

### UI/UX
- Search history and favorites — every successful search (any platform) goes into a history persisted server-side (`search_history.db`, shared across browsers/devices); repeated searches (same platform+type+query+category) move to the top instead of duplicating; favoriting an entry protects it from being deleted by "Limpar histórico" and survives re-runs; clicking an entry reconfigures the UI and re-runs the search
- **History and Meus Vídeos as modals, with filter/pagination in the history** — both used to live as either a whole separate page (Meus Vídeos) or an inline panel (History); now they're modals layered over the search page (`HistoryModal`/`LibraryModal`), so the search underneath stays mounted and visible. The history gained a searched-term text field and a site selector, plus pagination (10 per page) — all client-side, no new endpoint, since the list is already capped at 30 non-favorites server-side
- Simultaneous search across all platforms ("🌐 Tudo") — searches the same keyword across 𝕏, xHamster, XVideos, xFree, Pornhub, XNXX, and TNAFlix **sequentially** (not in parallel — see "per-site session" below), with each platform's results appearing as they arrive and a badge indicating each card's origin. Has independent "load more" per platform and bulk selection to download several videos from different platforms at once (closing both v1 scope gaps)
- **Per-site session** (`_SITE_SS` stopped being a single dict and became one slot per site — xHamster/XVideos/Pornhub/XNXX/TNAFlix) — before, since all of them shared a single backend session slot, a subsequent search would evict the previous one's session; that didn't matter while only one platform could be viewed at a time, but it silently broke "load more" in "🌐 Tudo" mode for at least two of the platforms (their session had already been replaced before the user even clicked anything). Fixed by giving each site an independent slot, looked up by `search_id` instead of assumed to be "the only active one right now"
- Download queue with pause/cancel/resume — yt-dlp has no native "pause," so pausing in practice means: signal the progress hook to abort (raises an exception, caught by `download_task`) and leave the `.part` file on disk; resuming is simply calling `/api/download/start` again with the same URL/format — since the output name is deterministic, yt-dlp finds the existing `.part` and continues via HTTP Range requests, no extra "resume" code needed. Cancel uses the same signal, but removes the `.part` (and `.ytdl`) instead of preserving it; cancelling an already-paused download (no thread running) deletes the file directly in the route, no signaling needed. Pause/cancel/resume controls are available anywhere download progress is shown: single-format modal, batch-download modal, and the background downloads tray
- Light theme — only the neutral palette (backgrounds/borders/text) is themed via CSS variables (`:root` = dark default, `html[data-theme="light"]` = light); accent/semantic colors (blue, red, green, yellow) and the always-dark surfaces of the fullscreen player (`PlayerModal`) stay constant in both themes, same as X/Twitter's own light theme. Choice persisted to `localStorage`, an inline script before React mounts avoids a flash of the wrong theme on first load for anyone who already chose light
- **Search runs in the background on the server** (same pattern as downloads) — before, a search (mainly X/xFree via Selenium, or "buscar em tudo" running 5 platforms in a row) stayed stuck inside one blocked `fetch()` for however long it took; if the tab went to the background (phone screen locks, switching apps), mobile browsers suspend/limit JS and network, potentially dropping the request and losing the whole search. Now `/api/search/start` and `/api/search/start_all` kick off the real work in a server thread and return a `task_id` right away; the client just polls `/api/search/task/<tid>` (every 1.5s), with the `task_id` saved to `localStorage` — closing and reopening the tab (or the OS killing a backgrounded tab) reconnects to the search that kept running the whole time, with the result showing up ready. `/api/search` keeps existing and working exactly as before (synchronous call) — the new endpoints just reuse the existing view via Flask's `test_request_context`, without duplicating any scraping logic. Deliberate scope: only the new search became async; "load more" (`/api/search/more`) stays synchronous, since it's usually fast and triggered while the user is already engaged looking at results, not "leaving and coming back later"

### Robustness fixes already made
- Pornhub TLS fingerprint block against yt-dlp (via `curl_cffi`)
- X's own cookie-validation endpoint discontinued (`verify_credentials.json` → swapped for a real upload-based proof)
- Login state stuck at `True` even with an expired session (desync fixed)
- Missing thumbnails on Pornhub's Home (different card attribute)
- Cross-page duplicates in Pornhub's pagination (dedup by ID)
- Gunicorn 26 *control socket* permission error (`--no-control-socket`)
- Download hanging when clicking "Baixar" while more videos were auto-loading (Gunicorn `sync` worker → `gthread` + 4 threads)
- ~1-1.5 GB RAM leak per Chrome session that crashes on its own (`_hard_kill_driver`)
- Automatic retry when Selenium (X or xFree) hits a transient Chrome I/O error (`Connection refused`, `tab crashed`) — reopens the session and resumes where it left off, without duplicating already-shown items
- Background watchdog (`_watchdog_sweep`, every 120s) closes idle sessions and kills orphaned chromedriver processes older than 15 min — covers cases the reactive cleanup doesn't catch (a tab closed without ever calling "load more" again, or the server itself being killed and losing track of the session)
- Periodic revalidation of X cookies (`_cookie_revalidate_check`, every 30 min) — before, the session was only rechecked on boot or when clicking "Validar"; if it expired while the server kept running, the app kept believing it was logged in until a raw API error showed up on a search/upload
- Orphaned `chromedriver` process leak when the X/xFree session crashed right at opening (e.g. `invalid session id` from Chrome closing the connection) — `_x_open_session`/`_xf_open_session` didn't have a `try/except` covering the whole body, so any error outside the already-handled path (timeout) left the driver without a `quit()`; now any exception during opening kills the driver before propagating
- X/xFree retries exhausting both attempts back-to-back in seconds, under real memory pressure on the machine (it's the user's personal desktop, not a dedicated server — VSCode, personal Chrome, MariaDB, and gnome-shell compete for the same RAM) — added a `sleep(2)` before each new attempt (fresh search and "load more" resume alike), to give a momentary memory/CPU spike a chance to pass, and the attempt count went from 2 to 3
- The fixed 2s backoff still wasn't enough for longer contention spikes (~40s seen in production, with a personal Chrome tab continuously consuming ~32% CPU for 3.6h) — swapped for escalating backoff (3s/6s/9s) and the attempt count went from 3 to 4, giving up to ~25-30s of total window to survive a longer spike before giving up
- Self-heal: if all 4 retry attempts are exhausted with a transient error (`_self_heal_restart`), the gunicorn worker restarts itself (`SIGTERM` on its own process — gunicorn's arbiter spawns a replacement right away, same mechanism as `--max-requests`), skipping if a download is in progress (runs as a background thread in the same worker). Doesn't fix the root cause (external CPU/memory contention), just guarantees a clean state faster than the watchdog (up to 120s later) could
- **Critical disk leak**: `_ss_driver()` creates a unique directory (`tempfile.mkdtemp()`) in `/tmp` as each Chrome session's `--user-data-dir`, but no cleanup path (`_ss_close`/`_xf_close`/`_hard_kill_driver`/watchdog) ever deleted that directory from disk — Chrome doesn't clean up an externally-provided `--user-data-dir` on its own (it only cleans up profiles it creates itself). Found while investigating why the server's `/tmp` reached 100% full (7.3 GB, ~27 old session directories never removed): with the disk full, any new Chrome session fails to write its profile and hangs immediately — very likely the real cause (or a relevant one) behind a good chunk of the "tab crashed" this roadmap had been attributing only to CPU contention. Fixed: `_hard_kill_driver` now deletes the session's `--user-data-dir` after killing the processes; the watchdog's orphan sweep also extracts and deletes the `--user-data-dir` of every orphaned chromedriver found; every standalone `driver.quit()` in `/api/search`'s failure-cleanup points was swapped for `_hard_kill_driver()` for the same reason. As a bonus, removed `_selenium_search`/`search_x_videos` — a second, dead/unreferenced X search path not hit by any active route, which also leaked its own `--user-data-dir` in a way `_hard_kill_driver` didn't follow at all
- Structured alert/log when a scraper stops returning results (`_record_scraper_outcome`) — a raised exception already shows up immediately as an error to the user; the gap was the *silent* case: the request "works" (200 OK, no exception) but the parser extracts nothing, because the site changed its HTML/JSON out from under a fragile selector/key. Tracks a streak of *home/category* searches in a row with zero results per platform (not keyword searches — a rare search can legitimately return zero, but a platform's feed/category should always have content); any success resets the streak. From 5 in a row with no result, logs a clearly-marked `[PARSER-ALERT]` (easy to grep); if it stays broken, re-alerts every 10 further failures instead of flooding the log on every call

---

## 🐛 Known limitations (not bugs to fix — real limits of the source site)

- **Pornhub / Trans**: no keyword-search endpoint on the site — search falls back to the category's featured feed
- **XVideos / Home**: each category's landing page doesn't paginate (same content on every page) — no "load more"
- **xFree**: needs Selenium (not plain HTTP) because the site loads content via client-side infinite scroll and blocks bots on the Gay/Trans categories

---

## 🔧 Proposed next steps

### New platforms
- [ ] Decide with the user which sites come next (candidates to raise: other aggregators with an orientation filter, sites with a public API, etc.)

---

## Operational notes

- Deployed under a `systemd` unit (`scrapperx.service`, `Type=simple`, `Restart=always`, `ExecStart=/app/scrapperx/start.sh`, `User=touch`) — restart with `sudo systemctl restart scrapperx.service`, **not** by running `restart.sh` by hand (the two fight over port 5000; see the [Installation](README.md#installation-and-setup) section for why)
- Always read the README before making changes; after every deploy, update **both** README files (`README.md` and `README.pt-BR.md`) and **both** roadmap files (`ROADMAP.md` and `ROADMAP.pt-BR.md`), then commit and push
