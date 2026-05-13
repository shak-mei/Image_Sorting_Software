import json
import tkinter as tk
from tkinter import ttk, messagebox
from db import get_connection

BUILTIN_CATEGORIES = [
    {"name": "Starred",  "folder": "starred",  "shortcut": "s", "color": "#FFD700", "builtin": True},
    {"name": "Archive",  "folder": "archive",  "shortcut": "a", "color": "#A0A0A0", "builtin": True},
]
MAX_CUSTOM = 3
DEFAULT_SHORTCUTS = ["d", "f", "g"]


def load_preset(preset_name: str) -> list[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT categories FROM category_presets WHERE preset_name = ?", (preset_name,)
        ).fetchone()
    if row:
        return json.loads(row["categories"])
    return []


def save_preset(preset_name: str, custom_categories: list[dict]):
    data = json.dumps(custom_categories)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO category_presets (preset_name, categories) VALUES (?, ?)",
            (preset_name, data),
        )


def list_presets() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT preset_name FROM category_presets ORDER BY preset_name").fetchall()
    return [r["preset_name"] for r in rows]


class CategoryDialog(tk.Toplevel):
    """
    Modal dialog to manage custom sort categories.
    Returns via self.result: list of all categories (builtins + custom) on OK,
    or None on cancel.
    """

    def __init__(self, parent, current_custom: list[dict]):
        super().__init__(parent)
        self.title("Manage Sort Categories")
        self.resizable(False, False)
        self.grab_set()
        self.result: list[dict] | None = None

        self._entries: list[dict] = []   # dicts with tk vars

        self._build_ui(current_custom)
        self.transient(parent)
        self.wait_visibility()
        self.focus_set()

    def _build_ui(self, current_custom: list[dict]):
        pad = {"padx": 10, "pady": 4}

        # --- Built-in (read-only) ---
        ttk.Label(self, text="Built-in categories (cannot be removed)",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", **pad)

        builtin_frame = ttk.Frame(self)
        builtin_frame.pack(fill="x", padx=10)
        for cat in BUILTIN_CATEGORIES:
            row = ttk.Frame(builtin_frame)
            row.pack(fill="x", pady=2)
            swatch = tk.Label(row, bg=cat["color"], width=2)
            swatch.pack(side="left", padx=(0, 6))
            ttk.Label(row, text=f"{cat['name']}  [key: {cat['shortcut'].upper()}]",
                      foreground="#555555").pack(side="left")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        # --- Custom ---
        ttk.Label(self, text=f"Custom categories (up to {MAX_CUSTOM})",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", **pad)

        self._custom_frame = ttk.Frame(self)
        self._custom_frame.pack(fill="x", padx=10)

        for i, cat in enumerate(current_custom[:MAX_CUSTOM]):
            self._add_row(cat.get("name", ""), cat.get("shortcut", DEFAULT_SHORTCUTS[i]))

        # Fill remaining slots up to MAX_CUSTOM to let user add
        # (rows are only added via _add_row when Add is clicked)

        self._add_btn = ttk.Button(self, text="+ Add Category", command=self._add_empty_row)
        self._add_btn.pack(anchor="w", padx=10, pady=4)
        self._refresh_add_btn()

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        # --- Presets ---
        preset_frame = ttk.Frame(self)
        preset_frame.pack(fill="x", padx=10)
        ttk.Label(preset_frame, text="Preset:").pack(side="left")
        self._preset_var = tk.StringVar()
        self._preset_combo = ttk.Combobox(preset_frame, textvariable=self._preset_var,
                                           width=20, state="normal")
        self._preset_combo["values"] = list_presets()
        self._preset_combo.pack(side="left", padx=4)
        ttk.Button(preset_frame, text="Load",  command=self._load_preset).pack(side="left", padx=2)
        ttk.Button(preset_frame, text="Save",  command=self._save_preset).pack(side="left", padx=2)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        # --- OK / Cancel ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=6)
        ttk.Button(btn_frame, text="OK",     command=self._ok).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")

    def _add_row(self, name: str = "", shortcut: str = ""):
        idx = len(self._entries)
        if idx >= MAX_CUSTOM:
            return

        if not shortcut:
            used = {e["shortcut"].get() for e in self._entries}
            shortcut = next((s for s in DEFAULT_SHORTCUTS if s not in used), "")

        row = ttk.Frame(self._custom_frame)
        row.pack(fill="x", pady=2)

        name_var = tk.StringVar(value=name)
        key_var  = tk.StringVar(value=shortcut)

        ttk.Label(row, text="Name:").pack(side="left")
        ttk.Entry(row, textvariable=name_var, width=18).pack(side="left", padx=4)
        ttk.Label(row, text="Key:").pack(side="left")
        key_entry = ttk.Entry(row, textvariable=key_var, width=3)
        key_entry.pack(side="left", padx=4)

        def remove(r=row, v={"name": name_var, "shortcut": key_var}):
            r.destroy()
            self._entries.remove(v)
            self._refresh_add_btn()

        ttk.Button(row, text="✕", width=2, command=remove).pack(side="left")

        entry = {"name": name_var, "shortcut": key_var}
        self._entries.append(entry)
        self._refresh_add_btn()

    def _add_empty_row(self):
        self._add_row()

    def _refresh_add_btn(self):
        state = "normal" if len(self._entries) < MAX_CUSTOM else "disabled"
        self._add_btn.configure(state=state)

    def _collect_custom(self) -> list[dict] | None:
        result = []
        used_keys = {cat["shortcut"] for cat in BUILTIN_CATEGORIES}
        for e in self._entries:
            name = e["name"].get().strip()
            key  = e["shortcut"].get().strip().lower()
            if not name:
                messagebox.showwarning("Missing name", "Every category needs a name.", parent=self)
                return None
            if not key or len(key) != 1:
                messagebox.showwarning("Invalid key", f"Shortcut for '{name}' must be a single character.", parent=self)
                return None
            if key in used_keys:
                messagebox.showwarning("Duplicate key", f"Shortcut '{key.upper()}' is already used.", parent=self)
                return None
            used_keys.add(key)
            folder = name.lower().replace(" ", "_")
            result.append({"name": name, "folder": folder, "shortcut": key,
                            "color": DEFAULT_CUSTOM_BADGE_COLOR, "builtin": False})
        return result

    def _ok(self):
        custom = self._collect_custom()
        if custom is None:
            return
        self.result = BUILTIN_CATEGORIES + custom
        self.destroy()

    def _load_preset(self):
        name = self._preset_var.get().strip()
        if not name:
            return
        cats = load_preset(name)
        if not cats:
            messagebox.showinfo("Not found", f"No preset named '{name}'.", parent=self)
            return
        for widget in self._custom_frame.winfo_children():
            widget.destroy()
        self._entries.clear()
        for cat in cats[:MAX_CUSTOM]:
            self._add_row(cat["name"], cat["shortcut"])

    def _save_preset(self):
        name = self._preset_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Enter a preset name first.", parent=self)
            return
        custom = self._collect_custom()
        if custom is None:
            return
        save_preset(name, custom)
        self._preset_combo["values"] = list_presets()
        messagebox.showinfo("Saved", f"Preset '{name}' saved.", parent=self)


DEFAULT_CUSTOM_BADGE_COLOR = "#64B5F6"
