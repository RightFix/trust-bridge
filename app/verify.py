"""Verification orchestration: deterministic checks first, AI for the rest,
then a single report that decides auto-release vs human review."""
from __future__ import annotations

from . import db, llm
from .checks import run_deterministic
from .schemas import ChecklistItem, Spec, VerificationReport


def run_verification(conn, job: dict, submission: dict) -> VerificationReport:
    spec = Spec.model_validate(job["spec"])
    content = submission.get("content") or ""
    filename = submission.get("filename")

    deterministic: list[dict] = []
    pending: list[ChecklistItem] = []

    for item in spec.checklist:
        result = None
        if item.kind == "OBJECTIVE":
            result = run_deterministic(item, content, filename)
        if result is None:
            # no codeable check (or SUBJECTIVE) → AI judges
            pending.append(item)
            continue
        passed, reason = result
        deterministic.append({
            "id": item.id, "text": item.text, "kind": item.kind,
            "source": "deterministic",
            "verdict": "pass" if passed else "fail",
            "reason": reason,
        })

    ai_items = llm.verify_with_ai(spec, content, submission.get("kind", "text"), pending)
    ai_results = [{
        "id": v["id"], "text": v["text"], "kind": v["kind"], "source": "ai",
        "verdict": v["verdict"], "reason": v["reason"],
    } for v in ai_items]

    # keep checklist order in the report
    order = {i.id: n for n, i in enumerate(spec.checklist)}
    items = sorted(deterministic + ai_results, key=lambda r: order.get(r["id"], 999))

    failures = [r for r in items if r["verdict"] == "fail"]
    reviews = [r for r in items if r["verdict"] == "needs_human_review"]
    auto_release = not failures and not reviews

    if auto_release:
        overall, rec = "pass", "All checklist items passed — release the milestone."
    elif failures and not reviews:
        overall = "fail"
        rec = (f"{len(failures)} item(s) failed — recommend request changes, "
               "or refund if unfixable. Human decides.")
    elif reviews and not failures:
        overall = "needs_human_review"
        rec = "Objective checks passed but subjective items need a human judgement."
    else:
        overall = "fail"
        rec = (f"{len(failures)} failed, {len(reviews)} need review — "
               "human decision required.")

    report = VerificationReport(
        job_id=job["id"], overall=overall, auto_release=auto_release,
        recommendation=rec, items=items,
        checked_by_ai=len(ai_results), checked_deterministically=len(deterministic),
        created_at=db.now(),
    )
    return report
