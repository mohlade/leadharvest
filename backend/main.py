import csv
import io
import os
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from database import get_conn, init_db
from mail_extractor import init_search, run_search


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Jobs Aggregator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": "jobs-aggregator"}


class SearchRequest(BaseModel):
    role: str = Field(..., min_length=1, description='Role/title, e.g. "real estate agent"')
    location: str = Field(..., min_length=1, description='State/province or city, e.g. "Texas" or "Newark, Trenton"')
    country: str = Field(default="US", description="US, CA, UK, AU, or IE")
    max_pages: int = Field(default=50, ge=1, le=500)
    personal_only: bool = Field(default=False, description="If true, only keep personal emails and drop generic ones (info@, office@, etc.). Default is False to capture all valid emails.")


@app.post("/api/contacts/search")
def start_search(req: SearchRequest):
    search_id = uuid.uuid4().hex
    init_search(search_id, req.role.strip(), req.location.strip())

    if os.getenv("VERCEL"):
        # On Vercel serverless, run fast search synchronously within function timeout (max 5 pages)
        try:
            run_search(
                search_id,
                req.role.strip(),
                req.location.strip(),
                req.country,
                min(req.max_pages, 5),
                req.personal_only,
            )
        except Exception:
            pass  # run_search already marks the search as failed; return its state below
        conn = get_conn()
        search = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
        rows = conn.execute(
            "SELECT * FROM contacts WHERE search_id = ? ORDER BY confidence DESC", (search_id,)
        ).fetchall()
        conn.close()
        return {
            "search_id": search_id,
            "role": req.role.strip(),
            "location": req.location.strip(),
            "status": search["status"] if search else "done",
            "pages_checked": search["pages_checked"] if search else 0,
            "emails_found": search["emails_found"] if search else len(rows),
            "message": search["message"] if search else None,
            "contacts": [dict(row) for row in rows],
        }

    thread = threading.Thread(
        target=run_search,
        args=(search_id, req.role.strip(), req.location.strip(), req.country, req.max_pages, req.personal_only),
        daemon=True,
    )
    thread.start()
    return {"search_id": search_id, "status": "running"}


@app.post("/api/contacts/search/{search_id}/stop")
def stop_search(search_id: str):
    conn = get_conn()
    search = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
    if not search:
        conn.close()
        return {"error": "search not found"}
    conn.execute(
        "UPDATE searches SET status = 'stopped', message = 'Search stopped by user' WHERE id = ?",
        (search_id,),
    )
    conn.commit()
    rows = conn.execute(
        "SELECT * FROM contacts WHERE search_id = ? ORDER BY confidence DESC", (search_id,)
    ).fetchall()
    conn.close()
    return {
        "search_id": search_id,
        "role": search["role"],
        "location": search["location"],
        "status": "stopped",
        "pages_checked": search["pages_checked"],
        "emails_found": len(rows),
        "message": "Search stopped by user",
        "contacts": [dict(r) for r in rows],
    }


@app.get("/api/contacts/search/{search_id}")
def get_search(search_id: str):
    conn = get_conn()
    search = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
    if not search:
        conn.close()
        return {"error": "search not found"}
    rows = conn.execute(
        "SELECT * FROM contacts WHERE search_id = ? ORDER BY confidence DESC", (search_id,)
    ).fetchall()
    conn.close()
    return {
        "search_id": search["id"],
        "role": search["role"],
        "location": search["location"],
        "status": search["status"],
        "pages_checked": search["pages_checked"],
        "emails_found": search["emails_found"],
        "message": search["message"],
        "started_at": search["started_at"],
        "finished_at": search["finished_at"],
        "contacts": [dict(row) for row in rows],
    }


@app.get("/api/contacts")
def list_searches():
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.id, s.role, s.location, s.status, s.pages_checked, s.emails_found,
               s.message, s.started_at, s.finished_at, COUNT(c.id) AS saved
        FROM searches s
        LEFT JOIN contacts c ON c.search_id = s.id
        GROUP BY s.id
        ORDER BY s.started_at DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()
    return {"searches": [dict(row) for row in rows]}


@app.get("/api/contacts/export.csv")
def export_csv(search_id: Optional[str] = Query(default=None, description="Search id to export")):
    conn = get_conn()
    if search_id:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE search_id = ? ORDER BY confidence DESC", (search_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contacts ORDER BY confidence DESC LIMIT 5000").fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "name", "company", "status", "confidence", "source_url", "first_seen_search_id", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row["email"],
                row["name"] or "",
                row["company"] or "",
                row["status"] or "",
                row["confidence"] or "",
                row["source_url"] or "",
                row["first_seen_search_id"] or "",
                row["created_at"] or "",
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )
