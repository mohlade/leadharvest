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


def get_conn():
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
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE contacts ADD COLUMN first_seen_search_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
