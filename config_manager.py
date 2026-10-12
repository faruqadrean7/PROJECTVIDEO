"""Config manager: simpan & baca file JSON di folder `tokens/`.

Fase 0: kerangka save/load sederhana.
Fase 1+: dipakai untuk menyimpan token OAuth per akun
         (youtube_<label>.json, tiktok_<label>.json).
"""

import datetime
import json
from pathlib import Path

# Folder tempat semua token tersimpan (satu level di atas file ini)
TOKENS_DIR = Path(__file__).resolve().parent / "tokens"


def ensure_tokens_dir() -> None:
    """Pastikan folder tokens/ ada."""
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)


def token_path(filename: str) -> Path:
    """Path lengkap ke file di dalam folder tokens/.

    Contoh: token_path("youtube_main.json") -> .../tokens/youtube_main.json
    """
    return TOKENS_DIR / filename


def save_json(filename: str, data: dict) -> Path:
    """Simpan dict sebagai JSON ke tokens/<filename>.

    Returns path file yang ditulis.
    """
    ensure_tokens_dir()
    path = token_path(filename)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_json(filename: str) -> dict | None:
    """Baca dict dari tokens/<filename>.

    Returns None kalau file tidak ada atau JSON-nya rusak.
    """
    path = token_path(filename)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def delete_json(filename: str) -> bool:
    """Hapus tokens/<filename>. Returns True kalau file benar-benar dihapus."""
    path = token_path(filename)
    if path.exists():
        path.unlink()
        return True
    return False


def list_json() -> list[str]:
    """Daftar semua file .json di folder tokens/ (sorted)."""
    ensure_tokens_dir()
    return sorted(p.name for p in TOKENS_DIR.glob("*.json"))


def list_accounts() -> dict:
    """Scan folder tokens/ dan kelompokkan akun per platform.

    Returns: {"youtube": [label, ...], "tiktok": [label, ...]}
    (dari file youtube_<label>.json / tiktok_<label>.json)
    """
    accounts = {"youtube": [], "tiktok": []}
    for name in list_json():
        for platform in ("youtube", "tiktok"):
            prefix = f"{platform}_"
            if name.startswith(prefix) and name.endswith(".json"):
                label = name[len(prefix):-len(".json")]
                if label and label not in accounts[platform]:
                    accounts[platform].append(label)
    return accounts


# ---------------------------------------------------------------- riwayat upload

HISTORY_FILE = Path(__file__).resolve().parent / "history.json"


def load_history() -> list:
    """Baca riwayat upload dari history.json (list, terbaru di depan)."""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def add_history_record(record: dict) -> list:
    """Tambahkan 1 record riwayat upload (maks 200 entri). Returns history baru."""
    history = load_history()
    history.insert(0, record)
    history = history[:200]
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return history
