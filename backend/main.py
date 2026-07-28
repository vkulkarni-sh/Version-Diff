"""
OASYS Version Diff — FastAPI backend.

Reads the "Amelia & OASYS Release Schedule" Confluence page to discover the
ordered list of releases and their Jira release links, pulls each release's
bugs + enhancements from Jira, and — given a Source and Destination version —
returns everything fixed across that (inclusive) range, with an optional
plain-English narrative.

Endpoints:
  GET  /api/health         — liveness + which integrations are configured
  GET  /api/versions       — ordered version list for the dropdowns
  POST /api/diff           — grouped Bugs/Enhancements across the range
  POST /api/diff/release-notes — generate a release-notes PDF (download path)
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

import config
from routers import api

app = FastAPI(title="OASYS Version Diff", version="0.1.0")

origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "confluence_configured": config.confluence_configured(),
        "jira_configured": config.jira_configured(),
        "anthropic_configured": config.anthropic_configured(),
        "jira_project": config.JIRA_PROJECT,
        "release_schedule_page_id": config.RELEASE_SCHEDULE_PAGE_ID,
    }
