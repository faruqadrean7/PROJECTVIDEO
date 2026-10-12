"""TikTok Content Posting API (Direct Post) — auth & upload.

Fase 2: implementasi lengkap.
- authenticate(): OAuth2 authorization code flow (browser -> localhost redirect).
- load_credentials(): baca token + auto-refresh access token.
- upload_video(): /v2/post/publish/video/init/ -> PUT chunk -> status fetch.

Catatan penting (sesuai dokumentasi resmi TikTok):
- Konten yang dipublish oleh client yang BELUM lolos audit dibatasi ke mode
  privat (SELF_ONLY). Untuk publish publik otomatis, app harus menjalani audit.
"""

import hashlib
import json
import math
import mimetypes
import os
import secrets as _secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

import config_manager

# ---------------------------------------------------------------- konfigurasi

# File config app TikTok dari secrets/tiktok_app_config.json.
# Isi: {"client_key": "...", "client_secret": "..."}
# Bisa di-override lewat env var TIKTOK_CONFIG_FILE / TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET.
CONFIG_FILE = Path(
    os.environ.get(
        "TIKTOK_CONFIG_FILE",
        str(Path(__file__).resolve().parent / "secrets" / "tiktok_app_config.json"),
    )
)

BASE_URL = "https://open.tiktokapis.com/v2"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = f"{BASE_URL}/oauth/token/"
INIT_URL = f"{BASE_URL}/post/publish/video/init/"
STATUS_URL = f"{BASE_URL}/post/publish/status/fetch/"

SCOPES = ["video.publish", "video.upload"]

# Redirect URI harus terdaftar di TikTok for Developers (Login Kit config).
# Aturan TikTok: hanya localhost / 127.0.0.1, WAJIB ada port, tanpa parameter.
# Default localhost:8080 — bisa di-override lewat env TIKTOK_REDIRECT_URI
# (kalau diganti, daftarkan juga URI baru di portal TikTok).
REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:8080/")
REDIRECT_PORT = urlparse(REDIRECT_URI).port or 8080

# Ukuran chunk upload (5 MB). TikTok menyarankan chunk besar untuk file besar.
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024

VALID_PRIVACY = (
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "SELF_ONLY",
)

FINAL_STATUSES = ("PUBLISH_COMPLETE", "FAILED")

POLL_INTERVAL_SEC = 5
POLL_TIMEOUT_SEC = 300


# ---------------------------------------------------------------- helpers

def token_filename(account_label: str) -> str:
    """Nama file token untuk satu akun, mis. tiktok_main.json."""
    return f"tiktok_{account_label}.json"


def _save_tokens(account_label: str, tokens: dict) -> None:
    """Simpan token TikTok ke tokens/tiktok_<label>.json."""
    config_manager.save_json(token_filename(account_label), tokens)


def load_app_config() -> dict:
    """Baca client key & secret dari secrets/tiktok_app_config.json (atau env).

    Prioritas: env TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET > isi file config.
    """
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"File config TikTok rusak (bukan JSON valid): {CONFIG_FILE}") from exc

    client_key = os.environ.get("TIKTOK_CLIENT_KEY", cfg.get("client_key"))
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", cfg.get("client_secret"))
    if not client_key or not client_secret:
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(
                f"File config TikTok tidak ditemukan: {CONFIG_FILE}\n"
                "1. Buat app di TikTok for Developers dengan scope video.publish & video.upload\n"
                "2. Buat file secrets/tiktok_app_config.json berisi:\n"
                '   {"client_key": "...", "client_secret": "..."}'
            )
        raise ValueError(
            "client_key dan client_secret harus diisi di secrets/tiktok_app_config.json "
            "(atau env TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET)."
        )
    return {"client_key": client_key, "client_secret": client_secret}


def _friendly_error(code: str, message: str, http_status: int) -> str:
    """Terjemahkan error code TikTok ke pesan yang jelas untuk user."""
    table = {
        "access_token_invalid": "Token TikTok tidak valid/kedaluwarsa — silakan login ulang akun ini.",
        "scope_not_authorized": "Token tidak memiliki izin scope yang diminta — login ulang & izinkan akses.",
        "spam_risk_too_many_posts": "Batas harian post lewat API untuk user ini tercapai.",
        "spam_risk_too_many_pending_share": "Terlalu banyak upload pending (maks 5 per 24 jam) — coba lagi nanti.",
        "spam_risk_user_banned_from_posting": "User ini diblokir dari membuat post baru.",
        "reached_active_user_cap": "Kuota harian active user untuk client ini tercapai — coba lagi besok.",
        "unaudited_client_can_only_post_to_private_accounts": (
            "App TikTok belum lolos audit — hanya bisa post ke akun privat (SELF_ONLY). "
            "Untuk publish publik, ajukan audit app di TikTok for Developers."
        ),
        "privacy_level_option_mismatch": "privacy_level tidak tersedia untuk akun ini — gunakan SELF_ONLY.",
        "rate_limit_exceeded": "Rate limit TikTok API tercapai — tunggu sebentar lalu coba lagi.",
        "invalid_param": f"Parameter tidak valid: {message}",
    }
    if code in table:
        return table[code]
    return f"Error TikTok API (HTTP {http_status}, {code}): {message}"


