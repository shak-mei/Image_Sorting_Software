from db import get_connection


def get_all_tag_names() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM tags ORDER BY name COLLATE NOCASE").fetchall()
        return [r["name"] for r in rows]


def get_or_create_tag(name: str) -> int:
    name = name.strip()
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        row = conn.execute(
            "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return row["id"]


def tag_image(image_path: str, tag_name: str, session_folder: str):
    tag_id = get_or_create_tag(tag_name)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO image_tags (image_path, tag_id, session_folder) VALUES (?, ?, ?)",
            (image_path, tag_id, session_folder),
        )


def untag_image(image_path: str, tag_name: str):
    with get_connection() as conn:
        conn.execute(
            """DELETE FROM image_tags
               WHERE image_path = ?
                 AND tag_id = (SELECT id FROM tags WHERE name = ? COLLATE NOCASE)""",
            (image_path, tag_name),
        )


def get_image_tags(image_path: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT t.name FROM tags t
               JOIN image_tags it ON t.id = it.tag_id
               WHERE it.image_path = ?
               ORDER BY t.name COLLATE NOCASE""",
            (image_path,),
        ).fetchall()
        return [r["name"] for r in rows]
