# Auto Upload TikTok + YouTube

Aplikasi desktop pribadi untuk upload 1 video ke **YouTube dan TikTok secara
paralel** (bersamaan), dengan judul, deskripsi, dan pengaturan yang bisa
disesuaikan per platform.

> Status: **Fase 5 (kode selesai)** — aplikasi v1 lengkap: auth & upload YouTube/TikTok via CLI + UI terintegrasi (upload paralel, progress, riwayat, validasi, retry, notifikasi).
> Lihat `RENCANA-PENGERJAAN.md` untuk roadmap lengkap.

## Struktur Project

```
├── app.py                  # Entry point, jendela utama UI
├── config_manager.py       # Simpan/baca kredensial & token lokal (JSON)
├── youtube_api.py          # Auth + upload YouTube (Fase 1)
├── tiktok_api.py           # Auth + upload TikTok (Fase 2)
├── uploader.py             # Orkestrasi upload paralel (Fase 4)
├── secrets/                # Client secret & app config (jangan di-commit)
├── tokens/                 # Token OAuth tersimpan (auto-generated)
├── requirements.txt
└── README.md
```

## Persiapan Awal

Python **3.11+** diperlukan.

```bash
# 1. Buat virtual environment
python3 -m venv venv

# 2. Aktifkan venv
#    Linux/macOS:
source venv/bin/activate
#    Windows:
venv\Scripts\activate

# 3. Install dependency
pip install -r requirements.txt
```

> **Catatan Linux:** CustomTkinter butuh Tk. Kalau muncul error
> `ImportError: libtk8.6.so` / `ModuleNotFoundError: No module named 'tkinter'`,
> install paket sistemnya (mis. `sudo pacman -S tk` di Arch,
> `sudo apt install python3-tk` di Debian/Ubuntu).

## Menjalankan Aplikasi

```bash
python app.py
```

## Menggunakan Aplikasi (Fase 4)

```bash
python app.py
```

Fitur yang sudah aktif:

- **Drop area** video (drag & drop atau tombol browse) + preview nama/ukuran/durasi
  (durasi & resolusi dibaca via `ffprobe`/ffmpeg).
- **Pemilih akun otomatis** — akun dibaca dari folder `tokens/` (yang benar-benar
  sudah login). Tombol **"＋ Hubungkan akun baru"** → pilih platform & label →
  browser login → akun langsung muncul di daftar.
- **Toggle "Sama untuk kedua platform"** — kalau dimatikan, muncul field
  override judul/deskripsi YouTube & caption TikTok.
- **Hashtag chip** — ketik tag lalu Enter/+, hapus dengan klik ✕.
- Section **YouTube** (visibilitas, kategori, thumbnail) & **TikTok** (privasi)
  yang bisa expand/collapse.
- **Upload paralel** — YouTube & TikTok jalan bersamaan di thread terpisah
  (`uploader.upload_to_both`), progress bar & log real-time per platform,
  UI tidak freeze. Mendukung beberapa akun per platform.
- **Hasil** — link YouTube tampil di log (klik "Buka" di riwayat), status
  TikTok (published/draft/privat).
- **Riwayat upload** — tersimpan di `history.json`, tampil sebagai daftar
  (nama file, tanggal, status per platform, tombol Buka).

## Penanganan Error & Polish (Fase 5)

- **Validasi input** sebelum upload: video belum dipilih, file tidak ada,
  judul kosong, tidak ada akun tercentang → dialog peringatan jelas.
- **Konfirmasi** kalau video besar (> 500 MB) atau durasi > 10 menit
  (batas umum TikTok) — user bisa batalkan.
- **Tombol "Coba lagi yang gagal"** — retry hanya akun/platform yang gagal,
  tanpa mengulang yang sudah berhasil.
- **Deteksi token expired/revoked** — pesan error diklasifikasi otomatis →
  dialog "Akun perlu login ulang" + tombol "Login ulang" langsung ke re-auth.
- **Notifikasi desktop** saat selesai (toggle 🔔, default nyala) — pakai
  `plyer`; kalau sistem tidak punya notification daemon, dilewati dengan aman.
- **Error tidak bikin crash** — semua kegagalan tertangkap, pesan bahasa
  Indonesia konsisten, detail lengkap di log.

> **Catatan integrasi API:** kode pemanggilan API asli sudah terpasang penuh
> (auth, upload, refresh token). Test upload sungguhan tinggal dijalankan
> begitu kredensial (`secrets/`) dan video contoh disiapkan.

## Menguji Upload YouTube (Fase 1)

Persiapan sekali saja:

1. Buka [Google Cloud Console](https://console.cloud.google.com/) → buat project
   (atau pakai yang ada) → aktifkan **YouTube Data API v3**.
2. Buat **OAuth Client ID** tipe **Desktop app**, download file JSON-nya, simpan
   sebagai `secrets/client_secret_google.json`.
3. Siapkan 1 file video contoh.

Jalankan test (upload default **private** supaya aman):

```bash
# Login browser akan terbuka otomatis saat pertama kali
python test_youtube.py video_contoh.mp4

# Opsi lengkap
python test_youtube.py video_contoh.mp4 --title "Judul Test" \
    --description "Deskripsi test" --tags test upload \
    --privacy unlisted --account main
```

Setelah sukses, link video di-print dan video bisa dicek di
[YouTube Studio](https://studio.youtube.com).

Catatan error yang sudah ditangani: token expired (auto-refresh, kalau gagal
suruh login ulang), kuota harian habis, format video tidak didukung, dan
koneksi putus di tengah upload (dilanjutkan dari chunk terakhir, bukan dari 0).

## Menguji Upload TikTok (Fase 2)

Persiapan sekali saja: buat app TikTok dengan scope `video.publish` &
`video.upload`, isi `secrets/tiktok_app_config.json` (lihat bagian atas), dan
daftarkan redirect URI `http://localhost:8080/`.

```bash
# Login browser terbuka otomatis saat pertama kali
python test_tiktok.py video_contoh.mp4

# Opsi lengkap
python test_tiktok.py video_contoh.mp4 --caption "Caption test #fyp" \
    --privacy SELF_ONLY --account main
```

**Penting:** kalau app belum lolos audit TikTok, video otomatis dipublish
**privat (SELF_ONLY)** — ini bukan error. Untuk publish publik otomatis,
ajukan audit app di TikTok for Developers.

## Menyiapkan Kredensial

📖 **Baca `PANDUAN-KREDENSIAL.md`** — panduan langkah demi langkah dari nol
(Google Cloud Console + TikTok for Developers) sampai bisa upload sungguhan,
termasuk troubleshooting.

Ringkasnya, siapkan 2 file di folder `secrets/`:

1. `secrets/client_secret_google.json` — OAuth Client ID tipe **Desktop app**
   dari Google Cloud Console (aktifkan **YouTube Data API v3** dulu).
2. `secrets/tiktok_app_config.json` — dari TikTok for Developers (scope
   `video.publish` & `video.upload`):

   ```json
   {
     "client_key": "...",
     "client_secret": "..."
   }
   ```

   Daftarkan redirect URI `http://localhost:8080/` di pengaturan app TikTok
   (kalau diganti lewat env `TIKTOK_REDIRECT_URI`, daftarkan juga yang baru).

## Keamanan

- `secrets/` dan `tokens/` sudah di-`.gitignore` — jangan pernah commit
  kredensial atau token.
- Token disimpan lokal di `tokens/` dan hanya dikirim ke API resmi
  Google/TikTok.
