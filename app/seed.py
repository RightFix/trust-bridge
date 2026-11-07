"""Demo seed data — two jobs that are demoable immediately.

Job A: Python function task with test cases → passes verification → auto-release.
Job B: blog post with word-count + required-sections checklist → partially fails
       → routed to the human reviewer.
"""
from __future__ import annotations

import json

from . import db, llm, verify

QUESTIONS_A = [
    "What specifically must be true for you to accept this work as “done”? "
    "Describe the exact outcome, format and quality bar.",
    "Can you share an example, reference or link that shows what “good” looks "
    "like for this job?",
    "What is the deadline (date and time), and is it a hard cutoff or a target?",
    "How many rounds of revisions are included in the price?",
    "What is explicitly NOT included (e.g. extra revisions, source files, "
    "deployment, follow-up changes)?",
]

ANSWERS_A = [
    "A single file solution.py that defines parse_amount(raw: str) -> float, "
    "handles $1,234.56, €99, 1000 and -$5.25 correctly, with type hints.",
    "Standard Python style: one small pure function, no dependencies, "
    "documented with a docstring.",
    "Friday 13 Nov 2026, 18:00 UTC — hard cutoff.",
    "2 rounds",
    "No CLI, no database, no currency conversion or crypto amounts.",
]

SPEC_A = {
    "title": "Python money-string parser (parse_amount)",
    "deliverables": [
        "solution.py — one module defining parse_amount",
        "Type-hinted signature with a docstring",
        "Test run showing all agreed cases passing",
    ],
    "checklist": [
        {"id": "c1", "kind": "OBJECTIVE", "text": "Deliverable is a Python file (.py)",
         "check": {"type": "file_type", "extensions": [".py"]}},
        {"id": "c2", "kind": "OBJECTIVE",
         "text": "parse_amount handles $1,234.56, €99, 1000 and -$5.25",
         "check": {"type": "code_tests", "test_code": (
             "from solution import parse_amount\n"
             "\n"
             "cases = [(\"$1,234.56\", 1234.56), (\"€99\", 99.0),\n"
             "         (\"1000\", 1000.0), (\"-$5.25\", -5.25)]\n"
             "for raw, expected in cases:\n"
             "    got = parse_amount(raw)\n"
             "    assert abs(got - expected) < 1e-9, (\n"
             "        f\"parse_amount({raw!r}) = {got!r}, expected {expected!r}\")\n"
             "print(f\"PASSED: {len(cases)}/{len(cases)} cases\")\n")}},
        {"id": "c3", "kind": "OBJECTIVE",
         "text": "Function signature uses type hints: "
                 "`def parse_amount(raw: str) -> float`",
         "check": {"type": "keywords", "mode": "all",
                   "values": ["def parse_amount(raw: str) -> float"]}},
    ],
    "deadline": "Friday 13 Nov 2026, 18:00 UTC (hard cutoff)",
    "revision_limit": 2,
    "out_of_scope": ["CLI or database integration",
                     "Currency conversion and crypto amounts",
                     "Inputs beyond the four agreed formats"],
}

REWRITE_A = """Plain-language version of what the client expects:

You're delivering: solution.py — one module defining parse_amount; a type-hinted
signature with a docstring; a test run showing the agreed cases passing.

The client accepts the work when:
  • [OBJECTIVE] Deliverable is a Python file (.py)  — checked by: file type
  • [OBJECTIVE] parse_amount handles $1,234.56, €99, 1000 and -$5.25  — checked by: running the test cases
  • [OBJECTIVE] Function signature uses type hints  — checked by: required keyword

Deadline: Friday 13 Nov 2026, 18:00 UTC (hard cutoff). Revisions included: 2.
Not included:
  • CLI or database integration
  • Currency conversion and crypto amounts
  • Inputs beyond the four agreed formats

All three items are OBJECTIVE: they are checked by code, not opinion. If the tests
pass, payment releases automatically (simulated escrow)."""

QUESTIONS_A_FREELANCER = [
    "Do you want the function to raise ValueError on unparseable input, or "
    "return 0.0? (not covered by the checklist)",
    "Is the €99 case expected to work for any currency symbol, or only $ and €?",
    "If a test case fails on the first submission, do you want a fix inside the "
    "same deadline?",
    "Are the out-of-scope items definitely excluded even if they seem small?",
]

