"""Test script Fase 2: login TikTok sekali → upload 1 video → print status akhir.

Cara pakai:
    python test_tiktok.py video_contoh.mp4
    python test_tiktok.py video_contoh.mp4 --caption "Caption test #fyp"

Catatan: kalau app TikTok belum lolos audit, video otomatis masuk sebagai
privat/self-only (SELF_ONLY) — itu bukan error, itu batasan TikTok.
"""

import argparse
import sys
from pathlib import Path

import tiktok_api


def _progress(pct: int) -> None:
    print(f"\rUploading... {pct}%", end="", flush=True)
    if pct == 100:
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test upload video ke TikTok")
    parser.add_argument("video", help="Path file video (contoh: video_contoh.mp4)")
    parser.add_argument("--caption", default="",
                        help="Caption video (opsional, hashtag # & mention @ dikenali)")
    parser.add_argument(
        "--privacy", choices=tiktok_api.VALID_PRIVACY, default="SELF_ONLY",
        help="Visibilitas. Untuk app belum diaudit hanya SELF_ONLY yang efektif "
             "(default: SELF_ONLY).",
    )
    parser.add_argument("--account", default="main",
                        help="Label akun untuk token (default: main)")
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"ERROR: file video tidak ditemukan: {args.video}", file=sys.stderr)
        sys.exit(1)

    # 1. Ambil credentials (login dulu kalau belum pernah)
    try:
        creds = tiktok_api.get_credentials(args.account)
    except (FileNotFoundError, ValueError, ConnectionError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Mengupload '{args.video}' ke TikTok "
          f"(akun '{args.account}', privacy {args.privacy})...")

    # 2. Upload
    try:
        status, publish_id = tiktok_api.upload_video(
            creds,
            file_path=args.video,
            caption=args.caption,
            privacy_level=args.privacy,
            progress_callback=_progress,
        )
    except (RuntimeError, TimeoutError, ConnectionError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # 3. Hasil
    print()
    print("=" * 50)
    print("UPLOAD BERHASIL")
    print(f"Status     : {status}")
    print(f"Publish ID : {publish_id}")
    print("=" * 50)
    print("Cek di aplikasi TikTok (menu postingan/draft).")

    if args.privacy == "SELF_ONLY":
        print()
        print("NOTE: video dipublish privat (SELF_ONLY). Ini normal kalau app")
        print("belum lolos audit TikTok. Untuk publish publik otomatis, ajukan")
        print("audit app di TikTok for Developers.")


if __name__ == "__main__":
    main()
