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


def _version_tuple(label: str) -> tuple:
    """Numeric version parts for ordering, e.g. 'Core-7.3.10' -> (7, 3, 10).
    Tuples of unequal length compare naturally (7,3) < (7,3,1) < (7,3,10)."""
    import re
    nums = re.findall(r"\d+", label or "")
    return tuple(int(n) for n in nums) if nums else (0,)


def _sort_key(v: dict):
    # Ascending by version NUMBER (so 7.3.1 < 7.3.2 < 7.3.10, and 6.20.x < 7.x),
    # then by label to keep same-number versions from different lines stable.
    return (_version_tuple(v.get("label", "")), v.get("label", ""))


def _build_versions() -> list[dict]:
    """Pull versions from every configured Confluence page, resolve from Jira."""
    # Harvest from every configured page. A page is parsed BOTH ways — the
    # release-schedule pages yield fixVersion links, the patch-releases page
    # yields expand macros with explicit ticket keys; each parser returns []
    # for a page that isn't its shape, so we don't need to know which is which.
    links: list[dict] = []          # {jira_version_id, project, section, url, doc_index}
    patches: list[dict] = []        # {label, ticket_keys, release_date, section, url}
    seen_ids: set[str] = set()
    seen_patch: set[str] = set()
    import re as _re
    for page_id in config.RELEASE_PAGE_IDS:
        try:
            html = confluence.get_release_schedule(page_id)
        except Exception as e:  # noqa: BLE001 — one bad page shouldn't drop the rest
            log.warning("Could not load Confluence page %s: %s", page_id, e)
            continue
        for link in confluence.extract_version_links(html):
            if link["jira_version_id"] in seen_ids:
                continue
            seen_ids.add(link["jira_version_id"])
            links.append(link)
        for p in confluence.extract_patch_versions(html, confluence.page_url(page_id)):
            # only real patch-version expands (label carries a dotted version)
            if not _re.search(r"\d+\.\d+", p["label"]) or p["label"] in seen_patch:
                continue
            seen_patch.add(p["label"])
            patches.append(p)

    # Resolve version metadata with ONE call per distinct project (AM5, UP, …)
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
            "ticket_keys": None,          # fetched by fixVersion
        })

    # Patch-line entries: tickets come from the explicit key list on the page.
    for p in patches:
        slug = "patch:" + _re.sub(r"[^a-z0-9.]+", "-", p["label"].lower()).strip("-")
        versions.append({
            "key": slug,
            "label": p["label"],
            "oasys_label": None,
            "jira_version_id": None,
            "project": config.JIRA_PROJECT,
            "section": p.get("section") or "V7 Patch Releases",
            "released": bool(p.get("release_date")),
            "release_date": p.get("release_date"),
            "url": p.get("url"),
            "doc_index": 10_000,
            "ticket_keys": p.get("ticket_keys") or [],
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
def _tickets_for(v: dict, refresh: bool) -> list[dict]:
    """Tickets for a version. Release versions query by fixVersion; patch-line
    entries fetch their explicit ticket-key list. Cached in the store either way."""
    key = v["key"]
    if not refresh:
        age = store.tickets_age(key)
        if age is not None and age < config.CACHE_TTL_SECONDS:
            return store.get_tickets(key)
    ticket_keys = v.get("ticket_keys")
    if ticket_keys:
        tickets = jira.issues_by_keys(ticket_keys)
    elif v.get("jira_version_id"):
        tickets = jira.issues_for_version(v["jira_version_id"])
    else:
        tickets = []
    store.save_tickets(key, tickets)
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
            for t in _tickets_for(v, refresh):
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
# Prompt builder (shared by the release-notes generator)
# --------------------------------------------------------------------------- #
def diff_to_prompt(d: dict) -> str:
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
