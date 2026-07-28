"""Offline smoke test for the Confluence parser + version ordering/range logic.

Uses a fixture derived from the real release-schedule page storage XHTML and a
fake Jira version resolver, so it runs with no network / no tokens.
Run:  ./venv/bin/python test_parser.py
"""
from services import confluence, version_diff, jira

# --- Fixture: mimics the real storage XHTML structure from the probe -------- #
FIXTURE = """
<h1>Overview</h1><p>blah blah</p>
<h2>Current Release Track</h2>
<table><tbody>
<tr><td><p>6.20.5</p></td><td><p><a href="https://soundhound.atlassian.net/projects/AM5/versions/34245/tab/release-report-all-issues" data-card-appearance="inline">https://soundhound.atlassian.net/projects/AM5/versions/34245/tab/release-report-all-issues</a></p></td></tr>
<tr><td><p>6.20.7</p></td><td><p><a href="https://soundhound.atlassian.net/projects/AM5/versions/35063/tab/release-report-all-issues">x</a></p></td></tr>
</tbody></table>
<h3>OASYS 1.x.0 (Q2 '26 - Q4 '26)</h3>
<table><tbody>
<tr><td><p>OASYS 1.1.0</p></td><td><p><a href="https://soundhound.atlassian.net/projects/UP/versions/34144/tab/release-report-all-issues">y</a></p></td></tr>
<tr><td><p>dup of first</p></td><td><p><a href="https://soundhound.atlassian.net/projects/AM5/versions/34245/tab/release-report-all-issues">dup</a></p></td></tr>
</tbody></table>
<h2>Anchor Release Track &amp; LTS</h2>
<table><tbody>
<tr><td><p>8.1.0</p></td><td><p><a href="https://soundhound.atlassian.net/projects/AM5/versions/36765/tab/release-report-all-issues">z</a></p></td></tr>
</tbody></table>
"""

# --- 1. Link extraction ------------------------------------------------------ #
links = confluence.extract_version_links(FIXTURE)
print("LINKS:")
for l in links:
    print(" ", l["doc_index"], l["project"], l["jira_version_id"], "| section:", l["section"])
assert [l["jira_version_id"] for l in links] == ["34245", "35063", "34144", "36765"], "dedup/order wrong"
assert links[0]["section"] == "Current Release Track"
assert links[2]["section"].startswith("OASYS 1.x.0")
assert links[2]["project"] == "UP"
assert links[3]["section"].startswith("Anchor Release Track & LTS"), links[3]["section"]
print("  -> link extraction OK\n")

# --- 2. Version build + ordering (fake Jira resolver) ------------------------ #
FAKE = {
    "34245": {"id": "34245", "name": "Core-6.20.5", "description": None, "released": True,  "release_date": "2026-04-15", "archived": False, "project_id": 1},
    "35063": {"id": "35063", "name": "Core-6.20.7", "description": None, "released": True,  "release_date": "2026-07-01", "archived": False, "project_id": 1},
    "34144": {"id": "34144", "name": "UP-1.1.0",    "description": "Placeholder for OASYS 1.1.0", "released": False, "release_date": None, "archived": False, "project_id": 2},
    "36765": {"id": "36765", "name": "Core-8.1.0",  "description": "Placeholder for OASYS 1.1.0", "released": False, "release_date": None, "archived": False, "project_id": 1},
}
confluence.get_release_schedule = lambda page_id=None: FIXTURE          # type: ignore
jira.versions_by_id = lambda projects: FAKE                            # type: ignore
jira.get_version = lambda vid: FAKE[vid]                                # type: ignore

versions = version_diff._build_versions()
print("ORDERED VERSIONS:")
for v in versions:
    print(f'  #{v["order_index"]} {v["label"]:14} rd={v["release_date"]} oasys={v["oasys_label"]}')
# dated (chronological) first, then undated in doc order
assert [v["key"] for v in versions] == ["34245", "35063", "34144", "36765"], [v["key"] for v in versions]
assert versions[2]["oasys_label"] == "OASYS 1.1.0"
print("  -> ordering + oasys label OK\n")

# --- 3. Inclusive range ------------------------------------------------------ #
r = version_diff.compute_range("34245", "34144", versions)
assert r == ["34245", "35063", "34144"], r
print("RANGE 6.20.5 -> UP-1.1.0 (inclusive):", r)
# reversed picks auto-order
assert version_diff.compute_range("34144", "34245", versions) == ["34245", "35063", "34144"]
print("  -> reversed selection auto-ordered OK\n")

# --- 4. issuetype categorization -------------------------------------------- #
assert jira.categorize("Bug") == "bug"
assert jira.categorize("Improvement") == "enhancement"
assert jira.categorize("New Feature") == "enhancement"
assert jira.categorize("Spike") == "other"
print("categorization OK")

print("\nALL PARSER/LOGIC TESTS PASSED")
