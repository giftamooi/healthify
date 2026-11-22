"""Penyimpanan data (SQLite). Satu file database di volume /data."""
import os
import sqlite3


def _db_path() -> str:
    return os.getenv("DB_PATH", "/data/healther.db")


def init_db() -> None:
    path = _db_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            latitude      REAL,
            longitude     REAL,
            vulnerabilities TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS medicines (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            dose_per_intake  REAL NOT NULL,
            intakes_per_day  INTEGER NOT NULL,
            stock_units      REAL NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def get_db():
    """Dependency FastAPI: satu koneksi per request, selalu ditutup."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
