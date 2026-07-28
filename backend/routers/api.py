"""
OASYS Version Diff — API routes.

  GET  /api/versions?refresh=0   — ordered version list for the two dropdowns
  POST /api/diff                 — grouped Bugs/Enhancements across the range
  POST /api/diff/release-notes    — generate a release-notes PDF, return download path
  GET  /api/diff/release-notes/{id} — download the generated PDF
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

import config
from models import DiffRequest, ReleaseNotesRequest
from services import release_notes, version_diff

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


@router.post("/diff/release-notes")
def post_release_notes(req: ReleaseNotesRequest) -> dict:
    """Generate a release-notes PDF for the range and return its download path.
    The AI prose (overview + highlights) is included when ANTHROPIC_API_KEY is
    set; otherwise the PDF still renders with the full ticket listing."""
    _require_config()
    try:
        return release_notes.create(req.source, req.destination)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("release-notes generation failed")
        raise _handle_upstream(e)


@router.get("/diff/release-notes/{file_id}")
def get_release_notes(file_id: str) -> FileResponse:
    path = release_notes.path_for(file_id)
    if path is None:
        raise HTTPException(404, "Release-notes file not found or expired. Generate it again.")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)
