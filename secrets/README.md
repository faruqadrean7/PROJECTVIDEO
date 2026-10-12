# secrets/

Folder ini berisi kredensial aplikasi — **jangan pernah di-commit ke git**.

| File | Isi | Dari mana |
|---|---|---|
| `client_secret_google.json` | OAuth Client ID (tipe Desktop app) | Google Cloud Console |
| `tiktok_app_config.json` | Client Key & Client Secret | TikTok for Developers |

Format `tiktok_app_config.json`:

```json
{
  "client_key": "...",
  "client_secret": "..."
}
```

Letakkan file di sini sesuai langkah persiapan di `../README.md`.