def _handle_api_response(resp: requests.Response) -> dict:
    """Parse respon TikTok; raise RuntimeError dengan pesan jelas kalau error."""
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"Respon TikTok tidak valid (HTTP {resp.status_code}).") from None

    error = body.get("error") or {}
    code = error.get("code")
    if code and code != "ok":
        raise RuntimeError(
            _friendly_error(code, error.get("message", ""), resp.status_code)
        )
    return body.get("data") or {}


def _auth_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _video_mime(file_path: str) -> str:
    """MIME yang didukung TikTok untuk upload: mp4/quicktime/webm."""
    mime = mimetypes.guess_type(file_path)[0]
    if mime in ("video/mp4", "video/quicktime", "video/webm"):
        return mime
    return "video/mp4"  # fallback paling umum


# ---------------------------------------------------------------- OAuth flow

def _wait_for_code(port: int, timeout: int = 300,
                   expected_state: str | None = None) -> str:
    """Jalankan server HTTP lokal untuk menangkap redirect OAuth berisi code.

    expected_state: kalau diisi, nilai state dari TikTok dicocokkan untuk
    mencegah serangan CSRF (sesuai rekomendasi OAuth 2.0).
    """
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nama method bawaan BaseHTTPRequestHandler)
            qs = parse_qs(urlparse(self.path).query)
            result["code"] = qs.get("code", [None])[0]
            result["error"] = qs.get("error", [None])[0]
            result["state"] = qs.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = bool(result["code"]) and not result["error"]
            html = (
                "<html><body><h3>Login TikTok berhasil ✓</h3>"
                "<p>Silakan tutup tab ini dan kembali ke aplikasi.</p></body></html>"
                if ok
                else "<html><body><h3>Login TikTok gagal/dibatalkan.</h3></body></html>"
            )
            self.wfile.write(html.encode("utf-8"))

        def log_message(self, *args):  # diamkan log bawaan server
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    try:
        server.timeout = 1
        deadline = time.time() + timeout
        while time.time() < deadline:
            server.handle_request()
            if "code" in result or "error" in result:
                break
    finally:
        server.server_close()

    if result.get("error"):
        raise RuntimeError(f"Login TikTok dibatalkan/ditolak: {result['error']}")
    if "code" not in result:
        raise TimeoutError("Tidak menerima redirect dari TikTok dalam batas waktu.")
    if expected_state and result.get("state") != expected_state:
        raise RuntimeError(
            "State tidak cocok (kemungkinan serangan CSRF) — coba login lagi.")
    return result["code"]


def _parse_token_response(resp: requests.Response) -> dict:
    """Parse respon token TikTok; tambahkan expires_at agar bisa dicek kedaluwarsa."""
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"Respon token TikTok tidak valid (HTTP {resp.status_code}).") from None

    if body.get("error"):
        err = body["error"]
        raise RuntimeError(f"Gagal tukar token TikTok ({err.get('code')}): {err.get('message')}")
    if "access_token" not in body:
        raise RuntimeError(f"Respon token TikTok tidak berisi access_token: {body}")

    body["expires_at"] = time.time() + body.get("expires_in", 86400)
    return body


