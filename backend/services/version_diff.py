"""
Orchestration for OASYS Version Diff.

Ties Confluence (which versions exist + their order + Jira links) to Jira (each
version's name/dates + the tickets fixed in it), caches everything to the local
SQLite store, and produces the Source→Destination diff plus an optional English
narrative.

Ordering: the schedule's versions are ordered chronologically by Jira release
date (a real upgrade timeline); versions with no release date yet (placeholders /
unreleased) are kept after dated ones, in the page's document order. The full
ordered list is returned to the UI so the included range is always transparent.
"""
from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Optional

import config
from services import confluence, jira, store

log = logging.getLogger(__name__)

_versions_lock = Lock()
_versions_cache: Optional[list[dict]] = None
_versions_cached_at: float = 0.0


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #
def _oasys_label(description: Optional[str]) -> Optional[str]:
    if not description:
        return None
    # Jira descriptions like "Placeholder for OASYS 1.1.0" carry the OASYS name.
    import re
    m = re.search(r"OASYS\s+[0-9][0-9A-Za-z.\-]*", description)
    return m.group(0) if m else None


def _sort_key(v: dict):
    rd = v.get("release_date")
    # dated versions first (chronological), then undated in document order
    return (rd is None, rd or "", v.get("doc_index", 0))


def _build_versions() -> list[dict]:
    """Pull the schedule from Confluence, resolve each version from Jira."""
    html = confluence.get_release_schedule()
    links = confluence.extract_version_links(html)

    # Resolve version metadata with ONE call per distinct project (AM5, UP)
    # instead of one call per version. Fall back to per-id lookup only for the
    # rare version that isn't in its project's list.
    projects = sorted({link["project"] for link in links})
    id_map = jira.versions_by_id(projects)

    versions: list[dict] = []
    for link in links:
        vid = link["jira_version_id"]
        meta = id_map.get(vid) or {}
        if not meta:
            try:
                meta = jira.get_version(vid)
            except Exception as e:  # noqa: BLE001 — a deleted/inaccessible version shouldn't kill the list
                log.warning("Could not resolve Jira version %s: %s", vid, e)
        name = meta.get("name") or f"{link['project']}-{vid}"
        versions.append({
            "key": vid,                       # numeric version id — globally unique
            "label": name,
            "oasys_label": _oasys_label(meta.get("description")),
            "jira_version_id": vid,
            "project": link["project"],
            "section": link.get("section"),
            "released": meta.get("released", False),
            "release_date": meta.get("release_date"),
            "url": link["url"],
            "doc_index": link["doc_index"],
        })
    versions.sort(key=_sort_key)
    for i, v in enumerate(versions):
        v["order_index"] = i
    return versions


def get_versions(refresh: bool = False) -> list[dict]:
    """Ordered version list for the dropdowns. Cached in memory + SQLite."""
    global _versions_cache, _versions_cached_at
    with _versions_lock:
        fresh = (
            _versions_cache is not None
            and (time.time() - _versions_cached_at) < config.CACHE_TTL_SECONDS
        )
        if not refresh and fresh:
            return _versions_cache

        if not refresh:
            # Try the persisted copy before hitting the network.
            age = store.versions_age()
            if age is not None and age < config.CACHE_TTL_SECONDS:
                rows = store.get_versions()
                if rows:
                    _versions_cache = rows
                    _versions_cached_at = time.time() - age
                    return rows

        versions = _build_versions()
        store.save_versions(versions)
        _versions_cache = versions
        _versions_cached_at = time.time()
        return versions


def _version_by_key(versions: list[dict], key: str) -> Optional[dict]:
    for v in versions:
        if v["key"] == key:
            return v
    return None


def compute_range(source_key: str, dest_key: str, versions: Optional[list[dict]] = None) -> list[str]:
    """Inclusive slice of version keys from source to destination (auto-ordered)."""
    versions = versions or get_versions()
    order = [v["key"] for v in versions]
    if source_key not in order:
        raise ValueError(f"Unknown source version: {source_key}")
    if dest_key not in order:
        raise ValueError(f"Unknown destination version: {dest_key}")
    i, j = order.index(source_key), order.index(dest_key)
    lo, hi = (i, j) if i <= j else (j, i)
    return order[lo:hi + 1]


