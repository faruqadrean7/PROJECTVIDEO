# Rencana Aplikasi: Auto Upload TikTok + YouTube (Desktop)

## 1. Tujuan
Aplikasi desktop pribadi yang memungkinkan upload 1 video ke YouTube dan TikTok secara bersamaan (paralel), dengan judul, deskripsi, dan pengaturan yang bisa disesuaikan per platform.

## 2. Tech Stack
| Komponen | Pilihan | Alasan |
|---|---|---|
| Bahasa | Python 3.11+ | Library resmi Google tersedia, mudah dipakai untuk automation |
| UI | CustomTkinter | Ringan, modern, tidak perlu install browser engine seperti Electron |
| YouTube API | YouTube Data API v3 (google-api-python-client) | Resmi, gratis, stabil |
| TikTok API | TikTok Content Posting API (REST via `requests`) | Resmi dari TikTok for Developers |
| Auth storage | File JSON lokal terenkripsi (atau `keyring` OS) | Simpan token OAuth supaya tidak login ulang terus |
| Threading | `concurrent.futures` / `threading` | Upload ke 2 platform berjalan paralel, UI tidak freeze |

## 2b. Deployment
Diputuskan: **Local (jalan di komputer sendiri)** untuk v1. Aplikasi desktop dijalankan langsung dari PC, tidak butuh server/hosting. Login OAuth pakai `localhost` sebagai redirect URL. Arsitektur dibuat modular (logic upload terpisah dari UI) supaya nanti gampang dimigrasi ke web app/server kalau butuh fitur jadwal otomatis tanpa komputer nyala terus.

## 2c. Multi-Akun
- Token OAuth disimpan **per akun**, bukan cuma satu: `tokens/youtube_<label>.json`, `tokens/tiktok_<label>.json`.
- Refresh token membuat akun tetap "connected" tanpa perlu login ulang, sampai token direvoke/expired atau akun sengaja di-disconnect.
- UI punya pemilih akun (chip/checkbox) di atas form upload — user centang 1 atau lebih akun (lintas platform) sebagai tujuan upload untuk video yang sama.
- Tambah akun baru = klik "Hubungkan akun baru" → browser login → beri label akun → token tersimpan.
- Kuota YouTube API (10.000 unit/hari) berlaku **per akun**, jadi multi-akun justru mengurangi risiko limit.
- Audit TikTok App berlaku di level aplikasi, bukan per akun — jadi begitu app diaudit, semua akun TikTok yang terhubung ikut bisa publish publik.

## 3. Struktur Folder
```
upload-app/
├── app.py                  # Entry point, jendela utama UI
├── config_manager.py       # Simpan/baca kredensial & token lokal
├── youtube_api.py          # Fungsi auth + upload YouTube
├── tiktok_api.py           # Fungsi auth + upload TikTok
├── uploader.py             # Orkestrasi: jalankan 2 upload paralel + progress
├── secrets/
│   ├── client_secret_google.json   # Diunduh dari Google Cloud Console
│   └── tiktok_app_config.json      # Client key/secret dari TikTok Developer
├── tokens/                 # Token OAuth tersimpan (auto-generated, jangan di-share)
├── requirements.txt
└── README.md               # Cara setup & jalankan
```

## 4. Alur Kerja Aplikasi (User Flow)
1. **Login pertama kali**
   - Klik "Hubungkan YouTube" → buka browser → login Google → izinkan akses → token disimpan.
   - Klik "Hubungkan TikTok" → buka browser → login TikTok → izinkan akses → token disimpan.
   - Setelah itu, buka aplikasi berikutnya tidak perlu login ulang (token di-refresh otomatis).
2. **Upload video**
   - Pilih file video (drag & drop atau file browser).
   - Isi judul & deskripsi umum (bisa override khusus per platform kalau mau beda).
   - Pilih visibilitas: Publik / Unlisted / Privat (YouTube), Publik/Draft/Privat (TikTok — catatan di bagian 6).
   - Klik "Upload ke Keduanya".
