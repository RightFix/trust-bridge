"""Escrow ledger.

Money movements are recorded as ledger entries in local SQLite. Every entry
carries a human-readable note so the UI and API can explain what happened.
"""
from __future__ import annotations

import sqlite3

from . import db


class LedgerError(ValueError):
    pass


def _held(conn: sqlite3.Connection, job_id: str) -> float:
    total = 0.0
    for e in db.ledger_entries(conn, job_id):
        if e["kind"] == "FUND":
            total += e["amount_usdt"]
        elif e["kind"] in ("RELEASE", "REFUND"):
            total -= e["amount_usdt"]
    return round(total, 2)


def held(conn: sqlite3.Connection, job_id: str) -> float:
    """USDT currently held in escrow for a job."""
    return _held(conn, job_id)


def _append(conn: sqlite3.Connection, job_id: str, kind: str, amount: float,
            note: str) -> dict:
    if amount <= 0:
        raise LedgerError("Amount must be positive (USDT).")
    conn.execute(
        "INSERT INTO ledger_entries (job_id, kind, amount_usdt, note, created_at)"
        " VALUES (?,?,?,?,?)",
        (job_id, kind, round(amount, 2), note.strip(), db.now()),
    )
    conn.commit()
    rows = db.ledger_entries(conn, job_id)
    return rows[-1]


def fund(conn: sqlite3.Connection, job: dict, amount: float | None = None) -> dict:
    """Client funds the milestone in the escrow ledger."""
    job_id = job["id"]
    if job["status"] not in (db.ST_CONFIRMED,):
        raise LedgerError("Confirm the locked spec on both sides before funding.")
    if held(conn, job_id) > 0:
        raise LedgerError("Milestone is already funded.")
    amount = float(amount if amount is not None else (job.get("amount_usdt") or 500))
    entry = _append(conn, job_id, "FUND", amount, "Milestone funded by client.")
    db.update_job(conn, job_id, status=db.ST_FUNDED, amount_usdt=amount)
    db.add_event(conn, job_id, "ledger", "Milestone funded",
                 f"{amount:g} USDT escrow funded by client.")
    return entry


def release(conn: sqlite3.Connection, job: dict, reason: str) -> dict:
    """Release held funds to the freelancer."""
    job_id = job["id"]
    amount = held(conn, job_id)
    if amount <= 0:
        raise LedgerError("Nothing held in escrow to release.")
    entry = _append(conn, job_id, "RELEASE", amount, reason or "Payment released.")
    db.update_job(conn, job_id, status=db.ST_RELEASED)
    db.add_event(conn, job_id, "ledger", "Funds released",
                 f"{amount:g} USDT → freelancer. {reason}".strip())
    return entry


def refund(conn: sqlite3.Connection, job: dict, reason: str) -> dict:
    """Return held funds to the client."""
    job_id = job["id"]
    amount = held(conn, job_id)
    if amount <= 0:
        raise LedgerError("Nothing held in escrow to refund.")
    entry = _append(conn, job_id, "REFUND", amount, reason or "Payment refunded.")
    db.update_job(conn, job_id, status=db.ST_REFUNDED)
    db.add_event(conn, job_id, "ledger", "Funds refunded",
                 f"{amount:g} USDT → client. {reason}".strip())
    return entry
