"""TrustBridge — FastAPI application entrypoint.

Run locally with one command:  python -m app
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import db, llm, seed
from .config import API_KEY
from .routes import router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

DESCRIPTION = """
**TrustBridge** helps freelancers and clients agree on a clear,
checkable definition of *done* before work starts, verifies the delivered work
against it, and holds/releases payment in an escrow ledger.

> There is no integration with Cleva, Tether, Upwork, Fiverr or any payment
> provider — this is a standalone prototype.

### Flow
`POST /api/jobs` (brief) → `POST /api/jobs/{id}/clarify` (answers → spec) →
`POST /api/jobs/{id}/confirm` (client + freelancer lock the spec) →
`POST /api/jobs/{id}/fund` → `POST /api/jobs/{id}/submit`
(deliverable + verification) → auto-release or human review.

Auth: send the `X-API-Key` header (see `.env.example`; the UI picks it up from
`/config.js` automatically).
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    if seed.ensure_seeded():
        print("Seeded demo data (2 jobs).")
    yield


app = FastAPI(
    title="TrustBridge API",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(router)


@app.get("/config.js", include_in_schema=False)
def config_js() -> Response:
    """Frontend config — exposes only the demo API key, never an LLM key."""
    return Response(
        "window.TRUSTBRIDGE_API_KEY=" + json.dumps(API_KEY) + ";\n",
        media_type="application/javascript",
    )


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "llm_provider": llm.provider_name()}


# Static UI last so /api, /docs and /openapi.json win the route match.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
