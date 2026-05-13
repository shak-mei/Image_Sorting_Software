"""
Image Sorter — main application window.

Layout (top → bottom):
  InfoFrame        folder / file name / progress counter
  ─────────────────────────────────────────────────────
  ViewFrame        ImageSorter  ┃  MetadataPanel (toggleable)
  ─────────────────────────────────────────────────────
  TagBar           tag chips + autocomplete input
  ─────────────────────────────────────────────────────
  ControlPanel     nav ← →  |  sort buttons  |  view toggles

Keyboard shortcuts
  Ctrl+O        Open folder
  S / A         Star / Archive  (built-in)
  D / F / G     Custom category 1 / 2 / 3  (if defined)
  ← → ↑ ↓      Navigate (single view: prev/next; grid: by column/row)
  Z             Undo
  I             Return to Inbox (move back to root folder, mark unsorted)
  G             Toggle grid / single view
  M             Toggle metadata panel
  Q             Quit
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import db
import tag_manager
import image_sorter as sorter_module
from metadata_panel import MetadataPanel
from grid_view import GridView
from category_dialog import CategoryDialog, BUILTIN_CATEGORIES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(path: str, max_len: int = 60) -> str:
    return path if len(path) <= max_len else "…" + path[-(max_len - 1):]


# ---------------------------------------------------------------------------
# InfoFrame
# ---------------------------------------------------------------------------

class InfoFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._folder_lbl = ttk.Label(self, text="Folder: —", foreground="#888888",
                                      font=("Segoe UI", 8))
        self._folder_lbl.pack(side="left", padx=10)

        self._file_lbl = ttk.Label(self, text="", font=("Segoe UI", 9, "bold"))
        self._file_lbl.pack(side="left", padx=10)

        self._counter_lbl = ttk.Label(self, text="", foreground="#888888",
                                       font=("Segoe UI", 9))
        self._counter_lbl.pack(side="right", padx=10)

        self._status_lbl = ttk.Label(self, text="", foreground="#4CAF50",
                                      font=("Segoe UI", 8))
        self._status_lbl.pack(side="right", padx=6)

    def update_folder_label(self, folder: str):
        self._folder_lbl.configure(text=f"Folder: {_short(folder)}")

    def update_file_label_and_index(self, fname: str, index: int, total: int):
        self._file_lbl.configure(text=fname)
        self._counter_lbl.configure(text=f"{index} / {total}")

    def set_status(self, text: str, color: str = "#4CAF50"):
        self._status_lbl.configure(text=text, foreground=color)


# ---------------------------------------------------------------------------
# TagBar
# ---------------------------------------------------------------------------

class TagBar(ttk.Frame):
    """Shows current image's tags as removable chips + autocomplete input."""

    def __init__(self, parent, on_tags_changed):
        super().__init__(parent)
        self._on_tags_changed = on_tags_changed
        self._image_path: str | None = None
        self._session_folder: str | None = None
        self._tags: list[str] = []

        ttk.Label(self, text="Tags:", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(8, 4))

        self._chips_frame = ttk.Frame(self)
        self._chips_frame.pack(side="left", fill="x")

        self._entry_var = tk.StringVar()
        self._entry = ttk.Entry(self, textvariable=self._entry_var, width=18,
                                 font=("Segoe UI", 8))
        self._entry.pack(side="left", padx=4)
        self._entry.bind("<Return>",     self._add_from_entry)
        self._entry.bind("<Tab>",        self._autocomplete)
        self._entry.bind("<KeyRelease>", self._on_key_release)
        self._entry.bind("<Escape>",     self._on_escape)

        self._dropdown = tk.Listbox(self, height=5, font=("Segoe UI", 8),
                                     activestyle="dotbox", relief="flat",
                                     selectbackground="#1565C0")
        self._dropdown_visible = False
        self._dropdown.bind("<<ListboxSelect>>", self._on_dropdown_select)

        self._all_tags: list[str] = []
        self._refresh_all_tags()

    def _refresh_all_tags(self):
        self._all_tags = tag_manager.get_all_tag_names()

    def load_image(self, image_path: str | None, session_folder: str | None):
        self._image_path   = image_path
        self._session_folder = session_folder
        self._tags = tag_manager.get_image_tags(image_path) if image_path else []
        self._entry_var.set("")
        self._hide_dropdown()
        self._render_chips()

    def _render_chips(self):
        for w in self._chips_frame.winfo_children():
            w.destroy()
        for tag in self._tags:
            chip = ttk.Frame(self._chips_frame, style="Chip.TFrame")
            chip.pack(side="left", padx=2, pady=2)
            ttk.Label(chip, text=tag, font=("Segoe UI", 8),
                       padding=(4, 1)).pack(side="left")
            ttk.Button(chip, text="✕", width=1,
                        command=lambda t=tag: self._remove_tag(t)).pack(side="left")

    def _add_tag(self, name: str):
        name = name.strip()
        if not name or name in self._tags:
            return
        if self._image_path and self._session_folder:
            tag_manager.tag_image(self._image_path, name, self._session_folder)
        self._tags.append(name)
        self._refresh_all_tags()
        self._render_chips()
        self._entry_var.set("")
        self._hide_dropdown()
        if self._on_tags_changed:
            self._on_tags_changed(self._image_path, self._tags)

    def _remove_tag(self, name: str):
        if self._image_path:
            tag_manager.untag_image(self._image_path, name)
        self._tags = [t for t in self._tags if t != name]
        self._render_chips()
        if self._on_tags_changed:
            self._on_tags_changed(self._image_path, self._tags)

    def _add_from_entry(self, _event=None):
        self._add_tag(self._entry_var.get())
        return "break"

    def _autocomplete(self, _event=None):
        typed = self._entry_var.get().strip().lower()
        matches = [t for t in self._all_tags if t.lower().startswith(typed) and t not in self._tags]
        if len(matches) == 1:
            self._add_tag(matches[0])
        elif matches:
            self._show_dropdown(matches)
        return "break"

    def _on_key_release(self, _event):
        typed = self._entry_var.get().strip()
        if not typed:
            self._hide_dropdown()
            return
        matches = [t for t in self._all_tags
                   if typed.lower() in t.lower() and t not in self._tags]
        if matches:
            self._show_dropdown(matches)
        else:
            self._hide_dropdown()

    def _show_dropdown(self, items: list[str]):
        self._dropdown.delete(0, "end")
        for item in items[:8]:
            self._dropdown.insert("end", item)
        if not self._dropdown_visible:
            self._dropdown.place(in_=self._entry,
                                  x=0, y=self._entry.winfo_height(),
                                  width=self._entry.winfo_width() * 2)
            self._dropdown.lift()
            self._dropdown_visible = True

    def _hide_dropdown(self):
        if self._dropdown_visible:
            self._dropdown.place_forget()
            self._dropdown_visible = False

    def _on_dropdown_select(self, _event):
        sel = self._dropdown.curselection()
        if sel:
            self._add_tag(self._dropdown.get(sel[0]))

    def _on_escape(self, _event):
        self._entry_var.set("")
        self._hide_dropdown()
        self.winfo_toplevel().focus_set()  # hand focus back to main window


