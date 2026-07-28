# OASYS Version Diff

A tool for delivery/support engineers to see **what changed between two OASYS
releases** when planning an upgrade — without hand-walking the release schedule.

It reads the **"Amelia & OASYS Release Schedule"** Confluence page to discover
the ordered list of releases and their Jira release links, pulls each release's
**bugs and enhancements** from Jira, and — given a **Source** and **Destination**
version — shows everything fixed across that (inclusive) range, grouped and
linked back to Jira, and generates a downloadable **release-notes PDF** (with an
AI-written Overview + Highlights when a Claude key is configured).

## How it works

```
Confluence page (1548517510)         Jira (soundhound.atlassian.net)
  release-schedule tables      ─┐       /rest/api/3/version/{id}      → name, dates
  <a .../projects/AM5|UP/       │──►     /rest/api/3/search/jql        → issues per fixVersion
     versions/{id}/...>        ─┘
         │
         ▼
  ordered version list ──►  pick Source + Destination  ──►  inclusive range
         │                                                        │
         ▼                                                        ▼
  cache → backend/data/version_diff.db          grouped Bugs / Enhancements + Jira links
                                                         │
                                                         ▼
                                          optional "Summarize in English" (Anthropic SDK)
```

- **Versions** are gathered from every configured Confluence page (the release
  schedule + the V7 patch-releases page), de-duplicated by Jira version id, and
  ordered **ascending by version number** (so `7.3.2` < `7.3.10`, `6.20.x` < `7.x`).
- **Range** is inclusive of both the Source and Destination versions.
- **Bug vs Enhancement** is derived from the Jira issue type (Bug → bug;
  Improvement / New Feature / Story / Epic / Task → enhancement; else → other).

## Stack

- Backend: FastAPI + uvicorn (`backend/`), stdlib SQLite cache, `httpx` for
  Atlassian REST, `anthropic` SDK for the summary.
- Frontend: React + Vite 4 + Tailwind (`frontend/`), served static under the
  `/version-diff/` subpath.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + which integrations are configured |
| GET | `/api/versions?refresh=0` | ordered version list for the dropdowns |
| POST | `/api/diff` `{source,destination,refresh?}` | grouped Bugs/Enhancements across the range |
| POST | `/api/diff/release-notes` `{source,destination}` | generate a release-notes PDF; returns `{download_path, filename, …}` |
| GET | `/api/diff/release-notes/{file_id}` | download the generated PDF |

`source`/`destination` are version **keys** (the numeric Jira version id from
`/api/versions`).

## Configuration (env, from shared `/opt/amelia-tools/.env`)

| Var | Required | Notes |
|---|---|---|
| `JIRA_USER_EMAIL` | yes | same user for Jira + Confluence |
| `JIRA_API_TOKEN` | yes | Jira Basic-auth token |
| `CONFLUENCE_API_TOKEN` | yes | Confluence Basic-auth token (same user) |
| `ANTHROPIC_API_KEY` | for PDF prose | omit → PDF still generates with the full ticket listing, just no AI Overview/Highlights |
| `VERSION_DIFF_MODEL` | no | default `claude-sonnet-5` |
| `VERSION_DIFF_CACHE_TTL` | no | seconds, default `3600` |
| `RELEASE_PAGE_IDS` | no | comma-separated Confluence page ids to harvest versions from; default is the release-schedule page `1548517510` + the V7 patch-releases page `1736212555` |
| `CONFLUENCE_CLOUD_ID` | no | default is the SoundHound cloud id |

See [DEPLOY.md](DEPLOY.md) for full deployment steps.

## Local dev

```bash
cd backend
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
# put JIRA_USER_EMAIL / JIRA_API_TOKEN / CONFLUENCE_API_TOKEN / ANTHROPIC_API_KEY in ./.env
./venv/bin/uvicorn main:app --port 8004 --reload

cd ../frontend && npm install && npm run dev   # proxies /api to :8004
```

Offline logic test (no tokens needed): `./backend/venv/bin/python backend/test_parser.py`.
