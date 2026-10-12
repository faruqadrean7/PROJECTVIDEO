"""YouTube Data API v3 — auth & upload.

Fase 1: implementasi lengkap.
- authenticate(): OAuth flow via browser (Desktop app), token disimpan per akun.
- load_credentials(): baca token tersimpan + auto-refresh kalau expired.
- upload_video(): videos.insert (resumable upload) + penanganan error umum.

Cara pakai ada di README.md & test_youtube.py.
"""

import json
import mimetypes
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config_manager

# Scope yang dibutuhkan aplikasi (hanya upload, bukan kelola channel)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# File client secret dari Google Cloud Console (OAuth Client ID, tipe Desktop app)
# Bisa di-override lewat env var GOOGLE_CLIENT_SECRET_FILE.
CLIENT_SECRET_FILE = Path(
    os.environ.get(
        "GOOGLE_CLIENT_SECRET_FILE",
        str(Path(__file__).resolve().parent / "secrets" / "client_secret_google.json"),
    )
)

# Ukuran chunk upload (8 MB) — cukup besar untuk cepat, cukup kecil untuk resume.
CHUNK_SIZE = 8 * 1024 * 1024

# Tipe callback progress: dipanggil dengan persen (int 0-100)
ProgressCallback = "Callable[[int], None]"


# ---------------------------------------------------------------- helpers

def token_filename(account_label: str) -> str:
    """Nama file token untuk satu akun, mis. youtube_main.json."""
    return f"youtube_{account_label}.json"


def _save_credentials(account_label: str, creds: Credentials) -> None:
    """Simpan credentials (termasuk refresh token) ke tokens/youtube_<label>.json."""
    config_manager.save_json(token_filename(account_label), json.loads(creds.to_json()))


def _friendly_error(exc: HttpError) -> str:
    """Terjemahkan HttpError Google API ke pesan yang jelas untuk user."""
    status = exc.resp.status
    reason = ""
    try:
        reason = exc.error_details[0].get("reason", "")
    except (IndexError, AttributeError, TypeError):
        pass

    if reason == "quotaExceeded":
        return ("Kuota YouTube API harian habis (10.000 unit/hari). "
                "Coba lagi besok, atau gunakan akun lain.")
    if reason == "uploadLimitExceeded":
        return "Channel YouTube ini sudah mencapai batas upload harian."
    if reason == "invalidVideoMetadata":
        return "Metadata video tidak valid (judul/deskripsi/kategori). Periksa input."
    if status == 400:
        return ("Format video tidak didukung YouTube atau metadata tidak valid "
                "(cek ekstensi & durasi video).")
    if status == 401:
        return "Token YouTube tidak valid — silakan login ulang akun ini."
    if status == 403:
        return ("Akses ditolak. Pastikan YouTube Data API v3 sudah diaktifkan "
                "di Google Cloud Console untuk project ini.")
    if status == 404:
        return "Resource YouTube tidak ditemukan (mungkin akun/channel bermasalah)."
    return f"Error YouTube API (HTTP {status}): {exc}"


# ---------------------------------------------------------------- auth

def authenticate(account_label: str) -> Credentials:
    """Buka browser untuk login Google, minta scope youtube.upload,
    simpan token ke tokens/youtube_<label>.json.

    Returns credentials siap pakai.
    """
    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"File client secret tidak ditemukan: {CLIENT_SECRET_FILE}\n"
            "1. Buka Google Cloud Console → buat OAuth Client ID tipe 'Desktop app'\n"
            "2. Aktifkan YouTube Data API v3\n"
            "3. Download file JSON-nya, taruh di secrets/client_secret_google.json"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    # port=0 → pakai port acak; prompt="consent" → selalu minta izin di browser
    creds = flow.run_local_server(port=0, prompt="consent")
    _save_credentials(account_label, creds)
    return creds


def load_credentials(account_label: str) -> Credentials | None:
    """Baca token tersimpan, auto-refresh kalau expired.

    Returns credentials siap pakai, atau None kalau akun belum pernah login.
    """
    data = config_manager.load_json(token_filename(account_label))
    if not data:
        return None

    creds = Credentials.from_authorized_user_info(data, SCOPES)

    # Refresh kalau token akses sudah kedaluwarsa (pakai refresh token)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise ConnectionError(
                f"Refresh token untuk akun '{account_label}' gagal/direvoke. "
                f"Silakan login ulang akun ini. ({exc})"
            ) from exc
        # Simpan ulang supaya token akses baru ikut tersimpan
        _save_credentials(account_label, creds)

    return creds


def get_credentials(account_label: str) -> Credentials:
    """Load token, atau langsung minta login kalau belum ada."""
    creds = load_credentials(account_label)
    if creds is None:
        return authenticate(account_label)
    return creds


# ---------------------------------------------------------------- upload

def upload_video(credentials: Credentials,
                 file_path: str,
                 title: str,
                 description: str = "",
                 tags: list[str] | None = None,
                 privacy_status: str = "private",
                 category_id: str = "22",
                 progress_callback=None) -> tuple[str, str]:
    """Upload video via videos.insert (resumable upload).

    Args:
        credentials: hasil authenticate()/load_credentials().
        file_path: path file video.
        title: judul video.
        description: deskripsi video.
        tags: list tag (opsional).
        privacy_status: 'public' | 'unlisted' | 'private' (default private).
        category_id: ID kategori YouTube (default 22 = People & Blogs).
        progress_callback: fungsi yang dipanggil dengan persen (0-100).

    Returns:
        (video_id, link) — contoh link: https://www.youtube.com/watch?v=...
    """
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File video tidak ditemukan: {file_path}")

    if privacy_status not in ("public", "unlisted", "private"):
        raise ValueError("privacy_status harus salah satu dari: public, unlisted, private")

    youtube = build("youtube", "v3", credentials=credentials)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Tebak MIME type dari ekstensi; fallback video/*
    mime_type = mimetypes.guess_type(file_path)[0] or "video/*"
    media = MediaFileUpload(file_path, mimetype=mime_type,
                            chunksize=CHUNK_SIZE, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    try:
        while response is None:
            # num_retries>0 → kalau koneksi putus di tengah, upload dilanjutkan
            # dari chunk terakhir (resumable), bukan mulai dari 0.
            status, response = request.next_chunk(num_retries=5)
            if status and progress_callback:
                progress_callback(int(status.progress() * 100))
    except HttpError as exc:
        raise RuntimeError(_friendly_error(exc)) from exc

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("Upload dilaporkan sukses tapi tidak ada video ID.")

    link = f"https://www.youtube.com/watch?v={video_id}"
    return video_id, link


def set_thumbnail(credentials: Credentials, video_id: str, thumbnail_path: str) -> None:
    """Pasang thumbnail custom untuk video (dipanggil setelah upload sukses)."""
    if not Path(thumbnail_path).exists():
        raise FileNotFoundError(f"File thumbnail tidak ditemukan: {thumbnail_path}")

    mime = mimetypes.guess_type(thumbnail_path)[0] or "image/jpeg"
    youtube = build("youtube", "v3", credentials=credentials)
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype=mime),
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"Gagal pasang thumbnail: {_friendly_error(exc)}") from exc
