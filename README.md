# TrustBridge · “ClearPay” prototype

**Agree on a checkable definition of *done* before the work starts — verify the delivery against it — release payment from a simulated escrow ledger.**

Built for the **Cleva × Tether “Future of Payments” hackathon**.

> ⚠️ **Simulated escrow only.** No real money, wallets, chains or payment providers are involved.
> There is **no integration with Cleva, Tether, Upwork or Fiverr** — none is claimed anywhere in
> this project. Every money surface in the UI is labelled **“Simulated escrow”** and every ledger
> row is stored with `simulated = 1`. All API keys are read from environment variables
> (see `.env.example`); no real secrets live in this repo.

---

## Two layers, one engine

| Layer | What it does | Payment |
|---|---|---|
| **1 · Clarity tool** | Brief builder → 3–5 AI clarification questions → structured spec (deliverables, acceptance checklist tagged `OBJECTIVE`/`SUBJECTIVE`, deadline, revision limit, out-of-scope) → freelancer plain-language rewrite + “questions to ask the client” → both sides confirm → **spec locked** (SHA-256) | none |
| **2 · Platform API** | The same engine exposed as a small REST API a marketplace could call, plus a **mock escrow ledger** (fund / release / refund) | simulated |

**Verification** prefers deterministic code over AI opinion:

* OBJECTIVE items → code: word count, file extension, required keywords/sections, and running
  provided test cases in a time-limited subprocess (10 s, temp dir, capped output).
* Everything else (SUBJECTIVE / non-codeable) → one LLM wrapper call returning per-item
  `pass / fail / needs_human_review` + a one-line reason.
* **All items pass → funds auto-release (simulated). Otherwise → Human Reviewer dashboard**
  where a reviewer sees checklist + submission + AI report and decides release / request changes / refund.

---

## Requirements

* Python **3.10+** (tested on 3.14) — no Node build step, no Docker.

## Setup

```bash
git clone https://github.com/RightFix/trust-bridge
cd trust-bridge

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # optional — defaults work for the demo
```

## Run — one command

```bash
python -m app
```

Open **<http://127.0.0.1:8765>** — the SQLite database is created and **seeded with two demo jobs**
automatically if it doesn’t exist.

* UI: `http://127.0.0.1:8765/`
* OpenAPI docs (Layer 2): `http://127.0.0.1:8765/docs`
* Health: `curl http://127.0.0.1:8765/api/health`

Reset the demo data any time: stop the server, delete `data/trustbridge.db`, start again.

### Optional: real LLM

The single wrapper module is `app/llm.py`. Without a key it runs in **deterministic offline mode**
(the whole demo works with no network). With a key:

```bash
export LLM_PROVIDER=openai        # or anthropic
export LLM_API_KEY=sk-...         # read from env only — never committed
# optional: LLM_BASE_URL, LLM_MODEL
python -m app
```

---

## Demo data (pre-seeded)

| Job | State at startup | What it shows |
|---|---|---|
| **A · Python money-string parser** | `funded`, submission prefilled | Click **Submit & run verification** → 3 deterministic checks pass (file type, running test cases, required signature) → **auto-release** in the simulated ledger |
| **B · Blog post: avoiding scope creep** | `human_review` with a full report | Word count **fails** (182 < 500), required section **fails** (“Key takeaways”), subjective tone item → **AI: needs human review** → open the Reviewer dashboard and decide |

---

## 2-minute demo script

> Prep: `python -m app`, open <http://127.0.0.1:8765>, keep the header role on **Client**.

**0:00–0:20 — The problem.** “Freelancers and clients disagree about what *done* means.
Scope creep starts with an undefined deliverable. TrustBridge makes both sides write it down,
check it, and only then move money — here in a simulated escrow.”

**0:20–1:00 — Job A, the happy path.**
1. Click job **“Python money-string parser”** → *Spec & confirmation*: show the checklist with
   `OBJECTIVE` badges (“checked by code”) and the locked-spec badge.
2. Switch role to **Freelancer** → *Freelancer view*: plain-language rewrite + “questions to ask
   the client” + the *Flag as unclear* button (mention: flagging returns the job to the client).
3. *Escrow (simulated)* tab → show the **FUND 450 USDT · simulated** entry and the
   “⚠ Simulated escrow — no real funds” banner.