# ---------------------------------------------------------------------------
# ControlPanel
# ---------------------------------------------------------------------------

class ControlPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self._app = app
        self._category_buttons: list[ttk.Button] = []
        self._build_static()

    def _build_static(self):
        # Navigation
        ttk.Button(self, text="←  Prev",
                    command=self._app.prev_image).pack(side="left", padx=4, pady=4)
        ttk.Button(self, text="Next  →",
                    command=self._app.next_image).pack(side="left", padx=4, pady=4)

        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=6, pady=4)

        # Undo
        ttk.Button(self, text="Undo (Z)",
                    command=self._app.undo).pack(side="left", padx=4, pady=4)

        # Right side
        ttk.Button(self, text="Categories…",
                    command=self._app.open_category_dialog).pack(side="right", padx=4, pady=4)
        ttk.Button(self, text="ℹ Meta (M)",
                    command=self._app.toggle_metadata).pack(side="right", padx=4, pady=4)
        ttk.Button(self, text="⊞ Grid (G)",
                    command=self._app.toggle_grid).pack(side="right", padx=4, pady=4)

        ttk.Separator(self, orient="vertical").pack(side="right", fill="y", padx=6, pady=4)

    def rebuild_category_buttons(self, categories: list[dict]):
        for btn in self._category_buttons:
            btn.destroy()
        self._category_buttons.clear()

        for cat in categories:
            btn = ttk.Button(
                self,
                text=f"{cat['name']}  ({cat['shortcut'].upper()})",
                command=lambda c=cat: self._app.sort_image(c),
            )
            btn.pack(side="left", padx=3, pady=4)
            self._category_buttons.append(btn)


