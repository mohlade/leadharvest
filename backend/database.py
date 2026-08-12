import os
import sqlite3
from pathlib import Path

def get_db_path() -> Path:
    env_path = os.getenv("DATABASE_PATH", "").strip()
    if env_path:
        return Path(env_path)
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/jobs.db")
    return Path(__file__).parent / "jobs.db"


# --------------------------------------------------------------------------
# Hosted persistence (Turso / libSQL)
# Set DATABASE_URL (e.g. libsql://<db>-<org>.turso.io) plus TURSO_AUTH_TOKEN.
# Data then lives in Turso's cloud, so it survives Vercel instance restarts —
# unlike /tmp/jobs.db, which is wiped constantly.
# The wrapper below mirrors the sqlite3 API used by the app, so none of the
# SQL in main.py / mail_extractor.py needs to change.
# A fresh connection is opened per get_conn() (like sqlite3.connect). Long-lived
# cached connections get reaped by Turso mid-search ("stream not found"),
# so we never cache one.
# --------------------------------------------------------------------------


class _TursoCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._rows = None

    def _cols(self):
        return [c[0] for c in (self._cursor.description or [])]

    def _load(self):
        if self._rows is None:
            rows = self._cursor.fetchall()
            self._rows = rows if rows is not None else []
            self._cols_cache = self._cols()
        return self._cols_cache

    def fetchone(self):
        cols = self._load()
        if not self._rows:
            return None
        return dict(zip(cols, self._rows.pop(0)))

    def fetchall(self):
        cols = self._load()
        rows, self._rows = self._rows, []
        return [dict(zip(cols, r)) for r in rows]


class _TursoConn:
    """Drop-in sqlite3.Connection backed by a Turso connection."""

    def __init__(self):
        import libsql_experimental as lxsql

        self._conn = lxsql.connect(
            os.getenv("DATABASE_URL", "").strip(),
            auth_token=os.getenv("TURSO_AUTH_TOKEN", "").strip() or None,
        )

    def execute(self, sql, args=None):
        if args is not None and not isinstance(args, tuple):
            args = tuple(args)
        return _TursoCursor(self._conn.execute(sql, args if args is not None else ()))

    def executescript(self, script):
        self._conn.executescript(script)

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def get_conn():
    if os.getenv("DATABASE_URL", "").strip():
        return _TursoConn()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_id TEXT,
            title TEXT NOT NULL,
            company TEXT,
            location TEXT,
            country TEXT,
            remote INTEGER DEFAULT 0,
            salary_min REAL,
            salary_max REAL,
            salary_currency TEXT,
            url TEXT,
            posted_date TEXT,
            raw_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_source_id ON jobs(source, source_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title);
        CREATE INDEX IF NOT EXISTS idx_jobs_country ON jobs(country);

        CREATE TABLE IF NOT EXISTS searches (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT DEFAULT 'running',
            pages_checked INTEGER DEFAULT 0,
            emails_found INTEGER DEFAULT 0,
            message TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id TEXT NOT NULL,
            email TEXT NOT NULL,
            name TEXT,
            company TEXT,
            role TEXT,
            location TEXT,
            source_url TEXT,
            confidence REAL,
            status TEXT,
            first_seen_search_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_contacts_search ON contacts(search_id);
        CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
        """
    )
    try:
        conn.execute("ALTER TABLE searches ADD COLUMN message TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE contacts ADD COLUMN first_seen_search_id TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()
