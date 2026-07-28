"""
Jira REST client for OASYS Version Diff.

Pulls the project's release "versions" and, for a given version, the issues
fixed in it (bugs + enhancements). Auth + the Atlassian-Document-Format text
extractor mirror the existing Log Analyse ``bin/jira-search`` tool.

Search endpoint (confirmed Phase 0 on this instance):
  - legacy  GET /rest/api/3/search        -> 410 GONE (removed)
  - current GET /rest/api/3/search/jql    -> the one to use (nextPageToken / isLast)
We default to /search/jql. The legacy path is kept only as a fallback for a
404/410 on the new endpoint (e.g. a differently-configured instance); a 400 is a
bad-query error and is surfaced, never treated as "endpoint missing".
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

import config

log = logging.getLogger(__name__)

# issuetype.name -> our two buckets. Anything unlisted falls to "other".
_BUG_TYPES = {"bug", "defect"}
_ENHANCEMENT_TYPES = {
    "improvement", "new feature", "story", "epic", "task", "sub-task",
    "enhancement", "feature", "change request",
}

_search_endpoint: Optional[str] = None  # cached: "jql" | "legacy"


def _auth_header() -> str:
    creds = f"{config.JIRA_USER_EMAIL}:{config.JIRA_API_TOKEN}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=config.JIRA_BASE_URL,
        headers={"Authorization": _auth_header(), "Accept": "application/json"},
        timeout=30.0,
    )


def browse_url(key: str) -> str:
    return f"{config.JIRA_BASE_URL}/browse/{key}"


def categorize(issuetype: str) -> str:
    name = (issuetype or "").strip().lower()
    if name in _BUG_TYPES:
        return "bug"
    if name in _ENHANCEMENT_TYPES:
        return "enhancement"
    return "other"


def adf_to_text(node: Any) -> str:
    """Recursively flatten an Atlassian Document Format node to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") in ("hardBreak", "paragraph"):
            return adf_to_text(node.get("content")) + "\n"
        return adf_to_text(node.get("content"))
    return ""


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #
def _version_to_dict(v: dict) -> dict:
    return {
        "id": str(v.get("id")),
        "name": v.get("name"),
        "description": v.get("description"),
        "released": bool(v.get("released")),
        "release_date": v.get("releaseDate"),
        "archived": bool(v.get("archived")),
        "project_id": v.get("projectId"),
    }


def list_versions(project: Optional[str] = None) -> list[dict]:
    """All release versions of a project (unordered as returned by Jira)."""
    project = project or config.JIRA_PROJECT
    with _client() as c:
        resp = c.get(f"/rest/api/3/project/{project}/versions")
        resp.raise_for_status()
        data = resp.json()
    return [_version_to_dict(v) for v in data]


def versions_by_id(projects: list[str]) -> dict[str, dict]:
    """Fetch each project's full version list ONCE and index by version id.

    Turns the per-link `get_version` fan-out (one HTTP call per version on the
    schedule) into one call per distinct project. A project that fails to list
    is skipped (its versions fall back to per-id resolution by the caller).
    """
    out: dict[str, dict] = {}
    for p in projects:
        try:
            for v in list_versions(p):
                out[v["id"]] = v
        except httpx.HTTPError as e:
            log.warning("Could not list versions for project %s: %s", p, e)
    return out


def get_version(version_id: str) -> dict:
    """Resolve a single version by its (globally unique) id.

    The Confluence schedule links versions from BOTH the AM5 and UP projects, so
    we resolve by id rather than assuming a project.
    Returns {id, name, description, released, release_date, archived, project_id}.
    """
    with _client() as c:
        resp = c.get(f"/rest/api/3/version/{version_id}")
        resp.raise_for_status()
        return _version_to_dict(resp.json())


# --------------------------------------------------------------------------- #
# Issues in a version
# --------------------------------------------------------------------------- #
_FIELDS = ["summary", "status", "issuetype", "priority"]


def _issue_to_dict(issue: dict) -> dict:
    f = issue.get("fields", {}) or {}
    key = issue.get("key", "")
    issuetype = (f.get("issuetype") or {}).get("name", "")
    status = (f.get("status") or {}).get("name", "")
    priority = (f.get("priority") or {}).get("name", "")
    return {
        "key": key,
        "summary": f.get("summary") or "",
        "status": status,
        "issuetype": issuetype,
        "priority": priority,
        "category": categorize(issuetype),
        "url": browse_url(key),
    }


def issues_for_version(version_id: str) -> list[dict]:
    """Every issue whose fixVersion is ``version_id``.

    Queried by the numeric version id alone — it's globally unique, so this
    works whether the version belongs to AM5 or UP without a project filter.
    Handles either search endpoint transparently.
    """
    global _search_endpoint
    jql = f'fixVersion = {version_id} ORDER BY issuetype ASC, key ASC'

    order = ["jql", "legacy"] if _search_endpoint is None else [_search_endpoint]
    last_err: Optional[Exception] = None
    for endpoint in order:
        try:
            issues = (_search_jql if endpoint == "jql" else _search_legacy)(jql)
            _search_endpoint = endpoint
            return [_issue_to_dict(i) for i in issues]
        except httpx.HTTPStatusError as e:
            # 404/410 => endpoint not available on this instance; try the other.
            # A 400 is a bad-query error — surface it, don't fall through to the
            # (now-removed) legacy endpoint.
            if e.response.status_code in (404, 410) and _search_endpoint is None:
                last_err = e
                continue
            raise
    if last_err:
        raise last_err
    return []


def _search_jql(jql: str) -> list[dict]:
    """Current endpoint: /rest/api/3/search/jql (token pagination)."""
    issues: list[dict] = []
    token: Optional[str] = None
    with _client() as c:
        while True:
            params: dict[str, Any] = {"jql": jql, "maxResults": 100, "fields": ",".join(_FIELDS)}
            if token:
                params["nextPageToken"] = token
            resp = c.get("/rest/api/3/search/jql", params=params)
            resp.raise_for_status()
            data = resp.json()
            issues.extend(data.get("issues", []))
            if data.get("isLast") or not data.get("nextPageToken"):
                break
            token = data["nextPageToken"]
    return issues


def _search_legacy(jql: str) -> list[dict]:
    """Legacy endpoint: /rest/api/3/search (startAt/maxResults)."""
    issues: list[dict] = []
    start = 0
    with _client() as c:
        while True:
            params = {"jql": jql, "startAt": start, "maxResults": 100, "fields": ",".join(_FIELDS)}
            resp = c.get("/rest/api/3/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("issues", [])
            issues.extend(batch)
            total = data.get("total", 0)
            start += len(batch)
            if not batch or start >= total:
                break
    return issues
