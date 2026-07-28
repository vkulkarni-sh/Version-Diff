"""
Confluence client for OASYS Version Diff.

Reads the "Amelia & OASYS Release Schedule" page (id 1548517510) and extracts,
in document order, every Jira release link it contains.

The page is a set of tables under section headings (Current / Anchor / LTS /
OASYS 1.x, etc.). Each release is an anchor of the form:

    <a href="https://soundhound.atlassian.net/projects/AM5/versions/23085/tab/release-report-all-issues" ...>

Both the AM5 and UP Jira projects appear. We capture the project + numeric
version id + the nearest preceding heading (its "section"), dedup by id keeping
first occurrence, and preserve document order. The version's human name / dates
are resolved separately from Jira by id (see services/jira.get_version).
"""
from __future__ import annotations

import base64
import logging
import re
from typing import Optional

import httpx

import config

log = logging.getLogger(__name__)

# Matches either a section heading or a Jira release link, so we can walk the
# document in order and attribute each link to the heading above it.
_HEADING_RE = re.compile(r"<h([1-4])\b[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(
    r"/projects/(?P<project>[A-Za-z0-9]+)/versions/(?P<id>\d+)",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&rarr;": "→", "&nbsp;": " "}


def _auth_header() -> str:
    creds = f"{config.JIRA_USER_EMAIL}:{config.CONFLUENCE_API_TOKEN}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def _strip(html: str) -> str:
    text = _TAG_RE.sub("", html)
    for k, v in _ENTITY.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip()


def get_release_schedule(page_id: Optional[str] = None) -> str:
    """Return the storage-format XHTML body of the release-schedule page."""
    page_id = page_id or config.RELEASE_SCHEDULE_PAGE_ID
    url = f"{config.CONFLUENCE_API_BASE}/content/{page_id}"
    with httpx.Client(timeout=30.0) as c:
        resp = c.get(
            url,
            params={"expand": "body.storage"},
            headers={"Authorization": _auth_header(), "Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()["body"]["storage"]["value"]


def extract_version_links(html: str) -> list[dict]:
    """Ordered, de-duplicated Jira release links found on the page.

    Returns dicts: {jira_version_id, project, section, url, doc_index}
    in document order (first occurrence wins for a repeated id).
    """
    # Build a single ordered stream of (position, kind, payload) events.
    events: list[tuple[int, str, object]] = []
    for m in _HEADING_RE.finditer(html):
        events.append((m.start(), "heading", _strip(m.group(2))))
    for m in _LINK_RE.finditer(html):
        events.append((m.start(), "link", (m.group("project"), m.group("id"))))
    events.sort(key=lambda e: e[0])

    out: list[dict] = []
    seen: set[str] = set()
    current_section = ""
    idx = 0
    for _pos, kind, payload in events:
        if kind == "heading":
            current_section = payload  # type: ignore[assignment]
            continue
        project, vid = payload  # type: ignore[misc]
        if vid in seen:
            continue
        seen.add(vid)
        out.append({
            "jira_version_id": vid,
            "project": project.upper(),
            "section": current_section,
            "url": (
                f"{config.JIRA_BASE_URL}/projects/{project.upper()}"
                f"/versions/{vid}/tab/release-report-all-issues"
            ),
            "doc_index": idx,
        })
        idx += 1
    return out