# ---------------------------------------------------------------------------
# Session Summary Dialog
# ---------------------------------------------------------------------------

class HelpDialog(tk.Toplevel):
    """Non-modal help window explaining the workflow and all keyboard shortcuts."""

    def __init__(self, parent, categories: list[dict]):
        super().__init__(parent)
        self.title("Help — Image Sorter")
        self.resizable(True, True)
        self.geometry("560x620")
        self.minsize(480, 400)

        # Scrollable canvas so the content is never clipped
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        inner = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        pad = {"padx": 20, "pady": 3}

        def heading(text):
            ttk.Label(inner, text=text, font=("Segoe UI", 11, "bold"),
                      foreground="#1565C0").pack(anchor="w", padx=20, pady=(14, 2))
            ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=20, pady=(0, 4))

        def para(text):
            ttk.Label(inner, text=text, font=("Segoe UI", 9),
                      wraplength=500, justify="left").pack(anchor="w", **pad)

        def row(key, desc, key_width=18):
            f = ttk.Frame(inner)
            f.pack(fill="x", padx=20, pady=1)
            ttk.Label(f, text=key, font=("Courier New", 9, "bold"),
                      foreground="#1565C0", width=key_width, anchor="w").pack(side="left")
            ttk.Label(f, text=desc, font=("Segoe UI", 9)).pack(side="left")

        # ── Overview ──────────────────────────────────────────────────
        heading("How it works")
        para(
            "Open a folder (File > Open Folder or Ctrl+O). The app scans for images "
            "and videos. Browse through them one at a time and press a shortcut key to "
            "move each file into a subfolder (Starred, Archive, or a custom category). "
            "You can undo any move, tag images for later searching, and switch to the "
            "Grid view to see your whole session at a glance."
        )

        # ── Opening a folder ─────────────────────────────────────────
        heading("Opening a folder")
        para(
            "Use File > Open Folder or press Ctrl+O. The app automatically creates "
            "subfolders (starred/, archive/, and any custom ones) inside the chosen folder. "
            "It supports images (.jpg .png .gif .bmp .webp .tiff) and videos (.mp4 .mov "
            ".avi .mkv .wmv and more)."
        )

        # ── Sorting ──────────────────────────────────────────────────
        heading("Sorting")
        para(
            "Each file is shown full-screen. Press the shortcut for a category to move "
            "the file and automatically advance to the next unsorted item. "
            "You can revisit already-sorted files in Grid view and re-sort them."
        )

        # ── Keyboard shortcuts ────────────────────────────────────────
        heading("Keyboard shortcuts")

        # Navigation
        ttk.Label(inner, text="Navigation", font=("Segoe UI", 9, "italic"),
                  foreground="#555555").pack(anchor="w", padx=20, pady=(4, 0))
        row("→ / ← / ↓ / ↑",  "Next / Prev (single view);  or move by column / row in Grid")
        row("Ctrl + O",        "Open a folder")
        row("Q",               "Quit the application")

        # Sorting
        ttk.Label(inner, text="Sorting", font=("Segoe UI", 9, "italic"),
                  foreground="#555555").pack(anchor="w", padx=20, pady=(8, 0))
        for cat in categories:
            row(cat["shortcut"].upper(), f"{cat['name']}  →  moves file to  {cat['folder']}/")
        row("Z",               "Undo the last move")
        row("I",               "Return to Inbox — move back to root folder, mark unsorted")

        # Views
        ttk.Label(inner, text="Views & panels", font=("Segoe UI", 9, "italic"),
                  foreground="#555555").pack(anchor="w", padx=20, pady=(8, 0))
        row("G",               "Toggle Grid overview / Single-image view")
        row("M",               "Toggle Metadata sidebar (EXIF, file info, tags)")

        # ── Tags ─────────────────────────────────────────────────────
        heading("Tags")
        para(
            "Type a tag name in the Tag bar at the bottom and press Enter to add it to the "
            "current image. Start typing to see autocomplete suggestions drawn from every "
            "tag you have ever used — this prevents 'kids' and 'children' from becoming "
            "separate tags by mistake. Click the  ✕  on any chip to remove a tag. "
            "Tags are stored in a database at  ~/.image_sorter/data.db  and persist across sessions."
        )

        # ── Grid view ────────────────────────────────────────────────
        heading("Grid view  (G)")
        para(
            "Shows all images in the folder as thumbnails. Sorted images display a "
            "coloured badge (gold = Starred, grey = Archive, blue = custom). "
            "Click any thumbnail to jump straight to it in single-image view."
        )

        # ── Custom categories ────────────────────────────────────────
        heading("Custom categories")
        para(
            "Open Sort > Manage Categories to add up to 3 extra categories beyond "
            "Starred and Archive. Each gets a name and a single-key shortcut. "
            "You can save and reload named presets so your favourite category sets "
            "are always one click away."
        )

        # ── Videos ──────────────────────────────────────────────────
        heading("Videos")
        para(
            "Video files are shown with a thumbnail from their first frame and a "
            "Play button that opens the file in your system's default video player. "
            "Sorting works the same as for images."
        )

        # ── Session summary ──────────────────────────────────────────
        heading("Session summary")
        para(
            "When every image has been sorted, a summary dialog appears with counts "
            "per category and three optional actions: copy Starred files to another "
            "folder, organise remaining files into YYYY-MM subfolders by EXIF date, "
            "or export a CSV report of every file and its action."
        )

        ttk.Button(inner, text="Close", command=self.destroy).pack(pady=16)


