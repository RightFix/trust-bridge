"""SIMULATED escrow ledger.

Nothing in this module touches real money, real chains, or real payment
providers. Every entry is marked ``simulated=True`` and carries an explicit
note so the UI and API can label it "Simulated escrow".
"""
from __future__ import annotations

import sqlite3

from . import db

SIMULATED_NOTE = "Simulated escrow — no real funds move."


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
    """Simulated USDT currently held in escrow for a job."""
    return _held(conn, job_id)


def _append(conn: sqlite3.Connection, job_id: str, kind: str, amount: float,
            note: str) -> dict:
    if amount <= 0:
        raise LedgerError("Amount must be positive (simulated USDT).")
    conn.execute(
        "INSERT INTO ledger_entries (job_id, kind, amount_usdt, note, simulated, created_at)"
        " VALUES (?,?,?,?,1,?)",
        (job_id, kind, round(amount, 2), f"{note} {SIMULATED_NOTE}".strip(), db.now()),
    )
    conn.commit()
    rows = db.ledger_entries(conn, job_id)
    return rows[-1]


def fund(conn: sqlite3.Connection, job: dict, amount: float | None = None) -> dict:
    """Client funds the milestone in the mock ledger."""
    job_id = job["id"]
    if job["status"] not in (db.ST_CONFIRMED,):
        raise LedgerError("Confirm the locked spec on both sides before funding.")
    if held(conn, job_id) > 0:
        raise LedgerError("Milestone is already funded (simulated).")
    amount = float(amount if amount is not None else (job.get("amount_usdt") or 500))
    entry = _append(conn, job_id, "FUND", amount, "Milestone funded by client.")
    db.update_job(conn, job_id, status=db.ST_FUNDED, amount_usdt=amount)
    db.add_event(conn, job_id, "ledger", "Milestone funded (simulated)",
                 f"{amount:g} USDT simulated escrow funded by client.")
    return entry


def release(conn: sqlite3.Connection, job: dict, reason: str) -> dict:
    """Release held funds to the freelancer (simulated)."""
    job_id = job["id"]
    amount = held(conn, job_id)
    if amount <= 0:
        raise LedgerError("Nothing held in simulated escrow to release.")
    entry = _append(conn, job_id, "RELEASE", amount, reason or "Payment released.")
    db.update_job(conn, job_id, status=db.ST_RELEASED)
    db.add_event(conn, job_id, "ledger", "Funds released (simulated)",
                 f"{amount:g} USDT simulated → freelancer. {reason}".strip())
    return entry


def refund(conn: sqlite3.Connection, job: dict, reason: str) -> dict:
    """Return held funds to the client (simulated)."""
    job_id = job["id"]
    amount = held(conn, job_id)
    if amount <= 0:
        raise LedgerError("Nothing held in simulated escrow to refund.")
    entry = _append(conn, job_id, "REFUND", amount, reason or "Payment refunded.")
    db.update_job(conn, job_id, status=db.ST_REFUNDED)
    db.add_event(conn, job_id, "ledger", "Funds refunded (simulated)",
                 f"{amount:g} USDT simulated → client. {reason}".strip())
    return entry
