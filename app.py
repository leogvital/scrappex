from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
import yt_dlp, os, json, threading, uuid, tempfile, sqlite3, shutil, glob, time, secrets, psutil, signal
from pathlib import Path
from datetime import timedelta
from http.cookiejar import MozillaCookieJar

app = Flask(__name__)


def _load_or_create_secret_key():
    # Persisted to disk (not regenerated per process) so restarting the server
    # doesn't invalidate everyone's login session.
    here = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
    key_file = os.path.join(here, ".flask_secret_key")
    if os.path.exists(key_file):
        with open(key_file) as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(key_file, "w") as f:
        f.write(key)
    os.chmod(key_file, 0o600)
    return key


app.secret_key = _load_or_create_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
CORS(app, supports_credentials=True)

DOWNLOAD_DIR = str(Path.home() / "Downloads" / "X-Videos")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COOKIES_FILE = os.path.join(tempfile.gettempdir(), "x_cookies.txt")  # Netscape format
download_progress = {}
session_state = {"logged_in": False, "username": "", "method": ""}

# ── App-level login (gates the whole app — separate from the X cookie session above) ──
# Credentials come from the environment (set in .env.local, which is gitignored —
# see .env.local.example) rather than being hardcoded, since this repo is public.
APP_USER = os.environ.get("SCRAPPERX_APP_USER", "admin")
APP_PASS = os.environ.get("SCRAPPERX_APP_PASS")
if not APP_PASS:
    print("⚠️  SCRAPPERX_APP_PASS não definida — login do app ficará bloqueado para todos. "
          "Copie .env.local.example para .env.local e defina uma senha.")
_APP_LOGIN_WHITELIST = {"/api/auth/app-login", "/api/auth/app-status", "/api/health"}

# ── Rate limiting for /api/auth/app-login ─────────────────────────────────
# In-memory only — fine for --workers 1 (no cross-process state to share) and
# a reset on server restart is harmless here (worst case: the counter starts
# fresh, not a security hole). No reverse proxy sits in front of gunicorn
# (confirmed via access logs showing real LAN IPs directly), so
# request.remote_addr is the real client IP, not a spoofable header.
_LOGIN_ATTEMPTS = {}       # ip -> [timestamp, ...] of recent failed attempts
_LOGIN_RATE_LIMIT = 5      # max failed attempts...
_LOGIN_RATE_WINDOW = 300   # ...within this many seconds (5 min)


def _login_rate_limited(ip):
    """
    Returns seconds until the next attempt is allowed, or 0 if not currently
    limited. Prunes attempts older than the window as a side effect, so both
    the per-IP list and the dict itself (once a key's list empties out) stay
    naturally bounded to "IPs with a failure in the current window" — no
    separate cleanup job needed.
    """
    now = time.time()
    attempts = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if now - t < _LOGIN_RATE_WINDOW]
    if attempts:
        _LOGIN_ATTEMPTS[ip] = attempts
    else:
        _LOGIN_ATTEMPTS.pop(ip, None)
    if len(attempts) >= _LOGIN_RATE_LIMIT:
        return max(0, int(_LOGIN_RATE_WINDOW - (now - attempts[0])) + 1)
    return 0


@app.before_request
def _require_app_login():
    if request.path.startswith("/api/") and request.path not in _APP_LOGIN_WHITELIST:
        if not session.get("app_logged_in"):
            return jsonify({"error": "Não autenticado."}), 401


@app.route("/api/auth/app-login", methods=["POST"])
def app_login():
    ip = request.remote_addr or "unknown"
    retry_after = _login_rate_limited(ip)
    if retry_after:
        return jsonify({"success": False,
                         "error": f"Muitas tentativas — aguarde {retry_after}s antes de tentar de novo."}), 429

    d = request.json or {}
    if d.get("username") == APP_USER and d.get("password") == APP_PASS:
        _LOGIN_ATTEMPTS.pop(ip, None)   # a correct login clears this IP's failure history
        session.permanent = True   # cookie survives closing the browser (30-day lifetime)
        session["app_logged_in"] = True
        return jsonify({"success": True})
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())
    return jsonify({"success": False, "error": "Usuário ou senha inválidos."})


@app.route("/api/auth/app-logout", methods=["POST"])
def app_logout():
    session.pop("app_logged_in", None)
    return jsonify({"success": True})


@app.route("/api/auth/app-status")
def app_status():
    return jsonify({"logged_in": bool(session.get("app_logged_in"))})


class _QuietLogger:
    """Suppress all yt-dlp console output."""
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


# ── Cookie Import Helpers ────────────────────────────────────────────────────

