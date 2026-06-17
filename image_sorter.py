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
    Single-image viewer with mark-then-finalize workflow:
    - Images are never moved during a session; sorting only updates an in-memory
      status dict.
    - finalize_moves() performs all the actual file moves at once.
    - On load, files already in category subfolders are included with their
      category pre-populated, so the Starred/Archive views show both previous
      sessions and new marks from the current session.
    - Callbacks: on_image_changed(index, path), on_sort(index, orig_path, action)
    """

    def __init__(self, parent, info_frame,
                 on_image_changed=None, on_sort=None):
        super().__init__(parent)
        self.info_frame = info_frame
        self._on_image_changed = on_image_changed
        self._on_sort          = on_sort

        self.current_folder: str | None = None

        # Current view's file list (filtered slice of master data)
        self.all_files: list[str] = []
        self.current_index: int = 0

        # Master data — populated once per folder, survives view switches
        self._master_files: list[str] = []
        self._master_homes: dict[str, str] = {}          # path → home folder for sorting
        self._master_initial_status: dict[str, str] = {} # path → status at load time
        self._inbox_set: set[str] = set()                # paths that live in non-category dirs

        # Shared mutable status — ALL marks for ALL views, keyed by original file path
        self.status: dict[str, str] = {}

        # Home folders indexed for the current view (rebuilt on each view switch)
        self._home_folders: dict[int, str] = {}

        # Undo: list of (file_path, prev_status) — no file moves to track
        self._undo_stack: list[tuple[str, str]] = []

        # View mode: "unsorted", "all", or a category folder name like "starred"/"archive"
        self._view_mode: str = "all"

        self._pil_cache: dict[str, Image.Image] = {}
        self._cache_lock = threading.Lock()
        self._preload_event = threading.Event()
        self._stop_flag = threading.Event()

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

    def select_new_folder(self, folder: str, categories: list[dict]):
        """Scan folder recursively, collecting every image/video including those
        already inside category subfolders.  Sets initial status from location."""
        self.current_folder = folder
        self._stop_flag.set()
        self._pil_cache.clear()
        self._undo_stack.clear()

        folder_to_cat = {cat["folder"].lower(): cat["name"].lower() for cat in categories}

        master_files: list[str] = []
        master_homes: dict[str, str] = {}
        master_initial: dict[str, str] = {}
        inbox_set: set[str] = set()

        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames.sort()
            dir_name = os.path.basename(dirpath).lower()

            # Category folders are processed by their parent — skip them here
            if dir_name in folder_to_cat:
                dirnames.clear()
                continue

            # Collect this directory's files together with files already in
            # category subfolders, then sort the combined list by filename so
            # the original per-folder order is preserved across all categories.
            dir_entries: list[tuple[str, str, str, bool]] = []  # (sort_key, fpath, initial_status, in_cat)

            for fname in filenames:
                if os.path.splitext(fname)[1].lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    dir_entries.append((fname.lower(), os.path.join(dirpath, fname), "", False))

            for subdir in os.listdir(dirpath):
                if subdir.lower() in folder_to_cat:
                    subdir_path = os.path.join(dirpath, subdir)
                    if os.path.isdir(subdir_path):
                        cat_status = folder_to_cat[subdir.lower()]
                        for fname in os.listdir(subdir_path):
                            if os.path.splitext(fname)[1].lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                                dir_entries.append((fname.lower(), os.path.join(subdir_path, fname), cat_status, True))

            dir_entries.sort(key=lambda e: e[0])

            for _, fpath, initial_status, in_cat in dir_entries:
                master_files.append(fpath)
                master_homes[fpath] = dirpath
                master_initial[fpath] = initial_status
                if not in_cat:
                    inbox_set.add(fpath)

            # Don't let os.walk descend into category subfolders
            dirnames[:] = [d for d in dirnames if d.lower() not in folder_to_cat]

        self._master_files = master_files
        self._master_homes = master_homes
        self._master_initial_status = master_initial
        self._inbox_set = inbox_set
        # Status starts equal to initial (pre-sorted files keep their category)
        self.status = dict(master_initial)

        self._activate_view("all")

    def _activate_view(self, view_mode: str):
        """Rebuild all_files and home_folders for the requested view, then show."""
        self._view_mode = view_mode
        self._stop_flag.set()

        if view_mode == "unsorted":
            view_files = [f for f in self._master_files if f in self._inbox_set]
        elif view_mode == "all":
            view_files = list(self._master_files)
        else:
            view_files = [
                f for f in self._master_files
                if self.status.get(f, "") == view_mode
            ]

        self.all_files = view_files
        self._home_folders = {i: self._master_homes[f] for i, f in enumerate(view_files)}
        self.current_index = 0
        self._stop_flag.clear()

        if self.all_files:
            self._preload_event.set()
            self.show_current()

    def load_category_view(self, target_folder: str, _categories: list[dict] = None):
        """Switch to a category view (starred / archive / custom)."""
        if not self.current_folder:
            return
        self._activate_view(target_folder.lower())

    # ------------------------------------------------------------------
    # Finalization — the only place files actually move
    # ------------------------------------------------------------------

    def finalize_moves(self, categories: list[dict]) -> dict[str, int]:
        """Move every file to its destination according to the current status.
        Returns {category_or_inbox: count_moved}."""
        folder_for = {cat["name"].lower(): cat["folder"] for cat in categories}
        counts: dict[str, int] = {}
        errors: list[str] = []

        for fpath in self._master_files:
            if not os.path.exists(fpath):
                continue  # already moved (e.g., by a previous finalize)
            current_status = self.status.get(fpath, "")
            home = self._master_homes.get(fpath, self.current_folder)
            fname = os.path.basename(fpath)

            if current_status == "":
                dest = os.path.join(home, fname)
            else:
                cat_folder = folder_for.get(current_status, current_status)
                dest = os.path.join(home, cat_folder, fname)

            if os.path.normpath(fpath) == os.path.normpath(dest):
                continue  # already in the right place

            try:
                Path(os.path.dirname(dest)).mkdir(parents=True, exist_ok=True)
                shutil.move(fpath, dest)
                key = current_status if current_status else "unsorted"
                counts[key] = counts.get(key, 0) + 1
            except Exception as e:
                errors.append(f"{fname}: {e}")

        if errors:
            messagebox.showerror(
                "Some moves failed",
                "\n".join(errors[:10]) + ("\n…" if len(errors) > 10 else ""),
            )

        return counts

    def pending_move_count(self) -> int:
        """Count files whose current status differs from their status at load time."""
        return sum(
            1 for f in self._master_files
            if self.status.get(f, "") != self._master_initial_status.get(f, "")
        )

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
        """Advance to the next image that hasn't been marked yet (unsorted view only)."""
        start = self.current_index + 1
        for i in range(start, len(self.all_files)):
            if not self.status.get(self.all_files[i]):
                self.current_index = i
                self.show_current()
                return
        if not any(not self.status.get(f) for f in self.all_files):
            self._signal_complete()

    def _signal_complete(self):
        if self._on_sort:
            self._on_sort(-1, "", "__complete__")

    def _advance_after_sort(self):
        """Next-unmarked in unsorted mode; sequential advance in all other views."""
        if self._view_mode == "unsorted":
            self.next_unsorted()
        elif self.current_index < len(self.all_files) - 1:
            self.current_index += 1
            self.show_current()

    # ------------------------------------------------------------------
    # Sorting — mark only, no file moves
    # ------------------------------------------------------------------

    def sort_image(self, category: dict, advance: bool = True):
        """Mark the current image with a category.  No file is moved."""
        if not self.all_files:
            return
        index = self.current_index
        orig_path = self.all_files[index]
        new_status = category["name"].lower()
        prev_status = self.status.get(orig_path, "")

        if prev_status == new_status:
            if advance:
                self._advance_after_sort()
            return

        self.status[orig_path] = new_status
        self._undo_stack.append((orig_path, prev_status))

        if self._on_sort:
            self._on_sort(index, orig_path, new_status)

        if advance:
            self._advance_after_sort()

    def undo_last_move(self):
        """Undo the last mark change."""
        if not self._undo_stack:
            messagebox.showinfo("Undo", "Nothing to undo.")
            return

        orig_path, prev_status = self._undo_stack.pop()
        self.status[orig_path] = prev_status

        view_idx = next((i for i, f in enumerate(self.all_files) if f == orig_path), None)
        if self._on_sort:
            self._on_sort(view_idx if view_idx is not None else -1, orig_path, prev_status)
        if view_idx is not None:
            self.current_index = view_idx
            self.show_current()

    def return_to_inbox(self, advance: bool = True):
        """Clear the mark on the current image (return it to unsorted state)."""
        if not self.all_files:
            return
        index = self.current_index
        orig_path = self.all_files[index]
        prev_status = self.status.get(orig_path, "")

        if not prev_status:
            return  # already unmarked

        self.status[orig_path] = ""
        self._undo_stack.append((orig_path, prev_status))

        if self._on_sort:
            self._on_sort(index, orig_path, "")

        if advance:
            self._advance_after_sort()
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
        with Image.open(path) as raw:
            raw.load()
            img = self._fix_orientation(raw).copy()
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
                continue
            fname = os.path.basename(path)
            with self._cache_lock:
                if fname in self._pil_cache:
                    continue
            try:
                with Image.open(path) as raw:
                    raw.load()
                    img = self._fix_orientation(raw).copy()
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
