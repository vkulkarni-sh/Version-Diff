"""
Central config for OASYS Version Diff.

All secrets come from the environment. On the server they are provided by the
shared ``/opt/amelia-tools/.env`` (via the systemd ``EnvironmentFile=``). For
local development, a ``.env`` in the repo root or backend/ is auto-loaded.

Auth model (confirmed by the other tools):
  - Jira      : Basic  base64(JIRA_USER_EMAIL : JIRA_API_TOKEN_SHJira)
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
# Version Diff authenticates to Jira with the shJira token
# (JIRA_API_TOKEN_SHJira in the shared env). Fall back to a plain
# JIRA_API_TOKEN only for back-compat with an older single-token setup.
JIRA_API_TOKEN = (
    os.getenv("JIRA_API_TOKEN_SHJira")
    or os.getenv("JIRA_API_TOKEN")
    or ""
).strip()
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
# Confluence pages that list versions + their Jira release links. Harvested in
# order; a version id seen on an earlier page wins. Override with a
# comma-separated RELEASE_PAGE_IDS to add/remove pages without a code change.
#   1548517510 — "Amelia & OASYS Release Schedule" (space PM)
#   1736212555 — "Amelia V7 Patch Releases"        (space RND)
RELEASE_SCHEDULE_PAGE_ID = (os.getenv("RELEASE_SCHEDULE_PAGE_ID") or "1548517510").strip()
PATCH_RELEASE_PAGE_ID = (os.getenv("PATCH_RELEASE_PAGE_ID") or "1736212555").strip()
RELEASE_PAGE_IDS = [
    p.strip() for p in (
        os.getenv("RELEASE_PAGE_IDS")
        or f"{RELEASE_SCHEDULE_PAGE_ID},{PATCH_RELEASE_PAGE_ID}"
    ).split(",") if p.strip()
]

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