def find_chrome_cookie_db():
    """Find Chrome/Chromium/Edge cookie database on Linux, Mac, Windows"""
    home = Path.home()
    candidates = [
        # Linux Chrome
        home / ".config/google-chrome/Default/Cookies",
        home / ".config/google-chrome-beta/Default/Cookies",
        home / ".config/chromium/Default/Cookies",
        # Linux Edge
        home / ".config/microsoft-edge/Default/Cookies",
        # Mac Chrome
        home / "Library/Application Support/Google/Chrome/Default/Cookies",
        home / "Library/Application Support/Chromium/Default/Cookies",
        # Mac Edge
        home / "Library/Application Support/Microsoft Edge/Default/Cookies",
        # Windows Chrome
        home / "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
        home / "AppData/Local/Google/Chrome/User Data/Default/Cookies",
        # Windows Edge
        home / "AppData/Local/Microsoft/Edge/User Data/Default/Network/Cookies",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def find_firefox_cookie_db():
    """Find Firefox cookie database"""
    home = Path.home()
    profiles = [
        home / ".mozilla/firefox",
        home / "snap/firefox/common/.mozilla/firefox",   # Ubuntu snap
        home / "Library/Application Support/Firefox/Profiles",
        home / "AppData/Roaming/Mozilla/Firefox/Profiles",
    ]
    for base in profiles:
        if base.exists():
            for db in base.rglob("cookies.sqlite"):
                return str(db)
    return None


def extract_x_cookies_from_chrome(db_path):
    """Extract x.com/twitter.com cookies from Chrome SQLite DB"""
    tmp = db_path + ".tmp_copy"
    shutil.copy2(db_path, tmp)  # Copy because Chrome may lock the file
    
    try:
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        
        # Try new schema (Cookies table with host_key)
        try:
            cur.execute("""
                SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly, encrypted_value
                FROM cookies
                WHERE host_key LIKE '%.x.com' OR host_key LIKE '%.twitter.com'
                   OR host_key = 'x.com' OR host_key = 'twitter.com'
            """)
            rows = cur.fetchall()
        except Exception:
            rows = []
        
        conn.close()
        
        if not rows:
            return False, "Nenhum cookie do X encontrado no Chrome. Certifique-se de estar logado no X no Chrome."
        
        # Try to decrypt (Linux: no encryption by default; Mac/Win: needs keychain)
        cookies_text = ["# Netscape HTTP Cookie File\n# https://curl.se/docs/http-cookies.html\n"]
        count = 0
        for host, name, value, path, expires_utc, secure, httponly, enc_value in rows:
            # On Linux, value is usually plain text
            if not value and enc_value:
                # Try simple decryption for Linux (v10 prefix = AES-128-CBC with fixed key)
                try:
                    import base64
                    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                    from cryptography.hazmat.backends import default_backend
                    key = b'peanuts' + b'\x00' * 9  # Linux Chrome default key (simplified)
                    # Actual Linux key: PBKDF2 with 'peanuts' and salt 'saltysalt'
                    enc = enc_value
                    if enc[:3] == b'v10':
                        enc = enc[3:]
                        # pad key
                        import hashlib
                        dk = hashlib.pbkdf2_hmac('sha1', b'peanuts', b'saltysalt', 1, dklen=16)
                        iv = b' ' * 16
                        cipher = Cipher(algorithms.AES(dk), modes.CBC(iv), backend=default_backend())
                        dec = cipher.decryptor()
                        raw = dec.update(enc) + dec.finalize()
                        value = raw[:-raw[-1]].decode('utf-8', errors='ignore')
                except Exception:
                    value = ""  # Skip if can't decrypt

            if not value:
                continue
            
            # Chrome stores expires as microseconds since Jan 1, 1601
            # Convert to Unix timestamp (seconds since Jan 1, 1970)
            if expires_utc > 0:
                unix_exp = (expires_utc - 11644473600000000) // 1000000
            else:
                unix_exp = 0
            
            domain = host if host.startswith(".") else "." + host
            secure_str = "TRUE" if secure else "FALSE"
            
            cookies_text.append(
                f"{domain}\tTRUE\t{path}\t{secure_str}\t{unix_exp}\t{name}\t{value}\n"
            )
            count += 1
        
        if count == 0:
            return False, "Cookies encontrados mas não foi possível ler os valores (podem estar criptografados). Tente exportar manualmente."
        
        with open(COOKIES_FILE, "w") as f:
            f.writelines(cookies_text)
        
        return True, f"{count} cookies importados do Chrome."
    
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def extract_x_cookies_from_firefox(db_path):
    """Extract x.com cookies from Firefox SQLite DB"""
    tmp = db_path + ".tmp_copy"
    shutil.copy2(db_path, tmp)
    
    try:
        conn = sqlite3.connect(tmp)
        cur = conn.cursor()
        cur.execute("""
            SELECT host, name, value, path, expiry, isSecure, isHttpOnly
            FROM moz_cookies
            WHERE host LIKE '%.x.com' OR host LIKE '%.twitter.com'
               OR host = 'x.com' OR host = 'twitter.com'
        """)
        rows = cur.fetchall()
        conn.close()
        
        if not rows:
            return False, "Nenhum cookie do X encontrado no Firefox. Certifique-se de estar logado no X no Firefox."
        
        cookies_text = ["# Netscape HTTP Cookie File\n"]
        count = 0
        for host, name, value, path, expiry, secure, httponly in rows:
            domain = host if host.startswith(".") else "." + host
            secure_str = "TRUE" if secure else "FALSE"
            cookies_text.append(f"{domain}\tTRUE\t{path}\t{secure_str}\t{expiry}\t{name}\t{value}\n")
            count += 1
        
        with open(COOKIES_FILE, "w") as f:
            f.writelines(cookies_text)
        
        return True, f"{count} cookies importados do Firefox."
    
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def extract_x_cookies_via_ytdlp(browser):
    """Use yt-dlp to extract x.com cookies from a browser (handles encryption/keyring)"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "logger": _QuietLogger(),
        "cookiesfrombrowser": (browser,),
        "cookiefile": COOKIES_FILE,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.extract_info("https://x.com/", download=False)
            except Exception:
                pass
    except Exception as e:
        return False, str(e)

    if os.path.exists(COOKIES_FILE):
        cookies = load_cookies_dict()
        if cookies.get("auth_token"):
            return True, f"Cookies extraídos via yt-dlp do {browser.capitalize()}."
        return False, "Cookies exportados mas sem token de autenticação. Verifique se está logado no X nesse navegador."
    return False, "Nenhum cookie foi salvo pelo yt-dlp."


def import_cookies_from_text(cookies_text):
    """Import cookies from pasted Netscape-format or JSON text"""
    text = cookies_text.strip()
    
    # Try JSON array (from browser extension like EditThisCookie / Cookie-Editor)
    if text.startswith("["):
        try:
            cookies = json.loads(text)
            lines = ["# Netscape HTTP Cookie File\n"]
            count = 0
            for c in cookies:
                domain = c.get("domain", ".x.com")
                if not domain.startswith("."):
                    domain = "." + domain
                secure = "TRUE" if c.get("secure", False) else "FALSE"
                expires = int(c.get("expirationDate", c.get("expires", 0)) or 0)
                path = c.get("path", "/")
                name = c.get("name", "")
                value = c.get("value", "")
                if name and value:
                    lines.append(f"{domain}\tTRUE\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                    count += 1
            if count == 0:
                return False, "Nenhum cookie válido encontrado no JSON."
            with open(COOKIES_FILE, "w") as f:
                f.writelines(lines)
            return True, f"{count} cookies importados via JSON."
        except Exception as e:
            return False, f"Erro ao parsear JSON: {e}"
    
    # Try Netscape format (already formatted)
    if "Netscape HTTP Cookie File" in text or "\t" in text:
        # Validate it has x.com cookies
        if "x.com" not in text and "twitter.com" not in text:
            return False, "Arquivo de cookies não contém cookies do X/Twitter."
        with open(COOKIES_FILE, "w") as f:
            if not text.startswith("# Netscape"):
                f.write("# Netscape HTTP Cookie File\n")
            f.write(text)
        # Count valid lines
        count = sum(1 for l in text.splitlines() if l and not l.startswith("#") and "\t" in l)
        return True, f"{count} cookies importados (formato Netscape)."
    
    return False, "Formato não reconhecido. Cole cookies em formato JSON (Cookie-Editor) ou Netscape."


def validate_cookies():
    """
    Test if cookies still work. `account/verify_credentials.json` — X's classic
    validation endpoint — now returns 404 ("that page does not exist") even for
    perfectly valid sessions (confirmed: the same cookies succeed at the real
    media-upload INIT call the tweet-publishing feature depends on). So probe
    with that INIT call instead — total_bytes=1 keeps the reserved upload trivial,
    and it reflects what actually matters (can this session publish a tweet).
    """
    if not os.path.exists(COOKIES_FILE):
        return False, "Arquivo de cookies não encontrado."

    cookies = load_cookies_dict()
    auth_token = cookies.get("auth_token", "")

    if not auth_token:
        return False, "Cookie auth_token não encontrado. Faça login novamente no X e reimporte os cookies."

    session = _build_x_session(cookies)
    try:
        resp = session.post(_UPLOAD_URL, data={
            "command": "INIT", "total_bytes": 1,
            "media_type": "video/mp4", "media_category": "tweet_video",
        }, timeout=10)
        if resp.status_code == 202:
            return True, "Cookies válidos — login confirmado!"
        if resp.status_code == 401:
            return False, "Sessão expirada. Faça login novamente no X e reimporte os cookies."
        if resp.status_code == 403:
            return False, "Acesso negado (403). Cookies podem estar corrompidos ou expirados."
        return False, f"Cookies inválidos (HTTP {resp.status_code})."
    except Exception as e:
        return False, f"Erro de validação: {e}"


# ── Search ───────────────────────────────────────────────────────────────────

def build_ydl_opts(extra=None, url=None):
    # _QuietLogger suppresses ERROR:/WARNING: lines that quiet=True doesn't catch
    opts = {"quiet": True, "no_warnings": True, "ignoreerrors": True,
            "logger": _QuietLogger()}
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    if url and "pornhub.com" in url:
        # yt-dlp's default request stack gets a 403 from Pornhub (TLS-fingerprint-based
        # block) — impersonating a real Chrome TLS handshake via curl_cffi bypasses it.
        # The Python API needs an ImpersonateTarget object, not the CLI's plain string.
        from yt_dlp.networking.impersonate import ImpersonateTarget
        opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    if extra:
        opts.update(extra)
    return opts


def load_cookies_dict():
    """Load cookies from Netscape file into a dict for requests"""
    cookies = {}
    if not os.path.exists(COOKIES_FILE):
        return cookies
    with open(COOKIES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
    return cookies


BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"


def _build_x_session(cookies):
    import requests as req
    s = req.Session()
    s.cookies.update(cookies)
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {BEARER}",
        "X-Csrf-Token": cookies.get("ct0", ""),
        "X-Twitter-Auth-Type": "OAuth2Session",
        "X-Twitter-Active-User": "yes",
        "Referer": "https://x.com/",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    })
    return s


def _parse_tweet_object(tweet_raw, users_map=None):
    """Parse a tweet dict (v1.1 embedded user or v2 adaptive users_map)."""
    tweet_id = tweet_raw.get("id_str", "")
    # v1.1: user embedded directly; v2 adaptive: lookup by user_id_str
    if "user" in tweet_raw:
        user = tweet_raw["user"]
    elif users_map:
        uid = tweet_raw.get("user_id_str", "")
        user = users_map.get(uid, {})
    else:
        user = {}
    screen_name = user.get("screen_name", "unknown")
    text = tweet_raw.get("full_text", tweet_raw.get("text", ""))

    extended = tweet_raw.get("extended_entities", {}).get("media", [])
    media_list = tweet_raw.get("entities", {}).get("media", [])
    all_media = extended or media_list
    has_video = any(m.get("type") in ("video", "animated_gif") for m in all_media)
    if not has_video:
        return None

    thumbnail, duration = "", 0
    for m in all_media:
        if m.get("type") in ("video", "animated_gif"):
            thumbnail = m.get("media_url_https", "")
            duration = m.get("video_info", {}).get("duration_millis", 0) / 1000
            break

    return {
        "id": tweet_id,
        "url": f"https://x.com/{screen_name}/status/{tweet_id}",
        "title": text[:120] + ("..." if len(text) > 120 else ""),
        "uploader": user.get("name", screen_name),
        "uploader_id": screen_name,
        "duration": int(duration),
        "thumbnail": thumbnail,
        "view_count": tweet_raw.get("view_count", 0),
        "like_count": tweet_raw.get("favorite_count", 0),
    }


def twitter_api_search(query, count=20):
    """Search tweets with videos — tries v1.1 then v2 adaptive endpoints."""
    cookies = load_cookies_dict()
    if not cookies.get("auth_token"):
        return [], "Cookie auth_token não encontrado. Faça login novamente."

    session = _build_x_session(cookies)
    base_params = {
        "q": query,
        "count": count,
        "tweet_mode": "extended",
        "result_type": "recent",
        "include_entities": "true",
        "include_ext_media_availability": "true",
    }

    endpoints = [
        ("https://x.com/i/api/1.1/search/tweets.json", {}),
        ("https://x.com/i/api/2/search/adaptive.json",
         {"cards_platform": "Web-12", "include_cards": "1"}),
    ]

    data = None
    last_err = None
    for url, extra_params in endpoints:
        params = {**base_params, **extra_params}
        try:
            resp = session.get(url, params=params, timeout=15)
            body = resp.text.strip() if resp.text else ""
            if resp.status_code == 403:
                last_err = "Acesso negado (403) — cookies expirados ou inválidos."
                continue
            if resp.status_code == 401:
                last_err = "Não autorizado (401) — reimporte os cookies."
                continue
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code} de {url}"
                print(f"Search {url} → {resp.status_code}: {body[:200]}")
                continue
            if not body:
                last_err = f"Resposta vazia de {url}"
                print(f"Search {url} → resposta vazia (status 200)")
                continue
            data = resp.json()
            print(f"Search OK via {url} (keys: {list(data.keys())[:5]})")
            break
        except Exception as e:
            last_err = str(e)
            print(f"Search {url} → erro: {e}")

    if data is None:
        return [], last_err or "Todos os endpoints de busca falharam."

    results = []
    try:
        # v1.1 format: {"statuses": [...]}
        if "statuses" in data:
            for tweet_raw in data["statuses"]:
                item = _parse_tweet_object(tweet_raw)
                if item:
                    results.append(item)
        # v2 adaptive format: {"globalObjects": {"tweets":{}, "users":{}}}
        elif "globalObjects" in data:
            tweets_map = data["globalObjects"].get("tweets", {})
            users_map  = data["globalObjects"].get("users", {})
            for tweet_raw in tweets_map.values():
                item = _parse_tweet_object(tweet_raw, users_map)
                if item:
                    results.append(item)
        results.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 0, reverse=True)
    except Exception as e:
        print(f"Parse error: {e}")

    return results, None


def twitter_api_user_media(username, count=20):
    """Get media tweets from a user via the adaptive search API."""
    uname = username.lstrip("@")
    return twitter_api_search(f"from:{uname} filter:videos", count)


# ── Selenium persistent-session scraper ──────────────────────────────────────
#
# One Chrome instance stays open between requests so pagination genuinely
# continues from where the user left off — no re-scraping, no duplicates.

import atexit

_SS = {           # active scrape session (one at a time — personal tool)
    "id": None, "driver": None, "seen_ids": set(),   # dedup by tweet ID
    "need_video_check": False, "duration_filter": "any", "finished": False,
    "scroll_count": 0, "no_new_streak": 0, "last_used": 0,
    "url": None, "type": None,   # kept so a crashed session can be reopened and
                                  # resumed (see _is_transient_browser_error)
}
_SS_TIMEOUT  = 600   # seconds before an idle session is considered stale
_SS_MAX_SCROLL = 60  # absolute scroll limit per session

# ── yt-dlp site session (XHamster / XVideos / Pornhub) ───────────────────────
# page: next page to fetch. XHamster/Pornhub 1-based, XVideos 0-based (both stored as-is).
# One independent slot per site (not a single shared dict) — "buscar em tudo"
# searches all three sequentially in the same request cycle, and a shared slot
# would have each site's search silently evict the previous one's session,
# making "carregar mais" permanently broken for whichever two sites didn't run
# last. Each slot is looked up by search_id, so cross-site lookups stay O(3).
def _new_site_ss():
    return {
        "id": None, "site": None, "query": None,
        "page": 1, "sort": "relevance", "duration": "any", "category": "straight",
        "seen_ids": set(),   # dedup across pages — some sites (e.g. Pornhub category
                             # browsing) repeat a handful of promoted items per page
        "finished": False, "last_used": 0,
    }


_SITE_SS = {site: _new_site_ss() for site in ("xhamster", "xvideos", "pornhub")}
_SITE_SS_TIMEOUT = 600

# ── xFree session (Selenium — both home and search load/paginate via client-side
# infinite scroll hitting a Cloudflare-gated JSON API that plain HTTP requests can't
# reach, so results are scrolled into the DOM by a real browser instead). Category
# (straight/gay/trans/all) is set by loading its dedicated route before searching —
# it's Vuex state, not a query param, so it must be set via real navigation. ──
_XF_SS = {
    "id": None, "driver": None, "seen_ids": set(),
    "duration": "any", "finished": False,
    "scroll_count": 0, "no_new_streak": 0, "last_used": 0,
    "category": "straight", "query": "",   # kept so a crashed session can be
                                            # reopened and resumed
}
_XF_SS_TIMEOUT    = 600
_XF_SS_MAX_SCROLL = 40

_XF_CATEGORY_PATH = {"straight": "/", "gay": "/gay", "trans": "/trans", "all": "/all"}


class _NoResultsError(Exception):
    """A Selenium search that legitimately found nothing (or needs a fresh X
    login) — as opposed to the browser/chromedriver crashing, which is the
    retryable case _is_transient_browser_error()/the search routes handle."""


# Substrings seen in real crashes so far: chromedriver dying mid-session leaves
# Selenium unable to reach it ("Connection refused" on its local control port —
# see README's "Robust cleanup of stuck processes" section) or the tab itself
# crashing under memory pressure. Matched case-insensitively against str(exc).
_TRANSIENT_BROWSER_ERRORS = (
    "connection refused", "tab crashed", "errno 5", "chrome not reachable",
    "session not created", "invalid session id", "disconnected",
    "no such window", "target window already closed", "broken pipe",
    "connection aborted", "remote end closed connection", "connection reset",
)

_BROWSER_RETRY_ATTEMPTS = 4  # 1 initial try + 3 retries with a fresh Chrome session


# ── Scraper health: alert when a scraper silently stops returning results ────
# A raised exception (network error, HTML parse error, Selenium crash) already
# surfaces immediately as an error message — that's not the gap. The dangerous
# case is *silent*: the request "succeeds" (200 OK, no exception) but the
# parser extracts nothing, because the target site changed its HTML/JSON shape
# out from under a brittle selector/key path. A single zero-result search is
# normal (a rare query, a momentarily empty page); several IN A ROW on an
# endpoint that should reliably have content (a category/home feed, not an
# arbitrary keyword search) is the actual signal something broke. Restricted
# to home/category-browse calls specifically to avoid false positives from
# genuinely narrow keyword searches returning zero legitimately.
_SCRAPER_HEALTH = {}
_SCRAPER_ZERO_ALERT_THRESHOLD = 5   # consecutive zero-result home/category calls before the first alert
_SCRAPER_ZERO_ALERT_REPEAT    = 10  # re-alert every N further consecutive failures, so a long-broken
                                     # scraper isn't spammed every call but also isn't forgotten


def _record_scraper_outcome(platform, got_results, context=""):
    h = _SCRAPER_HEALTH.setdefault(platform, {"zero_streak": 0, "last_alert_streak": 0})
    if got_results:
        h["zero_streak"] = 0
        h["last_alert_streak"] = 0
        return
    h["zero_streak"] += 1
    streak = h["zero_streak"]
    first_alert  = streak == _SCRAPER_ZERO_ALERT_THRESHOLD
    repeat_alert = streak > _SCRAPER_ZERO_ALERT_THRESHOLD and (streak - h["last_alert_streak"]) >= _SCRAPER_ZERO_ALERT_REPEAT
    if first_alert or repeat_alert:
        h["last_alert_streak"] = streak
        print(f"[PARSER-ALERT] platform={platform} zero_result_streak={streak} context={context!r} — "
              f"{_SCRAPER_ZERO_ALERT_THRESHOLD}+ buscas seguidas sem nenhum resultado num endpoint que "
              f"deveria sempre ter conteúdo. Provável mudança no HTML/JSON do site (parser quebrado) "
              f"ou o site fora do ar — vale checar manualmente.")


def _is_transient_browser_error(exc):
    """True if `exc` looks like a dead/crashed Chrome or chromedriver — worth
    silently retrying with a fresh session instead of surfacing a raw Python
    exception to the user."""
    return any(marker in str(exc).lower() for marker in _TRANSIENT_BROWSER_ERRORS)


_SITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

# ── XHamster sort/duration param maps ────────────────────────────────────────
# sort values accepted by xhamster.com: relevance | newest | views | best | longest
_XH_SORT = {
    "relevance": "",
    "newest":    "newest",
    "views":     "views",
    "best":      "best",
    "longest":   "longest",
}

# ── XVideos sort param map ────────────────────────────────────────────────────
# sort values: relevance | uploaddate | rating | length
_XV_SORT = {
    "relevance": "",
    "newest":    "uploaddate",
    "views":     "rating",
    "best":      "rating",
    "longest":   "length",
}

# ── Orientation → URL prefix (XHamster and XVideos both use the same scheme:
# a plain path prefix in front of the normal search/browse URL). ──────────────
_XH_CATEGORY_PATH = {"straight": "", "gay": "/gay", "trans": "/shemale"}
_XV_CATEGORY_PATH = {"straight": "", "gay": "/gay", "trans": "/shemale"}


def _scrape_xhamster(query, page=1, sort="relevance", category="straight"):
    """
    Scrape one page of XHamster results (~46-51 videos per page, 1-based).
    query=''/None → home/channel feed for the category (e.g. /gay, /shemale).
    category: straight | gay | trans. Returns (results_list, error_or_None).
    """
    import re, json, urllib.parse, requests
    from html import unescape

    prefix = _XH_CATEGORY_PATH.get(category, "")

    if query:
        params = {"page": page}
        sort_val = _XH_SORT.get(sort, "")
        if sort_val:
            params["sort"] = sort_val
        qs = urllib.parse.urlencode(params)
        url = f"https://xhamster.com{prefix}/search/{urllib.parse.quote(query)}?{qs}"
    else:
        url = f"https://xhamster.com{prefix}/?page={page}" if prefix else f"https://xhamster.com/?page={page}"

    try:
        r = requests.get(url, headers=_SITE_HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as ex:
        return [], f"Erro ao acessar XHamster: {ex}"

    m = re.search(r"window\.initials\s*=\s*(\{.+?\});\s*</script>", r.text, re.DOTALL)
    if not m:
        return [], "Não foi possível extrair dados do XHamster."
    try:
        data = json.loads(m.group(1))
    except Exception:
        return [], "Erro ao interpretar JSON do XHamster."

    # Search results live under searchResult; home/channel feeds live under
    # layoutPage.videoListProps — same item shape either way.
    items = (
        data.get("searchResult", {}).get("videoThumbProps")
        or data.get("layoutPage", {}).get("videoListProps", {}).get("videoThumbProps")
        or []
    )
    results = []
    for e in items:
        vid_url = e.get("pageURL", "")
        if not vid_url:
            continue
        results.append({
            "id":          str(e.get("id", "")),
            "url":         vid_url,
            "title":       unescape(e.get("title") or "Vídeo"),
            "uploader":    "",
            "uploader_id": "",
            "duration":    int(e.get("duration") or 0),
            "thumbnail":   e.get("imageURL") or e.get("thumbURL") or "",
            "view_count":  int(e.get("views") or 0),
            "like_count":  0,
        })

    # XHamster's default "relevance" ranking pins a handful of heavily-promoted
    # premium videos (huge view counts, e.g. VIP4K/CoupleForFun2023-style channels)
    # near the top of almost every search, regardless of the query — making
    # different keywords look like they return "the same" results. Re-rank so
    # videos whose title actually matches the query come first (stable sort
    # keeps XHamster's original relative order as a tiebreaker).
    if sort == "relevance" and query.strip():
        q_words = [w for w in re.findall(r"\w+", query.lower()) if len(w) >= 2]
        if q_words:
            def _relevance(r):
                title = r["title"].lower()
                return sum(1 for w in q_words if w in title)
            results.sort(key=_relevance, reverse=True)

    return results, None


def _scrape_xvideos(query, page=0, sort="relevance", category="straight"):
    """
    Scrape one page of XVideos results (~27-100 videos per page, 0-based).
    query=''/None → home/channel feed for the category (e.g. /gay, /shemale) —
    that landing page returns the same trending set regardless of `page`
    (confirmed: no query-param pagination on it), so home is always a single page.
    category: straight | gay | trans. Returns (results_list, error_or_None).
    """
    import re, requests, urllib.parse
    from html import unescape

    prefix = _XV_CATEGORY_PATH.get(category, "")

    if query:
        params = {"k": query, "p": page}
        sort_val = _XV_SORT.get(sort, "")
        if sort_val:
            params["sort"] = sort_val
        url = f"https://www.xvideos.com{prefix}/?" + urllib.parse.urlencode(params)
    else:
        url = f"https://www.xvideos.com{prefix}/"

    try:
        r = requests.get(url, headers=_SITE_HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as ex:
        return [], f"Erro ao acessar XVideos: {ex}"

    text = r.text
    block_re = re.compile(
        r'data-id="(\d+)"\s+data-eid="([a-z0-9]+)".*?'
        r'<a href="(/video\.[a-z0-9]+/[^"]*)"[^>]*>'
        r'<img[^>]+data-src="([^"]+)"',
        re.DOTALL,
    )
    title_re    = re.compile(r'class="title"[^>]*>.*?title="([^"]+)"', re.DOTALL)
    dur_re      = re.compile(r'<span class="duration">([^<]+)</span>')
    uploader_re = re.compile(r'class="name">([^<]+)</span>')

    results = []
    for bm in block_re.finditer(text):
        vid_id, eid, path, thumb = bm.groups()
        block_start = bm.start()
        next_m      = block_re.search(text, bm.end())
        block_end   = next_m.start() if next_m else len(text)
        block       = text[block_start:block_end]

        title_m    = title_re.search(block)
        dur_m      = dur_re.search(block)
        uploader_m = uploader_re.search(block)

        title    = unescape(title_m.group(1))    if title_m    else path.split("/")[-1].replace("_", " ")
        duration = dur_m.group(1).strip()        if dur_m      else ""
        uploader = unescape(uploader_m.group(1)) if uploader_m else ""

        dur_sec = 0
        if duration:
            if ":" in duration:
                parts = duration.split(":")
                try:
                    dur_sec = int(parts[0]) * 60 + int(parts[1])
                except (ValueError, IndexError):
                    pass
            else:
                nums = re.findall(r'\d+', duration)
                if nums:
                    val = int(nums[0])
                    low = duration.lower()
                    if "hora" in low or "hour" in low:
                        dur_sec = val * 3600
                    elif "seg" in low or "sec" in low:
                        dur_sec = val
                    else:
                        dur_sec = val * 60

        results.append({
            "id":          eid,
            "url":         "https://www.xvideos.com" + path,
            "title":       title,
            "uploader":    uploader,
            "uploader_id": "",
            "duration":    dur_sec,
            "thumbnail":   thumb,
            "view_count":  0,
            "like_count":  0,
        })
    return results, (None if results else "Nenhum resultado encontrado.")


# ── Pornhub orientation → dedicated vertical (Gay/Sáfica are separate site
# skins with their own search endpoint; Trans is a category page with no
# keyword-search endpoint, so it's browsed and filtered client-side). ──
_PH_CATEGORY = {
    "straight": {"search": "/video/search",       "browse": "/"},
    "gay":      {"search": "/gay/video/search",    "browse": "/gayporn"},
    "sapphic":  {"search": "/lesbian/video/search", "browse": "/lesbian"},
    "trans":    {"search": None,                    "browse": "/transgender"},
}


def _parse_pornhub_views(s):
    """Convert '80.9K' / '1.1M' / '46,966' → int."""
    s = (s or "").strip().upper()
    try:
        if s.endswith("M"):
            return int(float(s[:-1].replace(",", "")) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1].replace(",", "")) * 1_000)
        return int(s.replace(",", ""))
    except Exception:
        return 0


def _scrape_pornhub(query, page=1, category="straight"):
    """
    Scrape one page of pt.pornhub.com results (~35-50 videos per page, 1-based).
    category: straight | gay | sapphic | trans.
    Trans has no dedicated keyword-search endpoint on the site (only straight/gay/
    sapphic do) — for trans, `query` is ignored and this always browses the
    /transgender vertical (trending feed) instead of erroring.
    Returns (results_list, error_or_None).
    """
    import re, requests, urllib.parse
    from html import unescape

    cat = _PH_CATEGORY.get(category, _PH_CATEGORY["straight"])

    if query and cat["search"]:
        params = {"search": query, "page": page}
        url = f"https://pt.pornhub.com{cat['search']}?{urllib.parse.urlencode(params)}"
    else:
        url = f"https://pt.pornhub.com{cat['browse']}?page={page}"

    try:
        r = requests.get(url, headers=_SITE_HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as ex:
        return [], f"Erro ao acessar Pornhub: {ex}"

    html = r.text
    positions = [m.start() for m in re.finditer(r'class="pcVideoListItem', html)]
    results = []
    for i, start in enumerate(positions):
        end   = positions[i + 1] if i + 1 < len(positions) else len(html)
        block = html[start:end]

        id_m  = re.search(r'data-video-id="(\d+)"', block)
        key_m = re.search(r'viewkey=([a-z0-9]+)', block)
        if not id_m or not key_m:
            continue
        vkey = key_m.group(1)

        title_m = re.search(r'viewkey=' + re.escape(vkey) + r'"\s+title="([^"]+)"', block)
        # Card markup differs between search-result and trending/home cards —
        # try each known thumbnail attribute in turn, falling back to the <img src>.
        thumb_m = (
            re.search(r'data-image="([^"]+)"', block)
            or re.search(r'data-mediumthumb="([^"]+)"', block)
            or re.search(r'<img[^>]+src="([^"]+)"', block)
        )
        dur_m   = re.search(r'<var class="duration">([^<]+)</var>', block)
        views_m = re.search(r'class="views"[^>]*>\s*<var>([^<]+)</var>', block)
        user_m  = re.search(r'class="usernameLink">([^<]+)</a>', block)

        title = unescape(title_m.group(1)) if title_m else f"Pornhub #{id_m.group(1)}"

        dur_sec = 0
        if dur_m:
            try:
                parts = [int(p) for p in dur_m.group(1).strip().split(":")]
                if len(parts) == 3:
                    dur_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 2:
                    dur_sec = parts[0] * 60 + parts[1]
            except ValueError:
                pass

        results.append({
            "id":          id_m.group(1),
            "url":         f"https://pt.pornhub.com/view_video.php?viewkey={vkey}",
            "title":       title,
            "uploader":    unescape(user_m.group(1)) if user_m else "",
            "uploader_id": "",
            "duration":    dur_sec,
            "thumbnail":   thumb_m.group(1) if thumb_m else "",
            "view_count":  _parse_pornhub_views(views_m.group(1)) if views_m else 0,
            "like_count":  0,
        })

    return results, (None if results else "Nenhum resultado encontrado.")


def _parse_xfree_views(s):
    """Convert '1.1M' / '66.8K' / '830' → int."""
    s = (s or "").strip().upper().replace(" ", "").replace(",", "")
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(s)
    except Exception:
        return 0


def _parse_xfree_blocks(html):
    """
    Parse all `wall__item` video cards out of a rendered xfree.com page (SSR or DOM).
    Video links carry a category suffix — `/video?id=`, `/video-gay?id=` or
    `/video-trans?id=` — which is preserved so playback URLs stay correct.
    """
    import re
    from html import unescape

    positions = [m.start() for m in re.finditer(r'class="wall__item"', html)]
    results = []
    for i, start in enumerate(positions):
        end   = positions[i + 1] if i + 1 < len(positions) else len(html)
        block = html[start:end]

        id_m    = re.search(r'/video(-gay|-trans)?\?id=(\d+)', block)
        if not id_m:
            continue
        suffix = id_m.group(1) or ""
        vid_id = id_m.group(2)

        thumb_m = re.search(r'<img[^>]+data-type="poster"[^>]+src="([^"]+)"', block)
        views_m = re.search(r'alt="Played"[^>]*>\s*<span[^>]*>([^<]+)</span>', block, re.DOTALL)
        slug_m  = re.search(r'href="/video(?:-gay|-trans)?\?id=\d+(?:&amp;|&)title=([^"&]+)', block)
        desc_m  = re.search(r'class="description line-clamp"[^>]*>([\s\S]*?)</div>', block)
        user_m  = re.search(r'class="user-caption__main"[\s\S]*?<span[^>]*>([\s\S]*?)</span>', block)

        # Title: prefer description text, fall back to URL slug
        title = ""
        if desc_m:
            raw = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()
            title = re.split(r'\s*#', raw)[0].strip()
        if not title and slug_m:
            title = unescape(slug_m.group(1)).replace("-", " ").title()
        title = unescape(title or f"xfree #{vid_id}")[:200]

        uploader = ""
        if user_m:
            uploader = re.sub(r'<[^>]+>', '', user_m.group(1)).strip()

        results.append({
            "id":          vid_id,
            "url":         f"https://www.xfree.com/video{suffix}?id={vid_id}",
            "title":       title,
            "uploader":    uploader,
            "uploader_id": "",
            "duration":    0,
            "thumbnail":   thumb_m.group(1) if thumb_m else "",
            "view_count":  _parse_xfree_views(views_m.group(1)) if views_m else 0,
            "like_count":  0,
        })

    return results


def search_site_page(site, query, page, sort="relevance", duration="any", category="straight"):
    """
    Fetch exactly one page of results for `site`, applying client-side duration filter.
    page is 1-based for XHamster/Pornhub, 0-based for XVideos.
    (xFree is handled separately via the Selenium-based _XF_SS session — its home and
    search feeds only paginate client-side, so a plain HTTP GET per page doesn't work.)
    Returns (results_list, raw_count, error_or_None).
    raw_count = number of items before duration filter (used to detect end-of-results).
    """
    if site == "xhamster":
        results, err = _scrape_xhamster(query, page=page, sort=sort, category=category)
    elif site == "xvideos":
        results, err = _scrape_xvideos(query, page=page, sort=sort, category=category)
    elif site == "pornhub":
        results, err = _scrape_pornhub(query, page=page, category=category)
    else:
        return [], 0, f"Plataforma não suportada: {site}"

    raw_count = len(results)

    # Duration filter (client-side — both scrapers return duration in seconds)
    if results and duration and duration != "any":
        if duration == "short":     # < 10 min
            results = [r for r in results if 0 < r["duration"] <= 600]
        elif duration == "medium":  # 10 – 30 min
            results = [r for r in results if 600 < r["duration"] <= 1800]
        elif duration == "long":    # > 30 min
            results = [r for r in results if r["duration"] > 1800]

    return results, raw_count, err


def _hard_kill_driver(drv):
    """
    Close a Selenium driver, guaranteeing the underlying chromedriver + Chrome
    process tree actually dies even if the WebDriver session is already broken
    (e.g. "tab crashed", or chromedriver itself stopped responding — the errors
    users see as "Connection refused" / "tab crashed"). `driver.quit()` alone
    needs a *working* WebDriver HTTP connection to ask Chrome to close; if that
    connection is what's broken, quit() silently no-ops and the whole process
    tree (chromedriver + Chrome + its zygote/gpu/renderer children — around
    1-1.5 GB per session) leaks until the machine reboots.

    Walking the tree by parent/child PID as a fallback (tried first) doesn't
    work here: once chromedriver has already died, its children are reparented
    away immediately, so asking "what are this (now-dead) PID's children"
    finds nothing even though they're still running — confirmed by testing
    (simulated a crashed chromedriver; a tree-walk snapshotted right before the
    kill still found 0 of the 9 orphaned Chrome processes afterwards). Instead,
    match every live process whose cmdline carries this session's unique
    --user-data-dir (tagged on `drv` by `_ss_driver()`) — immune to reparenting
    since it doesn't depend on the process tree shape at all, only on a cmdline
    argument that's stable for the life of every process in that Chrome
    instance. Not process-group signals either — chromedriver shares gunicorn's
    process group, so a killpg here would take the server down with it.
    """
    if not drv:
        return
    user_data_dir = getattr(drv, "_user_data_dir", None)
    service_pid = None
    try:
        service_pid = drv.service.process.pid
    except Exception:
        pass
    try:
        drv.quit()
    except Exception:
        pass
    if service_pid:
        try:
            psutil.Process(service_pid).kill()
        except psutil.NoSuchProcess:
            pass
    if user_data_dir:
        for proc in psutil.process_iter(["cmdline"]):
            try:
                if any(user_data_dir in arg for arg in (proc.info["cmdline"] or [])):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Chrome never deletes a --user-data-dir we passed in ourselves (that
        # auto-cleanup only applies to profiles Chrome creates on its own) — so
        # every session leaks this directory on disk unless we remove it here.
        # Give the just-killed processes a moment to release their file handles
        # before rmtree runs, so it doesn't lose a race with a lingering writer.
        time.sleep(0.3)
        shutil.rmtree(user_data_dir, ignore_errors=True)


def _ss_close():
    _hard_kill_driver(_SS.get("driver"))
    _SS.update({
        "id": None, "driver": None, "seen_ids": set(),
        "need_video_check": False, "duration_filter": "any", "finished": False,
        "scroll_count": 0, "no_new_streak": 0, "last_used": 0,
    })


atexit.register(_ss_close)   # clean up on server shutdown


def _ss_driver():
    """Return a configured headless Chrome WebDriver with anti-detection."""
    import tempfile
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-features=IsolateOrigins,site-per-process")
    user_data_dir = tempfile.mkdtemp()
    opts.add_argument(f"--user-data-dir={user_data_dir}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    drv = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )
    # Tag the session with its unique --user-data-dir so _hard_kill_driver can
    # find every Chrome process it spawned (zygote/gpu/renderer/...) by cmdline
    # match later, even if chromedriver itself has already died and can no
    # longer be asked "what are your children" (they'd have been reparented
    # away by then — see _hard_kill_driver).
    drv._user_data_dir = user_data_dir

    # Use CDP to mask webdriver BEFORE any page loads (more effective than JS post-load)
    drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR','pt','en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """
    })
    return drv


