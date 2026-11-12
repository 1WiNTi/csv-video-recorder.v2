"""Test Task 2 - web service: upload a video, look it up by company name, serve it.

Run:  python web_service.py
Env:  FLASK_HOST (default 0.0.0.0), FLASK_PORT (default 8000)
"""
import hashlib
import os
import re
import sqlite3
import tempfile

from flask import Flask, Response, g, jsonify, request, send_from_directory, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "videos.db")
DEFAULT_EXT = ".webm"
ALLOWED_EXT = {".webm", ".mp4", ".mkv", ".mov", ".ogg", ".avi"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,      -- absolute path to the file on disk
    video_url TEXT NOT NULL,      -- public URL to the video
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GiB upload cap


# --------------------------------------------------------------------------- DB
def _connect() -> sqlite3.Connection:
    # timeout = busy timeout in seconds, so concurrent writers wait instead of failing
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    """One connection per request (Flask's server is threaded)."""
    if "db" not in g:
        g.db = _connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------- helpers
def _safe_filename(company_name: str, original_name: str, db: sqlite3.Connection) -> str:
    """'ACME GmbH' + 'x.webm' -> 'ACME_GmbH.webm' (unique per company)."""
    stem = re.sub(r"[^\w.-]+", "_", company_name, flags=re.UNICODE).strip("._") or "video"
    ext = os.path.splitext(original_name or "")[1].lower()
    if ext not in ALLOWED_EXT:
        ext = DEFAULT_EXT
    filename = stem + ext

    # Two different names can sanitize to the same stem ("A/B" vs "A B"):
    # if the file already belongs to another company, add a short hash.
    row = db.execute(
        "SELECT company_name FROM videos WHERE file_path = ?",
        (os.path.join(UPLOAD_DIR, filename),),
    ).fetchone()
    if row is not None and row["company_name"] != company_name:
        digest = hashlib.sha1(company_name.encode("utf-8")).hexdigest()[:8]
        filename = f"{stem}_{digest}{ext}"
    return filename


def _video_url(filename: str) -> str:
    # built from the current request, never from a hard-coded host
    return request.host_url.rstrip("/") + url_for("media", filename=filename)


def _error(message: str, status: int) -> Response:
    resp = jsonify({"error": message})
    resp.status_code = status
    return resp


# ----------------------------------------------------------------------- routes
@app.post("/upload")
def upload():
    company_name = (request.form.get("company_name") or "").strip()
    file = request.files.get("file")

    if not company_name:
        return _error("company_name is required", 400)
    if file is None or not file.filename:
        return _error("file is required", 400)

    db = get_db()
    filename = _safe_filename(company_name, file.filename, db)
    dest = os.path.join(UPLOAD_DIR, filename)

    # Write to a temp file first, then atomically replace: a half-uploaded
    # file never overwrites a good one.
    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_DIR, suffix=".part")
    os.close(fd)
    try:
        file.save(tmp_path)
        if os.path.getsize(tmp_path) == 0:
            return _error("uploaded file is empty", 400)
        os.replace(tmp_path, dest)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    video_url = _video_url(filename)

    old = db.execute(
        "SELECT file_path FROM videos WHERE company_name = ?", (company_name,)
    ).fetchone()

    # upsert: re-uploading the same company updates the row, no duplicates
    db.execute(
        """
        INSERT INTO videos (company_name, file_path, video_url)
        VALUES (?, ?, ?)
        ON CONFLICT(company_name) DO UPDATE SET
            file_path  = excluded.file_path,
            video_url  = excluded.video_url,
            updated_at = datetime('now')
        """,
        (company_name, dest, video_url),
    )
    db.commit()

    # extension changed on re-upload (.mp4 -> .webm): drop the orphaned old file
    if old is not None and old["file_path"] != dest and os.path.exists(old["file_path"]):
        os.remove(old["file_path"])

    return jsonify({"company_name": company_name, "video_url": video_url})


@app.get("/get_video_url")
def get_video_url():
    company_name = (request.args.get("company_name") or "").strip()
    if not company_name:
        return _error("company_name is required", 400)

    row = get_db().execute(
        "SELECT company_name, video_url FROM videos WHERE company_name = ?",
        (company_name,),
    ).fetchone()
    if row is None:
        return _error(f"no video found for company '{company_name}'", 404)
    return jsonify({"company_name": row["company_name"], "video_url": row["video_url"]})


@app.get("/media/<path:filename>")
def media(filename):
    # send_from_directory rejects path traversal (../) on its own
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/videos")
def list_videos():
    rows = get_db().execute(
        "SELECT id, company_name, file_path, video_url, created_at, updated_at "
        "FROM videos ORDER BY id"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=int(os.environ.get("FLASK_PORT", "8000")),
        threaded=True,
    )