4. Stay **Freelancer** → *Submission* tab → the correct `solution.py` is pre-filled →
   click **Submit & run verification**.
5. *Verification report* opens: 3 green ticks (file type / test cases `PASSED: 4/4` / required
   signature), banner *“payment released automatically (simulated)”* → *Escrow* tab shows
   **FUND → RELEASE**. Point at `simulated: true`.

**1:00–1:45 — Job B, the dispute path.**
1. Open **“Blog post: avoiding scope creep”** → *Verification report*: red ✕ word count
   (182 < 500), red ✕ missing “Key takeaways”, amber **AI · needs human review** on tone.
   “Objective checks are code; the AI recommends, a human decides.”
2. Switch role to **Reviewer** → same tab becomes the **Human review dashboard** with the AI
   recommendation → click **Release payment (simulated)** (or Request changes / Refund) →
   *Timeline* shows the reviewer decision, *Escrow* shows **RELEASE**.

**1:45–2:00 — Layer 2.** Open **`/docs`**: `POST /api/jobs` → `/clarify` → `/confirm` →
`/fund` → `/submit`, all with `X-API-Key`. “One engine, two layers: a clarity tool and an API
a marketplace could call — payments stay simulated.”

*(Bonus, if time):* back on the home page, paste a fresh brief → the AI asks 5 targeted
questions → answers → structured spec appears in seconds.

---

## REST API (Layer 2)

Auth: header `X-API-Key: <API_KEY>` (default `trustbridge-demo-key`, see `.env.example`).
Interactive docs: `/docs`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/jobs` | create a job from a plain-language brief |
| `POST` | `/api/jobs/{id}/clarify` | submit answers → structured spec |
| `POST` | `/api/jobs/{id}/confirm` | confirm as `client` or `freelancer` (locks spec) |
| `POST` | `/api/jobs/{id}/fund` | fund the milestone (**simulated**) |
| `POST` | `/api/jobs/{id}/submit` | submit a deliverable + run verification |
| `GET` | `/api/jobs/{id}` | status, spec, report, ledger entries, timeline |

Extra (used by the UI): `GET /api/jobs`, `GET /api/jobs/{id}/messages`, `POST /api/jobs/{id}/flag`,
`POST /api/jobs/{id}/spec`, `POST /api/jobs/{id}/review`, `GET /api/health`.

```bash
curl -X POST http://127.0.0.1:8765/api/jobs \
  -H "X-API-Key: trustbridge-demo-key" -H "Content-Type: application/json" \
  -d '{"brief":"Write a 600-word blog post about pricing as a freelancer."}'
```

Example `GET /api/jobs/{id}` payload includes `status`, `spec`, `report`, `ledger`
(each entry `simulated: true`) and `events`.

---

## Project layout

```
app/
  main.py      FastAPI app, /config.js, static mount, OpenAPI
  routes.py    REST endpoints + flow orchestration
  db.py        SQLite schema + data access, status machine
  ledger.py    SIMULATED escrow (fund / release / refund)
  llm.py       single LLM wrapper (mock | openai | anthropic) + prompt-injection guard
  checks.py    deterministic checks (word count, file type, keywords, sections, tests)
  verify.py    deterministic → AI → report → auto-release vs human review
  schemas.py   pydantic models, incl. the JSON schema the LLM must satisfy
  seed.py      the two demo jobs
static/        index.html, app.js, styles.css (no build step)
data/          trustbridge.db (gitignored, re-created + seeded on first run)
```

### Notes on safety (hackathon scope)

* Submitted deliverables are **untrusted data**: they only ever appear inside
  `<<<UNTRUSTED_DELIVERABLE …>>>` blocks with system-level instructions to ignore anything inside
  them; they can never change the checklist or the verdict rules.
* LLM output must match a pydantic JSON schema; invalid JSON is retried **once**, then the request
  fails loudly instead of accepting garbage.
* Code test cases run in a subprocess with a 10-second timeout in a temp directory — this is a
  **local demo**, not a hardened sandbox (don’t run untrusted submissions on a public server).
* No user accounts: the UI has a demo role switcher (Client / Freelancer / Reviewer) only.

## Licence / disclaimer

Hackathon prototype. Not affiliated with, endorsed by, or integrated with Cleva, Tether, Upwork or
Fiverr. No real payments are ever processed.