def _ss_inject_cookies(driver):
    """Inject cookies from the Netscape cookie file into the running browser."""
    if not os.path.exists(COOKIES_FILE):
        return
    injected = 0
    with open(COOKIES_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            raw_domain, _, path, secure, expiry, name, value = parts[:7]
            # Normalize domain: Netscape format uses leading dot for host-match cookies
            # Selenium needs the domain WITHOUT the leading dot for same-origin cookies,
            # but WITH it for subdomains. Keep as-is; Chrome handles both.
            domain = raw_domain.lstrip(".")
            if not domain.endswith("x.com") and not domain.endswith("twitter.com"):
                continue
            try:
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": "." + domain if not domain.startswith(".") else domain,
                    "path": path,
                    "secure": secure == "TRUE",
                }
                try:
                    cookie["expiry"] = int(expiry)
                except (ValueError, TypeError):
                    pass
                driver.add_cookie(cookie)
                injected += 1
            except Exception:
                pass
    print(f"  Injected {injected} cookies")


def _x_open_session(t, url, need_vc):
    """
    Create a headless Chrome session, log into X via cookie injection, and
    navigate to `url`, waiting for tweets to render (clicking the "Seguindo"
    tab first if `t == "following"`). Extracted out of the /api/search route
    so both the initial search and the crash-retry path (see
    _is_transient_browser_error) can reuse the exact same flow.

    Raises _NoResultsError if the page genuinely has no tweets or needs login
    (not retryable) — any other exception is a candidate transient browser
    crash for the caller to retry. Returns the driver on success.
    """
    import time
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import TimeoutException

    driver = _ss_driver()
    try:
        driver.get("https://x.com/")
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(1.5)
        _ss_inject_cookies(driver)

        driver.get("https://x.com/")
        WebDriverWait(driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(2)

        driver.get(url)

        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
            )
        except TimeoutException:
            title, cur = "", ""
            try:
                title = driver.title
                cur   = driver.current_url
            except Exception:
                pass
            needs_login = "login" in cur.lower() or "login" in title.lower()
            _hard_kill_driver(driver)
            raise _NoResultsError(
                "X solicitou login — reimporte os cookies." if needs_login
                else "Nenhum resultado encontrado para esta busca."
            )

        time.sleep(3)

        if t == "following":
            try:
                clicked = False
                for tab_el in driver.find_elements(By.CSS_SELECTOR, '[role="tab"]'):
                    label = (tab_el.text or "").strip().lower()
                    if "seguindo" in label or "following" in label:
                        driver.execute_script("arguments[0].click()", tab_el)
                        clicked = True
                        break
                if clicked:
                    time.sleep(3)
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
                    )
                    time.sleep(2)
                else:
                    print('  Aba "Seguindo" não encontrada — usando "Para você".')
            except Exception as e:
                print(f'  Erro ao alternar para "Seguindo": {e}')

        return driver
    except _NoResultsError:
        raise
    except Exception:
        _hard_kill_driver(driver)
        raise


