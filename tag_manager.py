import json
import os

from db import get_connection

JPEG_EXTS = {".jpg", ".jpeg"}


# ---------------------------------------------------------------------------
# Tag database operations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Writing tags into file metadata
# ---------------------------------------------------------------------------

def write_tags_to_file(image_path: str, tags: list[str]):
    """
    Persist tags inside the file itself so they travel with it:
      - JPEG  → EXIF ImageDescription field (via piexif)
      - Other → <filename>.tags.json sidecar next to the file
    Falls back to sidecar if piexif fails for any reason.
    Tags are always stored in the SQLite DB as well (done by tag_image).
    """
    if not os.path.exists(image_path):
        return
    ext = os.path.splitext(image_path)[1].lower()
    if ext in JPEG_EXTS:
        _write_exif_tags(image_path, tags)
    else:
        _write_sidecar_tags(image_path, tags)


def _write_exif_tags(image_path: str, tags: list[str]):
    try:
        import piexif
        tag_str = ", ".join(tags)
        try:
            exif_dict = piexif.load(image_path)
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        exif_dict.setdefault("0th", {})[piexif.ImageIFD.ImageDescription] = tag_str.encode("utf-8")
        piexif.insert(piexif.dump(exif_dict), image_path)
    except Exception:
        _write_sidecar_tags(image_path, tags)


def _write_sidecar_tags(image_path: str, tags: list[str]):
    sidecar_path = image_path + ".tags.json"
    try:
        if tags:
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump({"file": os.path.basename(image_path), "tags": tags}, f, indent=2)
        elif os.path.exists(sidecar_path):
            os.remove(sidecar_path)
    except Exception:
        pass
