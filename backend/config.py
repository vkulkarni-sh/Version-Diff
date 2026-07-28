"""
Central config for OASYS Version Diff.

All secrets come from the environment. On the server they are provided by the
shared ``/opt/amelia-tools/.env`` (via the systemd ``EnvironmentFile=``). For
local development, a ``.env`` in the repo root or backend/ is auto-loaded.

Auth model (confirmed by the other tools):
  - Jira      : Basic  base64(JIRA_USER_EMAIL : JIRA_API_TOKEN)
  - Confluence: Basic  base64(JIRA_USER_EMAIL : CONFLUENCE_API_TOKEN)   ← same user
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env for local dev (no-op on the server where env comes from systemd).
for candidate in (Path(__file__).resolve().parent / ".env",
                  Path(__file__).resolve().parent.parent / ".env"):
    if candidate.exists():
        load_dotenv(candidate)
        break

# --- Identity / auth (shared between Jira + Confluence) ---------------------
JIRA_USER_EMAIL = (os.getenv("JIRA_USER_EMAIL") or "").strip()
JIRA_API_TOKEN = (os.getenv("JIRA_API_TOKEN") or "").strip()
CONFLUENCE_API_TOKEN = (os.getenv("CONFLUENCE_API_TOKEN") or "").strip()

# --- Jira -------------------------------------------------------------------
JIRA_BASE_URL = (os.getenv("JIRA_BASE_URL") or "https://soundhound.atlassian.net").rstrip("/")
JIRA_PROJECT = (os.getenv("JIRA_PROJECT") or "AM5").strip()

# --- Confluence -------------------------------------------------------------
CONFLUENCE_CLOUD_ID = (
    os.getenv("CONFLUENCE_CLOUD_ID") or "c38bf6a9-cef0-46cd-89bd-53a87e3fa553"
).strip()
CONFLUENCE_API_BASE = (
    os.getenv("CONFLUENCE_API_BASE")
    or f"https://api.atlassian.com/ex/confluence/{CONFLUENCE_CLOUD_ID}/wiki/rest/api"
).rstrip("/")
# The "Amelia OASYS Release Schedule" page that lists every version + Jira link.
RELEASE_SCHEDULE_PAGE_ID = (os.getenv("RELEASE_SCHEDULE_PAGE_ID") or "1548517510").strip()

# --- Anthropic (English narrative) ------------------------------------------
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
VERSION_DIFF_MODEL = (os.getenv("VERSION_DIFF_MODEL") or "claude-sonnet-5").strip()

# --- Storage ----------------------------------------------------------------
DATA_DIR = Path(os.getenv("VERSION_DIFF_DATA") or (Path(__file__).resolve().parent / "data"))
DB_PATH = DATA_DIR / "version_diff.db"

# How long a cached version list / ticket set is considered fresh (seconds).
CACHE_TTL_SECONDS = int(os.getenv("VERSION_DIFF_CACHE_TTL") or "3600")


def jira_configured() -> bool:
    return bool(JIRA_USER_EMAIL and JIRA_API_TOKEN)


def confluence_configured() -> bool:
    return bool(JIRA_USER_EMAIL and CONFLUENCE_API_TOKEN)


def anthropic_configured() -> bool:
    return bool(ANTHROPIC_API_KEY)
