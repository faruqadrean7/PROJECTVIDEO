"""Auto Upload TikTok + YouTube — entry point & jendela utama UI.

Fase 5: penanganan error & polish.
- Validasi input dalam (video, judul, akun, durasi) sebelum upload.
- Konfirmasi untuk video besar / durasi melebihi batas platform.
- Tombol "Coba lagi" per platform — retry hanya akun yang gagal.
- Deteksi token expired/revoked → prompt login ulang + tombol re-auth.
- Notifikasi desktop saat upload selesai (toggle, default nyala).
- Pesan UI konsisten bahasa Indonesia.
"""

import datetime
import queue
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

import config_manager
import notifications
import tiktok_api
import uploader
import youtube_api
from video_metadata import format_duration, format_size, get_video_info

# Kategori YouTube: (id, label)
YOUTUBE_CATEGORIES = [
    ("22", "People & Blogs"),
    ("1", "Film & Animation"),
    ("2", "Autos & Vehicles"),
    ("10", "Music"),
    ("20", "Gaming"),
    ("24", "Entertainment"),
    ("26", "Howto & Style"),
    ("27", "Education"),
    ("28", "Science & Technology"),
]

YOUTUBE_VISIBILITY = ["Publik", "Unlisted", "Privat"]  # -> public/unlisted/private

TIKTOK_PRIVACY_OPTIONS = [
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "SELF_ONLY",
]

# Ambang konfirmasi
LARGE_FILE_BYTES = 500 * 1024 * 1024          # 500 MB
TIKTOK_MAX_DURATION_SEC = 10 * 60             # 10 menit (batas umum TikTok)

# Kata kunci error yang berarti token perlu login ulang
REAUTH_KEYWORDS = (
    "login ulang",
    "direvoke",
    "access_token_invalid",
    "refresh token",
)


class UploadApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Auto Upload TikTok + YouTube")
        self.root.geometry("800x1000")
        self.root.minsize(680, 780)
        self.root.grid_columnconfigure(0, weight=1)

        # State aplikasi
        self.video_path: str | None = None
        self.video_info: dict | None = None
        self.tags: list[str] = []
        self.thumbnail_path: str | None = None
        self.upload_running = False

        # Param upload terakhir (untuk tombol "Coba lagi")
        self._last_video_path: str | None = None
        self._last_youtube_params: dict | None = None
        self._last_tiktok_params: dict | None = None
        self._failed_accounts: dict = {"youtube": [], "tiktok": []}
        self._reauth_needed: list[tuple[str, str]] = []

        # Komunikasi worker thread -> UI
        self.msg_queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._refresh_accounts()
        self._refresh_history()

        # Polling tetap jalan supaya pesan dari worker (upload/auth) diproses
        self.root.after(100, self._poll_queue)

    # ================================================================ UI layout

    def _build_ui(self) -> None:
        # Header
        ctk.CTkLabel(
            self.root, text="Auto Upload TikTok + YouTube",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, pady=(16, 2), sticky="ew")
        ctk.CTkLabel(
            self.root, text="Upload paralel ke YouTube & TikTok",
            text_color="gray50", font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, pady=(0, 8))

        # --- 1. Drop area video ---
        self._build_drop_area()

        # --- 2. Pemilih akun (dari tokens/) ---
        self._build_account_picker()

        # --- 3. Form utama ---
        self._build_form()

        # --- 4. Section per platform (expand/collapse) ---
        self._build_youtube_section()
        self._build_tiktok_section()

        # --- 5. Progress per platform ---
        self._build_progress()

        # --- 6. Log real-time ---
        self._build_log()

        # --- 7. Tombol upload ---
        self.upload_btn = ctk.CTkButton(
            self.root, text="Upload ke Keduanya", height=48,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#E62117", hover_color="#C91B10",
            command=self._on_upload,
        )
        self.upload_btn.grid(row=11, column=0, padx=16, pady=(12, 4), sticky="ew")

        # --- 8. Tombol aksi (Coba lagi / Login ulang) — muncul saat perlu ---
        self.action_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.action_frame.grid(row=12, column=0, padx=16, pady=(0, 4), sticky="ew")
        self.action_frame.grid_columnconfigure((0, 1), weight=1)

        self.retry_btn = ctk.CTkButton(
            self.action_frame, text="↻  Coba lagi yang gagal",
            fg_color="gray30", hover_color="gray40", height=34,
            command=self._retry_failed,
        )
        self.retry_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.reauth_btn = ctk.CTkButton(
            self.action_frame, text="⟳  Login ulang akun",
            fg_color="#8A5A00", hover_color="#A06B00", height=34,
            command=self._on_reauth_click,
        )
        self.reauth_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")
        self.action_frame.grid_remove()

        # --- 9. Status ---
        self.status_label = ctk.CTkLabel(
            self.root, text="", text_color="gray60", font=ctk.CTkFont(size=12),
        )
        self.status_label.grid(row=13, column=0, pady=(0, 8))

        # --- 10. Riwayat upload ---
        self._build_history()

    def _build_drop_area(self) -> None:
        frame = ctk.CTkFrame(self.root, corner_radius=12, border_width=2,
                             border_color="gray40")
        frame.grid(row=2, column=0, padx=16, pady=(4, 8), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="📁  Seret video ke sini, atau klik tombol di bawah",
            font=ctk.CTkFont(size=14),
        ).grid(row=0, column=0, pady=(14, 2))
        ctk.CTkButton(
            frame, text="Pilih File Video…", width=180,
            command=self._browse_video,
        ).grid(row=1, column=0, pady=(4, 10))

        self.file_info_label = ctk.CTkLabel(
            frame, text="Belum ada file dipilih", text_color="gray50",
            font=ctk.CTkFont(size=12),
        )
        self.file_info_label.grid(row=2, column=0, pady=(0, 12))

        # Drag & drop
        try:
            frame.drop_target_register(DND_FILES)
            frame.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass  # kalau tkinterdnd2 bermasalah, browse button tetap jalan

    def _build_account_picker(self) -> None:
        frame = ctk.CTkFrame(self.root)
        frame.grid(row=3, column=0, padx=16, pady=6, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Akun tujuan upload:",
                     font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, padx=(14, 10), pady=12, sticky="nw")

        ctk.CTkLabel(frame, text="YouTube").grid(row=0, column=1, sticky="w")
        self.yt_box = ctk.CTkFrame(frame, fg_color="transparent")
        self.yt_box.grid(row=1, column=1, sticky="w", pady=(0, 4))

        ctk.CTkLabel(frame, text="TikTok").grid(row=2, column=1, sticky="w")
        self.tt_box = ctk.CTkFrame(frame, fg_color="transparent")
        self.tt_box.grid(row=3, column=1, sticky="w", pady=(0, 4))

        self.yt_account_vars: dict[str, ctk.BooleanVar] = {}
        self.tt_account_vars: dict[str, ctk.BooleanVar] = {}

        ctk.CTkButton(
            frame, text="＋ Hubungkan akun baru", width=180, height=30,
            fg_color="gray30", hover_color="gray40",
            command=self._open_connect_dialog,
        ).grid(row=0, column=2, rowspan=4, padx=14, pady=10, sticky="e")

    def _build_form(self) -> None:
        frame = ctk.CTkFrame(self.root)
        frame.grid(row=4, column=0, padx=16, pady=6, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        self.same_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(
            frame, text="Sama untuk kedua platform (judul & deskripsi)",
            variable=self.same_var, command=self._on_same_toggle,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        ctk.CTkLabel(frame, text="Judul *", anchor="w",
                     font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="ew", padx=14, pady=(8, 2))
        self.title_entry = ctk.CTkEntry(frame, placeholder_text="Judul video…")
        self.title_entry.grid(row=2, column=0, sticky="ew", padx=14)

        ctk.CTkLabel(frame, text="Deskripsi", anchor="w",
                     font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, sticky="ew", padx=14, pady=(8, 2))
        self.desc_textbox = ctk.CTkTextbox(frame, height=64)
        self.desc_textbox.grid(row=4, column=0, sticky="ew", padx=14)

        ctk.CTkLabel(frame, text="Hashtag / Tag", anchor="w",
                     font=ctk.CTkFont(size=12)).grid(
            row=5, column=0, sticky="ew", padx=14, pady=(8, 2))
        tag_row = ctk.CTkFrame(frame, fg_color="transparent")
        tag_row.grid(row=6, column=0, sticky="ew", padx=14, pady=(0, 4))
        tag_row.grid_columnconfigure(0, weight=1)

        self.tag_entry = ctk.CTkEntry(tag_row, placeholder_text="ketik tag lalu Enter / +")
        self.tag_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.tag_entry.bind("<Return>", lambda _e: self._add_tag())
        ctk.CTkButton(tag_row, text="+", width=40, command=self._add_tag).grid(
            row=0, column=1)

        self.tags_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.tags_frame.grid(row=7, column=0, sticky="ew", padx=14, pady=(0, 12))

    def _build_youtube_section(self) -> None:
        header = ctk.CTkFrame(self.root)
        header.grid(row=5, column=0, padx=16, pady=(6, 0), sticky="ew")
        self.yt_expanded = True
        self.yt_header_btn = ctk.CTkButton(
            header, text="▼  YouTube — pengaturan khusus", anchor="w",
            fg_color="transparent", hover_color="gray25", height=34,
            command=self._toggle_yt,
        )
        self.yt_header_btn.grid(row=0, column=0, sticky="ew")

        self.yt_section = ctk.CTkFrame(self.root)
        self.yt_section.grid(row=6, column=0, padx=16, sticky="ew")
        self.yt_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.yt_section, text="Visibilitas", anchor="w",
                     font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        self.yt_visibility_var = ctk.StringVar(value="Privat")
        ctk.CTkSegmentedButton(
            self.yt_section, values=YOUTUBE_VISIBILITY,
            variable=self.yt_visibility_var,
        ).grid(row=1, column=0, sticky="ew", padx=14)

        ctk.CTkLabel(self.yt_section, text="Kategori", anchor="w",
                     font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, sticky="w", padx=14, pady=(10, 2))
        self.yt_category_var = ctk.StringVar(value="People & Blogs")
        ctk.CTkOptionMenu(
            self.yt_section, values=[label for _id, label in YOUTUBE_CATEGORIES],
            variable=self.yt_category_var,
        ).grid(row=3, column=0, sticky="ew", padx=14)

        thumb_row = ctk.CTkFrame(self.yt_section, fg_color="transparent")
        thumb_row.grid(row=4, column=0, sticky="ew", padx=14, pady=(10, 2))
        thumb_row.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(thumb_row, text="Pilih thumbnail…", width=150,
                      command=self._browse_thumbnail).grid(row=0, column=0, sticky="w")
        self.thumb_label = ctk.CTkLabel(
            thumb_row, text="(opsional, default tanpa thumbnail)",
            text_color="gray50", font=ctk.CTkFont(size=12), anchor="w")
        self.thumb_label.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        # Override field (muncul kalau toggle "sama" dimatikan)
        self.yt_override_frame = ctk.CTkFrame(self.yt_section, fg_color="transparent")
        self.yt_override_frame.grid(row=5, column=0, sticky="ew", padx=14, pady=(6, 10))
        self.yt_override_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.yt_override_frame, text="Judul YouTube (override)",
                     anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="ew", pady=(4, 2))
        self.yt_title_entry = ctk.CTkEntry(self.yt_override_frame,
                                           placeholder_text="kosongkan = pakai judul umum")
        self.yt_title_entry.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(self.yt_override_frame, text="Deskripsi YouTube (override)",
                     anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, sticky="ew", pady=(6, 2))
        self.yt_desc_textbox = ctk.CTkTextbox(self.yt_override_frame, height=50)
        self.yt_desc_textbox.grid(row=3, column=0, sticky="ew")
        self.yt_override_frame.grid_remove()

    def _build_tiktok_section(self) -> None:
        header = ctk.CTkFrame(self.root)
        header.grid(row=7, column=0, padx=16, pady=(6, 0), sticky="ew")
        self.tt_expanded = True
        self.tt_header_btn = ctk.CTkButton(
            header, text="▼  TikTok — pengaturan khusus", anchor="w",
            fg_color="transparent", hover_color="gray25", height=34,
            command=self._toggle_tt,
        )
        self.tt_header_btn.grid(row=0, column=0, sticky="ew")

        self.tt_section = ctk.CTkFrame(self.root)
        self.tt_section.grid(row=8, column=0, padx=16, sticky="ew")
        self.tt_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.tt_section, text="Privasi", anchor="w",
                     font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        self.tt_privacy_var = ctk.StringVar(value="SELF_ONLY")
        ctk.CTkOptionMenu(
            self.tt_section, values=list(TIKTOK_PRIVACY_OPTIONS),
            variable=self.tt_privacy_var,
        ).grid(row=1, column=0, sticky="ew", padx=14)

        ctk.CTkLabel(
            self.tt_section,
            text="Catatan: app TikTok yang belum lolos audit hanya bisa "
                 "publish privat (SELF_ONLY).",
            text_color="gray50", font=ctk.CTkFont(size=11), anchor="w",
            wraplength=600, justify="left",
        ).grid(row=2, column=0, sticky="ew", padx=14, pady=(6, 2))

        self.tt_override_frame = ctk.CTkFrame(self.tt_section, fg_color="transparent")
        self.tt_override_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=(4, 10))
        self.tt_override_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.tt_override_frame, text="Caption TikTok (override)",
                     anchor="w", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="ew", pady=(4, 2))
        self.tt_caption_entry = ctk.CTkEntry(
            self.tt_override_frame,
            placeholder_text="kosongkan = pakai judul umum + hashtag")
        self.tt_caption_entry.grid(row=1, column=0, sticky="ew")
        self.tt_override_frame.grid_remove()

    def _build_progress(self) -> None:
        frame = ctk.CTkFrame(self.root)
        frame.grid(row=9, column=0, padx=16, pady=(6, 0), sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="YouTube", width=70, anchor="w").grid(
            row=0, column=0, padx=(14, 6), pady=(10, 2), sticky="w")
        self.yt_progress = ctk.CTkProgressBar(frame)
        self.yt_progress.set(0)
        self.yt_progress.grid(row=0, column=1, padx=(0, 14), pady=(10, 2), sticky="ew")
        self.yt_progress_label = ctk.CTkLabel(frame, text="—", width=60, anchor="e")
        self.yt_progress_label.grid(row=0, column=2, padx=(0, 10), pady=(10, 2))

        ctk.CTkLabel(frame, text="TikTok", width=70, anchor="w").grid(
            row=1, column=0, padx=(14, 6), pady=(2, 10), sticky="w")
        self.tt_progress = ctk.CTkProgressBar(frame)
        self.tt_progress.set(0)
        self.tt_progress.grid(row=1, column=1, padx=(0, 14), pady=(2, 10), sticky="ew")
        self.tt_progress_label = ctk.CTkLabel(frame, text="—", width=60, anchor="e")
        self.tt_progress_label.grid(row=1, column=2, padx=(0, 10), pady=(2, 10))

    def _build_log(self) -> None:
        frame = ctk.CTkFrame(self.root)
        frame.grid(row=10, column=0, padx=16, pady=6, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Log real-time",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, sticky="w")
        self.notify_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(header, text="🔔 Notifikasi saat selesai",
                      variable=self.notify_var, width=30,
                      font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="e")
        self.log_textbox = ctk.CTkTextbox(frame, height=90, state="disabled")
        self.log_textbox.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

    def _build_history(self) -> None:
        header = ctk.CTkFrame(self.root)
        header.grid(row=14, column=0, padx=16, pady=(6, 0), sticky="ew")
        self.history_expanded = False
        self.history_btn = ctk.CTkButton(
            header, text="▶  Riwayat Upload", anchor="w",
            fg_color="transparent", hover_color="gray25", height=34,
            command=self._toggle_history,
        )
        self.history_btn.grid(row=0, column=0, sticky="ew")

        self.history_list = ctk.CTkScrollableFrame(self.root, height=170)

    # ================================================================ handlers UI

    def _on_drop(self, event) -> None:
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]
        if files:
            self._set_video(str(files[0]))

    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Pilih file video",
            filetypes=[("Video", "*.mp4 *.mov *.webm *.mkv *.avi *.m4v"),
                       ("Semua file", "*.*")],
        )
        if path:
            self._set_video(path)

    def _browse_thumbnail(self) -> None:
        path = filedialog.askopenfilename(
            title="Pilih thumbnail (opsional)",
            filetypes=[("Gambar", "*.jpg *.jpeg *.png *.webp"),
                       ("Semua file", "*.*")],
        )
        if path:
            self.thumbnail_path = path
            self.thumb_label.configure(text=f"✅ {Path(path).name}")

    def _set_video(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            self._set_status("⚠️ File tidak ditemukan.", error=True)
            return
        self.video_path = str(p)
        try:
            self.video_info = get_video_info(str(p))
        except OSError:
            self.video_info = None

        if self.video_info:
            size = format_size(self.video_info["size_bytes"])
            dur = format_duration(self.video_info.get("duration_sec"))
            res = ""
            if self.video_info.get("width"):
                res = f"  ·  {self.video_info['width']}×{self.video_info['height']}"
            text = f"✅ {p.name}  ·  {size}  ·  {dur}{res}"
        else:
            text = f"✅ {p.name}"
        self.file_info_label.configure(text=text)
        self._set_status("")

    def _add_tag(self) -> None:
        raw = self.tag_entry.get().strip()
        if not raw:
            return
        tag = raw.lstrip("#").strip()
        if tag and tag not in self.tags:
            self.tags.append(tag)
        self.tag_entry.delete(0, "end")
        self._render_tags()

    def _remove_tag(self, tag: str) -> None:
        if tag in self.tags:
            self.tags.remove(tag)
        self._render_tags()

    def _render_tags(self) -> None:
        for child in self.tags_frame.winfo_children():
            child.destroy()
        for tag in self.tags:
            ctk.CTkButton(
                self.tags_frame, text=f"#{tag}  ✕", height=26, width=80,
                fg_color="gray30", hover_color="gray45",
                font=ctk.CTkFont(size=12),
                command=lambda t=tag: self._remove_tag(t),
            ).pack(side="left", padx=(0, 6), pady=2)

    def _on_same_toggle(self) -> None:
        same = bool(self.same_var.get())
        if same:
            self.yt_override_frame.grid_remove()
            self.tt_override_frame.grid_remove()
        else:
            self.yt_override_frame.grid()
            self.tt_override_frame.grid()

    def _toggle_yt(self) -> None:
        self.yt_expanded = not self.yt_expanded
        if self.yt_expanded:
            self.yt_section.grid()
            self.yt_header_btn.configure(text="▼  YouTube — pengaturan khusus")
        else:
            self.yt_section.grid_remove()
            self.yt_header_btn.configure(text="▶  YouTube — pengaturan khusus")

    def _toggle_tt(self) -> None:
        self.tt_expanded = not self.tt_expanded
        if self.tt_expanded:
            self.tt_section.grid()
            self.tt_header_btn.configure(text="▼  TikTok — pengaturan khusus")
        else:
            self.tt_section.grid_remove()
            self.tt_header_btn.configure(text="▶  TikTok — pengaturan khusus")

    def _toggle_history(self) -> None:
        self.history_expanded = not self.history_expanded
        if self.history_expanded:
            self.history_list.grid(row=15, column=0, padx=16, pady=(4, 12), sticky="ew")
            self.history_btn.configure(text="▼  Riwayat Upload")
        else:
            self.history_list.grid_remove()
            self.history_btn.configure(text="▶  Riwayat Upload")

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.configure(text=text, text_color="red" if error else "gray60")

    # ================================================================ akun

    def _refresh_accounts(self) -> None:
        """Baca akun dari tokens/ dan render ulang checkbox-nya."""
        accounts = config_manager.list_accounts()

        for box, vars_, labels in (
            (self.yt_box, self.yt_account_vars, accounts["youtube"]),
            (self.tt_box, self.tt_account_vars, accounts["tiktok"]),
        ):
            for child in box.winfo_children():
                child.destroy()
            vars_.clear()
            if not labels:
                ctk.CTkLabel(box, text="(belum ada akun terhubung)",
                             text_color="gray50",
                             font=ctk.CTkFont(size=11)).pack(side="left")
            for acc in labels:
                var = ctk.BooleanVar(value=True)
                vars_[acc] = var
                ctk.CTkCheckBox(box, text=acc, variable=var, width=20).pack(
                    side="left", padx=(0, 10))

    def _open_connect_dialog(self, platform: str | None = None,
                             label: str | None = None) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Hubungkan Akun Baru")
        dialog.geometry("400x280")
        dialog.transient(self.root)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Hubungkan Akun Baru",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(
            pady=(18, 10))

        ctk.CTkLabel(dialog, text="Platform", anchor="w").pack(padx=24, fill="x")
        platform_var = ctk.StringVar(value=platform or "YouTube")
        ctk.CTkOptionMenu(dialog, values=["YouTube", "TikTok"],
                          variable=platform_var).pack(padx=24, fill="x", pady=(2, 8))

        ctk.CTkLabel(dialog, text="Label akun (untuk membedakan beberapa akun)",
                     anchor="w").pack(padx=24, fill="x")
        label_entry = ctk.CTkEntry(dialog,
                                   placeholder_text="mis. main / gaming")
        label_entry.insert(0, label or "")
        label_entry.pack(padx=24, fill="x", pady=(2, 12))

        def _connect() -> None:
            chosen = platform_var.get()
            lbl = label_entry.get().strip() or "main"
            dialog.destroy()
            self._run_authenticate(chosen, lbl)

        ctk.CTkButton(dialog, text="Hubungkan & Login", command=_connect,
                      fg_color="#E62117", hover_color="#C91B10").pack(
            padx=24, fill="x", pady=(4, 8))
        ctk.CTkLabel(dialog, text="Browser akan terbuka untuk login.",
                     text_color="gray50", font=ctk.CTkFont(size=11)).pack()

    def _run_authenticate(self, platform: str, label: str) -> None:
        self._set_status(f"⏳ Login {platform} (label '{label}')… browser akan terbuka.")

        def worker():
            try:
                if platform == "YouTube":
                    youtube_api.authenticate(label)
                else:
                    tiktok_api.authenticate(label)
                self.msg_queue.put(("auth_ok", platform, label))
            except Exception as exc:
                self.msg_queue.put(("auth_error", platform, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    # ================================================================ data form

    def collect_form_data(self) -> dict:
        same = bool(self.same_var.get())

        yt_labels = [a for a, var in self.yt_account_vars.items() if var.get()]
        tt_labels = [a for a, var in self.tt_account_vars.items() if var.get()]

        shared_title = self.title_entry.get().strip()
        shared_desc = self.desc_textbox.get("1.0", "end").strip()

        yt_override_title = self.yt_title_entry.get().strip() if not same else ""
        yt_override_desc = self.yt_desc_textbox.get("1.0", "end").strip() if not same else ""
        tt_override_caption = self.tt_caption_entry.get().strip() if not same else ""

        if same:
            yt_title, yt_desc = shared_title, shared_desc
            tt_caption = shared_title
        else:
            yt_title = yt_override_title or shared_title
            yt_desc = yt_override_desc or shared_desc
            tt_caption = tt_override_caption or shared_title

        hashtag_text = " ".join(f"#{t}" for t in self.tags)
        if hashtag_text:
            tt_caption = f"{tt_caption} {hashtag_text}".strip()

        category_label = self.yt_category_var.get()
        category_id = next(
            (cid for cid, label in YOUTUBE_CATEGORIES if label == category_label), "22"
        )
        visibility_map = {"Publik": "public", "Unlisted": "unlisted", "Privat": "private"}

        return {
            "video": {
                "path": self.video_path,
                "size_bytes": self.video_info["size_bytes"] if self.video_info else None,
                "size_human": format_size(self.video_info["size_bytes"]) if self.video_info else None,
                "duration_sec": self.video_info.get("duration_sec") if self.video_info else None,
                "duration_human": format_duration(self.video_info.get("duration_sec")) if self.video_info else None,
            },
            "same_for_both": same,
            "accounts": {"youtube": yt_labels, "tiktok": tt_labels},
            "shared": {"title": shared_title, "description": shared_desc,
                       "tags": list(self.tags)},
            "youtube": {
                "title": yt_title,
                "description": yt_desc,
                "tags": list(self.tags),
                "visibility": visibility_map.get(self.yt_visibility_var.get(), "private"),
                "category_id": category_id,
                "category_label": category_label,
                "thumbnail": self.thumbnail_path,
            },
            "tiktok": {
                "caption": tt_caption,
                "privacy": self.tt_privacy_var.get(),
            },
        }

    # ================================================================ validasi

    def _validate(self, data: dict) -> list[str]:
        """Validasi lengkap sebelum upload. Returns list pesan error (kosong = OK)."""
        errors = []
        if not data["video"]["path"]:
            errors.append("• Pilih file video dulu.")
        elif not Path(data["video"]["path"]).is_file():
            errors.append("• File video tidak ditemukan di lokasi tersebut.")
        if not (data["accounts"]["youtube"] or data["accounts"]["tiktok"]):
            errors.append("• Centang minimal 1 akun tujuan upload.")
        if not data["shared"]["title"].strip():
            errors.append("• Judul masih kosong.")
        return errors

    def _collect_warnings(self, data: dict) -> list[str]:
        """Peringatan yang butuh konfirmasi user (bukan blocker)."""
        warnings = []
        size = data["video"].get("size_bytes") or 0
        if size > LARGE_FILE_BYTES:
            warnings.append(
                f"• Video berukuran {data['video'].get('size_human', 'besar')} "
                f"(> 500 MB) — upload bisa memakan waktu lama."
            )
        dur = data["video"].get("duration_sec")
        if dur and dur > TIKTOK_MAX_DURATION_SEC and data["accounts"]["tiktok"]:
            warnings.append(
                "• Durasi video lebih dari 10 menit — TikTok umumnya membatasi "
                "maks 10 menit, video bisa ditolak TikTok."
            )
        return warnings

    # ================================================================ upload

    def _on_upload(self) -> None:
        if self.upload_running:
            return
        data = self.collect_form_data()

        errors = self._validate(data)
        if errors:
            self._set_status("⚠️ Form belum lengkap — periksa pesan error.", error=True)
            messagebox.showwarning("Form belum lengkap", "\n".join(errors))
            return

        warnings = self._collect_warnings(data)
        if warnings:
            lanjut = messagebox.askyesno(
                "Konfirmasi upload",
                "\n".join(warnings) + "\n\nLanjutkan upload?",
            )
            if not lanjut:
                self._set_status("Upload dibatalkan.")
                return

        youtube_params = {
            "accounts": data["accounts"]["youtube"],
            "video_path": data["video"]["path"],
            "title": data["youtube"]["title"],
            "description": data["youtube"]["description"],
            "tags": data["youtube"]["tags"],
            "privacy_status": data["youtube"]["visibility"],
            "category_id": data["youtube"]["category_id"],
            "thumbnail": data["youtube"]["thumbnail"],
        }
        tiktok_params = {
            "accounts": data["accounts"]["tiktok"],
            "video_path": data["video"]["path"],
            "caption": data["tiktok"]["caption"],
            "privacy_level": data["tiktok"]["privacy"],
        }

        self._start_upload_worker(data["video"]["path"], youtube_params, tiktok_params)

    def _start_upload_worker(self, video_path: str,
                             youtube_params: dict, tiktok_params: dict) -> None:
        """Mulai upload paralel di thread terpisah (dipakai upload baru & retry)."""
        self._last_video_path = video_path
        self._last_youtube_params = youtube_params
        self._last_tiktok_params = tiktok_params
        self._failed_accounts = {"youtube": [], "tiktok": []}
        self._reauth_needed = []
        self.action_frame.grid_remove()

        self._reset_progress()
        self._append_log("system", f"▶ Mulai upload '{Path(video_path).name}'")
        self.upload_running = True
        self.upload_btn.configure(state="disabled", text="Mengupload…")

        def worker():
            try:
                results = uploader.upload_to_both(
                    video_path,
                    youtube_params,
                    tiktok_params,
                    progress_callback=self._on_worker_progress,
                    log_callback=self._on_worker_log,
                )
                self.msg_queue.put(("upload_done", results, video_path))
            except Exception as exc:
                self.msg_queue.put(("upload_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _retry_failed(self) -> None:
        """Ulangi upload hanya untuk akun yang gagal (per platform)."""
        if self.upload_running:
            return
        yt_params = dict(self._last_youtube_params or {})
        yt_params["accounts"] = self._failed_accounts["youtube"]
        tt_params = dict(self._last_tiktok_params or {})
        tt_params["accounts"] = self._failed_accounts["tiktok"]

        if not (yt_params["accounts"] or tt_params["accounts"]):
            self._set_status("Tidak ada akun yang gagal untuk dicoba ulang.")
            return

        self._append_log("system",
                         f"↻ Mencoba ulang: YouTube {yt_params['accounts']} · "
                         f"TikTok {tt_params['accounts']}")
        self._start_upload_worker(self._last_video_path or "",
                                  yt_params, tt_params)

    def _on_reauth_click(self) -> None:
        if not self._reauth_needed:
            return
        platform, account = self._reauth_needed[0]
        self._open_connect_dialog(platform="YouTube" if platform == "youtube" else "TikTok",
                                  label=account)

    def _on_worker_progress(self, platform: str, account: str, pct: int) -> None:
        self.msg_queue.put(("progress", platform, account, pct))

    def _on_worker_log(self, platform: str, message: str) -> None:
        self.msg_queue.put(("log", platform, message))

    def _reset_progress(self) -> None:
        self.yt_progress.set(0)
        self.tt_progress.set(0)
        self.yt_progress_label.configure(text="—")
        self.tt_progress_label.configure(text="—")

    def _update_progress(self, platform: str, account: str, pct: int) -> None:
        pct = max(0, min(100, pct))
        if platform == "youtube":
            self.yt_progress.set(pct / 100)
            self.yt_progress_label.configure(text=f"{pct}%")
        else:
            self.tt_progress.set(pct / 100)
            self.tt_progress_label.configure(text=f"{pct}%")
        if pct == 100:
            self._append_log(platform, f"[{account}] upload selesai 100%")

    def _append_log(self, platform: str, message: str) -> None:
        tag = {"youtube": "[YouTube]", "tiktok": "[TikTok]", "system": "[Sistem]"}.get(
            platform, f"[{platform}]")
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f"{tag} {message}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    @staticmethod
    def _classify_error(message: str) -> str | None:
        """Klasifikasi error: 'reauth' kalau token perlu login ulang, else None."""
        msg = message.lower()
        if any(k in msg for k in REAUTH_KEYWORDS):
            return "reauth"
        return None

    def _finish_upload(self, results: dict, video_path: str) -> None:
        self.upload_running = False
        self.upload_btn.configure(state="normal", text="Upload ke Keduanya")

        yt_ok = [r for r in results["youtube"] if r["status"] == "ok"]
        yt_err = [r for r in results["youtube"] if r["status"] == "error"]
        tt_ok = [r for r in results["tiktok"] if r["status"] == "ok"]
        tt_err = [r for r in results["tiktok"] if r["status"] == "error"]

        # Simpan info untuk tombol "Coba lagi" & deteksi re-auth
        self._failed_accounts = {
            "youtube": [r["account"] for r in yt_err],
            "tiktok": [r["account"] for r in tt_err],
        }
        self._reauth_needed = []
        for platform, errs in (("youtube", yt_err), ("tiktok", tt_err)):
            for r in errs:
                if self._classify_error(r["message"]) == "reauth":
                    self._reauth_needed.append((platform, r["account"]))

        # Riwayat
        record = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "file": Path(video_path).name,
            "title": (self._last_youtube_params or {}).get("title", ""),
            "same_for_both": bool(self.same_var.get()),
            "youtube": results["youtube"],
            "tiktok": results["tiktok"],
        }
        config_manager.add_history_record(record)
        self._refresh_history()

        # Log link
        for r in yt_ok:
            self._append_log("system", f"🔗 Link YouTube: {r['link']}")
        for r in yt_err:
            self._append_log("youtube", f"[{r['account']}] GAGAL: {r['message']}")
        for r in tt_err:
            self._append_log("tiktok", f"[{r['account']}] GAGAL: {r['message']}")

        # Ringkasan status
        summary = []
        if yt_ok:
            summary.append(f"YouTube: {len(yt_ok)} berhasil")
        if yt_err:
            summary.append(f"YouTube: {len(yt_err)} gagal")
        if tt_ok:
            summary.append(f"TikTok: {len(tt_ok)} berhasil ({tt_ok[0]['message']})")
        if tt_err:
            summary.append(f"TikTok: {len(tt_err)} gagal")

        ok_all = not yt_err and not tt_err and (yt_ok or tt_ok)
        status_text = " · ".join(summary) if summary else "Tidak ada yang diupload."
        self._set_status(("✅ " if ok_all else "⚠️ ") + status_text, error=not ok_all)

        # Tombol aksi
        if self._failed_accounts["youtube"] or self._failed_accounts["tiktok"]:
            parts = []
            if self._failed_accounts["youtube"]:
                parts.append(f"YT {self._failed_accounts['youtube']}")
            if self._failed_accounts["tiktok"]:
                parts.append(f"TT {self._failed_accounts['tiktok']}")
            self.retry_btn.configure(text="↻  Coba lagi: " + " · ".join(parts))
            self.action_frame.grid()
        if self._reauth_needed:
            self.reauth_btn.configure(
                text=f"⟳  Login ulang: {self._reauth_needed[0][1]} ({self._reauth_needed[0][0]})")
            messagebox.showwarning(
                "Akun perlu login ulang",
                f"Akun {self._reauth_needed[0][1]} ({self._reauth_needed[0][0]}) "
                "token-nya tidak valid/kedaluwarsa.\n\n"
                "Klik tombol 'Login ulang' untuk masuk lagi.",
            )

        # Notifikasi desktop
        if self.notify_var.get():
            title = "Upload selesai" if ok_all else "Upload selesai (ada yang gagal)"
            notifications.notify(title, status_text)

    def _refresh_history(self) -> None:
        history = config_manager.load_history()
        for child in self.history_list.winfo_children():
            child.destroy()

        if not history:
            ctk.CTkLabel(self.history_list, text="Belum ada riwayat upload.",
                         text_color="gray50").pack(pady=10)
            return

        for rec in history[:30]:
            row = ctk.CTkFrame(self.history_list)
            row.pack(fill="x", padx=6, pady=3)
            row.grid_columnconfigure(1, weight=1)

            yt_text = "YouTube: —"
            for r in rec.get("youtube", []):
                yt_text = f"YouTube: {'✅' if r['status'] == 'ok' else '❌ ' + r['message'][:40]}"
            tt_text = "TikTok: —"
            for r in rec.get("tiktok", []):
                tt_text = f"TikTok: {'✅ ' + r['message'] if r['status'] == 'ok' else '❌ ' + r['message'][:40]}"

            label = ctk.CTkLabel(
                row,
                text=f"{rec.get('file', '?')}  ·  {rec.get('timestamp', '?')}\n"
                     f"{yt_text}   |   {tt_text}",
                font=ctk.CTkFont(size=11), anchor="w", justify="left",
            )
            label.grid(row=0, column=0, padx=10, pady=6, sticky="w")

            links = [r["link"] for r in rec.get("youtube", [])
                     if r.get("status") == "ok" and r.get("link")]
            if links:
                ctk.CTkButton(
                    row, text="Buka", width=60, height=26,
                    command=lambda url=links[0]: webbrowser.open(url),
                ).grid(row=0, column=1, padx=8, pady=6, sticky="e")

    # ================================================================ polling

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, platform, account, pct = msg
                    self._update_progress(platform, account, pct)
                elif kind == "log":
                    _, platform, text = msg
                    self._append_log(platform, text)
                elif kind == "upload_done":
                    _, results, video_path = msg
                    self._finish_upload(results, video_path)
                elif kind == "upload_error":
                    _, err = msg
                    self.upload_running = False
                    self.upload_btn.configure(state="normal", text="Upload ke Keduanya")
                    self._set_status(f"❌ {err}", error=True)
                    self._append_log("system", f"❌ {err}")
                    if self.notify_var.get():
                        notifications.notify("Upload gagal", str(err))
                elif kind == "auth_ok":
                    _, platform, label = msg
                    self._refresh_accounts()
                    self._set_status(f"✅ Akun {platform} '{label}' terhubung.")
                elif kind == "auth_error":
                    _, platform, err = msg
                    self._set_status(f"❌ Login {platform} gagal: {err}", error=True)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = UploadApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
