import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from PIL import Image, ImageTk, ExifTags

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".3gp", ".m4v"}
PRELOAD_AHEAD   = 4
PRELOAD_BEHIND  = 2


class ImageSorter(ttk.Frame):
    """
    Single-image viewer with:
    - Image & video display (first frame + Play button for video)
    - Background preloading
    - Sort / undo using full image list + status dict (images are never
      removed from the list so the grid view always has the full picture)
    - Callbacks: on_image_changed(index, path), on_sort(index, filename, action)
    """

    def __init__(self, parent, info_frame,
                 on_image_changed=None, on_sort=None):
        super().__init__(parent)
        self.info_frame = info_frame
        self._on_image_changed = on_image_changed  # callable(index, path)
        self._on_sort          = on_sort            # callable(index, fname, action)

        self.current_folder: str | None = None
        self.all_files: list[str] = []   # full paths, never shrinks
        self.status: dict[str, str] = {} # basename -> action key (empty = unsorted)
        self.current_index: int = 0

        # PIL image cache {basename: PIL.Image}
        self._pil_cache: dict[str, Image.Image] = {}
        self._cache_lock = threading.Lock()
        self._preload_event = threading.Event()
        self._stop_flag = threading.Event()

        # Undo stack: list of (index, original_path, new_path)
        self._undo_stack: list[tuple[int, str, str]] = []

        # Build UI
        self._image_label = tk.Label(self, bg="#1e1e1e")
        self._image_label.pack(expand=True, fill="both")

        self._play_btn = ttk.Button(self, text="▶  Play Video",
                                     command=self._play_video)

        # Keep a ref so PhotoImage isn't GC'd
        self._current_photo: ImageTk.PhotoImage | None = None
        self._current_video_path: str | None = None

        # Start background preloader
        t = threading.Thread(target=self._preloader_loop, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Folder loading
    # ------------------------------------------------------------------

    def select_new_folder(self, folder: str):
        self.current_folder = folder
        self._stop_flag.set()   # pause preloader briefly
        self._pil_cache.clear()
        self._undo_stack.clear()

        all_names = sorted(
            f for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
        )
        self.all_files = [os.path.join(folder, n) for n in all_names]
        self.status = {}

        if not self.all_files:
            messagebox.showinfo("No Media", "No images or videos found in selected folder!")
            return

        self.current_index = 0
        self._stop_flag.clear()
        self._preload_event.set()
        self.show_current()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def show_current(self):
        if not self.all_files:
            return

        path = self.all_files[self.current_index]
        ext  = os.path.splitext(path)[1].lower()
        self._current_video_path = None

        if ext in VIDEO_EXTENSIONS:
            self._show_video(path)
        else:
            self._show_image(path)

        fname = os.path.basename(path)
        self.info_frame.update_file_label_and_index(
            fname, self.current_index + 1, len(self.all_files)
        )

        if self._on_image_changed:
            self._on_image_changed(self.current_index, path)

        self._preload_event.set()

    def _show_image(self, path: str):
        self._play_btn.pack_forget()
        try:
            pil = self._get_or_load(path)
            w = self.winfo_width()  or 800
            h = self.winfo_height() or 600
            pil_display = pil.copy()
            pil_display.thumbnail((max(w - 20, 200), max(h - 20, 200)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(pil_display)
            self._current_photo = photo
            self._image_label.configure(image=photo, bg="#1e1e1e")
        except Exception as e:
            self._image_label.configure(image="", text=f"Cannot load:\n{e}", bg="#1e1e1e",
                                         fg="white", font=("Segoe UI", 10))

    def _show_video(self, path: str):
        self._current_video_path = path
        frame_pil = self._extract_video_frame(path)
        if frame_pil:
            w = self.winfo_width()  or 800
            h = self.winfo_height() or 600
            frame_pil.thumbnail((max(w - 20, 200), max(h - 80, 200)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(frame_pil)
            self._current_photo = photo
            self._image_label.configure(image=photo, text="", bg="#1e1e1e")
        else:
            self._image_label.configure(image="", text="🎬  Video\n(no preview)",
                                         bg="#1e1e1e", fg="white", font=("Segoe UI", 14))
        self._play_btn.pack(pady=6)

    def _extract_video_frame(self, path: str):
        if not CV2_AVAILABLE:
            return None
        try:
            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            cap.release()
            if ok:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return Image.fromarray(frame)
        except Exception:
            pass
        return None

    def _play_video(self):
        if self._current_video_path:
            os.startfile(self._current_video_path)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def next_image(self):
        if self.current_index < len(self.all_files) - 1:
            self.current_index += 1
            self.show_current()

    def previous_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current()

    def jump_to(self, index: int):
        if 0 <= index < len(self.all_files):
            self.current_index = index
            self.show_current()

    def next_unsorted(self):
        """Advance to the next image that hasn't been sorted yet."""
        start = self.current_index + 1
        for i in range(start, len(self.all_files)):
            fname = os.path.basename(self.all_files[i])
            if not self.status.get(fname):
                self.current_index = i
                self.show_current()
                return
        # All remaining are sorted — show completion
        unsorted = sum(1 for f in self.all_files
                       if not self.status.get(os.path.basename(f)))
        if unsorted == 0:
            self._signal_complete()

    def _signal_complete(self):
        if self._on_sort:
            self._on_sort(-1, "", "__complete__")

    # ------------------------------------------------------------------
    # Sorting actions
    # ------------------------------------------------------------------

    def sort_image(self, category: dict):
        """Move the current image to the category's subfolder."""
        if not self.all_files:
            return
        path = self.all_files[self.current_index]
        fname = os.path.basename(path)
        folder_name = category["folder"]
        dest_dir = os.path.join(self.current_folder, folder_name)
        Path(dest_dir).mkdir(exist_ok=True)
        dest = os.path.join(dest_dir, fname)

        try:
            shutil.move(path, dest)
        except Exception as e:
            messagebox.showerror("Move failed", str(e))
            return

        self.status[fname] = category["name"].lower()
        self._undo_stack.append((self.current_index, path, dest))

        if self._on_sort:
            self._on_sort(self.current_index, fname, category["name"].lower())

        self.next_unsorted()

    def undo_last_move(self):
        if not self._undo_stack:
            messagebox.showinfo("Undo", "Nothing to undo.")
            return

        index, original, moved = self._undo_stack.pop()
        fname = os.path.basename(original)
        try:
            shutil.move(moved, original)
        except Exception as e:
            messagebox.showerror("Undo failed", str(e))
            return

        self.status[fname] = ""
        if self._on_sort:
            self._on_sort(index, fname, "")
        self.current_index = index
        self.show_current()

    # ------------------------------------------------------------------
    # Preloading
    # ------------------------------------------------------------------

    def _get_or_load(self, path: str) -> Image.Image:
        fname = os.path.basename(path)
        with self._cache_lock:
            if fname in self._pil_cache:
                return self._pil_cache[fname]
        img = Image.open(path)
        img = self._fix_orientation(img)
        img.load()
        with self._cache_lock:
            self._pil_cache[fname] = img
        return img

    def _preloader_loop(self):
        while True:
            self._preload_event.wait()
            self._preload_event.clear()
            if self._stop_flag.is_set():
                continue
            self._do_preload()

    def _do_preload(self):
        if not self.all_files:
            return
        indices = []
        for delta in range(1, PRELOAD_AHEAD + 1):
            idx = self.current_index + delta
            if idx < len(self.all_files):
                indices.append(idx)
        for delta in range(1, PRELOAD_BEHIND + 1):
            idx = self.current_index - delta
            if idx >= 0:
                indices.append(idx)

        for idx in indices:
            if self._stop_flag.is_set() or self._preload_event.is_set():
                break
            path = self.all_files[idx]
            ext  = os.path.splitext(path)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                continue  # skip preload for video
            fname = os.path.basename(path)
            with self._cache_lock:
                if fname in self._pil_cache:
                    continue
            try:
                img = Image.open(path)
                img = self._fix_orientation(img)
                img.load()
                with self._cache_lock:
                    self._pil_cache[fname] = img
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fix_orientation(self, image: Image.Image) -> Image.Image:
        try:
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

    def current_path(self) -> str | None:
        if self.all_files:
            return self.all_files[self.current_index]
        return None