_STATUS_RE = __import__("re").compile(r"x\.com/([^/?#]+)/status/(\d+)")


def _canonical_tweet_url(art, By):
    """
    Return (tweet_id, username, canonical_url) for the MAIN tweet inside an
    article, or (None, None, None) if it cannot be determined.

    Strategy:
      Primary — iterate <a href*="/status/"> elements and pick the first one
      that contains a <time> descendant. X puts the main tweet's timestamp link
      in the article header; quoted/embedded tweets appear lower in the DOM, so
      DOM order gives us the outer tweet first. We query the <a> directly instead
      of finding <time> and walking up with XPath "..", which fails when <time>
      is not an immediate child of <a> (e.g. wrapped in a <span>).
      Fallback — first /status/ link that isn't analytics/photo/video.
    """
    # --- primary: first <a> that wraps a <time> (= main tweet timestamp) ---
    for lnk in art.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]'):
        try:
            if not lnk.find_elements(By.CSS_SELECTOR, 'time'):
                continue
        except Exception:
            continue
        href = lnk.get_attribute("href") or ""
        m = _STATUS_RE.search(href)
        if m:
            username, tweet_id = m.group(1), m.group(2)
            return tweet_id, username, f"https://x.com/{username}/status/{tweet_id}"

    # --- fallback: first safe /status/ link ---
    for lnk in art.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]'):
        href = lnk.get_attribute("href") or ""
        if any(s in href for s in ("/analytics", "/photo/", "/video/")):
            continue
        m = _STATUS_RE.search(href)
        if m:
            username, tweet_id = m.group(1), m.group(2)
            return tweet_id, username, f"https://x.com/{username}/status/{tweet_id}"

    return None, None, None


def _extract_video_thumbnail(art, By):
    """
    Return the video thumbnail URL from a tweet article element.

    X's DOM puts the profile avatar (pbs.twimg.com/profile_images/…) first,
    so a naive img[src*="pbs.twimg.com"] selector always grabs the avatar.

    Strategy (in order of reliability):
      1. <video poster="…"> inside the video player — the actual video frame.
      2. Any img whose src contains a video-thumbnail path keyword.
      3. Any img inside the video-player container.
      4. Any pbs.twimg.com img whose src does NOT contain "profile_images".
    """
    # 1. video poster attribute (most accurate — the frame X chose as preview)
    try:
        v = art.find_element(By.CSS_SELECTOR,
            '[data-testid="videoPlayer"] video, [data-testid="videoComponent"] video')
        poster = v.get_attribute("poster") or ""
        if poster:
            return poster
    except Exception:
        pass

    # 2. img with video-thumbnail path in src
    for kw in ("ext_tw_video_thumb", "tweet_video_thumb",
                "amplify_video_thumb", "card_img", "media_thumbnail"):
        try:
            src = art.find_element(
                By.CSS_SELECTOR, f'img[src*="{kw}"]'
            ).get_attribute("src") or ""
            if src:
                return src
        except Exception:
            pass

    # 3. any img inside the video player container
    for sel in ('[data-testid="videoPlayer"] img',
                '[data-testid="videoComponent"] img',
                '[data-testid="animatedMediaPlayer"] img'):
        try:
            src = art.find_element(By.CSS_SELECTOR, sel).get_attribute("src") or ""
            if src:
                return src
        except Exception:
            pass

    # 4. fallback: first pbs.twimg.com img that is NOT a profile picture
    for img in art.find_elements(By.CSS_SELECTOR, 'img[src*="pbs.twimg.com"]'):
        src = img.get_attribute("src") or ""
        if src and "profile_images" not in src:
            return src

    return ""


_DURATION_TEXT_RE = __import__("re").compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _parse_duration_str(txt):
    """Convert 'M:SS', 'MM:SS' or 'H:MM:SS' to seconds. Returns 0 on mismatch."""
    m = _DURATION_TEXT_RE.match(txt.strip())
    if not m:
        return 0
    a, b, c = m.groups()
    if c is not None:
        return int(a) * 3600 + int(b) * 60 + int(c)
    return int(a) * 60 + int(b)


def _extract_video_duration(art, By):
    """
    Return the video duration (seconds) from the small "M:SS" badge X overlays
    on video thumbnails, or 0 if not found / not a timed video.
    """
    for sel in ('[data-testid="videoPlayer"]', '[data-testid="videoComponent"]',
                '[data-testid="animatedMediaPlayer"]'):
        try:
            container = art.find_element(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for el in container.find_elements(By.CSS_SELECTOR, "span"):
            sec = _parse_duration_str(el.text or "")
            if sec:
                return sec
    return 0


def _ss_parse(driver, seen_ids, results, page_size, need_video_check, duration_filter="any"):
    """Read all currently rendered articles; append new unseen video ones."""
    from selenium.webdriver.common.by import By

    for art in driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]'):
        if len(results) >= page_size:
            break
        try:
            tweet_id, username, tweet_url = _canonical_tweet_url(art, By)

            # Dedup by numeric tweet ID — immune to URL variants
            if not tweet_id or tweet_id in seen_ids:
                continue
            seen_ids.add(tweet_id)

            if need_video_check:
                if not art.find_elements(
                    By.CSS_SELECTOR,
                    '[data-testid="videoPlayer"],[data-testid="videoComponent"],'
                    '[data-testid="animatedMediaPlayer"],video'
                ):
                    continue

            text = ""
            try:
                text = art.find_element(
                    By.CSS_SELECTOR, '[data-testid="tweetText"]'
                ).text[:120]
            except Exception:
                pass

            thumbnail = _extract_video_thumbnail(art, By)
            duration  = _extract_video_duration(art, By)

            # Duration filter — only skip when duration is known (>0);
            # unknown-duration videos are kept to avoid endless scrolling.
            if duration and duration_filter and duration_filter != "any":
                if duration_filter == "short" and not (0 < duration <= 600):
                    continue
                if duration_filter == "medium" and not (600 < duration <= 1800):
                    continue
                if duration_filter == "long" and not (duration > 1800):
                    continue

            results.append({
                "id": tweet_id, "url": tweet_url,
                "title": text or f"Vídeo de @{username}",
                "uploader": username, "uploader_id": username,
                "duration": duration, "thumbnail": thumbnail,
                "view_count": 0, "like_count": 0,
            })
        except Exception as e:
            print(f"  parse: {e}")