SOLUTION_PY = '''"""Money-string parsing for the ClearPay demo."""

from __future__ import annotations


def parse_amount(raw: str) -> float:
    """Parse a currency string such as '$1,234.56' or '€99' into a float.

    Handles thousands separators, currency symbols, plain numbers and
    parenthesised or leading-minus negatives.
    """
    text = raw.strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    cleaned = "".join(ch for ch in text if ch.isdigit() or ch in ".-+")
    if cleaned in ("", "-", "+", "."):
        raise ValueError(f"not a money amount: {raw!r}")
    return float(cleaned)
'''

QUESTIONS_B = QUESTIONS_A

ANSWERS_B = [
    "A polished 600-word blog post in Markdown with an Introduction and a "
    "Key takeaways section, ready to publish.",
    "Our example post: short paragraphs, second person, no corporate jargon, "
    "one practical tip per paragraph.",
    "Wednesday 11 Nov 2026, 12:00 UTC.",
    "1 round",
    "No images, no SEO meta description, no social promotion.",
]

SPEC_B = {
    "title": "Blog post: avoiding scope creep (600 words)",
    "deliverables": [
        "Markdown blog post of about 600 words",
        "Introduction and Key takeaways sections",
    ],
    "checklist": [
        {"id": "c1", "kind": "OBJECTIVE",
         "text": "Between 500 and 700 words",
         "check": {"type": "word_count", "min": 500, "max": 700}},
        {"id": "c2", "kind": "OBJECTIVE",
         "text": "Includes an Introduction and a Key takeaways section",
         "check": {"type": "sections", "values": ["Introduction", "Key takeaways"]}},
        {"id": "c3", "kind": "SUBJECTIVE",
         "text": "Tone matches the client's example: friendly and conversational",
         "check": None},
    ],
    "deadline": "Wednesday 11 Nov 2026, 12:00 UTC",
    "revision_limit": 1,
    "out_of_scope": ["Images or graphics", "SEO meta description",
                     "Social media promotion"],
}

REWRITE_B = """Plain-language version of what the client expects:

You're delivering: a Markdown blog post of about 600 words with an Introduction
and a Key takeaways section.

The client accepts the work when:
  • [OBJECTIVE] Between 500 and 700 words  — checked by: word count
  • [OBJECTIVE] Includes an Introduction and a Key takeaways section  — checked by: required sections
  • [SUBJECTIVE] Tone matches the client's example: friendly and conversational  — human judgement

Deadline: Wednesday 11 Nov 2026, 12:00 UTC. Revisions included: 1.
Not included:
  • Images or graphics
  • SEO meta description
  • Social media promotion

The first two items are checked by code. The tone item needs a human: if the
objective checks pass but tone is off, a reviewer decides (simulated escrow)."""

QUESTIONS_B_FREELANCER = [
    "Can you paste the exact example post you keep mentioning? “Friendly and "
    "conversational” means different things to different people.",
    "Is 600 words a hard range, or is 480 fine if the content is tight?",
    "Who signs off the subjective tone call — you or your marketing lead?",
    "Are the out-of-scope items (images, SEO meta, social promotion) definitely "
    "excluded even if they seem small?",
]

DRAFT_B = """## Introduction

Scope creep is the quiet killer of freelance projects. A client asks for one
small extra, you say yes to keep them happy, and suddenly the two-day job has
taken a week. The fix is not a bigger contract; it is a clearer agreement
written down before you start.

Most freelancers already sense this. They price for the work they were told
about, then absorb the work that appears later. A friendly conversation at the
start beats an awkward invoice at the end.

## Why it happens

Scope creep usually starts with a missing definition of done. Nobody wrote down
what the deliverable was, so every new idea looks reasonable. When the client
says "while you are in there", there is no shared list to point at.

## What to do instead

Write the acceptance list together. Keep it short, keep it objective where you
can, and make the subjective parts explicit. When a new request arrives, check
it against the list. If it is not on the list, it is a new piece of work with a
new price.
"""


