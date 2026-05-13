import tkinter as tk
from tkinter import ttk
import os
import threading
from PIL import Image, ImageTk

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

THUMB_SIZES = {
    "S": (90,  70),
    "M": (130, 100),
    "L": (190, 148),
}
PADDING = 6
COLS    = 5

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".3gp", ".m4v"}

BADGE_COLORS = {
    "starred": "#FFD700",
    "archive": "#A0A0A0",
}
DEFAULT_CUSTOM_BADGE = "#64B5F6"

UNSORTED_BG = "#2b2b2b"
SELECTED_BG = "#1565C0"


class GridView(ttk.Frame):
    """Thumbnail overview of all images in the current folder."""

    def __init__(self, parent, on_select_callback, on_open_callback=None):
        super().__init__(parent)
        # single click  → navigate to image, stay in grid
        # double click  → navigate to image, return to single view
        self._on_select = on_select_callback
        self._on_open   = on_open_callback

        self._thumb_w, self._thumb_h = THUMB_SIZES["M"]

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=4, pady=(2, 0))
        ttk.Label(toolbar, text="Size:", font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
        self._size_var = tk.StringVar(value="M")
        for key in ("S", "M", "L"):
            ttk.Radiobutton(toolbar, text=key, value=key, variable=self._size_var,
                            command=self._on_size_change).pack(side="left", padx=2)
        ttk.Label(toolbar, text="  Double-click to open in single view",
                  font=("Segoe UI", 7), foreground="#888888").pack(side="left", padx=10)

        # ── Canvas + scrollbar ───────────────────────────────────────
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(side="top", fill="both", expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg="#1e1e1e", highlightthickness=0)
        self._vscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vscroll.set)

        self._vscroll.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._canvas.bind("<Configure>",        self._on_resize)
        self._canvas.bind("<MouseWheel>",        self._on_mousewheel)
        self._canvas.bind("<Button-1>",          self._on_click)
        self._canvas.bind("<Double-Button-1>",   self._on_double_click)

        self._all_files: list[str] = []
        self._status: dict[str, str] = {}
        self._current_index: int = -1

        self._thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self._placeholder: ImageTk.PhotoImage | None = None
        self._items: dict[int, dict] = {}

        self._cols = COLS
        self._load_thread: threading.Thread | None = None
        self._stop_loading = threading.Event()

    @property
    def cols(self) -> int:
        return self._cols

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_folder(self, all_files: list[str], status: dict[str, str], current_index: int):
        self._stop_loading.set()
        if self._load_thread and self._load_thread.is_alive():
            self._load_thread.join(timeout=1)

        self._all_files = all_files
        self._status    = status
        self._current_index = current_index
        self._thumb_cache.clear()
        self._items.clear()
        self._stop_loading.clear()

        self._render_grid()

        self._load_thread = threading.Thread(target=self._load_thumbs_bg, daemon=True)
        self._load_thread.start()

    def update_status(self, filename: str, action: str):
        self._status[filename] = action
        index = next((i for i, f in enumerate(self._all_files)
                      if os.path.basename(f) == filename), None)
        if index is not None:
            self.after(0, lambda: self._redraw_item(index))

    def set_current(self, index: int):
        old = self._current_index
        self._current_index = index
        if old >= 0:
            self.after(0, lambda: self._redraw_item(old))
        self.after(0, lambda: self._redraw_item(index))
        self.after(0, lambda: self._scroll_to(index))

    # ------------------------------------------------------------------
    # Size change
    # ------------------------------------------------------------------

    def _on_size_change(self):
        self._thumb_w, self._thumb_h = THUMB_SIZES[self._size_var.get()]
        self._placeholder = None
        self._thumb_cache.clear()
        self._stop_loading.set()
        if self._load_thread and self._load_thread.is_alive():
            self._load_thread.join(timeout=0.3)
        self._stop_loading.clear()
        self._render_grid()
        if self._all_files:
            self._load_thread = threading.Thread(target=self._load_thumbs_bg, daemon=True)
            self._load_thread.start()

    # ------------------------------------------------------------------
    # Grid rendering
    # ------------------------------------------------------------------

    def _cell_size(self):
        return self._thumb_w + PADDING * 2, self._thumb_h + PADDING * 2 + 18

    def _cell_xy(self, index: int):
        cw, ch = self._cell_size()
        col = index % self._cols
        row = index // self._cols
        x = col * cw + PADDING
        y = row * ch + PADDING
        return x, y

    def _render_grid(self):
        self._canvas.delete("all")
        self._items.clear()

        if not self._all_files:
            return

        canvas_w = self._canvas.winfo_width() or (COLS * (self._thumb_w + PADDING * 2))
        self._cols = max(1, canvas_w // (self._thumb_w + PADDING * 2))

        cw, ch = self._cell_size()
        total_rows = (len(self._all_files) + self._cols - 1) // self._cols
        total_h = total_rows * ch + PADDING
        self._canvas.configure(scrollregion=(0, 0, self._cols * cw, total_h))

        if self._placeholder is None:
            self._placeholder = self._make_placeholder()

        for i, fpath in enumerate(self._all_files):
            self._draw_item(i, fpath)

    def _draw_item(self, index: int, fpath: str):
        fname = os.path.basename(fpath)
        x, y  = self._cell_xy(index)
        action = self._status.get(fname, "")
        is_current = (index == self._current_index)

        bg = SELECTED_BG if is_current else UNSORTED_BG
        self._canvas.create_rectangle(
            x, y, x + self._thumb_w + PADDING, y + self._thumb_h + PADDING,
            fill=bg, outline="#444444", width=2 if is_current else 1,
            tags=f"cell_{index}"
        )

        thumb = self._thumb_cache.get(fname, self._placeholder)
        self._canvas.create_image(
            x + PADDING // 2 + self._thumb_w // 2,
            y + PADDING // 2 + self._thumb_h // 2,
            image=thumb, tags=f"cell_{index}"
        )

        if action:
            color = BADGE_COLORS.get(action.lower(), DEFAULT_CUSTOM_BADGE)
            self._canvas.create_rectangle(
                x, y, x + self._thumb_w + PADDING, y + 14,
                fill=color, outline="", tags=f"cell_{index}"
            )
            self._canvas.create_text(
                x + (self._thumb_w + PADDING) // 2, y + 7,
                text=action.upper(), fill="white",
                font=("Segoe UI", 6, "bold"), tags=f"cell_{index}"
            )

        short_name = fname if len(fname) <= 18 else fname[:15] + "…"
        self._canvas.create_text(
            x + (self._thumb_w + PADDING) // 2,
            y + self._thumb_h + PADDING - 4,
            text=short_name, fill="#cccccc",
            font=("Segoe UI", 7), tags=f"cell_{index}"
        )

    def _redraw_item(self, index: int):
        if index < 0 or index >= len(self._all_files):
            return
        self._canvas.delete(f"cell_{index}")
        self._draw_item(index, self._all_files[index])

    def _scroll_to(self, index: int):
        if not self._all_files:
            return
        _, y = self._cell_xy(index)
        _, ch = self._cell_size()
        total_rows = (len(self._all_files) + self._cols - 1) // self._cols
        total_h = total_rows * ch
        if total_h == 0:
            return
        frac = y / total_h
        self._canvas.yview_moveto(max(0.0, frac - 0.1))

    # ------------------------------------------------------------------
    # Background thumbnail loading
    # ------------------------------------------------------------------

    def _load_thumbs_bg(self):
        for i, fpath in enumerate(self._all_files):
            if self._stop_loading.is_set():
                break
            fname = os.path.basename(fpath)
            if fname in self._thumb_cache:
                continue
            try:
                tw, th  = self._thumb_w, self._thumb_h
                pil_img = self._load_thumb_pil(fpath, tw, th)
                self.after(0, lambda fi=fname, pi=pil_img, idx=i: self._apply_thumb(fi, pi, idx))
            except Exception:
                pass

    def _load_thumb_pil(self, fpath: str, tw: int, th: int) -> Image.Image:
        ext = os.path.splitext(fpath)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            return self._video_thumb(fpath, tw, th)
        img = Image.open(fpath)
        img = self._fix_orientation(img)
        img.thumbnail((tw, th), Image.LANCZOS)
        return img

    def _video_thumb(self, fpath: str, tw: int, th: int) -> Image.Image:
        if CV2_AVAILABLE:
            cap = cv2.VideoCapture(fpath)
            ok, frame = cap.read()
            cap.release()
            if ok:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img.thumbnail((tw, th), Image.LANCZOS)
                return img
        return self._make_placeholder_pil()

    def _apply_thumb(self, fname: str, pil_img: Image.Image, index: int):
        photo = ImageTk.PhotoImage(pil_img)
        self._thumb_cache[fname] = photo
        self._redraw_item(index)

    # ------------------------------------------------------------------
    # Placeholder
    # ------------------------------------------------------------------

    def _make_placeholder_pil(self) -> Image.Image:
        return Image.new("RGB", (self._thumb_w, self._thumb_h), color=(60, 60, 60))

    def _make_placeholder(self) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(self._make_placeholder_pil())

    # ------------------------------------------------------------------
    # Orientation fix
    # ------------------------------------------------------------------

    def _fix_orientation(self, image: Image.Image) -> Image.Image:
        try:
            from PIL import ExifTags
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == "Orientation":
                    break
            exif = image._getexif()
            if exif and orientation in exif:
                if exif[orientation] == 3:
                    image = image.rotate(180, expand=True)
                elif exif[orientation] == 6:
                    image = image.rotate(270, expand=True)
                elif exif[orientation] == 8:
                    image = image.rotate(90, expand=True)
        except Exception:
            pass
        return image

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_resize(self, _event):
        self._render_grid()

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _index_from_event(self, event) -> int | None:
        x = self._canvas.canvasx(event.x)
        y = self._canvas.canvasy(event.y)
        cw, ch = self._cell_size()
        col = int(x // cw)
        row = int(y // ch)
        index = row * self._cols + col
        return index if 0 <= index < len(self._all_files) else None

    def _on_click(self, event):
        index = self._index_from_event(event)
        if index is not None:
            self._on_select(index)

    def _on_double_click(self, event):
        index = self._index_from_event(event)
        if index is not None and self._on_open:
            self._on_open(index)