def _ss_scroll_down(driver):
    """
    Scroll down one viewport at a time (not to the absolute bottom).
    This keeps the intersection-observer triggers that X uses to lazy-load
    new tweets firing correctly, instead of jumping past all pending content.
    """
    driver.execute_script("window.scrollBy(0, window.innerHeight * 1.5)")


def _ss_fetch_page(page_size=20):
    """
    Collect `page_size` new results by parsing visible articles then scrolling
    as needed.  Returns (results_list, has_more).
    """
    import time
    driver    = _SS["driver"]
    seen_ids  = _SS["seen_ids"]
    need_vc   = _SS["need_video_check"]
    dur_filt  = _SS.get("duration_filter", "any")
    results   = []

    # Parse whatever is already visible (may already have new articles from prior scroll)
    _ss_parse(driver, seen_ids, results, page_size, need_vc, dur_filt)

    while len(results) < page_size and not _SS["finished"]:
        prev_seen = len(seen_ids)
        _ss_scroll_down(driver)
        time.sleep(3)          # give X's lazy-loader time to fetch and render
        _SS["scroll_count"] += 1
        _ss_parse(driver, seen_ids, results, page_size, need_vc, dur_filt)

        if len(seen_ids) == prev_seen:
            _SS["no_new_streak"] += 1
            if _SS["no_new_streak"] >= 4:   # 4 empty scrolls → truly end of feed
                _SS["finished"] = True
                break
        else:
            _SS["no_new_streak"] = 0

        if _SS["scroll_count"] >= _SS_MAX_SCROLL:
            _SS["finished"] = True
            break

    _SS["last_used"] = time.time()
    has_more = not _SS["finished"]
    print(f"  page: {len(results)} new, {len(seen_ids)} total seen, scrolls={_SS['scroll_count']}, has_more={has_more}")
    return results, has_more


def _xf_close():
    _hard_kill_driver(_XF_SS.get("driver"))
    _XF_SS.update({
        "id": None, "driver": None, "seen_ids": set(),
        "duration": "any", "finished": False,
        "scroll_count": 0, "no_new_streak": 0, "last_used": 0,
        "category": "straight", "query": "",
    })


atexit.register(_xf_close)   # clean up on server shutdown


def _xf_open_session(category, query):
    """
    Create a headless Chrome session, navigate to the given xFree category, and
    type `query` into the site's own search box if provided (see the category
    note in _XF_SS's definition for why this can't just be a query param).
    Extracted out of the /api/search route so both the initial search and the
    crash-retry path (see _is_transient_browser_error) can reuse the same flow.

    Raises _NoResultsError if the category page never renders any videos (not
    retryable) — any other exception is a candidate transient browser crash
    for the caller to retry. Returns the driver on success.
    """
    import time
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import TimeoutException

    driver = _ss_driver()
    try:
        driver.get(f"https://www.xfree.com{_XF_CATEGORY_PATH.get(category, '/')}")
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".wall__item"))
            )
        except TimeoutException:
            _hard_kill_driver(driver)
            raise _NoResultsError("Nenhum vídeo encontrado no xfree.com.")
        time.sleep(1)

        if query:
            # Category is Vuex state set by the page we just loaded — searching via
            # the site's own search box (client-side nav) keeps that state, unlike
            # navigating straight to a /search?q=... URL, which resets it.
            inp = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name=q]"))
            )
            driver.execute_script("arguments[0].click()", inp)
            inp.send_keys(query)
            inp.send_keys(Keys.ENTER)
            WebDriverWait(driver, 15).until(lambda drv: "search" in drv.current_url)
            time.sleep(1.5)

        return driver
    except _NoResultsError:
        raise
    except Exception:
        _hard_kill_driver(driver)
        raise


def _xf_scroll_down(driver):
    """Scroll one viewport at a time so xfree's scroll-triggered XHR fires naturally."""
    driver.execute_script("window.scrollBy(0, window.innerHeight * 1.5)")


def _xf_parse(driver, seen_ids, results, page_size, duration_filter="any"):
    """Read all currently rendered wall__item cards; append new unseen ones."""
    for item in _parse_xfree_blocks(driver.page_source):
        if len(results) >= page_size:
            break
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])

        if duration_filter and duration_filter != "any":
            d = item["duration"]
            if duration_filter == "short" and not (0 < d <= 600):
                continue
            if duration_filter == "medium" and not (600 < d <= 1800):
                continue
            if duration_filter == "long" and not (d > 1800):
                continue

        results.append(item)


def _xf_fetch_page(page_size=20):
    """
    Collect `page_size` new xfree search results by parsing rendered cards then
    scrolling to trigger the site's own infinite-scroll XHR as needed.
    Returns (results_list, has_more).
    """
    import time
    driver   = _XF_SS["driver"]
    seen_ids = _XF_SS["seen_ids"]
    dur_filt = _XF_SS.get("duration", "any")
    results  = []

    _xf_parse(driver, seen_ids, results, page_size, dur_filt)

    while len(results) < page_size and not _XF_SS["finished"]:
        prev_seen = len(seen_ids)
        _xf_scroll_down(driver)
        time.sleep(2.5)         # give xfree's XHR time to fetch and render
        _XF_SS["scroll_count"] += 1
        _xf_parse(driver, seen_ids, results, page_size, dur_filt)

        if len(seen_ids) == prev_seen:
            _XF_SS["no_new_streak"] += 1
            if _XF_SS["no_new_streak"] >= 4:   # 4 empty scrolls → truly end of results
                _XF_SS["finished"] = True
                break
        else:
            _XF_SS["no_new_streak"] = 0

        if _XF_SS["scroll_count"] >= _XF_SS_MAX_SCROLL:
            _XF_SS["finished"] = True
            break

    _XF_SS["last_used"] = time.time()
    has_more = not _XF_SS["finished"]
    print(f"  xfree page: {len(results)} new, {len(seen_ids)} total seen, scrolls={_XF_SS['scroll_count']}, has_more={has_more}")
    return results, has_more


def get_video_formats(url):
    opts = build_ydl_opts({"skip_download": True}, url=url)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                fmts = []
                for f in info.get("formats", []):
                    if f.get("vcodec") == "none":
                        continue
                    size_b = f.get("filesize") or f.get("filesize_approx") or 0
                    fmts.append({
                        "format_id": f.get("format_id", ""),
                        "ext": f.get("ext", "mp4"),
                        "width": f.get("width", 0),
                        "height": f.get("height", 0),
                        "fps": f.get("fps", 0),
                        "vcodec": f.get("vcodec", ""),
                        "filesize_mb": round(size_b / 1048576, 2) if size_b else 0,
                        "tbr": f.get("tbr", 0),
                    })
                fmts.sort(key=lambda x: x["height"] or 0, reverse=True)
                return {"title": info.get("title", ""), "uploader": info.get("uploader", ""),
                        "duration": info.get("duration", 0), "thumbnail": info.get("thumbnail", ""),
                        "formats": fmts}
    except Exception as ex:
        print(f"Formats error: {ex}")
    return None


# Live tasks only: task_id -> {"stop": threading.Event(), "action": "pause"|"cancel", "filename": str|None}.
# Popped once download_task's thread exits (paused/cancelled/complete/error alike) —
# a paused task has no entry here, since nothing is running for it anymore; its
# resumable state lives in download_progress instead (see _resume_hint below).
_download_control = {}


class _DownloadPaused(Exception):
    pass


class _DownloadCancelledByUser(Exception):
    pass


def _remove_partial_files(filename):
    """Best-effort delete of a yt-dlp destination file and its .part/.ytdl siblings."""
    if not filename:
        return
    for candidate in (filename, filename + ".part", filename + ".ytdl"):
        try:
            if os.path.exists(candidate):
                os.remove(candidate)
        except Exception:
            pass


def download_task(task_id, url, format_id, out_dir):
    download_progress[task_id] = {"status": "downloading", "percent": 0}
    ctrl = {"stop": threading.Event(), "action": None, "filename": None}
    _download_control[task_id] = ctrl

    def hook(d):
        if d.get("filename"):
            ctrl["filename"] = d["filename"]
        if ctrl["stop"].is_set():
            raise (_DownloadCancelledByUser if ctrl["action"] == "cancel" else _DownloadPaused)()
        if d["status"] == "downloading":
            try:
                pct = float(d.get("_percent_str", "0%").strip().replace("%", ""))
            except:
                pct = 0
            download_progress[task_id].update({"percent": pct, "speed": d.get("_speed_str", ""), "eta": d.get("_eta_str", "")})
        elif d["status"] == "finished":
            download_progress[task_id].update({"status": "finished", "percent": 100})

    opts = build_ydl_opts({"format": format_id,
                            "outtmpl": os.path.join(out_dir, "%(title)s_%(id)s.%(ext)s"),
                            "progress_hooks": [hook], "merge_output_format": "mp4"}, url=url)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                download_progress[task_id] = {
                    "status": "error",
                    "error": "Nenhum vídeo encontrado neste tweet (pode ser embed externo ou tweet sem vídeo)",
                }
                return
            # prepare_filename may return path without final extension after merge;
            # look for the actual file on disk as fallback
            fp = ydl.prepare_filename(info)
            if not os.path.exists(fp):
                # yt-dlp might have merged into .mp4 — find the most recent file
                candidates = sorted(
                    glob.glob(os.path.join(out_dir, f"*{info.get('id', '')}*")),
                    key=os.path.getmtime, reverse=True,
                )
                fp = candidates[0] if candidates else fp
            download_progress[task_id].update({
                "status": "complete", "filepath": fp, "filename": os.path.basename(fp),
            })
    except _DownloadPaused:
        # Deliberately leave the .part file on disk — yt-dlp resumes from it via
        # HTTP Range requests when download_task runs again with the same
        # url/format_id (same deterministic outtmpl -> same destination path).
        download_progress[task_id].update({
            "status": "paused", "url": url, "format_id": format_id, "filename": ctrl["filename"],
        })
    except _DownloadCancelledByUser:
        _remove_partial_files(ctrl["filename"])
        download_progress[task_id] = {"status": "cancelled"}
    except Exception as ex:
        download_progress[task_id] = {"status": "error", "error": str(ex)}
    finally:
        _download_control.pop(task_id, None)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/session")
def session_info():
    has_cookies = os.path.exists(COOKIES_FILE)
    return jsonify({**session_state, "has_cookies": has_cookies, "download_dir": DOWNLOAD_DIR})

# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.route("/api/auth/auto-import", methods=["POST"])
def auto_import():
    """Try to auto-import cookies from installed browser"""
    data = request.json or {}
    browser = data.get("browser", "auto")

    if browser in ("chrome", "auto"):
        db = find_chrome_cookie_db()
        if db:
            ok, msg = extract_x_cookies_from_chrome(db)
            if ok:
                session_state.update({"logged_in": True, "method": "chrome"})
                return jsonify({"success": True, "message": msg, "browser": "Chrome"})
            # Chrome cookies likely encrypted by keyring — try yt-dlp as fallback
            ok2, msg2 = extract_x_cookies_via_ytdlp("chrome")
            if ok2:
                session_state.update({"logged_in": True, "method": "chrome"})
                return jsonify({"success": True, "message": msg2, "browser": "Chrome"})
            if browser == "chrome":
                return jsonify({"success": False, "error": f"{msg} | yt-dlp: {msg2}"})

    if browser in ("firefox", "auto"):
        db = find_firefox_cookie_db()
        if db:
            ok, msg = extract_x_cookies_from_firefox(db)
            if ok:
                session_state.update({"logged_in": True, "method": "firefox"})
                return jsonify({"success": True, "message": msg, "browser": "Firefox"})
            if browser == "firefox":
                return jsonify({"success": False, "error": msg})
        else:
            # Firefox not found via direct DB — try yt-dlp (also works for snap)
            ok2, msg2 = extract_x_cookies_via_ytdlp("firefox")
            if ok2:
                session_state.update({"logged_in": True, "method": "firefox"})
                return jsonify({"success": True, "message": msg2, "browser": "Firefox"})
            if browser == "firefox":
                return jsonify({"success": False, "error": "Firefox não encontrado ou sem cookies do X."})

    if browser == "auto":
        return jsonify({"success": False, "error": "Nenhum navegador com cookies do X encontrado. Tente a aba 'Via yt-dlp' ou cole os cookies manualmente."})

    return jsonify({"success": False, "error": "Navegador não encontrado."})