class SessionSummaryDialog(tk.Toplevel):
    def __init__(self, parent, status: dict, folder: str, categories: list[dict]):
        super().__init__(parent)
        self.title("Session Complete")
        self.resizable(False, False)
        self.grab_set()

        counts: dict[str, int] = {}
        unsorted = 0
        for fname, action in status.items():
            if action:
                counts[action] = counts.get(action, 0) + 1
            else:
                unsorted += 1

        ttk.Label(self, text="Sorting session summary",
                  font=("Segoe UI", 11, "bold")).pack(padx=20, pady=(16, 8))

        frame = ttk.Frame(self)
        frame.pack(padx=20, pady=4)

        for cat in categories:
            key = cat["name"].lower()
            count = counts.get(key, 0)
            ttk.Label(frame, text=f"{cat['name']}:", width=14, anchor="w").grid(
                row=categories.index(cat), column=0, sticky="w")
            ttk.Label(frame, text=str(count), font=("Segoe UI", 9, "bold")).grid(
                row=categories.index(cat), column=1, sticky="w", padx=8)

        if unsorted:
            row_idx = len(categories)
            ttk.Label(frame, text="Unsorted:", width=14, anchor="w",
                      foreground="#FF7043").grid(row=row_idx, column=0, sticky="w")
            ttk.Label(frame, text=str(unsorted),
                      foreground="#FF7043", font=("Segoe UI", 9, "bold")).grid(
                row=row_idx, column=1, sticky="w", padx=8)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=16, pady=8)

        # Post-sort actions
        ttk.Label(self, text="Post-sort actions",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=20)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(padx=20, pady=6, fill="x")

        ttk.Button(btn_frame, text="Copy ⭐ Starred to another folder…",
                    command=lambda: self._copy_starred(folder)).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Organize remaining by date (YYYY-MM)",
                    command=lambda: self._run_date_sort(folder)).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Export CSV report…",
                    command=lambda: self._export_csv(folder, status)).pack(fill="x", pady=2)

        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

    def _copy_starred(self, folder: str):
        src = os.path.join(folder, "starred")
        if not os.path.isdir(src):
            messagebox.showinfo("Nothing to copy", "No 'starred' folder found.", parent=self)
            return
        dest = filedialog.askdirectory(title="Copy starred images to…", parent=self)
        if not dest:
            return
        import shutil
        for fname in os.listdir(src):
            shutil.copy2(os.path.join(src, fname), os.path.join(dest, fname))
        messagebox.showinfo("Done", f"Copied starred images to:\n{dest}", parent=self)

    def _run_date_sort(self, folder: str):
        import date_sorter
        date_sorter.organize_images_by_month(folder)
        messagebox.showinfo("Done", "Images organised into YYYY-MM subfolders.", parent=self)

    def _export_csv(self, folder: str, status: dict):
        import csv
        dest = filedialog.asksaveasfilename(
            title="Save CSV", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")], parent=self
        )
        if not dest:
            return
        with open(dest, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "action"])
            for fname, action in status.items():
                w.writerow([fname, action or "unsorted"])
        messagebox.showinfo("Exported", f"Report saved to:\n{dest}", parent=self)