3. **Proses upload**
   - Progress bar terpisah untuk YouTube dan TikTok, berjalan bersamaan.
   - Log status real-time (mis. "Uploading to YouTube... 45%", "TikTok: processing...").
4. **Selesai**
   - Tampilkan link video YouTube.
   - Tampilkan status TikTok (published/draft, sesuai izin akun/app).

## 5. Spesifikasi Fitur

### Fitur Wajib (v1)
- Autentikasi OAuth ke YouTube & TikTok, token tersimpan & auto-refresh.
- Upload 1 video ke 2 platform sekaligus (paralel, bukan berurutan).
- Input judul, deskripsi, tag/hashtag.
- Pilih thumbnail custom untuk YouTube.
- Progress bar & log per platform.
- Riwayat upload (tabel: nama file, tanggal, status YouTube, status TikTok, link).

### Fitur Tambahan (v2, opsional)
- Multi-akun (kalau punya lebih dari 1 channel/akun).
- Jadwalkan upload (queue + auto-run di jam tertentu).
- Template judul/deskripsi (mis. otomatis tambahkan hashtag tetap).
- Auto-crop/resize video kalau rasio tidak sesuai (perlu `ffmpeg`).
- Notifikasi desktop saat upload selesai.

## 6. Spesifikasi Teknis per Platform

### YouTube Data API v3
- Endpoint utama: `videos.insert` (resumable upload).
- Scope OAuth: `https://www.googleapis.com/auth/youtube.upload`
- Kuota harian default: 10.000 unit/hari (upload video ≈ 1.600 unit → cukup untuk ±6 upload/hari dengan akun default, bisa ajukan penambahan kuota kalau perlu lebih).
- Field yang bisa diatur: title, description, tags, categoryId, privacyStatus, thumbnail.

### TikTok Content Posting API
- Endpoint: `/v2/post/publish/video/init/` (mulai sesi upload) → upload chunk video → `/v2/post/publish/status/fetch/` (cek status).
- Scope OAuth: `video.publish`, `video.upload`
- **Batasan penting**: App yang belum lolos audit TikTok (unaudited) hanya bisa publish sebagai **draft/privat/self-only** — video tidak otomatis publik. Untuk publish langsung publik, perlu mengajukan **audit aplikasi** ke TikTok (proses review, bisa beberapa hari–minggu).
- Rate limit: ada batas jumlah post per hari per user (perlu dicek di dashboard developer TikTok karena bisa berubah).

## 7. Keamanan
- Jangan hardcode client secret di kode — simpan di file terpisah (folder `secrets/`), tambahkan ke `.gitignore` kalau nanti di-push ke GitHub.
- Token akses disimpan lokal saja, tidak dikirim ke server manapun selain API resmi Google/TikTok.
- Opsional: enkripsi file token pakai `cryptography` (Fernet) dengan password lokal.

## 8. Rencana Pengerjaan (Tahapan)
1. Setup project + dependency (`customtkinter`, `google-api-python-client`, `google-auth-oauthlib`, `requests`).
2. Implementasi auth YouTube (login + simpan token) → test upload manual.
3. Implementasi auth TikTok (login + simpan token) → test upload manual (draft mode).
4. Bangun UI utama (form input + tombol upload).
5. Gabungkan logic upload paralel (thread untuk YouTube, thread untuk TikTok).
6. Tambahkan progress bar, log, riwayat upload.
7. Testing end-to-end dengan video asli.
8. (Opsional) Ajukan audit TikTok App untuk publish publik otomatis.

## 9. Yang Perlu Kamu Siapkan Sebelum Coding Dimulai
- [ ] File `client_secret.json` dari Google Cloud Console (OAuth Client ID tipe "Desktop app").
- [ ] Client Key & Client Secret dari TikTok for Developers (app dengan scope `video.publish`).
- [ ] Video contoh untuk testing.
- [ ] Konfirmasi: apakah upload TikTok cukup sebagai draft dulu, atau langsung mau ajukan audit untuk publish publik?
