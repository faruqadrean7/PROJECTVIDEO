# tokens/

Folder ini berisi token OAuth tersimpan per akun — **auto-generated oleh
aplikasi, jangan pernah di-commit ke git**.

Contoh isi:

- `youtube_main.json` — token akun YouTube berlabel `main`
- `tiktok_main.json` — token akun TikTok berlabel `main`

Token dibuat lewat alur login di aplikasi (`authenticate()` di
`youtube_api.py` / `tiktok_api.py`) dan di-refresh otomatis.
