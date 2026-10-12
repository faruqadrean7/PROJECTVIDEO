"""Orkestrasi upload paralel YouTube + TikTok.

Fase 4: implementasi lengkap.
- upload_to_both(): jalankan upload YouTube & TikTok di thread terpisah
  secara paralel (ThreadPoolExecutor), UI tidak freeze.
- Per platform bisa upload ke lebih dari 1 akun (berurutan dalam thread-nya).
- Progress & log dikirim via callback agar UI bisa update secara live.
"""

from concurrent.futures import ThreadPoolExecutor

import tiktok_api
import youtube_api

# Callback yang dipakai UI:
#   progress_callback(platform, account_label, pct)   # pct 0-100
#   log_callback(platform, message)


def _upload_youtube(params: dict, progress_cb, log_cb) -> list[dict]:
    """Upload ke semua akun YouTube terpilih (berurutan). Returns list result."""
    results = []
    for account in params["accounts"]:
        try:
            creds = youtube_api.get_credentials(account)
            log_cb("youtube", f"[{account}] mulai upload…")
            video_id, link = youtube_api.upload_video(
                creds,
                file_path=params["video_path"],
                title=params["title"],
                description=params.get("description", ""),
                tags=params.get("tags") or [],
                privacy_status=params.get("privacy_status", "private"),
                category_id=params.get("category_id", "22"),
                progress_callback=lambda pct, a=account: progress_cb("youtube", a, pct),
            )
            if params.get("thumbnail"):
                try:
                    youtube_api.set_thumbnail(creds, video_id, params["thumbnail"])
                    log_cb("youtube", f"[{account}] thumbnail terpasang")
                except Exception as exc:
                    log_cb("youtube", f"[{account}] thumbnail gagal dipasang: {exc}")
            results.append({"account": account, "status": "ok",
                            "video_id": video_id, "link": link,
                            "message": "berhasil"})
            log_cb("youtube", f"[{account}] selesai: {link}")
        except Exception as exc:
            results.append({"account": account, "status": "error",
                            "video_id": None, "link": None,
                            "message": str(exc)})
            log_cb("youtube", f"[{account}] GAGAL: {exc}")
    return results


def _upload_tiktok(params: dict, progress_cb, log_cb) -> list[dict]:
    """Upload ke semua akun TikTok terpilih (berurutan). Returns list result."""
    results = []
    for account in params["accounts"]:
        try:
            creds = tiktok_api.get_credentials(account)
            log_cb("tiktok", f"[{account}] mulai upload…")
            status, publish_id = tiktok_api.upload_video(
                creds,
                file_path=params["video_path"],
                caption=params.get("caption", ""),
                privacy_level=params.get("privacy_level", "SELF_ONLY"),
                progress_callback=lambda pct, a=account: progress_cb("tiktok", a, pct),
            )
            results.append({"account": account, "status": "ok",
                            "publish_id": publish_id, "link": None,
                            "message": f"status: {status}"})
            log_cb("tiktok", f"[{account}] selesai (status {status}). "
                             "Cek di app TikTok — privat kalau app belum diaudit.")
        except Exception as exc:
            results.append({"account": account, "status": "error",
                            "publish_id": None, "link": None,
                            "message": str(exc)})
            log_cb("tiktok", f"[{account}] GAGAL: {exc}")
    return results


def upload_to_both(video_path: str,
                   youtube_params: dict,
                   tiktok_params: dict,
                   progress_callback=None,
                   log_callback=None) -> dict:
    """Jalankan upload YouTube & TikTok di thread terpisah secara paralel.

    Args:
        video_path: path file video.
        youtube_params: {
            "accounts": [label, ...], "title": str, "description": str,
            "tags": list, "privacy_status": str, "category_id": str,
            "thumbnail": str | None,
        }
        tiktok_params: {
            "accounts": [label, ...], "caption": str, "privacy_level": str,
        }
        progress_callback(platform, account, pct): update progress live.
        log_callback(platform, message): pesan log real-time.

    Returns:
        {"youtube": [result...], "tiktok": [result...]}
        result = {"account", "status": "ok"|"error", "link"/"publish_id"/"video_id", "message"}
    """
    def _noop(*_args, **_kwargs):
        pass

    progress_cb = progress_callback or _noop
    log_cb = log_callback or _noop

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_yt = pool.submit(_upload_youtube, youtube_params, progress_cb, log_cb)
        fut_tt = pool.submit(_upload_tiktok, tiktok_params, progress_cb, log_cb)
        yt_results = fut_yt.result()
        tt_results = fut_tt.result()

    return {"youtube": yt_results, "tiktok": tt_results}
