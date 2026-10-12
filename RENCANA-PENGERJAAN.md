# Rencana Pengerjaan Bertahap

Total 6 fase, dikerjakan berurutan. Tiap fase punya deliverable yang bisa langsung ditest sebelum lanjut ke fase berikutnya — jadi kalau ada masalah, ketahuan lebih awal.

---

## Fase 0 — Setup Fondasi Project
**Tujuan**: Kerangka project siap, semua dependency terpasang, struktur folder final.

**Langkah**:
1. Buat struktur folder sesuai spesifikasi (`app.py`, `config_manager.py`, `youtube_api.py`, `tiktok_api.py`, `uploader.py`, `secrets/`, `tokens/`).
2. Setup virtual environment Python (`venv`) supaya dependency tidak bentrok dengan Python sistem.
3. Install dependency inti: `customtkinter`, `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `requests`, `python-dotenv`.
4. Buat `requirements.txt` dari dependency yang terpasang.
5. Buat `config_manager.py` dasar: fungsi untuk baca/tulis file JSON di folder `tokens/` (belum ada logic auth, baru kerangka save/load).
6. Buat `.gitignore` (kalau nanti mau versioning): exclude `tokens/`, `secrets/`, `venv/`.
7. Buat `README.md` awal: cara install & jalankan (`pip install -r requirements.txt`, `python app.py`).

**Deliverable**: `python app.py` bisa dijalankan (boleh masih kosong/placeholder window), tidak ada error import.

**Cara test**: Jalankan `python app.py`, pastikan tidak crash, semua library ke-import tanpa error.

---

## Fase 1 — Autentikasi & Upload YouTube (Single Account)
**Tujuan**: Bisa login 1 akun YouTube dan upload 1 video via script/CLI dulu (belum lewat UI).

**Langkah**:
1. Setup OAuth Client ID di Google Cloud Console (tipe **Desktop app**), download `client_secret_google.json`, taruh di `secrets/`.
2. Aktifkan **YouTube Data API v3** di project Google Cloud tersebut.
3. Tulis `youtube_api.py`:
   - Fungsi `authenticate(account_label)`: buka browser untuk login, minta scope `youtube.upload`, simpan token ke `tokens/youtube_<label>.json`.
   - Fungsi `load_credentials(account_label)`: baca token tersimpan, auto-refresh kalau expired, return objek credentials siap pakai.
   - Fungsi `upload_video(credentials, file_path, title, description, tags, privacy_status, category_id)`: pakai `videos.insert` (resumable upload), return video ID & link.
4. Tulis script test sederhana (`test_youtube.py`) yang: login sekali → upload 1 video contoh → print link hasil upload.
5. Handle error umum: token expired, kuota habis, format video tidak didukung, koneksi terputus saat upload (idealnya bisa resume, bukan mulai dari 0).

**Deliverable**: Video test berhasil muncul di akun YouTube kamu (privat/unlisted), dengan judul & deskripsi sesuai input.

**Cara test**: Jalankan `test_youtube.py`, cek video benar-benar muncul di YouTube Studio.

---

## Fase 2 — Autentikasi & Upload TikTok (Single Account)
**Tujuan**: Bisa login 1 akun TikTok dan upload 1 video via script/CLI dulu.

**Langkah**:
1. Pastikan app di TikTok for Developers sudah punya scope `video.publish` dan `video.upload`.
2. Tulis `tiktok_api.py`:
   - Fungsi `authenticate(account_label)`: jalankan OAuth2 authorization code flow (buka browser → user login → redirect ke `localhost` dengan code → tukar code jadi access token + refresh token) → simpan ke `tokens/tiktok_<label>.json`.
   - Fungsi `load_credentials(account_label)`: baca token, auto-refresh access token pakai refresh token kalau sudah expired.
   - Fungsi `upload_video(credentials, file_path, caption, privacy_level)`:
     a. Panggil `/v2/post/publish/video/init/` untuk mulai sesi, dapat `upload_url` & `publish_id`.
     b. Upload file video dalam chunk ke `upload_url` (sesuai spek TikTok, ada batas ukuran per chunk).
     c. Poll `/v2/post/publish/status/fetch/` sampai status jadi `PUBLISH_COMPLETE` atau gagal.
3. Tulis script test (`test_tiktok.py`): login sekali → upload 1 video contoh → print status akhir.
4. Handle catatan penting: kalau app belum diaudit, video otomatis masuk sebagai **draft/self-only** — pastikan ini ditampilkan jelas ke user di hasil test, bukan dianggap error.

**Deliverable**: Video test berhasil muncul di TikTok (draft atau publik, tergantung status audit app), dengan caption sesuai input.

**Cara test**: Jalankan `test_tiktok.py`, cek video muncul di aplikasi TikTok (menu draft/postingan).

---

## Fase 3 — Bangun UI Utama (dengan Data Dummy)
**Tujuan**: Tampilan aplikasi jadi, semua field & interaksi berfungsi secara visual (logic upload asli belum disambung).

**Langkah**:
1. Buat jendela utama `app.py` pakai `customtkinter`: layout sesuai mockup yang sudah disepakati (drop area video, field judul/deskripsi/hashtag, toggle "sama untuk kedua platform", section pengaturan YouTube & TikTok yang bisa expand/collapse, tombol upload).
2. Implementasi drag & drop file video + tombol "browse file" (pakai `tkinterdnd2` atau file dialog biasa).
3. Implementasi preview: nama file, durasi, ukuran video (pakai `moviepy` atau `ffprobe` untuk baca metadata).
4. Implementasi toggle "sama untuk kedua platform" — kalau dimatikan, muncul field caption terpisah untuk YouTube & TikTok.
5. Implementasi input hashtag sebagai chip yang bisa ditambah/dihapus.
6. Implementasi bagian pemilih akun (chip/checkbox akun yang terhubung) — untuk sekarang data akun masih dummy/hardcoded.
7. Tombol "Upload ke Keduanya" untuk sekarang cukup print/log data form ke console (belum upload asli).

**Deliverable**: Aplikasi bisa dibuka, semua field bisa diisi, terlihat rapi sesuai mockup, data form bisa dicetak ke console saat tombol upload ditekan.

**Cara test**: Buka app, isi semua field, drag video, klik upload, cek console menampilkan data yang benar.

---

## Fase 4 — Integrasi: Sambungkan UI ke Logic Upload
**Tujuan**: Semua yang di UI benar-benar memanggil `youtube_api.py` dan `tiktok_api.py`, upload berjalan paralel.

**Langkah**:
1. Tulis `uploader.py`: fungsi `upload_to_both(video_path, youtube_params, tiktok_params, selected_accounts)` yang menjalankan upload YouTube & TikTok di **thread terpisah** secara bersamaan (pakai `threading` atau `concurrent.futures.ThreadPoolExecutor`).
2. Sambungkan tombol "Hubungkan akun baru" di UI ke fungsi `authenticate()` — setelah sukses, akun baru langsung muncul di daftar pemilih akun (bukan dummy lagi).
3. Sambungkan pemilih akun ke token yang benar-benar tersimpan di `tokens/`.
4. Tambahkan progress bar & label status per platform, di-update secara live selama thread upload berjalan (pakai callback/queue supaya UI thread tidak nge-freeze).
5. Tambahkan log area kecil di bawah form untuk menampilkan pesan real-time (mis. "YouTube: uploading 45%", "TikTok: memproses video...").
6. Setelah selesai, tampilkan hasil: link YouTube (klik untuk buka), status TikTok (published/draft).
7. Tambahkan riwayat upload sederhana: simpan ke file JSON lokal (`history.json`), tampilkan sebagai tabel di aplikasi (nama file, tanggal, status YouTube, status TikTok, link).

**Deliverable**: Aplikasi bisa upload video asli ke YouTube & TikTok secara bersamaan dari 1 form, dengan progress & hasil yang terlihat jelas.

**Cara test**: Upload video sungguhan lewat UI, pastikan muncul di kedua platform, cek riwayat tercatat dengan benar.

---

## Fase 5 — Penanganan Error & Polish
**Tujuan**: Aplikasi tahan terhadap kondisi gagal, dan terasa nyaman dipakai sehari-hari.

**Langkah**:
1. Validasi input sebelum upload: video belum dipilih, judul kosong, tidak ada akun terpilih → tampilkan pesan error jelas, jangan biarkan tombol upload diklik tanpa validasi.
2. Handle kegagalan jaringan saat upload: tampilkan pesan error spesifik + tombol "Coba lagi" per platform (tidak perlu ulang dari awal kalau salah satu platform saja yang gagal).
3. Handle token expired/revoked: deteksi otomatis, munculkan prompt "Akun X perlu login ulang" dengan tombol langsung ke proses re-auth.
4. Tambahkan konfirmasi sebelum upload kalau video berukuran besar (mis. > 500MB) atau durasi tidak sesuai batas platform (TikTok ada batas durasi tertentu).
5. Tambahkan notifikasi desktop saat upload selesai (pakai `plyer` atau `win10toast` tergantung OS).
6. Rapikan pesan-pesan UI (bahasa konsisten, tidak ada teks placeholder yang lolos).
7. Testing menyeluruh dengan beberapa skenario: 1 akun, multi-akun, video besar, video gagal ditengah jalan, koneksi internet diputus paksa saat upload.

**Deliverable**: Aplikasi stabil dipakai harian, error tidak membuat aplikasi crash, selalu ada pesan yang jelas ke user.

**Cara test**: Jalankan semua skenario di langkah 7 satu per satu, pastikan aplikasi merespons dengan baik di tiap kasus.

---

## Fase 6 — Opsional / Pengembangan Lanjutan
Dikerjakan setelah v1 stabil dan benar-benar dipakai, sesuai kebutuhan:

- **Audit TikTok App**: ajukan review ke TikTok for Developers supaya video bisa langsung publik (bukan draft). Proses ini di luar coding, submission lewat dashboard TikTok.
- **Jadwal upload otomatis**: tambahkan queue + scheduler lokal (video diupload otomatis di jam tertentu tanpa perlu buka app manual).
- **Migrasi ke server/online**: kalau butuh upload tanpa komputer nyala terus — ubah dari desktop app ke web app + background worker di VPS.
- **Auto-resize/crop video**: integrasi `ffmpeg` untuk otomatis menyesuaikan rasio video per platform.
- **Enkripsi token**: tambahkan password lokal untuk enkripsi file di folder `tokens/`, supaya lebih aman kalau komputer dipakai orang lain.

---

## Ringkasan Urutan
| Fase | Fokus | Bisa ditest sendiri? |
|---|---|---|
| 0 | Setup project | Ya — aplikasi jalan tanpa error |
| 1 | Auth + upload YouTube | Ya — video muncul di YouTube |
| 2 | Auth + upload TikTok | Ya — video muncul di TikTok |
| 3 | UI lengkap (dummy) | Ya — semua field berfungsi visual |
| 4 | Integrasi UI + logic asli | Ya — upload asli ke 2 platform sekaligus |
| 5 | Error handling & polish | Ya — aplikasi stabil dipakai harian |
| 6 | Fitur lanjutan (opsional) | Sesuai kebutuhan |