@app.route("/api/auth/paste-cookies", methods=["POST"])
def paste_cookies():
    """Import cookies from pasted text (JSON or Netscape format)"""
    data = request.json or {}
    text = data.get("cookies", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Nenhum cookie fornecido."})
    
    ok, msg = import_cookies_from_text(text)
    if ok:
        session_state.update({"logged_in": True, "method": "paste"})
    return jsonify({"success": ok, "message": msg if ok else None, "error": msg if not ok else None})


@app.route("/api/auth/yt-dlp-browser", methods=["POST"])
def ytdlp_browser():
    """Use yt-dlp's built-in browser cookie extraction"""
    data = request.json or {}
    browser = data.get("browser", "chrome")  # chrome, firefox, edge, safari, opera

    # yt-dlp writes cookies to cookiefile during __init__ / __exit__, not during
    # extract_info — so the URL failing as "Unsupported" is fine; cookies are
    # still written. We ignore the URL error and check the file afterward.
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "logger": _QuietLogger(),
        "cookiesfrombrowser": (browser,),
        "cookiefile": COOKIES_FILE,
        "playlistend": 1,
    }
    init_error = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.extract_info("https://x.com/", download=False)
            except Exception:
                pass  # URL may not be a supported extractor; cookies still exported on __exit__
    except Exception as e:
        init_error = str(e)

    if os.path.exists(COOKIES_FILE):
        cookies = load_cookies_dict()
        if cookies.get("auth_token"):
            session_state.update({"logged_in": True, "method": browser})
            return jsonify({"success": True, "message": f"Cookies extraídos do {browser.capitalize()}!"})
        return jsonify({
            "success": False,
            "error": f"Cookies exportados mas sem token de autenticação do X. Certifique-se de estar logado no X no {browser.capitalize()} e tente novamente."
        })

    err_msg = init_error or f"Não foi possível extrair cookies do {browser.capitalize()}. Verifique se está instalado e logado no X."
    return jsonify({"success": False, "error": err_msg})


@app.route("/api/auth/validate", methods=["POST"])
def validate():
    ok, msg = validate_cookies()
    # Always sync — previously this only flipped to True and never back to False,
    # so once cookies expired mid-session the app kept believing "logged_in: true"
    # until an explicit logout, and searches/uploads failed with X's raw API errors
    # instead of the app showing the re-auth screen.
    session_state["logged_in"] = ok
    return jsonify({"valid": ok, "message": msg})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session_state.update({"logged_in": False, "username": "", "method": ""})
    if os.path.exists(COOKIES_FILE):
        os.remove(COOKIES_FILE)
    return jsonify({"success": True})


# ── Video endpoints ──────────────────────────────────────────────────────────

@app.route("/api/search", methods=["POST"])
def search():
    import urllib.parse, time

    d = request.json or {}
    q        = d.get("query", "").strip()
    t        = d.get("type", "keyword")
    platform = d.get("platform", "x").lower()
    page_size = max(5, min(int(d.get("count", 20)), 40))

    # ── xFree (home + search) — client-side infinite scroll, needs a real browser ──
    if platform == "xfree":
        category = d.get("category", "straight")
        if category not in _XF_CATEGORY_PATH:
            category = "straight"
        _xf_close()
        duration = d.get("duration", "any")
        last_err = None
        for attempt in range(_BROWSER_RETRY_ATTEMPTS):
            driver = None
            try:
                driver = _xf_open_session(category, q)

                sid = str(uuid.uuid4())[:12]
                _XF_SS.update({
                    "id": sid, "driver": driver, "seen_ids": set(),
                    "duration": duration, "finished": False,
                    "scroll_count": 0, "no_new_streak": 0, "last_used": time.time(),
                    "category": category, "query": q,
                })
                driver = None  # ownership transferred to _XF_SS; don't quit it below

                results, has_more = _xf_fetch_page(page_size)
                _record_scraper_outcome("xfree", bool(results), context=f"category={category} query={q!r}")
                if not results and not has_more:
                    return jsonify({"error": "Nenhum vídeo encontrado no xfree.com.",
                                    "results": [], "has_more": False})
                return jsonify({
                    "results": results, "count": len(results),
                    "has_more": has_more, "search_id": sid,
                })
            except _NoResultsError as e:
                _hard_kill_driver(driver)
                # xFree has no login wall — every _NoResultsError here means the
                # category page rendered but no .wall__item ever appeared, which
                # a real category page should always have.
                _record_scraper_outcome("xfree", False, context=f"category={category} query={q!r}")
                return jsonify({"error": str(e), "results": [], "has_more": False})
            except Exception as e:
                _hard_kill_driver(driver)
                _xf_close()
                last_err = e
                if attempt + 1 < _BROWSER_RETRY_ATTEMPTS and _is_transient_browser_error(e):
                    delay = 3 * (attempt + 1)  # 3s, 6s, 9s — escalating, in case contention is a longer dip
                    print(f"  xfree: sessão do navegador travou ({e}) — tentativa {attempt+2}/{_BROWSER_RETRY_ATTEMPTS} em {delay}s...")
                    time.sleep(delay)
                    continue
                break
        if _is_transient_browser_error(last_err):
            _self_heal_restart(f"xfree esgotou {_BROWSER_RETRY_ATTEMPTS} tentativas: {last_err}")
        return jsonify({"error": f"Erro no navegador: {last_err}", "results": [], "has_more": False}), 500

    # ── External sites (XHamster, XVideos, Pornhub) ───────────────────────────
    if platform in ("xhamster", "xvideos", "pornhub"):
        # query="" is valid now — it means "Home" (browse the category's landing feed)
        sort     = d.get("sort", "relevance")
        duration = d.get("duration", "any")
        category = d.get("category", "straight")
        # XHamster/Pornhub start at page 1; XVideos starts at page 0
        first_page = 0 if platform == "xvideos" else 1
        sid = str(uuid.uuid4())[:12]
        ss = _SITE_SS[platform]
        ss.update({
            "id": sid, "site": platform, "query": q,
            "page": first_page + 1,   # next page to fetch
            "sort": sort, "duration": duration, "category": category,
            "seen_ids": set(), "finished": False, "last_used": time.time(),
        })
        results, raw_count, err = search_site_page(platform, q, page=first_page, sort=sort, duration=duration, category=category)
        if not q:
            # Only home/category browsing, not keyword searches — a rare
            # keyword can legitimately return zero, but a category landing
            # page should always have content.
            _record_scraper_outcome(platform, raw_count > 0, context=f"category={category}")
        if err and not results:
            return jsonify({"error": err, "results": [], "has_more": False})
        # has_more based on raw page size: if the site returned a full page, there are likely more
        has_more = raw_count >= 10
        if raw_count == 0:
            ss["finished"] = True
            has_more = False
        # XVideos' category landing page returns the exact same set regardless of
        # page — there's no more to fetch, so don't offer a "load more" that would
        # just loop forever getting 0 new (deduped) results.
        if platform == "xvideos" and not q:
            has_more = False
            ss["finished"] = True
        # Dedup — some sites (e.g. Pornhub category browsing) repeat a handful of
        # promoted items across consecutive pages.
        results = [r for r in results if r["id"] not in ss["seen_ids"] and not ss["seen_ids"].add(r["id"])]
        return jsonify({
            "results": results, "count": len(results),
            "has_more": has_more, "search_id": sid,
        })

    # ── X.com via Selenium ────────────────────────────────────────────────────
    if t not in ("home", "following") and not q:
        return jsonify({"error": "Query obrigatória"}), 400

    if t == "keyword":
        enc = urllib.parse.quote(f"{q} filter:videos")
        url, need_vc = f"https://x.com/search?q={enc}&src=typed_query&f=video", False
    elif t == "hashtag":
        url, need_vc = f"https://x.com/hashtag/{q.lstrip('#')}?src=hashtag_click&f=video", False
    elif t == "user":
        url, need_vc = f"https://x.com/{q.lstrip('@')}/media", True
    elif t == "home":
        url, need_vc = "https://x.com/home", True
    elif t == "following":
        # Same page as "home" — the "Seguindo" tab is selected via click below.
        url, need_vc = "https://x.com/home", True
    else:
        enc = urllib.parse.quote(f"{q} filter:videos")
        url, need_vc = f"https://x.com/search?q={enc}&src=typed_query&f=video", False

    _ss_close()
    last_err = None
    for attempt in range(_BROWSER_RETRY_ATTEMPTS):
        driver = None
        try:
            driver = _x_open_session(t, url, need_vc)

            sid = str(uuid.uuid4())[:12]
            _SS.update({
                "id": sid, "driver": driver, "seen_ids": set(),
                "need_video_check": need_vc, "duration_filter": d.get("duration", "any"),
                "finished": False,
                "scroll_count": 0, "no_new_streak": 0, "last_used": time.time(),
                "url": url, "type": t,
            })
            driver = None  # ownership transferred to _SS; don't quit it below

            results, has_more = _ss_fetch_page(page_size)
            if t in ("home", "following"):
                # Only the feed types, not keyword/hashtag/user searches — a
                # narrow keyword search can legitimately return zero results,
                # but an active account's own feed should always have tweets.
                _record_scraper_outcome("x", bool(results), context=f"type={t}")
            return jsonify({
                "results": results, "count": len(results),
                "has_more": has_more, "search_id": sid,
            })
        except _NoResultsError as e:
            _hard_kill_driver(driver)
            # Exclude the "needs login" case — that's an auth problem, not a
            # sign the tweet-parsing logic broke.
            if t in ("home", "following") and "solicitou login" not in str(e):
                _record_scraper_outcome("x", False, context=f"type={t}")
            return jsonify({"error": str(e), "results": [], "has_more": False})
        except Exception as e:
            # If the crash happened before `driver` was handed off to _SS (e.g.
            # during initial navigation), _ss_close() below won't see it — clean
            # it up here so the Chrome/chromedriver process and its --user-data-dir
            # don't leak.
            _hard_kill_driver(driver)
            _ss_close()
            last_err = e
            if attempt + 1 < _BROWSER_RETRY_ATTEMPTS and _is_transient_browser_error(e):
                delay = 3 * (attempt + 1)  # 3s, 6s, 9s — escalating, in case contention is a longer dip
                print(f"  X: sessão do navegador travou ({e}) — tentativa {attempt+2}/{_BROWSER_RETRY_ATTEMPTS} em {delay}s...")
                time.sleep(delay)
                continue
            break
    if _is_transient_browser_error(last_err):
        _self_heal_restart(f"X esgotou {_BROWSER_RETRY_ATTEMPTS} tentativas: {last_err}")
    return jsonify({"error": f"Erro no navegador: {last_err}", "results": [], "has_more": False}), 500


# ── Background search tasks ───────────────────────────────────────────────────
# A fresh search (especially X/xFree via Selenium, or "buscar em tudo" running
# all 5 platforms one after another) can take from several seconds to over a
# minute. Previously that whole time lived inside a single blocking fetch() on
# the client — if the tab got backgrounded (phone screen off, user switches
# app) mobile browsers throttle or fully suspend JS/networking, and the
# in-flight request either stalls or is dropped, losing the search entirely.
# Same fix as downloads: the actual work moves into a server-side thread that
# keeps running regardless of what the client tab does, tracked in
# _search_tasks and polled by task_id — /api/search itself is untouched and
# still works exactly as before for anything that wants a synchronous call.
_search_tasks = {}
_SEARCH_TASK_MAX_AGE = 3600  # seconds — stale finished tasks get swept by the watchdog
_ALL_SEARCH_PLATFORMS = ["x", "xhamster", "xvideos", "xfree", "pornhub"]


def _call_search_view(body):
    """
    Invoke the existing `search()` view function as if a real POST /api/search
    request had arrived, without going through actual HTTP — reuses every
    branch of that function verbatim (xfree/xhamster/xvideos/pornhub/X, retry
    logic, session bookkeeping, all of it) instead of duplicating any of that
    logic for background execution. `test_request_context` synthesizes a real
    Flask request/app context so `request.json` etc. work normally inside;
    `app.make_response` normalizes whatever the view returned (a bare
    Response, or a (body, status) tuple) the same way Flask's own dispatcher
    would for a real request.
    """
    with app.test_request_context("/api/search", method="POST", json=body):
        rv = search()
        resp = app.make_response(rv)
        return resp.status_code, resp.get_json()


def _run_single_search_task(task_id, body):
    _search_tasks[task_id] = {"status": "running", "kind": "single", "started": time.time()}
    try:
        status_code, resp = _call_search_view(body)
        is_error = status_code >= 400 or bool(resp.get("error"))
        _search_tasks[task_id] = {
            "status": "error" if is_error else "complete",
            "kind": "single", "body": resp, "finished": time.time(),
        }
    except Exception as e:
        _search_tasks[task_id] = {"status": "error", "kind": "single",
                                   "body": {"error": f"Erro no navegador: {e}"}, "finished": time.time()}