# ---------------------------------------------------------------------------
# Exit confirmation dialog
# ---------------------------------------------------------------------------

class ExitConfirmDialog(tk.Toplevel):
    """Ask the user whether to exit, optionally reviewing the session summary first."""

    def __init__(self, parent, sorted_count: int, total_count: int):
        super().__init__(parent)
        self.title("Exit")
        self.resizable(False, False)
        self.grab_set()
        self.result: str | None = None  # "exit" | "summary" | None (cancelled)

        msg = (f"You have sorted {sorted_count} of {total_count} image(s).\n"
               "Are you sure you want to quit?")
        ttk.Label(self, text=msg, font=("Segoe UI", 10),
                  wraplength=340, justify="center").pack(padx=24, pady=(20, 12))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(padx=24, pady=(0, 18))
        ttk.Button(btn_frame, text="View Summary & Exit",
                   command=lambda: self._close("summary")).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Exit",
                   command=lambda: self._close("exit")).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Cancel",
                   command=lambda: self._close(None)).pack(side="left", padx=4)

        self.bind("<Escape>", lambda _: self._close(None))

    def _close(self, result):
        self.result = result
        self.destroy()


# ---------------------------------------------------------------------------
# MainApp
# ---------------------------------------------------------------------------

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        db.init_db()

        self.title("Image Sorter")
        self.geometry("1200x800")
        self.state("zoomed")
        self.configure(bg="#1e1e1e")

        self._categories = list(BUILTIN_CATEGORIES)
        self._current_folder: str | None = None
        self._grid_mode = False
        self._meta_visible = False

        # -- Info bar --
        self._info_frame = InfoFrame(self)
        self._info_frame.pack(fill="x", padx=4, pady=(4, 0))
        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # -- Main content area --
        self._content = ttk.Frame(self)
        self._content.pack(fill="both", expand=True)

        # View container (left)
        self._view_frame = ttk.Frame(self._content)
        self._view_frame.pack(side="left", fill="both", expand=True)

        # ImageSorter (single-image mode)
        self._sorter = sorter_module.ImageSorter(
            self._view_frame, self._info_frame,
            on_image_changed=self._on_image_changed,
            on_sort=self._on_sort,
        )
        self._sorter.pack(fill="both", expand=True)

        # GridView (hidden initially)
        self._grid = GridView(self._view_frame,
                              on_select_callback=self._on_grid_select,
                              on_open_callback=self._on_grid_open)

        # MetadataPanel (hidden initially)
        self._meta = MetadataPanel(self._content)

        # -- Tag bar --
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._tag_bar = TagBar(self, on_tags_changed=self._on_tags_changed)
        self._tag_bar.pack(fill="x", padx=4, pady=2)

        # -- Control panel --
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._ctrl = ControlPanel(self, self)
        self._ctrl.pack(fill="x")
        self._ctrl.rebuild_category_buttons(self._categories)

        # -- Menu --
        self._build_menu()

        # -- Keyboard shortcuts --
        self._bind_keys()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        print("Image Sorter ready.")

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self):
        bar = tk.Menu(self)
        self.config(menu=bar)

        file_menu = tk.Menu(bar, tearoff=0)
        bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Folder…   Ctrl+O", command=self.select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        view_menu = tk.Menu(bar, tearoff=0)
        bar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Grid (G)",       command=self.toggle_grid)
        view_menu.add_command(label="Toggle Metadata (M)",   command=self.toggle_metadata)

        sort_menu = tk.Menu(bar, tearoff=0)
        bar.add_cascade(label="Sort", menu=sort_menu)
        sort_menu.add_command(label="Manage Categories…",    command=self.open_category_dialog)
        sort_menu.add_command(label="Undo Last (Z)",         command=self.undo)

        help_menu = tk.Menu(bar, tearoff=0)
        bar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="How to Use / Keyboard Shortcuts", command=self._show_help)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _bind_keys(self):
        # Ctrl+O — open folder
        self.bind_all("<Control-o>", lambda e: self.select_folder())

        # All single-key shortcuts go through one handler so we can gate
        # on focus: if a text widget (Entry, Combobox, dialog) has focus,
        # let the keystroke through normally and skip the shortcut.
        self.bind_all("<KeyPress>", self._on_keypress)

    def _focus_is_text(self) -> bool:
        """Return True when keyboard focus is inside a text input or any dialog."""
        focused = self.focus_get()
        if focused is None:
            return False
        # Any modal dialog / Toplevel that isn't the main window
        if focused.winfo_toplevel() is not self:
            return True
        return focused.winfo_class() in ("Entry", "TEntry", "TCombobox", "Text", "Listbox")

    def _on_keypress(self, event: tk.Event):
        if self._focus_is_text():
            return  # let the widget handle the keystroke normally

        key = event.keysym.lower()

        if key == "right":
            if self._grid_mode:
                self._grid_navigate(+1)
            else:
                self.next_image()
        elif key == "left":
            if self._grid_mode:
                self._grid_navigate(-1)
            else:
                self.prev_image()
        elif key == "down":
            if self._grid_mode:
                self._grid_navigate(+self._grid.cols)
            else:
                self.next_image()
        elif key == "up":
            if self._grid_mode:
                self._grid_navigate(-self._grid.cols)
            else:
                self.prev_image()
        elif key == "z":
            self.undo()
        elif key == "i":
            self.return_to_inbox()
        elif key == "q":
            self._on_close()
        elif key == "m":
            self.toggle_metadata()
        elif key == "g":
            self.toggle_grid()
        else:
            for cat in self._categories:
                if key == cat["shortcut"].lower():
                    self.sort_image(cat)
                    return "break"

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def _on_close(self):
        sorted_count = sum(1 for v in self._sorter.status.values() if v)
        if sorted_count == 0:
            if messagebox.askyesno("Exit", "Are you sure you want to quit?", parent=self):
                self.destroy()
            return
        dlg = ExitConfirmDialog(self, sorted_count, len(self._sorter.all_files))
        self.wait_window(dlg)
        if dlg.result == "exit":
            self.destroy()
        elif dlg.result == "summary":
            summary = SessionSummaryDialog(self, self._sorter.status,
                                           self._current_folder or "", self._categories)
            self.wait_window(summary)
            self.destroy()

    # ------------------------------------------------------------------
    # Folder selection
    # ------------------------------------------------------------------

    def select_folder(self):
        sorted_count = sum(1 for v in self._sorter.status.values() if v)
        if sorted_count > 0:
            choice = messagebox.askyesnocancel(
                "Active Session",
                f"You have {sorted_count} sorted image(s) in the current session.\n\n"
                "View the session summary before loading a new folder?\n\n"
                "(Yes = show summary first,  No = skip,  Cancel = don't open)",
                parent=self,
            )
            if choice is None:
                return
            if choice:
                dlg = SessionSummaryDialog(self, self._sorter.status,
                                           self._current_folder or "", self._categories)
                self.wait_window(dlg)

        folder = filedialog.askdirectory(title="Select folder containing images")
        if not folder:
            return
        self._current_folder = folder

        # Create subfolders for all categories
        for cat in self._categories:
            Path(os.path.join(folder, cat["folder"])).mkdir(exist_ok=True)

        self._info_frame.update_folder_label(folder)
        self._sorter.select_new_folder(folder)

        # Prime the grid but don't switch to it
        self._grid.load_folder(
            self._sorter.all_files,
            self._sorter.status,
            self._sorter.current_index,
        )
        self._info_frame.set_status("")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def next_image(self):
        self._sorter.next_image()

    def prev_image(self):
        self._sorter.previous_image()

    def undo(self):
        self._sorter.undo_last_move()

    def return_to_inbox(self):
        self._sorter.return_to_inbox(advance=not self._grid_mode)
        self._info_frame.set_status("→ Inbox", "#FF9800")

    def _grid_navigate(self, delta: int):
        new_idx = self._sorter.current_index + delta
        if 0 <= new_idx < len(self._sorter.all_files):
            self._sorter.jump_to(new_idx)

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def sort_image(self, category: dict):
        # In grid mode don't auto-advance; stay on the current image so the
        # user can immediately re-sort or inspect the badge change.
        self._sorter.sort_image(category, advance=not self._grid_mode)

    # ------------------------------------------------------------------
    # View toggles
    # ------------------------------------------------------------------

    def toggle_grid(self):
        if self._grid_mode:
            self._grid.pack_forget()
            self._sorter.pack(fill="both", expand=True)
            self._grid_mode = False
            self._sorter.show_current()   # refresh info bar + image after grid navigation
        else:
            self._sorter.pack_forget()
            self._grid.pack(fill="both", expand=True)
            self._grid.set_current(self._sorter.current_index)
            self._grid_mode = True

    def toggle_metadata(self):
        if self._meta_visible:
            self._meta.pack_forget()
            self._meta_visible = False
        else:
            self._meta.pack(side="right", fill="y", padx=(0, 4), pady=4)
            self._meta_visible = True
            self._refresh_metadata()

    def _refresh_metadata(self):
        if not self._meta_visible:
            return
        path = self._sorter.current_path()
        tags = tag_manager.get_image_tags(path) if path else []
        self._meta.update_for_image(path or "", tags)

    # ------------------------------------------------------------------
    # Callbacks from ImageSorter
    # ------------------------------------------------------------------

    def _on_image_changed(self, index: int, path: str):
        self._tag_bar.load_image(path, self._current_folder)
        self._refresh_metadata()
        if self._grid_mode:
            self._grid.set_current(index)

    def _on_sort(self, index: int, fname: str, action: str):
        if action == "__complete__":
            self._info_frame.set_status("All sorted!", "#4CAF50")
            self._show_session_summary()
            return
        if fname:
            self._grid.update_status(fname, action)
            if action:
                self._info_frame.set_status(f"→ {action}", "#64B5F6")
            else:
                self._info_frame.set_status("Undone", "#FF7043")

    def _on_tags_changed(self, path: str | None, tags: list[str]):
        if path:
            tag_manager.write_tags_to_file(path, tags)
        self._refresh_metadata()

    # ------------------------------------------------------------------
    # Grid click
    # ------------------------------------------------------------------

    def _on_grid_select(self, index: int):
        """Single click — navigate to image, stay in grid."""
        self._sorter.jump_to(index)

    def _on_grid_open(self, index: int):
        """Double click — navigate to image and return to single view."""
        self._sorter.jump_to(index)
        if self._grid_mode:
            self.toggle_grid()

    # ------------------------------------------------------------------
    # Category management
    # ------------------------------------------------------------------

    def open_category_dialog(self):
        custom_current = [c for c in self._categories if not c.get("builtin")]
        dlg = CategoryDialog(self, custom_current)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._categories = dlg.result
            # Create folders if folder is open
            if self._current_folder:
                for cat in self._categories:
                    Path(os.path.join(self._current_folder, cat["folder"])).mkdir(exist_ok=True)
            self._ctrl.rebuild_category_buttons(self._categories)

    # ------------------------------------------------------------------
    # Session summary
    # ------------------------------------------------------------------

    def _show_help(self):
        HelpDialog(self, self._categories)

    def _show_session_summary(self):
        SessionSummaryDialog(self, self._sorter.status,
                              self._current_folder or "", self._categories)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
