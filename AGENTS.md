# AGENTS.md

Instructions for AI coding agents (Claude Code or otherwise) working in this repo.

## What this is

**scrapperx** (X Video Scraper) — a self-hosted web app to search and download videos from
X (Twitter), XHamster, XVideos, xFree, Pornhub, XNXX, TNAFlix and RedTube.

- **Backend**: `app.py` — single-file Flask app. Selenium (headless Chrome) for X and
  xFree; plain `requests`-based HTML scraping for XHamster/XVideos/Pornhub/XNXX/TNAFlix/RedTube.
- **Frontend**: `index.html` — single-file React 18 app, compiled in-browser via Babel.
  **No build step.** Edit it directly; there is no `npm run build`.
- **Deployment**: systemd service (`scrapperx.service`) running `start.sh`, which launches
  `gunicorn app:app --workers 1 --worker-class gthread --threads 4`. Single worker + threads
  means module-level globals (`_SITE_SS`, `_SS`, `_XF_SS`, etc.) are safely shared in-process —
  no multi-process state-sync concerns, but *do* think about thread races between concurrent
  requests touching the same global dict.
- `package-lock.json` and `x-video-scraper.jsx` are stray/unrelated files in this checkout —
  leave them out of commits (not part of this app).

## Restarting the live service

```
sudo systemctl restart scrapperx.service
```

**Never** restart via `su` + `restart.sh` — the service is systemd-managed, and running the
script manually conflicts with the managed process.

## Testing changes before deploying

There's no test suite. Verify changes like this instead:

- **Backend (`app.py`) logic**: copy `app.py` to a scratch directory and import it from there
  — importing it in place fails because `_load_or_create_secret_key()` tries to read/write
  `.flask_secret_key`, which isn't writable by every user. From the scratch copy:
  ```python
  import app_copy as A
  c = A.app.test_client()
  with c.session_transaction() as sess:
      sess['app_logged_in'] = True   # routes require this; see _require_app_login
  r = c.post('/api/search', json={...})
  ```
  Set `SCRAPPERX_APP_PASS` and `COOKIES_FILE` env vars to dummy values first so the app
  doesn't block on missing real config. Delete the scratch copy when done.
- **Scraper functions directly**: for a quick check against the live site (no Flask needed),
  just `import` the scratch copy and call e.g. `A._scrape_redtube(...)` directly.
- **Frontend (`index.html`) JSX syntax**: extract the `<script type="text/babel">` block and
  run it through `@babel/preset-react` to catch syntax errors before deploying — a broken
  JSX edit otherwise only surfaces as a blank page in the browser.
- **Live UI behavior**: Playwright works in this environment; raw `file://` navigation to a
  local HTML fixture does **not** (`net::ERR_FILE_NOT_FOUND`) — serve it over
  `python3 -m http.server <port> --bind 127.0.0.1` and navigate to `http://127.0.0.1:<port>/...`
  instead. Raw `selenium.webdriver.Chrome()` fails here too
  (`SessionNotCreatedException: cannot kill Chrome`) — use Playwright for anything needing a
  real browser.
- **No live X session is available in this environment** (`x_cookies.txt`/the cookies file
  isn't accessible) — X-specific scraping logic can only be verified against local HTML
  fixtures, not the real site. Say so explicitly when reporting a fix rather than implying
  it was confirmed live.

## When a user-reported bug doesn't reproduce in isolated testing

This has come up repeatedly: a plausible, locally-verified fix ships, and the user reports
the exact same symptom persists. Don't keep guessing blind. Add a small, temporary,
**visible-on-screen** debug readout (not just a console.log — the user is often on mobile
with no devtools access) showing the actual runtime values at the point of failure, ask for
a fresh screenshot, then remove the debug code once root cause is confirmed. This found the
real cause both times it was tried this session:
- X thumbnails rendering blank → overlay showed `video.thumbnail` was never actually empty;
  the URL was valid but failing to *load client-side* (network/DNS-level blocking of
  `twimg.com`, not a scraping bug) — fixed by proxying through `/api/thumb-proxy`.
- RedTube "carregar mais" appearing to do nothing → overlay showed the server-side page
  counter had silently jumped to page 7 and returned content byte-identical to page 1 — the
  infinite-scroll effect was re-firing in a rapid invisible loop, not a pagination bug per se.

Related trap: don't trust a site's own self-reported result count (e.g. "200,000 Vídeos") as
the real depth of what's actually reachable via pagination — it's frequently a loose,
inflated tag-match total. If you need to know how deep real pagination goes, page through it
directly and count where new content actually stops. And don't treat a single anomalous page
as a hard "end of results" signal — verify it's not a transient hiccup (rate-limit/cache
glitch) before permanently cutting off something that may still have real content further in.

## Deployment workflow (do this after every change that ships)

After deploying a change (restarting the service, or just finishing a commit that's meant to
go live), update all four docs to describe what changed, **in the same session**:
- `README.md` / `README.pt-BR.md` — the detailed "how it works / why" narrative docs.
- `ROADMAP.md` / `ROADMAP.pt-BR.md` — the changelog-style bullet list.

Keep the English and Portuguese versions in sync (same content, translated, not abbreviated
in one language). Then `git commit` + `git push origin main`.

Exception: purely temporary diagnostic code (debug overlays, see above) doesn't need doc
updates — only the real fix that replaces it does. If an intermediate commit's docs turn out
to describe an incorrect conclusion (e.g. a fix later found to be based on a wrong
hypothesis), correct the docs in a follow-up commit rather than leaving stale reasoning in
place.

## Git conventions

- This checkout needs `git -c safe.directory=/app/scrapperx <command>` (ad-hoc flag per
  command — don't persist it to global config).
- Never `git add -A` / `git add .` — stage specific files by name.
- Never create empty commits; only commit when there's an actual change.
- Commit messages end with a `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
  trailer (or whichever model is actually running).
- Prefer new commits over `--amend`; don't force-push.

## Communication

The user communicates in Brazilian Portuguese (pt-BR) in chat — respond in pt-BR regardless
of the language code/comments are written in (code and docs stay in English).
