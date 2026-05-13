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
        self._on_image_changed = on_image_changed
        self._on_sort          = on_sort

        self.current_folder: str | None = None
        self.all_files: list[str] = []
        self.status: dict[str, str] = {}
        self.current_index: int = 0

        self._pil_cache: dict[str, Image.Image] = {}
        self._cache_lock = threading.Lock()
        self._preload_event = threading.Event()
        self._stop_flag = threading.Event()

        # undo stack: (index, path_before_move, path_after_move, prev_status)
        self._undo_stack: list[tuple[int, str, str, str]] = []
        # tracks where each file actually is now (may differ from all_files after sorting)
        self._locations: dict[int, str] = {}

        self._image_label = tk.Label(self, bg="#1e1e1e")
        self._image_label.pack(expand=True, fill="both")

        self._play_btn = ttk.Button(self, text="▶  Play Video",
                                     command=self._play_video)

        self._current_photo: ImageTk.PhotoImage | None = None
        self._current_video_path: str | None = None

        t = threading.Thread(target=self._preloader_loop, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Folder loading
    # ------------------------------------------------------------------

    def select_new_folder(self, folder: str):
        self.current_folder = folder
        self._stop_flag.set()
        self._pil_cache.clear()
        self._undo_stack.clear()
        self._locations.clear()

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

    def _actual_path(self, index: int) -> str:
        """Return the file's current physical location (may differ from all_files after sorting)."""
        loc = self._locations.get(index)
        return loc if loc is not None else self.all_files[index]

    def show_current(self):
        if not self.all_files:
            return

        path = self._actual_path(self.current_index)
        ext  = os.path.splitext(path)[1].lower()
        self._current_video_path = None

        if ext in VIDEO_EXTENSIONS:
            self._show_video(path)
        else:
            self._show_image(path)

        fname = os.path.basename(self.all_files[self.current_index])
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

    def sort_image(self, category: dict, advance: bool = True):
        """Move the current image to the category's subfolder.

        advance=False keeps the selection in place (used in grid mode so the
        user can re-sort the same image without auto-advancing).
        """
        if not self.all_files:
            return
        index = self.current_index
        path = self._actual_path(index)
        fname = os.path.basename(self.all_files[index])
        folder_name = category["folder"]
        dest_dir = os.path.join(self.current_folder, folder_name)
        Path(dest_dir).mkdir(exist_ok=True)
        dest = os.path.join(dest_dir, fname)

        try:
            shutil.move(path, dest)
        except Exception as e:
            messagebox.showerror("Move failed", str(e))
            return

        prev_status = self.status.get(fname, "")
        self.status[fname] = category["name"].lower()
        self._undo_stack.append((index, path, dest, prev_status))
        self._locations[index] = dest

        if self._on_sort:
            self._on_sort(index, fname, category["name"].lower())

        if advance:
            self.next_unsorted()

    def undo_last_move(self):
        if not self._undo_stack:
            messagebox.showinfo("Undo", "Nothing to undo.")
            return

        index, original, moved, prev_status = self._undo_stack.pop()
        fname = os.path.basename(self.all_files[index])
        try:
            shutil.move(moved, original)
        except Exception as e:
            messagebox.showerror("Undo failed", str(e))
            return

        self.status[fname] = prev_status
        self._locations[index] = original
        if self._on_sort:
            self._on_sort(index, fname, prev_status)
        self.current_index = index
        self.show_current()

    def return_to_inbox(self, advance: bool = True):
        """Move the current image back to the root folder, marking it unsorted."""
        if not self.all_files:
            return
        index = self.current_index
        path  = self._actual_path(index)
        fname = os.path.basename(self.all_files[index])
        dest  = os.path.join(self.current_folder, fname)

        if os.path.normpath(path) == os.path.normpath(dest):
            return  # already in inbox

        try:
            shutil.move(path, dest)
        except Exception as e:
            messagebox.showerror("Move failed", str(e))
            return

        prev_status = self.status.get(fname, "")
        self.status[fname] = ""
        self._undo_stack.append((index, path, dest, prev_status))
        self._locations[index] = dest

        if self._on_sort:
            self._on_sort(index, fname, "")

        if advance:
            self.next_unsorted()
        else:
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
            path = self._actual_path(idx)
            ext  = os.path.splitext(path)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                continue
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
            return self._actual_path(self.current_index)
        return None
