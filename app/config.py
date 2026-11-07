"""Environment configuration. Real secrets come only from env / .env (gitignored)."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=VALUE lines, # comments). Existing env wins."""
    path = Path(path or os.environ.get("ENV_FILE", BASE_DIR / ".env"))
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

# API key for the REST API (demo auth only — not a user authentication system).
API_KEY = os.environ.get("API_KEY", "trustbridge-demo-key")

# LLM provider selection is handled inside app.llm (LLM_PROVIDER / LLM_API_KEY /
# LLM_BASE_URL / LLM_MODEL). No key → deterministic mock provider.