# --------------------------------------------------------------------------- #
# Tickets per version (cached)
# --------------------------------------------------------------------------- #
def _tickets_for(version_key: str, refresh: bool) -> list[dict]:
    if not refresh:
        age = store.tickets_age(version_key)
        if age is not None and age < config.CACHE_TTL_SECONDS:
            return store.get_tickets(version_key)
    tickets = jira.issues_for_version(version_key)
    store.save_tickets(version_key, tickets)
    return tickets


# --------------------------------------------------------------------------- #
# Diff
# --------------------------------------------------------------------------- #
def diff(source_key: str, dest_key: str, refresh: bool = False) -> dict:
    versions = get_versions()
    range_keys = compute_range(source_key, dest_key, versions)

    buckets = []
    total_bugs = total_enh = total_other = 0
    for key in range_keys:
        v = _version_by_key(versions, key)
        bucket = {"version": v, "bugs": [], "enhancements": [], "other": [], "error": None}
        try:
            for t in _tickets_for(key, refresh):
                cat = t.get("category", "other")
                if cat == "bug":
                    bucket["bugs"].append(t)
                elif cat == "enhancement":
                    bucket["enhancements"].append(t)
                else:
                    bucket["other"].append(t)
        except Exception as e:  # noqa: BLE001
            log.warning("Jira lookup failed for version %s: %s", key, e)
            bucket["error"] = str(e)
        total_bugs += len(bucket["bugs"])
        total_enh += len(bucket["enhancements"])
        total_other += len(bucket["other"])
        buckets.append(bucket)

    src = _version_by_key(versions, range_keys[0])
    dst = _version_by_key(versions, range_keys[-1])
    return {
        "source": src,
        "destination": dst,
        "range_keys": range_keys,
        "buckets": buckets,
        "total_bugs": total_bugs,
        "total_enhancements": total_enh,
        "total_other": total_other,
    }


# --------------------------------------------------------------------------- #
# English narrative (Anthropic SDK)
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "You are a release-notes assistant for the SoundHound OASYS platform. "
    "Given the bugs and enhancements fixed across a range of releases, write a "
    "clear, concise upgrade summary in plain English for a delivery engineer "
    "planning an upgrade. Group the narrative by theme where natural. Reference "
    "tickets inline by their key (e.g. AM5-18731) so they can be cross-checked. "
    "Do not invent tickets or details beyond what is provided. Use short "
    "paragraphs and bullet lists; no preamble, no closing pleasantries."
)


def _diff_to_prompt(d: dict) -> str:
    lines = [
        f"Upgrade from {d['source']['label']} to {d['destination']['label']}.",
        f"Versions in range ({len(d['range_keys'])}): "
        + ", ".join(v["label"] for v in [b["version"] for b in d["buckets"]]),
        f"Totals: {d['total_bugs']} bugs, {d['total_enhancements']} enhancements.",
        "",
    ]
    for b in d["buckets"]:
        v = b["version"]
        lines.append(f"### {v['label']}"
                     + (f" ({v['oasys_label']})" if v.get("oasys_label") else "")
                     + (f" — released {v['release_date']}" if v.get("release_date") else ""))
        if b["error"]:
            lines.append(f"(could not load tickets: {b['error']})")
        for t in b["bugs"]:
            lines.append(f"- BUG {t['key']}: {t['summary']} [{t['status']}]")
        for t in b["enhancements"]:
            lines.append(f"- ENH {t['key']}: {t['summary']} [{t['status']}]")
        lines.append("")
    return "\n".join(lines)


def narrate(source_key: str, dest_key: str) -> str:
    if not config.anthropic_configured():
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set on this server — the English summary is "
            "unavailable. The grouped ticket list is still fully available."
        )
    import anthropic

    d = diff(source_key, dest_key)
    prompt = _diff_to_prompt(d)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=180.0, max_retries=2)
    msg = client.messages.create(
        model=config.VERSION_DIFF_MODEL,
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if getattr(block, "type", None) == "text")