def _exchange_code(cfg: dict, code: str, code_verifier: str) -> dict:
    """Tukar authorization code jadi access token + refresh token.

    code_verifier wajib dikirim karena desktop flow TikTok memakai PKCE.
    """
    resp = requests.post(TOKEN_URL, data={
        "client_key": cfg["client_key"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }, timeout=30)
    return _parse_token_response(resp)


def _refresh_tokens(cfg: dict, refresh_token: str) -> dict:
    """Refresh access token pakai refresh token."""
    resp = requests.post(TOKEN_URL, data={
        "client_key": cfg["client_key"],
        "client_secret": cfg["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, timeout=30)
    return _parse_token_response(resp)


def _generate_pkce() -> tuple[str, str]:
    """Buat pasangan PKCE untuk desktop flow TikTok.

    TikTok mensyaratkan: code_verifier (43-128 karakter) dan
    code_challenge = SHA256(verifier) dalam HEX encoding (bukan base64url).

    Returns (code_verifier, code_challenge).
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(_secrets.choice(alphabet) for _ in range(64))
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
    return verifier, challenge


def authenticate(account_label: str) -> dict:
    """Jalankan OAuth2 authorization code flow (dengan PKCE, wajib desktop):
    buka browser -> user login -> redirect ke localhost dengan code ->
    tukar code jadi access token + refresh token -> simpan ke tokens/.

    Returns dict token siap pakai.
    """
    cfg = load_app_config()

    # state untuk anti-CSRF (diverifikasi ulang di redirect)
    state = _secrets.token_urlsafe(16)
    code_verifier, code_challenge = _generate_pkce()
    params = {
        "client_key": cfg["client_key"],
        "response_type": "code",
        # TikTok desktop: scope dipisah koma (,) di URL authorize
        "scope": ",".join(SCOPES),
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    print(f"Buka browser untuk login TikTok (redirect: {REDIRECT_URI})...")
    webbrowser.open(auth_url)

    code = _wait_for_code(REDIRECT_PORT, expected_state=state)
    tokens = _exchange_code(cfg, code, code_verifier)
    _save_tokens(account_label, tokens)
    return tokens


def load_credentials(account_label: str) -> dict | None:
    """Baca token tersimpan; auto-refresh access token kalau sudah kedaluwarsa.

    Returns dict token siap pakai, atau None kalau akun belum pernah login.
    """
    data = config_manager.load_json(token_filename(account_label))
    if not data:
        return None

    if time.time() >= data.get("expires_at", 0) and data.get("refresh_token"):
        try:
            data = _refresh_tokens(load_app_config(), data["refresh_token"])
        except Exception as exc:
            raise ConnectionError(
                f"Refresh token TikTok akun '{account_label}' gagal/direvoke. "
                f"Silakan login ulang akun ini. ({exc})"
            ) from exc
        _save_tokens(account_label, data)

    return data


def get_credentials(account_label: str) -> dict:
    """Load token, atau langsung minta login kalau belum ada."""
    creds = load_credentials(account_label)
    if creds is None:
        return authenticate(account_label)
    return creds


# ---------------------------------------------------------------- upload

def upload_video(credentials: dict,
                 file_path: str,
                 caption: str = "",
                 privacy_level: str = "SELF_ONLY",
                 progress_callback=None) -> tuple[str, str]:
    """Upload video ke TikTok (Direct Post).

    Alur:
      a. /v2/post/publish/video/init/ -> dapat publish_id & upload_url
      b. Upload file dalam chunk ke upload_url (PUT, header Content-Range)
      c. Poll /v2/post/publish/status/fetch/ sampai PUBLISH_COMPLETE / FAILED

    Args:
        credentials: hasil authenticate()/load_credentials().
        file_path: path file video.
        caption: caption video (hashtag # dan mention @ otomatis dikenali).
        privacy_level: salah satu dari VALID_PRIVACY.
                       App belum diaudit -> hanya SELF_ONLY yang efektif.
        progress_callback: fungsi yang dipanggil dengan persen (0-100).

    Returns:
        (status_akhir, publish_id) — status: PUBLISH_COMPLETE / FAILED / dst.
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File video tidak ditemukan: {file_path}")
    if privacy_level not in VALID_PRIVACY:
        raise ValueError(f"privacy_level harus salah satu dari: {', '.join(VALID_PRIVACY)}")

    access_token = credentials["access_token"]

    # a. Inisialisasi sesi upload
    video_size = os.path.getsize(file_path)
    chunk_size = min(DEFAULT_CHUNK_SIZE, max(video_size, 1))
    total_chunks = math.ceil(video_size / chunk_size)

    init_body = {
        "post_info": {
            "title": caption,
            "privacy_level": privacy_level,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        },
    }
    init_resp = requests.post(INIT_URL, headers=_auth_headers(access_token),
                              json=init_body, timeout=30)
    data = _handle_api_response(init_resp)
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")
    if not publish_id or not upload_url:
        raise RuntimeError("Respon init TikTok tidak berisi publish_id/upload_url.")

    # b. Upload chunk satu per satu (harus berurutan)
    content_type = _video_mime(file_path)
    with open(file_path, "rb") as f:
        for i in range(total_chunks):
            chunk = f.read(chunk_size)
            start = i * chunk_size
            end = start + len(chunk) - 1
            put_resp = requests.put(upload_url, data=chunk, timeout=300, headers={
                "Content-Type": content_type,
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{video_size}",
            })
            if put_resp.status_code not in (200, 201, 204):
                raise RuntimeError(
                    f"Gagal upload chunk {i + 1}/{total_chunks} "
                    f"(HTTP {put_resp.status_code}): {put_resp.text[:300]}"
                )
            if progress_callback:
                progress_callback(int((i + 1) / total_chunks * 100))

    # c. Poll status sampai selesai
    status, fail_reason = _poll_status(access_token, publish_id)

    if status == "FAILED":
        raise RuntimeError(f"TikTok gagal memproses video: {fail_reason}")

    return status, publish_id


def _poll_status(access_token: str, publish_id: str) -> tuple[str, str | None]:
    """Poll status publish sampai PUBLISH_COMPLETE / FAILED / timeout.

    Returns (status, fail_reason).
    """
    deadline = time.time() + POLL_TIMEOUT_SEC
    while time.time() < deadline:
        resp = requests.post(STATUS_URL, headers=_auth_headers(access_token),
                             json={"publish_id": publish_id}, timeout=30)
        data = _handle_api_response(resp)
        status = data.get("status")
        if status in FINAL_STATUSES:
            return status, data.get("fail_reason")
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(
        "TikTok tidak selesai memproses video dalam batas waktu "
        f"({POLL_TIMEOUT_SEC} dtk). Publish ID: {publish_id}"
    )
