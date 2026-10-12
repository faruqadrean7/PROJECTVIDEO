"""Test script Fase 1: login YouTube sekali → upload 1 video → print link.

Cara pakai:
    python test_youtube.py video_contoh.mp4
    python test_youtube.py video_contoh.mp4 --title "Judul Test" --privacy unlisted

Hasil upload dicek di YouTube Studio (video privat/unlisted).
"""

import argparse
import sys
from pathlib import Path

import youtube_api


def _progress(pct: int) -> None:
    print(f"\rUploading... {pct}%", end="", flush=True)
    if pct == 100:
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Test upload video ke YouTube")
    parser.add_argument("video", help="Path file video (contoh: video_contoh.mp4)")
    parser.add_argument("--title", default="Test Upload Auto Upload App",
                        help="Judul video (default: 'Test Upload Auto Upload App')")
    parser.add_argument("--description", default="",
                        help="Deskripsi video (opsional)")
    parser.add_argument("--tags", nargs="*", default=[],
                        help="Tag video, pisahkan dengan spasi (opsional)")
    parser.add_argument("--privacy", choices=["public", "unlisted", "private"],
                        default="private",
                        help="Visibilitas (default: private)")
    parser.add_argument("--category", default="22",
                        help="ID kategori YouTube (default: 22 = People & Blogs)")
    parser.add_argument("--account", default="main",
                        help="Label akun untuk token (default: main)")
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"ERROR: file video tidak ditemukan: {args.video}", file=sys.stderr)
        sys.exit(1)

    # 1. Ambil credentials (login dulu kalau belum pernah)
    try:
        creds = youtube_api.get_credentials(args.account)
    except (FileNotFoundError, ConnectionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Mengupload '{args.video}' ke YouTube "
          f"(akun '{args.account}', visibilitas {args.privacy})...")

    # 2. Upload
    try:
        video_id, link = youtube_api.upload_video(
            creds,
            file_path=args.video,
            title=args.title,
            description=args.description,
            tags=args.tags,
            privacy_status=args.privacy,
            category_id=args.category,
            progress_callback=_progress,
        )
    except RuntimeError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # 3. Hasil
    print()
    print("=" * 50)
    print("UPLOAD BERHASIL")
    print(f"Video ID : {video_id}")
    print(f"Link     : {link}")
    print("=" * 50)
    print("Cek di YouTube Studio: https://studio.youtube.com")


if __name__ == "__main__":
    main()
