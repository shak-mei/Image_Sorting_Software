import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".image_sorter" / "data.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT    UNIQUE NOT NULL COLLATE NOCASE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS image_tags (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path     TEXT    NOT NULL,
                tag_id         INTEGER NOT NULL REFERENCES tags(id),
                session_folder TEXT    NOT NULL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(image_path, tag_id)
            );

            CREATE TABLE IF NOT EXISTS category_presets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                preset_name TEXT UNIQUE NOT NULL,
                categories  TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
