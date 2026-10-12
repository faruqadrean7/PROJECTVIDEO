# Panduan Menyiapkan Kredensial (Google + TikTok) — Sampai Bisa Upload Sungguhan

Panduan langkah demi langkah untuk menyiapkan semua kredensial yang dibutuhkan
aplikasi ini, dari nol sampai video benar-benar ter-upload ke YouTube & TikTok.

**Yang harus Anda siapkan di akhir panduan ini:**

| # | File | Isi | Dari mana |
|---|---|---|---|
| 1 | `secrets/client_secret_google.json` | OAuth Client ID (tipe **Desktop app**) | Google Cloud Console |
| 2 | `secrets/tiktok_app_config.json` | Client Key & Client Secret | TikTok for Developers |
| 3 | `video_contoh.mp4` (nama bebas) | Video untuk testing | File Anda sendiri |

Semua file kredensial ditaruh di folder `secrets/` yang sudah di-`.gitignore`
(jangan pernah di-commit ke git).

---

## Bagian A — Google Cloud Console (YouTube)

> Waktu: ±10–15 menit. Akun Google yang dipakai = akun YouTube tujuan upload.

### A1. Buat project (kalau belum punya)
1. Buka [Google Cloud Console](https://console.cloud.google.com/).
2. Klik dropdown **project** di kiri atas → **New Project**.
3. Beri nama (mis. `upload-app`) → **Create** → pastikan project baru terpilih.

### A2. Aktifkan YouTube Data API v3
1. Buka menu **APIs & Services → Library** (atau langsung
   [link YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com)).
2. Pastikan project yang benar terpilih → klik **Enable**.

### A3. Konfigurasi OAuth consent screen
> Wajib dilakukan **sebelum** membuat OAuth Client ID.

1. Buka **APIs & Services → OAuth consent screen**
   (atau [link langsung](https://console.cloud.google.com/apis/credentials/consent)).
2. **User type**: pilih **External** (kalau muncul pilihan Internal, pakai
   External — Internal hanya untuk Google Workspace).
3. Isi form:
   - **App name**: `Auto Upload TikTok + YouTube`
   - **User support email**: email Anda
   - **Developer contact email**: email Anda
4. **Save and Continue** sampai selesai (scope & test users di bawah).

**Penting — test users:** karena scope `youtube.upload` termasuk "sensitive",
app yang masih *testing* hanya bisa dipakai oleh akun yang terdaftar sebagai
**Test users**. Tambahkan email Google Anda sendiri:
- Tab **Audience** (atau **Test users**) → **Add users** → masukkan email Anda →
  **Save**.

> Kalau nanti muncul layar *"Google hasn't verified this app"* saat login —
> itu normal untuk app pribadi. Klik **Advanced → Go to [app name] (unsafe)**.
> Untuk menghilangkan layar itu sepenuhnya, ajukan verifikasi app — biasanya
> tidak perlu untuk pemakaian pribadi.

### A4. Buat OAuth Client ID (tipe Desktop app)
1. Buka **APIs & Services → Credentials**
   (atau [link langsung](https://console.cloud.google.com/apis/credentials)).
2. Klik **+ Create Credentials → OAuth client ID**.
3. **Application type**: pilih **Desktop app**.
4. **Name**: `upload-app-desktop` (bebas).
5. Klik **Create**.

### A5. Download & simpan file client secret
1. Di halaman Credentials, klik ikon **⬇ Download JSON** pada client yang baru
   dibuat.
2. Simpan file sebagai:

   ```
   secrets/client_secret_google.json
   ```

   (Nama file **harus persis** ini — aplikasi membacanya dari lokasi itu.)

### A6. Yang perlu diketahui
- **Kuota**: YouTube Data API memberi 10.000 unit/hari per project. Satu upload
  video ≈ 1.600 unit → ±6 upload/hari. Berlaku per **akun Google** yang login,
  jadi pakai beberapa akun = kuota lebih besar.
- **Token tersimpan** di `tokens/youtube_<label>.json` dan di-refresh otomatis —
  tidak perlu login ulang setiap buka app.

---

## Bagian B — TikTok for Developers

> Waktu: ±10–15 menit. Akun TikTok yang dipakai = akun tujuan upload.

### B1. Daftar developer
1. Buka [TikTok for Developers](https://developers.tiktok.com/) → **Sign up /
   Log in** pakai akun TikTok Anda.

### B2. Buat app + aktifkan produk
1. Klik **My Apps** (atau ikon profil → **Manage apps**) →
   **Create app** (kalau ada pilihan platform, pilih yang sesuai — mis.
   **Web / Desktop**; yang penting produknya bisa ditambah).
2. Isi nama app (mis. `upload-app`), deskripsi, dan logo (bebas).
3. Di halaman app, **tambahkan produk**:
   - **Login Kit** — wajib, dipakai untuk login OAuth.
   - **Content Posting API** — wajib, dipakai untuk upload video.
4. Pada **Login Kit**, pastikan **scope** berikut aktif/tercentang:
   - `video.publish`
   - `video.upload`

### B3. Daftarkan Redirect URI
> Ini langkah yang paling sering bikin error — ikuti aturannya.

1. Di bagian **Login Kit → Redirect URI**, klik **Add**.
2. Masukkan persis:

   ```
   http://localhost:8080/
   ```

   Aturan TikTok untuk desktop app (wajib dipatuhi):
   - Hanya host **`localhost`** atau **`127.0.0.1`** yang diizinkan.
   - **Wajib ada port** (di sini `8080`).
   - URI harus **statis** — tidak boleh ada parameter (`?`) atau fragment (`#`).
   - Maksimal 10 URI. Kalau port bisa berubah, TikTok juga menerima wildcard
     port, mis. `http://127.0.0.1:*/` — tapi default aplikasi ini `8080`.

> Kalau port 8080 sedang dipakai program lain, Anda bisa ganti port lewat env:
> ```
> TIKTOK_REDIRECT_URI=http://localhost:9090/ python app.py
> ```
> **Dan daftarkan juga** `http://localhost:9090/` di Redirect URI TikTok.

### B4. Ambil Client Key & Client Secret
1. Di halaman app TikTok, buka tab **Security** (atau **Manage** → **Client
   Key/Secret**).
2. Salin **Client Key** dan **Client Secret**.
3. Buat file `secrets/tiktok_app_config.json`:

   ```json
   {
     "client_key": "PASTE_CLIENT_KEY_DI_SINI",
     "client_secret": "PASTE_CLIENT_SECRET_DI_SINI"
   }
   ```

> Alternatif: pakai environment variable (nilai env menang atas file):
> ```
> TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=... python test_tiktok.py video.mp4
> ```

### B5. Yang perlu diketahui
- **Audit app**: app yang **belum lolos audit** TikTok hanya bisa publish video
  sebagai **privat/self-only** — bukan error, itu batasan TikTok. Untuk publish
  publik otomatis, ajukan **audit** lewat dashboard developer (proses review
  bisa beberapa hari–minggu). Audit berlaku di level **app**, jadi begitu
  lolos, semua akun yang terhubung bisa publish publik.
- **PKCE**: untuk desktop app, TikTok mewajibkan PKCE — sudah ditangani
  otomatis oleh kode aplikasi (tidak perlu konfigurasi tambahan).
- **Token** tersimpan di `tokens/tiktok_<label>.json`, di-refresh otomatis.

---

## Bagian C — Test Upload Sungguhan

### C1. Siapkan video contoh
Gunakan video `.mp4` (paling aman), durasi singkat (30 detik–2 menit), ukuran
kecil (di bawah 500 MB) untuk test pertama. Taruh di folder project, mis.
`video_contoh.mp4`.

### C2. Aktifkan environment & cek config
```bash
source venv/bin/activate
ls secrets/           # harus ada client_secret_google.json & tiktok_app_config.json
```

### C3. Test YouTube (via CLI)
```bash
python test_youtube.py video_contoh.mp4 --privacy unlisted
```
- Browser terbuka → login Google → izinkan akses (lewati layar "unverified").
- Tunggu upload selesai → link video di-print.
- Cek hasil di [YouTube Studio](https://studio.youtube.com).

### C4. Test TikTok (via CLI)
```bash
python test_tiktok.py video_contoh.mp4 --caption "Test upload #fyp"
```
- Browser terbuka → login TikTok → izinkan akses.
- Status akhir di-print (`PUBLISH_COMPLETE`). Karena app belum diaudit, video
  masuk **privat/self-only** — cek di aplikasi TikTok (menu postingan).
- Catatan: kalau error `unaudited_client_can_only_post_to_private_accounts`,
  itu normal — pakai `--privacy SELF_ONLY`.

### C5. Upload lewat aplikasi (UI)
```bash
python app.py
```
1. Klik **＋ Hubungkan akun baru** → pilih platform → label (mis. `main`) →
   browser login. Ulangi untuk platform satunya.
2. Seret video ke drop area → isi judul/deskripsi/hashtag → pilih akun →
   klik **Upload ke Keduanya**.
3. Progress bar & log berjalan paralel; link YouTube muncul di log; riwayat
   tersimpan di `history.json` (klik ▶ Riwayat Upload).

---

## Bagian D — Troubleshooting

| Masalah | Penyebab & Solusi |
|---|---|
| `redirect_uri_mismatch` (Google) | Client secret salah project, atau file bukan tipe Desktop app. Ulangi A4–A5. |
| Layar "Google hasn't verified this app" | Normal untuk app pribadi. Klik **Advanced → Go to … (unsafe)**. Pastikan email Anda terdaftar di **Test users** (A3). |
| `Error 10006 / redirect URI` (TikTok) | URI di kode tidak sama persis dengan yang didaftarkan. Cek B3: harus `http://localhost:8080/` dengan port, tanpa parameter. |
| Login TikTok gagal / `code_challenge` error | Pastikan app memakai **Login Kit** dengan PKCE (kode sudah otomatis) dan scope `video.publish, video.upload` aktif. |
| `unaudited_client_can_only_post_to_private_accounts` | App belum diaudit → hanya bisa privat. Bukan error; gunakan `SELF_ONLY` (default). |
| `quotaExceeded` (YouTube) | Kuota 10.000 unit/hari habis. Tunggu besok atau login akun lain. |
| `access_token_invalid` / disuruh login ulang | Token expired/direvoke. Klik tombol **Login ulang** di app, atau hapus file token di `tokens/` lalu login lagi. |
| Port 8080 sibuk | Ganti port via env `TIKTOK_REDIRECT_URI` **dan** daftarkan URI baru di portal TikTok (B3). |
| `ImportError: libtk8.6.so` / `No module named 'tkinter'` | Library Tk belum terpasang: Arch `sudo pacman -S tk`, Debian/Ubuntu `sudo apt install python3-tk`. |
| Upload gagal di tengah (koneksi putus) | YouTube: resumable (lanjut dari chunk terakhir). TikTok: coba lagi via tombol **Coba lagi yang gagal** di app. |

---

## Checklist Akhir

- [ ] `secrets/client_secret_google.json` ada & valid (A5)
- [ ] `secrets/tiktok_app_config.json` ada & valid (B4)
- [ ] Redirect URI `http://localhost:8080/` terdaftar di TikTok (B3)
- [ ] `video_contoh.mp4` siap (C1)
- [ ] `python test_youtube.py video_contoh.mp4 --privacy unlisted` → video muncul di YouTube
- [ ] `python test_tiktok.py video_contoh.mp4` → status `PUBLISH_COMPLETE` (privat)
- [ ] `python app.py` → upload dari UI berjalan paralel

Setelah semua hijau, aplikasi siap dipakai harian. 🎉