def _body_for_all_platform(platform, d):
    q = d.get("query", "")
    count = d.get("count", 20)
    if platform == "x":
        return {"query": q, "type": "keyword", "platform": "x", "duration": "any", "count": count}
    if platform == "xfree":
        return {"query": q, "platform": "xfree", "type": "search", "category": d.get("xfCategory", "straight"), "count": count}
    if platform == "pornhub":
        return {"query": q, "platform": "pornhub", "type": "search", "category": d.get("phCategory", "straight"), "count": count}
    return {"query": q, "platform": platform, "type": "search", "sort": "relevance", "duration": "any",
            "category": d.get("siteCategory", "straight"), "count": count}


def _run_aggregate_search_task(task_id, d):
    task = {
        "status": "running", "kind": "aggregate", "started": time.time(),
        "results": [], "done": 0, "total": len(_ALL_SEARCH_PLATFORMS), "current": None,
        "search_ids": {}, "has_more": {},
    }
    _search_tasks[task_id] = task
    any_results = False
    for i, p in enumerate(_ALL_SEARCH_PLATFORMS):
        task["current"] = p
        task["done"] = i
        try:
            status_code, resp = _call_search_view(_body_for_all_platform(p, d))
            if status_code < 400 and not resp.get("error") and resp.get("results"):
                any_results = True
                tagged = [{**r, "_platform": p} for r in resp["results"]]
                task["results"] = task["results"] + tagged
                task["search_ids"][p] = resp.get("search_id")
                task["has_more"][p] = bool(resp.get("has_more"))
        except Exception:
            pass  # skip this platform, keep going with the rest — same as before
    task["current"] = None
    task["done"] = task["total"]
    task["status"] = "complete"
    task["finished"] = time.time()
    if not any_results:
        task["error"] = "Nenhum vídeo encontrado em nenhuma plataforma."


