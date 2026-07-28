# Deploying OASYS Version Diff

Target: `amedeliveryutil01.aws.amelia.com` (RHEL 8). Public URL after deploy:
`http://toolhub.amelia.com/version-diff/`.

| | |
|---|---|
| Repo | `vkulkarni-sh/Version-Diff` |
| Server path | `/opt/amelia-version-diff` |
| Backend | uvicorn/FastAPI on `127.0.0.1:8004`, systemd unit `amelia-version-diff` |
| Frontend | Vite build served static by nginx under `/version-diff/` |
| Runs as | `vkulkarn:ipsoft` |

## 0. Environment keys (shared `/opt/amelia-tools/.env`)

This tool needs `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`, `CONFLUENCE_API_TOKEN`,
and (for the English summary) `ANTHROPIC_API_KEY`. Check which are present:

```bash
sudo grep -oE '^(JIRA_USER_EMAIL|JIRA_API_TOKEN|CONFLUENCE_API_TOKEN|ANTHROPIC_API_KEY)=' /opt/amelia-tools/.env
```

If `CONFLUENCE_API_TOKEN` is missing, append it (value from the Atlassian API
token page for the same user as Jira):

```bash
echo 'CONFLUENCE_API_TOKEN=REPLACE_WITH_TOKEN' | sudo tee -a /opt/amelia-tools/.env
```

## 1. Clone + backend venv

```bash
sudo git clone https://github.com/vkulkarni-sh/Version-Diff.git /opt/amelia-version-diff
sudo python3.11 -m venv /opt/amelia-version-diff/backend/venv
sudo /opt/amelia-version-diff/backend/venv/bin/pip install -r /opt/amelia-version-diff/backend/requirements.txt
```

## 2. Frontend build (Vite 4 — glibc 2.28 pin already in package.json)

```bash
cd /opt/amelia-version-diff/frontend && sudo npm install && sudo npm run build
```

## 3. Ownership (vkulkarn login group is ipsoft — trailing colon, no group name)

```bash
sudo chown -R vkulkarn: /opt/amelia-version-diff
```

## 4. systemd unit

```bash
sudo cp /opt/amelia-version-diff/systemd/amelia-version-diff.service /etc/systemd/system/amelia-version-diff.service
sudo systemctl daemon-reload
sudo systemctl enable --now amelia-version-diff
sudo systemctl status amelia-version-diff --no-pager
```

## 5. nginx — add two location blocks to the single config

Insert the blocks from `nginx/version-diff.snippet.conf` INSIDE the existing
`server { ... }` in `/etc/nginx/conf.d/amelia-tools.conf`, and mirror the same
edit into the `amelia-portal` repo's nginx copy so a portal pull doesn't revert
it. Then:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 6. Portal tile (in the `amelia-portal` repo → `portal/index.html`)

Add a tile after the Fetch Call Recording tile (adjust to match the existing
tile markup):

```html
<a class="tool-card" href="/version-diff/">
  <div class="tool-icon">🔀</div>
  <div class="tool-name">OASYS Version Diff</div>
  <div class="tool-desc">Bugs & enhancements fixed between two OASYS releases, from Confluence + Jira.</div>
</a>
```

Deploy the portal per its usual flow (git pull on `/opt/amelia-portal`).

## 7. Verify

```bash
# Backend alive + integrations configured
curl -s http://127.0.0.1:8004/api/health | python3 -m json.tool

# Through nginx (loopback + Host header; TLS terminates at the LB, port 80 only)
curl -s -H "Host: amedeliveryutil01.aws.amelia.com" http://127.0.0.1/version-diff/api/health | python3 -m json.tool

# Version list (first call crawls Confluence + Jira, then cached ~1h)
curl -s -H "Host: amedeliveryutil01.aws.amelia.com" http://127.0.0.1/version-diff/api/versions | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["count"],"versions");[print(v["order_index"],v["label"],v.get("release_date")) for v in d["versions"][:10]]'
```

Then open `http://toolhub.amelia.com/version-diff/`, pick a Source and
Destination, click **Compare**, confirm ticket links open the right Jira
issues, and click **Summarize in English**.

## Deploying updates later

`deploy = git pull on the server` (this tool runs from the checkout):

```bash
cd /opt/amelia-version-diff && sudo git pull
# if backend changed:
sudo systemctl restart amelia-version-diff
# if frontend changed:
cd /opt/amelia-version-diff/frontend && sudo npm run build
```

## Notes / gotchas

- **Search endpoint**: Jira Cloud removed the legacy `GET /rest/api/3/search`
  (returns 410 here). This tool uses `GET /rest/api/3/search/jql`.
- **Two projects**: the schedule links versions from both **AM5** and **UP**;
  versions are resolved by their (globally unique) numeric id, so no per-project
  config is needed.
- **Cache**: version list + per-version tickets are cached in
  `backend/data/version_diff.db` for `VERSION_DIFF_CACHE_TTL` seconds (default
  3600). Use the UI's **Refresh versions** button or `?refresh=true` /
  `{"refresh": true}` to force a re-pull.
- **Port 8004** is this tool's slot — add it to the server port map.
