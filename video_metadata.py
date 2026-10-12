"""Baca metadata video: ukuran file & durasi/resolusi (via ffprobe).

ffprobe dibundel dengan ffmpeg. Kalau tidak tersedia, ukuran file tetap
terbaca, durasi jadi None (UI menampilkan "—").
"""

import json
import os
import shutil
import subprocess


def get_video_info(path: str) -> dict:
    """Baca metadata video.

    Returns dict: path, size_bytes, duration_sec, width, height, has_ffprobe.
    """
    info = {
        "path": path,
        "size_bytes": os.path.getsize(path),
        "duration_sec": None,
        "width": None,
        "height": None,
        "has_ffprobe": False,
    }

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return info

    info["has_ffprobe"] = True
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error",
             "-show_entries", "format=duration:stream=width,height,codec_type",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        if "duration" in fmt:
            info["duration_sec"] = float(fmt["duration"])
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and stream.get("width"):
                info["width"] = stream["width"]
                info["height"] = stream["height"]
                break
    except (json.JSONDecodeError, subprocess.SubprocessError, OSError, ValueError):
        pass  # gagal baca metadata -> biarkan None

    return info


def format_size(size_bytes: int) -> str:
    """Format ukuran byte jadi MB/GB yang mudah dibaca."""
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"


def format_duration(duration_sec: float | None) -> str:
    """Format durasi detik jadi mm:ss atau h:mm:ss."""
    if duration_sec is None:
        return "—"
    total = int(duration_sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
