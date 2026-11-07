"""REST API + flow orchestration (Layer 2 platform API and the UI both use it)."""
from __future__ import annotations

import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Security
from fastapi.security import APIKeyHeader

from . import db, ledger, llm, verify
from .schemas import (
    ClarifyRequest, CreateJobRequest, FlagRequest, FundRequest,
    ReviewRequest, RoleRequest, SpecUpdateRequest, SubmitRequest,
)

router = APIRouter(prefix="/api")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def require_api_key(x_api_key: str | None = Security(api_key_header)) -> None:
    from .config import API_KEY
    if not API_KEY or not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")


def _job_or_404(conn, job_id: str) -> dict:
    job = db.get_job(conn, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


def _detail(conn, job_or_id) -> dict:
    job_id = job_or_id if isinstance(job_or_id, str) else job_or_id["id"]
    job = db.get_job(conn, job_id)
    job["messages"] = db.get_messages(conn, job["id"])
    job["report"] = db.latest_report(conn, job["id"])
    job["review"] = db.latest_review(conn, job["id"])
    job["submission"] = db.latest_submission(conn, job["id"])
    job["held_usdt"] = ledger.held(conn, job["id"])
    return job


def _lock_hash(spec_dict: dict) -> str:
    canonical = json.dumps(spec_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# jobs
# --------------------------------------------------------------------------
@router.post("/jobs", dependencies=[Depends(require_api_key)])
def create_job(body: CreateJobRequest, conn=Depends(_conn)) -> dict:
    title = (body.title or " ".join(body.brief.split())[:60]).strip()
    job_id = db.create_job(conn, title, body.brief.strip())
    try:
        questions = llm.generate_questions(body.brief)
    except llm.LLMError as exc:
        db.update_job(conn, job_id, status=db.ST_CLARIFYING)
        raise HTTPException(status_code=502, detail=f"LLM question generation failed: {exc}")
    for q in questions:
        db.add_message(conn, job_id, "system", "question", q.text)
    db.add_event(conn, job_id, "job", "Job created",
                 "Client described the job in plain language.")
    db.add_event(conn, job_id, "clarify", "Clarification questions asked",
                 f"{len(questions)} targeted follow-up questions.")
    return _detail(conn, job_id)


@router.get("/jobs", dependencies=[Depends(require_api_key)])
def get_jobs(conn=Depends(_conn)) -> dict:
    return {"jobs": db.list_jobs(conn)}


@router.get("/jobs/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str, conn=Depends(_conn)) -> dict:
    return _detail(conn, _job_or_404(conn, job_id))


@router.get("/jobs/{job_id}/messages", dependencies=[Depends(require_api_key)])
def get_messages(job_id: str, conn=Depends(_conn)) -> dict:
    _job_or_404(conn, job_id)
    return {"messages": db.get_messages(conn, job_id)}


# --------------------------------------------------------------------------
# clarification → spec
# --------------------------------------------------------------------------
@router.post("/jobs/{job_id}/clarify", dependencies=[Depends(require_api_key)])
def clarify(job_id: str, body: ClarifyRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    if job["status"] != db.ST_CLARIFYING:
        raise HTTPException(status_code=409, detail="Job is not awaiting clarification.")
    questions = [m for m in db.get_messages(conn, job_id) if m["kind"] == "question"]
    if not questions:
        raise HTTPException(status_code=409, detail="No clarification questions to answer.")
    answered: list[tuple[dict, str]] = []
    for idx, q in enumerate(questions):
        ans = (body.answers.get(str(q["seq"])) or body.answers.get(f"q{idx + 1}")
               or "").strip()
        if not ans:
            raise HTTPException(
                status_code=422,
                detail=f"Question {idx + 1} still needs an answer before the spec can be built.")
        answered.append((q, ans))
    for q, ans in answered:
        db.add_message(conn, job_id, "client", "answer", ans, seq=q["seq"] + 0.5)
    qa = db.get_messages(conn, job_id)
    try:
        spec = llm.generate_spec(job["brief"], qa)
        rewrite = llm.freelancer_view(spec)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM spec generation failed: {exc}")
    db.update_job(conn, job_id, status=db.ST_SPEC_READY,
                  spec_json=spec.model_dump_json(),
                  rewrite_json=json.dumps(rewrite, ensure_ascii=False),
                  flags_json="[]", confirmed_client=0, confirmed_freelancer=0,
                  lock_hash=None)
    db.add_event(conn, job_id, "spec", "Structured spec generated",
                 f"{len(spec.checklist)} checklist items "
                 f"({sum(1 for i in spec.checklist if i.kind == 'OBJECTIVE')} objective).")
    return _detail(conn, job_id)


@router.post("/jobs/{job_id}/flag", dependencies=[Depends(require_api_key)])
def flag_item(job_id: str, body: FlagRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    if job["status"] not in (db.ST_SPEC_READY, db.ST_CONFIRMED, db.ST_SPEC_EDITING):
        raise HTTPException(status_code=409, detail="Spec is not open for flags.")
    if not job["spec"]:
        raise HTTPException(status_code=409, detail="No spec yet.")
    ids = {i["id"] for i in job["spec"]["checklist"]}
    if body.item_id not in ids:
        raise HTTPException(status_code=422, detail="Unknown checklist item id.")
    flags = [f for f in job["flags"] if f["item_id"] != body.item_id]
    flags.append({"item_id": body.item_id, "note": body.note, "at": db.now()})
    db.update_job(conn, job_id, status=db.ST_SPEC_EDITING,
                  flags_json=json.dumps(flags),
                  confirmed_client=0, confirmed_freelancer=0, lock_hash=None)
    db.add_event(conn, job_id, "flag", "Freelancer flagged an item as unclear",
                 f"{body.item_id}: {body.note or 'no note'}")
    return _detail(conn, job_id)


@router.post("/jobs/{job_id}/spec", dependencies=[Depends(require_api_key)])
def update_spec(job_id: str, body: SpecUpdateRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    if job["status"] not in (db.ST_SPEC_EDITING, db.ST_SPEC_READY):
        raise HTTPException(status_code=409, detail="Spec is locked; edits are not allowed.")
    try:
        rewrite = llm.freelancer_view(body.spec)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM rewrite failed: {exc}")
    db.update_job(conn, job_id, status=db.ST_SPEC_READY,
                  title=body.spec.title, spec_json=body.spec.model_dump_json(),
                  rewrite_json=json.dumps(rewrite, ensure_ascii=False),
                  flags_json="[]", confirmed_client=0, confirmed_freelancer=0,
                  lock_hash=None)
    db.add_event(conn, job_id, "spec", "Client updated the spec",
                 "Flags addressed; both parties must confirm again.")
    return _detail(conn, job_id)


# --------------------------------------------------------------------------
# confirmation lock
# --------------------------------------------------------------------------
@router.post("/jobs/{job_id}/confirm", dependencies=[Depends(require_api_key)])
def confirm(job_id: str, body: RoleRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    if body.role not in ("client", "freelancer"):
        raise HTTPException(status_code=422, detail="Confirm as client or freelancer.")
    if job["status"] not in (db.ST_SPEC_READY, db.ST_CONFIRMED):
        raise HTTPException(status_code=409, detail="Spec is not ready to confirm.")
    if job["locked"]:
        raise HTTPException(status_code=409, detail="Spec is already locked.")
    if not job["spec"]:
        raise HTTPException(status_code=409, detail="No spec yet.")
    field = "confirmed_client" if body.role == "client" else "confirmed_freelancer"
    db.update_job(conn, job_id, **{field: 1})
    job = db.get_job(conn, job_id)
    both = job["confirmed_client"] and job["confirmed_freelancer"]
    db.add_event(conn, job_id, "confirm", f"{body.role.title()} confirmed the spec",
                 "" if both else "Waiting for the other party to confirm.")
    if both:
        db.update_job(conn, job_id, status=db.ST_CONFIRMED,
                      lock_hash=_lock_hash(job["spec"]))
        db.add_event(conn, job_id, "lock", "Spec locked",
                     "Both parties confirmed. The spec can no longer be edited.")
    return _detail(conn, job_id)


# --------------------------------------------------------------------------
# simulated escrow
# --------------------------------------------------------------------------
@router.post("/jobs/{job_id}/fund", dependencies=[Depends(require_api_key)])
def fund(job_id: str, body: FundRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    try:
        ledger.fund(conn, job, body.amount_usdt)
    except ledger.LedgerError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _detail(conn, job_id)


# --------------------------------------------------------------------------
# submission + verification
# --------------------------------------------------------------------------
@router.post("/jobs/{job_id}/submit", dependencies=[Depends(require_api_key)])
def submit(job_id: str, body: SubmitRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    if job["status"] not in (db.ST_FUNDED, db.ST_CHANGES, db.ST_SUBMITTED):
        raise HTTPException(
            status_code=409,
            detail="Job must be funded (simulated) before a deliverable can be submitted.")
    if not job["spec"]:
        raise HTTPException(status_code=409, detail="No spec to verify against.")
    sub_id = db.add_submission(conn, job_id, body.kind, body.content, body.filename)
    db.update_job(conn, job_id, status=db.ST_SUBMITTED)
    db.add_event(conn, job_id, "submit", "Deliverable submitted",
                 f"{body.kind} submission #{sub_id} "
                 f"{('(' + body.filename + ')') if body.filename else ''}".strip())

    submission = db.latest_submission(conn, job_id)
    report = verify.run_verification(conn, job, submission)
    db.save_verification(conn, job_id, report.model_dump())

    if report.auto_release:
        try:
            ledger.release(conn, db.get_job(conn, job_id), report.recommendation)
        except ledger.LedgerError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        db.add_event(conn, job_id, "verify", "Verification passed",
                     f"{len(report.items)} items passed automatically.")
    else:
        db.update_job(conn, job_id, status=db.ST_HUMAN_REVIEW)
        n_fail = sum(1 for i in report.items if i.verdict == "fail")
        n_rev = sum(1 for i in report.items if i.verdict == "needs_human_review")
        db.add_event(conn, job_id, "verify", "Verification needs a human",
                     f"{n_fail} failed, {n_rev} need human review.")
    out = _detail(conn, job_id)
    out["report"] = report.model_dump()
    return out


# --------------------------------------------------------------------------
# human reviewer
# --------------------------------------------------------------------------
@router.post("/jobs/{job_id}/review", dependencies=[Depends(require_api_key)])
def review(job_id: str, body: ReviewRequest, conn=Depends(_conn)) -> dict:
    job = _job_or_404(conn, job_id)
    if job["status"] != db.ST_HUMAN_REVIEW:
        raise HTTPException(status_code=409, detail="Job is not in human review.")
    report = db.latest_report(conn, job_id) or {}
    db.save_review(conn, job_id, body.decision, body.note,
                   report.get("recommendation", ""))
    job = db.get_job(conn, job_id)
    if body.decision == "release":
        try:
            ledger.release(conn, job, body.note or "Human reviewer released payment.")
        except ledger.LedgerError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    elif body.decision == "refund":
        try:
            ledger.refund(conn, job, body.note or "Human reviewer refunded the client.")
        except ledger.LedgerError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    else:
        db.update_job(conn, job_id, status=db.ST_CHANGES)
        db.add_event(conn, job_id, "review", "Reviewer requested changes",
                     body.note or "Freelancer must resubmit.")
    return _detail(conn, job_id)