@app.route("/api/search/start", methods=["POST"])
def search_task_start():
    d = request.json or {}
    task_id = str(uuid.uuid4())
    threading.Thread(target=_run_single_search_task, args=(task_id, d), daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/search/start_all", methods=["POST"])
def search_task_start_all():
    d = request.json or {}
    task_id = str(uuid.uuid4())
    threading.Thread(target=_run_aggregate_search_task, args=(task_id, d), daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/search/task/<tid>")
def search_task_status(tid):
    return jsonify(_search_tasks.get(tid, {"status": "not_found"}))


@app.route("/api/search/more", methods=["POST"])
def search_more():
    import time
    d = request.json or {}
    sid       = d.get("search_id", "")
    page_size = max(5, min(int(d.get("count", 20)), 40))

    # ── xFree search session (Selenium) ──────────────────────────────────────
    if _XF_SS["id"] == sid:
        if time.time() - _XF_SS.get("last_used", 0) > _XF_SS_TIMEOUT:
            _xf_close()
            return jsonify({"error": "Sessão expirada — faça uma nova busca.",
                            "results": [], "has_more": False}), 400
        if _XF_SS["finished"]:
            return jsonify({"results": [], "has_more": False, "search_id": sid})
        try:
            results, has_more = _xf_fetch_page(page_size)
            return jsonify({
                "results": results, "count": len(results),
                "has_more": has_more, "search_id": sid,
            })
        except Exception as e:
            if not _is_transient_browser_error(e):
                _xf_close()
                return jsonify({"error": f"Erro ao carregar mais: {e}",
                                "results": [], "has_more": False}), 500
            # chromedriver/Chrome died mid-scroll — reopen on the same category
            # (+ redo the search box if there was a query) and keep going from
            # where we left off; seen_ids/scroll_count carry over so already-
            # shown items get filtered rather than repeated.
            print(f"  xfree: sessão do navegador travou ({e}) — tentando retomar 'carregar mais'...")
            saved = dict(_XF_SS)
            _xf_close()
            time.sleep(3)  # let a momentary memory/CPU spike pass before reopening
            try:
                driver = _xf_open_session(saved.get("category", "straight"), saved.get("query", ""))
                _XF_SS.update({
                    "id": sid, "driver": driver, "seen_ids": saved["seen_ids"],
                    "duration": saved["duration"], "finished": False,
                    "scroll_count": saved["scroll_count"], "no_new_streak": 0,
                    "last_used": time.time(),
                    "category": saved.get("category", "straight"), "query": saved.get("query", ""),
                })
                results, has_more = _xf_fetch_page(page_size)
                return jsonify({
                    "results": results, "count": len(results),
                    "has_more": has_more, "search_id": sid,
                })
            except Exception as e2:
                _xf_close()
                if _is_transient_browser_error(e2):
                    _self_heal_restart(f"xfree falhou ao retomar 'carregar mais': {e2}")
                return jsonify({"error": f"Erro ao carregar mais: {e2}",
                                "results": [], "has_more": False}), 500

    # ── Site session (XHamster / XVideos / Pornhub) ──────────────────────────
    # Each site has its own slot now (see _SITE_SS definition) — look up which
    # one (if any) this search_id belongs to rather than assuming a single slot.
    site_match = next((site for site, ss in _SITE_SS.items() if ss["id"] == sid), None)
    if site_match:
        ss = _SITE_SS[site_match]
        if time.time() - ss.get("last_used", 0) > _SITE_SS_TIMEOUT:
            ss.update({"id": None, "finished": True})
            return jsonify({"error": "Sessão expirada — faça uma nova busca.",
                            "results": [], "has_more": False}), 400
        if ss["finished"]:
            return jsonify({"results": [], "has_more": False, "search_id": sid})
        cur_page = ss["page"]
        results, raw_count, err = search_site_page(
            ss["site"], ss["query"],
            page=cur_page,
            sort=ss.get("sort", "relevance"),
            duration=ss.get("duration", "any"),
            category=ss.get("category", "straight"),
        )
        ss["page"]      = cur_page + 1
        ss["last_used"] = time.time()
        has_more = raw_count >= 10   # if site returned content, assume more pages exist
        if raw_count == 0:
            ss["finished"] = True
            has_more = False
        # Dedup — some sites (e.g. Pornhub category browsing) repeat a handful of
        # promoted items across consecutive pages.
        results = [r for r in results if r["id"] not in ss["seen_ids"] and not ss["seen_ids"].add(r["id"])]
        return jsonify({
            "results": results, "count": len(results),
            "has_more": has_more, "search_id": sid,
        })

    # ── X session (Selenium) ──────────────────────────────────────────────────
    if (not _SS["driver"]
            or _SS["id"] != sid
            or time.time() - _SS.get("last_used", 0) > _SS_TIMEOUT):
        _ss_close()
        return jsonify({"error": "Sessão expirada — faça uma nova busca.",
                        "results": [], "has_more": False}), 400

    if _SS["finished"]:
        return jsonify({"results": [], "has_more": False, "search_id": sid})

    try:
        results, has_more = _ss_fetch_page(page_size)
        return jsonify({
            "results": results, "count": len(results),
            "has_more": has_more, "search_id": sid,
        })
    except Exception as e:
        if not _is_transient_browser_error(e):
            _ss_close()
            return jsonify({"error": f"Erro ao carregar mais: {e}",
                            "results": [], "has_more": False}), 500
        # chromedriver/Chrome died mid-scroll — reopen the same search and keep
        # going from where we left off; seen_ids/scroll_count carry over so
        # already-shown tweets get filtered rather than repeated.
        print(f"  X: sessão do navegador travou ({e}) — tentando retomar 'carregar mais'...")
        saved = dict(_SS)
        _ss_close()
        time.sleep(3)  # let a momentary memory/CPU spike pass before reopening
        try:
            driver = _x_open_session(saved.get("type"), saved.get("url"), saved["need_video_check"])
            _SS.update({
                "id": sid, "driver": driver, "seen_ids": saved["seen_ids"],
                "need_video_check": saved["need_video_check"], "duration_filter": saved["duration_filter"],
                "finished": False, "scroll_count": saved["scroll_count"], "no_new_streak": 0,
                "last_used": time.time(), "url": saved.get("url"), "type": saved.get("type"),
            })
            results, has_more = _ss_fetch_page(page_size)
            return jsonify({
                "results": results, "count": len(results),
                "has_more": has_more, "search_id": sid,
            })
        except Exception as e2:
            _ss_close()
            if _is_transient_browser_error(e2):
                _self_heal_restart(f"X falhou ao retomar 'carregar mais': {e2}")
            return jsonify({"error": f"Erro ao carregar mais: {e2}",
                            "results": [], "has_more": False}), 500


@app.route("/api/preview", methods=["POST"])
def preview_video():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL obrigatória"}), 400
    opts = build_ydl_opts({"skip_download": True}, url=url)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return jsonify({"error": "Vídeo não encontrado"}), 404
            # Best combined (video+audio in one stream) — browser plays without merging
            combined = [
                f for f in info.get("formats", [])
                if f.get("vcodec") not in ("none", None)
                and f.get("acodec") not in ("none", None)
                and f.get("url")
            ]
            # Sort descending by height then bitrate → best quality first
            combined.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)

            if not combined:
                # No combined format — pick best video-only (browser may still play it)
                combined = sorted(
                    [f for f in info.get("formats", [])
                     if f.get("vcodec") not in ("none", None) and f.get("url")],
                    key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
                    reverse=True,
                )
            if not combined:
                return jsonify({"error": "Nenhum formato disponível"}), 404

            pf = combined[0]
            return jsonify({
                "url":       pf.get("url"),
                "ext":       pf.get("ext", "mp4"),
                "width":     pf.get("width"),
                "height":    pf.get("height"),
                "thumbnail": info.get("thumbnail", ""),
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/formats", methods=["POST"])
def formats():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL obrigatória"}), 400
    info = get_video_formats(url)
    return jsonify(info) if info else (jsonify({"error": "Não foi possível obter formatos"}), 400)


@app.route("/api/download/start", methods=["POST"])
def start_dl():
    d = request.json or {}
    task_id = str(uuid.uuid4())
    t = threading.Thread(target=download_task, args=(task_id, d.get("url", ""), d.get("format_id", "best"), DOWNLOAD_DIR))
    t.daemon = True
    t.start()
    return jsonify({"task_id": task_id})


@app.route("/api/download/progress/<tid>")
def dl_progress(tid):
    return jsonify(download_progress.get(tid, {"status": "not_found"}))


@app.route("/api/download/pause/<tid>", methods=["POST"])
def pause_dl(tid):
    ctrl = _download_control.get(tid)
    if not ctrl:
        return jsonify({"error": "Download não encontrado ou já finalizado."}), 404
    ctrl["action"] = "pause"
    ctrl["stop"].set()
    return jsonify({"ok": True})


@app.route("/api/download/cancel/<tid>", methods=["POST"])
def cancel_dl(tid):
    # Still running: signal the hook to abort on its next call.
    ctrl = _download_control.get(tid)
    if ctrl:
        ctrl["action"] = "cancel"
        ctrl["stop"].set()
        return jsonify({"ok": True})
    # Already paused (no thread left to signal): clean up the partial file directly.
    p = download_progress.get(tid)
    if p and p.get("status") == "paused":
        _remove_partial_files(p.get("filename"))
        download_progress[tid] = {"status": "cancelled"}
        return jsonify({"ok": True})
    return jsonify({"error": "Download não encontrado ou já finalizado."}), 404


@app.route("/api/download/file/<tid>")
def dl_file(tid):
    p = download_progress.get(tid, {})
    if p.get("status") != "complete":
        return jsonify({"error": "Arquivo não pronto"}), 400
    fp = p.get("filepath", "")
    if not os.path.exists(fp):
        fp = fp.rsplit(".", 1)[0] + ".mp4"
    if os.path.exists(fp):
        return send_file(fp, as_attachment=True)
    return jsonify({"error": "Arquivo não encontrado"}), 404


# ── Library (downloaded videos) ───────────────────────────────────────────────

_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi"}


def _library_path(name):
    """Resolve `name` to an absolute path inside DOWNLOAD_DIR, or None if unsafe/missing."""
    safe = os.path.basename(name or "")
    if not safe:
        return None
    fp = os.path.abspath(os.path.join(DOWNLOAD_DIR, safe))
    if os.path.commonpath([fp, DOWNLOAD_DIR]) != os.path.abspath(DOWNLOAD_DIR):
        return None
    return fp


@app.route("/api/library")
def library_list():
    items = []
    for name in os.listdir(DOWNLOAD_DIR):
        ext = os.path.splitext(name)[1].lower()
        if ext not in _VIDEO_EXTS:
            continue
        fp = os.path.join(DOWNLOAD_DIR, name)
        if not os.path.isfile(fp):
            continue
        st = os.stat(fp)
        items.append({
            "name": name,
            "size_mb": round(st.st_size / 1048576, 2),
            "mtime": st.st_mtime,
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"items": items})


@app.route("/api/library/video/<path:name>")
def library_video(name):
    fp = _library_path(name)
    if not fp or not os.path.isfile(fp):
        return jsonify({"error": "Arquivo não encontrado"}), 404
    return send_file(fp, conditional=True)


@app.route("/api/library/delete", methods=["POST"])
def library_delete():
    name = (request.json or {}).get("name", "")
    fp = _library_path(name)
    if not fp or not os.path.isfile(fp):
        return jsonify({"error": "Arquivo não encontrado"}), 404
    try:
        os.remove(fp)
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500
    return jsonify({"success": True})


# ── Upload de vídeo (chunked) + publicação de tweet ──────────────────────────

_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
_TWEET_URL  = "https://api.twitter.com/1.1/statuses/update.json"


def _x_api_error(step, status_code, body):
    """
    Build an error message for a failed X API call. On 401 (expired session —
    e.g. "OAuth access token has expired") also resets session_state so the
    frontend shows the re-auth screen on the next check, instead of the user
    hitting this same raw English API error on every subsequent action.
    """
    if status_code == 401:
        session_state["logged_in"] = False
        return "Sessão do X expirada. Reimporte os cookies e tente de novo."
    return f"{step} falhou ({status_code}): {body[:300]}"


@app.route("/api/upload/init", methods=["POST"])
def upload_init():
    d           = request.json or {}
    total_bytes = int(d.get("total_bytes", 0))
    media_type  = d.get("media_type", "video/mp4")
    if total_bytes <= 0:
        return jsonify({"error": "total_bytes inválido"}), 400
    cookies = load_cookies_dict()
    if not cookies.get("auth_token"):
        return jsonify({"error": "Não autenticado. Reimporte os cookies."}), 401
    session = _build_x_session(cookies)
    r = session.post(_UPLOAD_URL, data={
        "command":        "INIT",
        "total_bytes":    total_bytes,
        "media_type":     media_type,
        "media_category": "tweet_video",
    })
    if r.status_code != 202:
        return jsonify({"error": _x_api_error("Upload INIT", r.status_code, r.text)}), 500
    return jsonify({"media_id": r.json()["media_id_string"]})


@app.route("/api/upload/chunk", methods=["POST"])
def upload_chunk():
    media_id  = request.form.get("media_id", "")
    seg_index = request.form.get("segment_index", 0)
    chunk_f   = request.files.get("chunk")
    if not media_id or chunk_f is None:
        return jsonify({"error": "Parâmetros inválidos"}), 400
    cookies = load_cookies_dict()
    if not cookies.get("auth_token"):
        return jsonify({"error": "Não autenticado."}), 401
    session = _build_x_session(cookies)
    r = session.post(_UPLOAD_URL, data={
        "command":       "APPEND",
        "media_id":      media_id,
        "segment_index": seg_index,
    }, files={"media": chunk_f.read()})
    if r.status_code not in (200, 204):
        return jsonify({"error": _x_api_error("APPEND", r.status_code, r.text)}), 500
    return jsonify({"ok": True})


@app.route("/api/upload/finalize", methods=["POST"])
def upload_finalize():
    media_id = (request.json or {}).get("media_id", "")
    if not media_id:
        return jsonify({"error": "media_id obrigatório"}), 400
    cookies = load_cookies_dict()
    if not cookies.get("auth_token"):
        return jsonify({"error": "Não autenticado."}), 401
    session = _build_x_session(cookies)
    r = session.post(_UPLOAD_URL, data={"command": "FINALIZE", "media_id": media_id})
    if r.status_code not in (200, 201):
        return jsonify({"error": _x_api_error("FINALIZE", r.status_code, r.text)}), 500
    proc = r.json().get("processing_info")
    if proc:
        import time as _t
        while proc.get("state") not in ("succeeded", "failed"):
            _t.sleep(min(proc.get("check_after_secs", 3), 8))
            r2   = session.get(_UPLOAD_URL, params={"command": "STATUS", "media_id": media_id})
            proc = r2.json().get("processing_info", {})
        if proc.get("state") == "failed":
            msg = proc.get("error", {}).get("message", "Processamento de vídeo falhou.")
            return jsonify({"error": msg}), 500
    return jsonify({"media_id": media_id})


@app.route("/api/tweet/create", methods=["POST"])
def tweet_create():
    d        = request.json or {}
    text     = (d.get("text") or "").strip()
    media_id = (d.get("media_id") or "").strip()
    if not text and not media_id:
        return jsonify({"error": "Texto ou vídeo obrigatório."}), 400
    cookies = load_cookies_dict()
    if not cookies.get("auth_token"):
        return jsonify({"error": "Não autenticado. Reimporte os cookies."}), 401
    session = _build_x_session(cookies)

    # Tenta v1.1 (retorna objeto completo com user.screen_name)
    params = {"status": text or " "}
    if media_id:
        params["media_ids"] = media_id
    r = session.post(_TWEET_URL, data=params)
    if r.status_code in (200, 201):
        data  = r.json()
        tid   = data.get("id_str", "")
        uname = data.get("user", {}).get("screen_name") or session_state.get("username") or "i"
        url   = f"https://x.com/{uname}/status/{tid}" if tid else "https://x.com"
        return jsonify({"success": True, "tweet_id": tid, "url": url})

    # Fallback v2
    payload = {"text": text or " "}
    if media_id:
        payload["media"] = {"media_ids": [media_id]}
    r2 = session.post(
        "https://api.twitter.com/2/tweets",
        json=payload,
        headers={"Content-Type": "application/json"},
    )
    if r2.status_code in (200, 201):
        data  = r2.json().get("data", {})
        tid   = data.get("id", "")
        uname = session_state.get("username") or "i"
        url   = f"https://x.com/{uname}/status/{tid}" if tid else "https://x.com"
        return jsonify({"success": True, "tweet_id": tid, "url": url})

    if r.status_code == 401 and r2.status_code == 401:
        return jsonify({"error": _x_api_error("Publicar tweet", 401, "")}), 500
    return jsonify({"error": f"v1.1 ({r.status_code}): {r.text[:200]} | v2 ({r2.status_code}): {r2.text[:200]}"}), 500


# Restore the X login state from cookies already on disk — runs on every process
# start (both `python app.py` and gunicorn importing this module), so restarting
# the server doesn't force the user back through the X auth screen.
if os.path.exists(COOKIES_FILE):
    try:
        ok, _ = validate_cookies()
        session_state["logged_in"] = ok
    except Exception as ex:
        print(f"Startup cookie validation failed: {ex}")


# ── Self-heal: worker restart after browser-crash retries are fully exhausted ─
# Retry+backoff (_BROWSER_RETRY_ATTEMPTS) already recovers from a single crashed
# Chrome tab. If ALL attempts fail, that's a stronger signal — e.g. sustained
# CPU/memory contention on the host — so this does one more thing beyond just
# surfacing the error: cleans up any tracked session and asks gunicorn's own
# arbiter to respawn this worker (SIGTERM is exactly what --max-requests worker
# recycling uses internally, so this is standard gunicorn behavior, not a hack).
# Skipped entirely if a download is running — download_task() runs as a
# background thread inside this same worker process and would be killed with
# it. This does NOT fix external contention (e.g. another Chrome tab hogging
# CPU) — it only guarantees scrapperx's own state gets a clean slate faster
# than the watchdog sweep (up to 120s later) would.
def _self_heal_restart(reason):
    def _do():
        time.sleep(3)  # let the just-returned HTTP response finish flushing
        if any(t.get("status") == "downloading" for t in download_progress.values()):
            print(f"  Self-heal: pulado (download em andamento) — motivo: {reason}")
            return
        print(f"  Self-heal: reiniciando o worker — motivo: {reason}")
        for cleanup in (_ss_close, _xf_close, _watchdog_sweep):
            try:
                cleanup()
            except Exception as e:
                print(f"  Self-heal: erro em {cleanup.__name__}: {e}")
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_do, daemon=True, name="scrapperx-self-heal").start()


# ── Watchdog: catches what the reactive cleanup paths (_ss_close()/_xf_close()
# on error, or the timeout check in /api/search/more) can't ──────────────────
# Neither of those runs unless a *new* request happens to touch the stale
# session — if a user just closes the tab after starting a search and never
# calls "load more" again, that Chrome session would otherwise idle forever.
# Same for a session orphaned by the server itself being killed (`kill -9`,
# OOM): the next process's _SS/_XF_SS start out empty, so it has no idea the
# old chromedriver/Chrome tree even exists — the exact ~15h/~1.5GB leak found
# in production before _hard_kill_driver existed. A periodic sweep closes idle
# tracked sessions and separately kills any chromedriver process older than
# _WATCHDOG_ORPHAN_AGE that isn't backing a currently tracked session, so a
# leak survives at most one sweep interval instead of indefinitely.
_WATCHDOG_INTERVAL    = 120   # seconds between sweeps
_WATCHDOG_ORPHAN_AGE  = 900   # seconds — well past any real navigation/search,
                              # so nothing legitimate is still "untracked" this long


def _watchdog_sweep():
    now = time.time()
    try:
        stale = [tid for tid, t in _search_tasks.items()
                 if t.get("status") in ("complete", "error") and now - t.get("finished", 0) > _SEARCH_TASK_MAX_AGE]
        for tid in stale:
            _search_tasks.pop(tid, None)
    except Exception as e:
        print(f"  Watchdog: erro limpando search tasks antigas: {e}")

    try:
        if _SS.get("driver") and now - _SS.get("last_used", 0) > _SS_TIMEOUT:
            print("  Watchdog: sessão do X ociosa — encerrando.")
            _ss_close()
    except Exception as e:
        print(f"  Watchdog: erro encerrando sessão do X: {e}")

    try:
        if _XF_SS.get("driver") and now - _XF_SS.get("last_used", 0) > _XF_SS_TIMEOUT:
            print("  Watchdog: sessão do xfree ociosa — encerrando.")
            _xf_close()
    except Exception as e:
        print(f"  Watchdog: erro encerrando sessão do xfree: {e}")

    tracked_pids = set()
    for ss in (_SS, _XF_SS):
        drv = ss.get("driver")
        if drv:
            try:
                tracked_pids.add(drv.service.process.pid)
            except Exception:
                pass

    try:
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                name = (proc.info["name"] or "").lower()
                if "chromedriver" not in name:
                    continue
                if proc.info["pid"] in tracked_pids:
                    continue
                age = now - proc.info["create_time"]
                if age <= _WATCHDOG_ORPHAN_AGE:
                    continue
                print(f"  Watchdog: matando chromedriver órfão pid={proc.info['pid']} (idade {int(age)}s).")
                user_data_dirs = set()
                for child in proc.children(recursive=True):
                    try:
                        for arg in child.cmdline():
                            if arg.startswith("--user-data-dir="):
                                user_data_dirs.add(arg.split("=", 1)[1])
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                proc.kill()
                if user_data_dirs:
                    time.sleep(0.3)  # let just-killed processes release their file handles
                    for d in user_data_dirs:
                        shutil.rmtree(d, ignore_errors=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print(f"  Watchdog: erro varrendo processos órfãos: {e}")


def _watchdog_loop():
    while True:
        time.sleep(_WATCHDOG_INTERVAL)
        _watchdog_sweep()


threading.Thread(target=_watchdog_loop, daemon=True, name="scrapperx-watchdog").start()


# ── Periodic X cookie revalidation ────────────────────────────────────────────
# Until now, session_state["logged_in"] was only (re)checked at server boot and
# when the user manually clicked "Validar" — if the X session expired while the
# server just kept running (the common case, since restarts are infrequent),
# the app kept believing it was logged in until an actual search/upload hit a
# raw X API error (see the earlier "OAuth access token has expired" incident).
# Re-running the same validate_cookies() used at boot/"Validar" periodically
# closes that gap: the UI flips to the re-auth screen within one interval of
# the session actually expiring, instead of only on the next restart.
_COOKIE_REVALIDATE_INTERVAL = 1800   # 30 min — cookies don't expire that fast;
                                      # no reason to hit X's API more often than this


def _cookie_revalidate_check():
    if not os.path.exists(COOKIES_FILE):
        return
    try:
        ok, msg = validate_cookies()
        was_logged_in = session_state.get("logged_in")
        session_state["logged_in"] = ok
        if was_logged_in and not ok:
            print(f"  Revalidação periódica: sessão do X expirou ({msg}).")
        elif not was_logged_in and ok:
            print("  Revalidação periódica: sessão do X voltou a ficar válida.")
    except Exception as e:
        print(f"  Revalidação periódica: erro ao validar cookies do X: {e}")


def _cookie_revalidate_loop():
    while True:
        time.sleep(_COOKIE_REVALIDATE_INTERVAL)
        _cookie_revalidate_check()


threading.Thread(target=_cookie_revalidate_loop, daemon=True, name="scrapperx-cookie-revalidate").start()


if __name__ == "__main__":
    print(f"📁 Download dir: {DOWNLOAD_DIR}")
    print(f"🍪 Cookies file: {COOKIES_FILE}")
    app.run(debug=True, port=5000)


# ── Serve frontend ────────────────────────────────────────────────────────────
from flask import Response as FlaskResponse

@app.route("/")
def serve_index():
    # Resolve absolute path — works with gunicorn from any working dir
    here = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
    index_path = os.path.join(here, "index.html")
    if not os.path.exists(index_path):
        # Fallback: check current working directory
        index_path = os.path.join(os.getcwd(), "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        return FlaskResponse(html, mimetype="text/html")
    return "<h2>index.html não encontrado. Coloque-o na mesma pasta que o app.py</h2>", 404
