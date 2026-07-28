"""
OASYS Version Diff — API routes.

  GET  /api/versions?refresh=0   — ordered version list for the two dropdowns
  POST /api/diff                 — grouped Bugs/Enhancements across the range
  POST /api/diff/summary         — AI English narrative for the same range
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query

import config
from models import DiffRequest, SummaryRequest
from services import version_diff

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["version-diff"])


def _require_config() -> None:
    missing = []
    if not config.confluence_configured():
        missing.append("CONFLUENCE_API_TOKEN (+ JIRA_USER_EMAIL)")
    if not config.jira_configured():
        missing.append("JIRA_API_TOKEN (+ JIRA_USER_EMAIL)")
    if missing:
        raise HTTPException(
            status_code=503,
            detail="Missing server configuration: " + ", ".join(missing)
            + ". Add to /opt/amelia-tools/.env and restart amelia-version-diff.",
        )


def _handle_upstream(e: Exception) -> HTTPException:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        who = "Confluence" if "confluence" in str(e.request.url).lower() else "Jira"
        if code in (401, 403):
            return HTTPException(502, f"{who} rejected the credentials ({code}). Check the API token.")
        return HTTPException(502, f"{who} returned HTTP {code}.")
    if isinstance(e, httpx.HTTPError):
        return HTTPException(504, f"Could not reach Atlassian: {e}")
    return HTTPException(500, str(e))


@router.get("/versions")
def get_versions(refresh: bool = Query(default=False)) -> dict:
    _require_config()
    try:
        versions = version_diff.get_versions(refresh=refresh)
    except Exception as e:  # noqa: BLE001
        log.exception("get_versions failed")
        raise _handle_upstream(e)
    return {"versions": versions, "count": len(versions)}


@router.post("/diff")
def post_diff(req: DiffRequest) -> dict:
    _require_config()
    if req.source == req.destination:
        # A single version is a legitimate query (what shipped in exactly this one).
        pass
    try:
        return version_diff.diff(req.source, req.destination, refresh=req.refresh)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("diff failed")
        raise _handle_upstream(e)


@router.post("/diff/summary")
def post_summary(req: SummaryRequest) -> dict:
    _require_config()
    if not config.anthropic_configured():
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set — the English summary is unavailable.")
    try:
        return {"summary": version_diff.narrate(req.source, req.destination)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("summary failed")
        raise _handle_upstream(e)