def _seed_job_a(conn) -> None:
    job_id = db.create_job(conn, "Python money-string parser (parse_amount)",
                           "I need a Python function that parses money strings "
                           "like \"$1,234.56\" or \"€99\" into floats. It should "
                           "handle thousands separators, currency symbols, plain "
                           "numbers and negative amounts, with type hints and tests.",
                           prefill={"kind": "code", "filename": "solution.py",
                                    "content": SOLUTION_PY})
    for i, (q, a) in enumerate(zip(QUESTIONS_A, ANSWERS_A), start=1):
        db.add_message(conn, job_id, "system", "question", q, seq=i)
        db.add_message(conn, job_id, "client", "answer", a, seq=i + 0.5)
    _finish_setup(conn, job_id, SPEC_A, REWRITE_A, QUESTIONS_A_FREELANCER)
    from . import ledger
    ledger.fund(conn, db.get_job(conn, job_id), 450)
    db.add_event(conn, job_id, "demo", "Seeded demo job",
                 "Job A — passes verification and auto-releases (simulated).")


def _seed_job_b(conn) -> None:
    job_id = db.create_job(conn, "Blog post: avoiding scope creep (600 words)",
                           "Write a 600-word blog post for our SaaS blog about how "
                           "freelancers can avoid scope creep with clients. Tone: "
                           "friendly and conversational, like our example post. Must "
                           "include an Introduction and a Key takeaways section.")
    for i, (q, a) in enumerate(zip(QUESTIONS_B, ANSWERS_B), start=1):
        db.add_message(conn, job_id, "system", "question", q, seq=i)
        db.add_message(conn, job_id, "client", "answer", a, seq=i + 0.5)
    _finish_setup(conn, job_id, SPEC_B, REWRITE_B, QUESTIONS_B_FREELANCER)
    from . import ledger
    ledger.fund(conn, db.get_job(conn, job_id), 250)

    db.add_submission(conn, job_id, "text", DRAFT_B, filename="scope-creep-draft.md")
    job = db.get_job(conn, job_id)
    report = verify.run_verification(conn, job, db.latest_submission(conn, job_id))
    db.save_verification(conn, job_id, report.model_dump())
    db.update_job(conn, job_id, status=db.ST_HUMAN_REVIEW)
    db.add_event(conn, job_id, "submit", "Deliverable submitted",
                 "text submission (scope-creep-draft.md)")
    n_fail = sum(1 for i in report.items if i.verdict == "fail")
    n_rev = sum(1 for i in report.items if i.verdict == "needs_human_review")
    db.add_event(conn, job_id, "verify", "Verification needs a human",
                 f"{n_fail} failed, {n_rev} need human review.")
    db.add_event(conn, job_id, "demo", "Seeded demo job",
                 "Job B — partially fails verification → human reviewer dashboard.")


def _finish_setup(conn, job_id: str, spec: dict, rewrite: str,
                  questions: list[str]) -> None:
    from .routes import _lock_hash
    db.update_job(conn, job_id,
                  status=db.ST_CONFIRMED, spec_json=json.dumps(spec),
                  rewrite_json=json.dumps({"rewrite": rewrite,
                                           "questions": questions},
                                          ensure_ascii=False),
                  confirmed_client=1, confirmed_freelancer=1,
                  lock_hash=_lock_hash(spec))
    db.add_event(conn, job_id, "job", "Job created",
                 "Client described the job in plain language.")
    db.add_event(conn, job_id, "clarify", "Clarification questions answered",
                 "Client answered the AI's follow-up questions.")
    db.add_event(conn, job_id, "spec", "Structured spec generated",
                 f"{len(spec['checklist'])} checklist items.")
    db.add_event(conn, job_id, "confirm", "Both parties confirmed the spec",
                 "Client and freelancer confirmed.")
    db.add_event(conn, job_id, "lock", "Spec locked",
                 "Spec hash recorded; no further edits allowed.")


def ensure_seeded() -> bool:
    """Create the demo data if the database is empty. Returns True if seeded."""
    conn = db.connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        if count:
            return False
        _seed_job_a(conn)
        _seed_job_b(conn)
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    db.init_db()
    print("Seeded:" if ensure_seeded() else "Already seeded (nothing to do).")
    for j in db.list_jobs(db.connect()):
        print(f"  {j['id']}  {j['status']:>14}  {j['title']}")
