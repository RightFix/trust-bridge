"""TrustBridge — data access layer (SQLite)."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "trustbridge.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    brief TEXT NOT NULL,
    status TEXT NOT NULL,
    spec_json TEXT,
    rewrite_json TEXT,
    flags_json TEXT NOT NULL DEFAULT '[]',
    confirmed_client INTEGER NOT NULL DEFAULT 0,
    confirmed_freelancer INTEGER NOT NULL DEFAULT 0,
    lock_hash TEXT,
    amount_usdt REAL NOT NULL DEFAULT 0,
    prefill_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,          -- client | freelancer | system
    kind TEXT NOT NULL,          -- question | answer | note
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    kind TEXT NOT NULL,          -- FUND | RELEASE | REFUND
    amount_usdt REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USDT',
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    kind TEXT NOT NULL,          -- text | file | code
    filename TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    decision TEXT NOT NULL,      -- release | request_changes | refund
    note TEXT NOT NULL DEFAULT '',
    recommendation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id),
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_job ON messages(job_id);
CREATE INDEX IF NOT EXISTS idx_ledger_job ON ledger_entries(job_id);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
"""

# --- job status machine -----------------------------------------------------
ST_CLARIFYING = "clarifying"        # answering follow-up questions
ST_SPEC_READY = "spec_ready"        # spec generated, awaiting confirmations
ST_SPEC_EDITING = "spec_editing"    # freelancer flagged items, client editing
ST_CONFIRMED = "confirmed"          # both sides confirmed, spec locked
ST_FUNDED = "funded"                # escrow funded
ST_SUBMITTED = "submitted"          # deliverable submitted, verification ran
ST_VERIFYING = "verifying"          # checks running
ST_HUMAN_REVIEW = "human_review"    # routed to human reviewer
ST_RELEASED = "released"            # funds released to freelancer
ST_REFUNDED = "refunded"            # funds returned to client
ST_CHANGES = "changes_requested"    # reviewer asked for changes (resubmit allowed)

STATUS_LABELS = {
    ST_CLARIFYING: "Clarifying",
    ST_SPEC_READY: "Spec awaiting confirmation",
    ST_SPEC_EDITING: "Spec edits requested",
    ST_CONFIRMED: "Spec locked",
    ST_FUNDED: "Milestone funded",
    ST_SUBMITTED: "Submitted",
    ST_VERIFYING: "Verifying",
    ST_HUMAN_REVIEW: "Human review",
    ST_RELEASED: "Released",
    ST_REFUNDED: "Refunded",
    ST_CHANGES: "Changes requested",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "job") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    # The demo DB lives on a normal disk where each synchronous commit can cost
    # >1s of fsync. WAL + synchronous=NORMAL keeps the same durability we need
    # for a local demo while making writes effectively instant.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# --- json helpers -----------------------------------------------------------
def _loads(value, default):
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def job_to_dict(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict:
    d = dict(row)
    d["spec"] = _loads(d.pop("spec_json", None), None)
    d["rewrite"] = _loads(d.pop("rewrite_json", None), None)
    d["flags"] = _loads(d.pop("flags_json", None), [])
    d["prefill"] = _loads(d.pop("prefill_json", None), None)
    d["confirmed_client"] = bool(d["confirmed_client"])
    d["confirmed_freelancer"] = bool(d["confirmed_freelancer"])
    d["locked"] = bool(d["lock_hash"])
    d["status_label"] = STATUS_LABELS.get(d["status"], d["status"])
    if conn is not None:
        d["ledger"] = ledger_entries(conn, d["id"])
        d["events"] = get_events(conn, d["id"])
    return d


# --- jobs -------------------------------------------------------------------
def create_job(conn: sqlite3.Connection, title: str, brief: str,
               prefill: dict | None = None) -> str:
    job_id = new_id()
    ts = now()
    conn.execute(
        "INSERT INTO jobs (id, title, brief, status, prefill_json, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (job_id, title, brief, ST_CLARIFYING,
         json.dumps(prefill) if prefill else None, ts, ts),
    )
    conn.commit()
    return job_id


def get_job(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return job_to_dict(row, conn) if row else None


def list_jobs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [job_to_dict(r, conn) for r in rows]


def update_job(conn: sqlite3.Connection, job_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
    conn.commit()


# --- messages (clarification chat) ------------------------------------------
def add_message(conn: sqlite3.Connection, job_id: str, role: str, kind: str,
                content: str, seq: int | None = None) -> int:
    if seq is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq),0)+1 AS s FROM messages WHERE job_id=?",
            (job_id,)).fetchone()
        seq = row["s"]
    cur = conn.execute(
        "INSERT INTO messages (job_id, seq, role, kind, content, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (job_id, seq, role, kind, content, now()))
    conn.commit()
    return cur.lastrowid


def get_messages(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM messages WHERE job_id=? ORDER BY seq ASC", (job_id,)).fetchall()
    return [dict(r) for r in rows]


# --- events (status timeline) ----------------------------------------------
def add_event(conn: sqlite3.Connection, job_id: str, kind: str, label: str,
              detail: str = "") -> None:
    conn.execute(
        "INSERT INTO events (job_id, kind, label, detail, created_at) VALUES (?,?,?,?,?)",
        (job_id, kind, label, detail, now()))
    conn.commit()


def get_events(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM events WHERE job_id=? ORDER BY id ASC", (job_id,)).fetchall()
    return [dict(r) for r in rows]


# --- ledger ----------------------------------------------------------------
def ledger_entries(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM ledger_entries WHERE job_id=? ORDER BY id ASC",
        (job_id,)).fetchall()
    return [dict(r) for r in rows]


# --- submissions / verification / reviews -----------------------------------
def add_submission(conn: sqlite3.Connection, job_id: str, kind: str,
                   content: str, filename: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO submissions (job_id, kind, filename, content, created_at)"
        " VALUES (?,?,?,?,?)",
        (job_id, kind, filename, content, now()))
    conn.commit()
    return cur.lastrowid


def latest_submission(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM submissions WHERE job_id=? ORDER BY id DESC LIMIT 1",
        (job_id,)).fetchone()
    return dict(row) if row else None


def all_submissions(conn: sqlite3.Connection, job_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM submissions WHERE job_id=? ORDER BY id ASC",
        (job_id,)).fetchall()
    return [dict(r) for r in rows]


def save_verification(conn: sqlite3.Connection, job_id: str, report: dict) -> None:
    conn.execute(
        "INSERT INTO verifications (job_id, report_json, created_at) VALUES (?,?,?)",
        (job_id, json.dumps(report), now()))
    conn.commit()


def latest_report(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute(
        "SELECT report_json FROM verifications WHERE job_id=? ORDER BY id DESC LIMIT 1",
        (job_id,)).fetchone()
    return _loads(row["report_json"], None) if row else None


def save_review(conn: sqlite3.Connection, job_id: str, decision: str, note: str,
                recommendation: str) -> None:
    conn.execute(
        "INSERT INTO reviews (job_id, decision, note, recommendation, created_at)"
        " VALUES (?,?,?,?,?)",
        (job_id, decision, note, recommendation, now()))
    conn.commit()


def latest_review(conn: sqlite3.Connection, job_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM reviews WHERE job_id=? ORDER BY id DESC LIMIT 1",
        (job_id,)).fetchone()
    return dict(row) if row else None
