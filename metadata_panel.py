import tkinter as tk
from tkinter import ttk
import os
from datetime import datetime
from PIL import Image, ExifTags

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

EXIF_DISPLAY = {
    "Make": "Camera Make",
    "Model": "Camera Model",
    "DateTime": "Date/Time",
    "DateTimeOriginal": "Date Taken",
    "ExposureTime": "Exposure",
    "FNumber": "F-Number",
    "ISOSpeedRatings": "ISO",
    "FocalLength": "Focal Length",
    "Flash": "Flash",
    "GPSInfo": "GPS",
    "Software": "Software",
    "ImageWidth": "Width",
    "ImageLength": "Height",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".3gp", ".m4v"}


class MetadataPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, width=260)
        self.pack_propagate(False)

        header = ttk.Label(self, text="File Info", font=("Segoe UI", 10, "bold"))
        header.pack(anchor="w", padx=10, pady=(8, 4))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=6)

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = ttk.Frame(self._canvas)
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

        self._rows: list[tuple[ttk.Label, ttk.Label]] = []

    def _on_frame_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _clear(self):
        for widget in self._inner.winfo_children():
            widget.destroy()
        self._rows.clear()

    def _add_row(self, label: str, value: str):
        row = ttk.Frame(self._inner)
        row.pack(fill="x", padx=8, pady=1)
        lbl = ttk.Label(row, text=label + ":", foreground="#888888",
                         font=("Segoe UI", 8), width=14, anchor="w")
        lbl.pack(side="left")
        val = ttk.Label(row, text=value, font=("Segoe UI", 8),
                         wraplength=140, justify="left", anchor="w")
        val.pack(side="left", fill="x", expand=True)

    def _add_section(self, title: str):
        frame = ttk.Frame(self._inner)
        frame.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Separator(frame, orient="horizontal").pack(fill="x")
        ttk.Label(frame, text=title, font=("Segoe UI", 8, "bold"),
                  foreground="#555555").pack(anchor="w")

    def update_for_image(self, image_path: str, tags: list[str]):
        self._clear()
        if not image_path or not os.path.exists(image_path):
            self._add_row("Status", "No file loaded")
            return

        ext = os.path.splitext(image_path)[1].lower()
        is_video = ext in VIDEO_EXTENSIONS

        # --- File info ---
        self._add_section("File")
        stat = os.stat(image_path)
        size_kb = stat.st_size / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        self._add_row("Name", os.path.basename(image_path))
        self._add_row("Size", size_str)
        self._add_row("Modified", mod_time)
        self._add_row("Type", "Video" if is_video else "Image")

        if is_video:
            self._populate_video_info(image_path)
        else:
            self._populate_image_info(image_path)

        # --- Tags ---
        self._add_section("Tags")
        if tags:
            for tag in tags:
                ttk.Label(self._inner, text=f"  • {tag}", font=("Segoe UI", 8)).pack(anchor="w", padx=8)
        else:
            ttk.Label(self._inner, text="  (none)", font=("Segoe UI", 8),
                      foreground="#999999").pack(anchor="w", padx=8)

    def _populate_image_info(self, image_path: str):
        try:
            with Image.open(image_path) as img:
                self._add_section("Image")
                self._add_row("Dimensions", f"{img.width} × {img.height}")
                self._add_row("Mode", img.mode)

                exif_data = img._getexif() if hasattr(img, "_getexif") else None
                if exif_data:
                    self._add_section("EXIF")
                    tag_map = {v: k for k, v in ExifTags.TAGS.items()}
                    for friendly_key, display_label in EXIF_DISPLAY.items():
                        tag_id = tag_map.get(friendly_key)
                        if tag_id and tag_id in exif_data:
                            raw = exif_data[tag_id]
                            value = self._format_exif_value(friendly_key, raw)
                            if value:
                                self._add_row(display_label, value)
        except Exception:
            pass

    def _populate_video_info(self, video_path: str):
        if not CV2_AVAILABLE:
            return
        try:
            cap = cv2.VideoCapture(video_path)
            width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps    = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()

            self._add_section("Video")
            self._add_row("Dimensions", f"{width} × {height}")
            if fps and fps > 0:
                self._add_row("FPS", f"{fps:.1f}")
            if frames and fps and fps > 0:
                secs = int(frames / fps)
                self._add_row("Duration", f"{secs // 60}m {secs % 60}s")
        except Exception:
            pass

    def _format_exif_value(self, key: str, raw) -> str:
        try:
            if key == "ExposureTime":
                if isinstance(raw, tuple):
                    return f"{raw[0]}/{raw[1]}s"
                return f"{raw}s"
            if key == "FNumber":
                v = raw[0] / raw[1] if isinstance(raw, tuple) else float(raw)
                return f"f/{v:.1f}"
            if key == "FocalLength":
                v = raw[0] / raw[1] if isinstance(raw, tuple) else float(raw)
                return f"{v:.0f} mm"
            if key == "GPSInfo":
                return "(available)"
            if key == "Flash":
                return "On" if raw else "Off"
            return str(raw)
        except Exception:
            return str(raw)
