"""Notifikasi desktop — wrapper plyer dengan fallback aman.

Kalau tidak ada backend notifikasi di sistem (mis. tanpa notification daemon),
fungsi ini diam saja dan tidak membuat aplikasi crash.
"""


def notify(title: str, message: str) -> None:
    """Kirim notifikasi desktop. Gagal senyap (tidak pernah raise)."""
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name="Auto Upload TikTok + YouTube",
            timeout=5,
        )
    except Exception:
        pass  # tidak ada backend notifikasi -> abaikan
