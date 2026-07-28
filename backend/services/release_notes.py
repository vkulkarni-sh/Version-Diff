"""
Release-notes generation for OASYS Version Diff.

Given a Source→Destination range, produces a downloadable, release-notes-style
**PDF**:
  1. Claude writes a grounded Overview + themed Key Highlights (JSON), citing
     ticket keys — no invented tickets. Skipped gracefully if no ANTHROPIC key.
  2. ReportLab renders a branded PDF: title, source→dest, generation date and
     totals, the prose, then every version's Bug Fixes / Enhancements as
     bullet lists with clickable Jira links.

The PDF is written to ``data/exports/<id>.pdf`` and served by the download
endpoint. Generation is grounded in the same structured diff the /diff endpoint
returns, so the ticket listing is authoritative.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm

import config
from services import version_diff

log = logging.getLogger(__name__)

EXPORTS_DIR = config.DATA_DIR / "exports"

# OASYS palette (matches the frontend / brand)
_VIOLET = colors.HexColor("#6d3eff")
_VIOLET_LT = colors.HexColor("#a78bfa")
_ROSE = colors.HexColor("#e11d48")
_EMERALD = colors.HexColor("#059669")
_SLATE = colors.HexColor("#334155")
_MUTED = colors.HexColor("#64748b")

_RN_SYSTEM = (
    "You are a technical writer producing customer-facing release notes for the "
    "SoundHound OASYS platform. You are given the bugs and enhancements fixed "
    "across a range of releases. Write a concise, professional Overview and a "
    "set of themed Key Highlights.\n"
    "Rules:\n"
    "- Ground EVERYTHING in the provided tickets. Never invent tickets, numbers, "
    "or features.\n"
    "- Cite ticket keys in parentheses where relevant, e.g. (AM5-18731).\n"
    "- Highlights should group related changes into themes and lead with customer "
    "impact, not internal jargon.\n"
    "Return ONLY valid JSON, no markdown fences, matching exactly:\n"
    '{"overview": "2-4 sentence paragraph", "highlights": ["bullet", "bullet", ...]}'
)


def _prose(d: dict) -> dict:
    """Claude-generated {overview, highlights[]}. Empty if no key / on failure."""
    if not config.anthropic_configured():
        return {"overview": "", "highlights": []}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=180.0, max_retries=2)
        msg = client.messages.create(
            model=config.VERSION_DIFF_MODEL,
            max_tokens=2048,
            system=_RN_SYSTEM,
            messages=[{"role": "user", "content": version_diff.diff_to_prompt(d)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        data = json.loads(text)
        return {
            "overview": str(data.get("overview", "")).strip(),
            "highlights": [str(h).strip() for h in data.get("highlights", []) if str(h).strip()],
        }
    except Exception as e:  # noqa: BLE001 — prose is best-effort; the PDF still renders without it
        log.warning("Release-notes prose generation failed: %s", e)
        return {"overview": "", "highlights": []}


# --------------------------------------------------------------------------- #
# PDF rendering
# --------------------------------------------------------------------------- #
def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("rnTitle", parent=base["Title"], fontSize=24, leading=28,
                                 textColor=_VIOLET, spaceAfter=2),
        "subtitle": ParagraphStyle("rnSub", parent=base["Heading2"], fontSize=14, leading=18,
                                   textColor=_SLATE, spaceAfter=2),
        "meta": ParagraphStyle("rnMeta", parent=base["Normal"], fontSize=9, textColor=_MUTED,
                               spaceAfter=10),
        "h2": ParagraphStyle("rnH2", parent=base["Heading2"], fontSize=14, leading=18,
                             textColor=_VIOLET, spaceBefore=10, spaceAfter=6),
        "vh": ParagraphStyle("rnVH", parent=base["Heading2"], fontSize=13, leading=16,
                            textColor=colors.HexColor("#1e293b"), spaceBefore=14, spaceAfter=2,
                            borderPadding=(0, 0, 4, 0)),
        "vhmeta": ParagraphStyle("rnVHmeta", parent=base["Normal"], fontSize=8.5, textColor=_MUTED,
                                spaceAfter=6),
        "bugh": ParagraphStyle("rnBugH", parent=base["Heading3"], fontSize=10.5, textColor=_ROSE,
                              spaceBefore=6, spaceAfter=2),
        "enhh": ParagraphStyle("rnEnhH", parent=base["Heading3"], fontSize=10.5, textColor=_EMERALD,
                              spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("rnBody", parent=base["Normal"], fontSize=10, leading=14,
                              alignment=TA_LEFT, spaceAfter=4),
        "ticket": ParagraphStyle("rnTicket", parent=base["Normal"], fontSize=9.5, leading=13,
                                leftIndent=10, spaceAfter=1),
    }


def _ticket_line(t: dict, styles: dict):
    from reportlab.platypus import Paragraph
    key = escape(t.get("key", ""))
    summary = escape(t.get("summary", ""))
    status = escape(t.get("status", ""))
    url = t.get("url", "")
    link = f'<a href="{escape(url)}" color="#6d3eff"><b>{key}</b></a>' if url else f"<b>{key}</b>"
    status_txt = f' <font color="#64748b">[{status}]</font>' if status else ""
    return Paragraph(f"{link} &mdash; {summary}{status_txt}", styles["ticket"])


def _draw_chrome(canvas, doc):
    """Top rule + footer with page number on every page."""
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(_VIOLET)
    canvas.setLineWidth(2)
    canvas.line(20 * mm, h - 14 * mm, w - 20 * mm, h - 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_MUTED)
    canvas.drawString(20 * mm, h - 12.5 * mm, "SoundHound AI · OASYS")
    canvas.drawRightString(w - 20 * mm, 12 * mm, f"Page {doc.page}")
    canvas.drawString(20 * mm, 12 * mm, "OASYS Release Notes")
    canvas.restoreState()


def build_pdf(d: dict, prose: dict, out_path: Path) -> None:
    from reportlab.platypus import (HRFlowable, ListFlowable, ListItem, PageBreak,
                                    Paragraph, SimpleDocTemplate, Spacer)

    styles = _styles()
    src, dst = d["source"], d["destination"]
    generated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    story = [
        Paragraph("OASYS Release Notes", styles["title"]),
        Paragraph(f"{escape(src['label'])} &rarr; {escape(dst['label'])}", styles["subtitle"]),
        Paragraph(
            f"Generated {generated} &nbsp;·&nbsp; {len(d['range_keys'])} version(s) &nbsp;·&nbsp; "
            f"{d['total_bugs']} bug fixes &nbsp;·&nbsp; {d['total_enhancements']} enhancements",
            styles["meta"],
        ),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#e2e8f0"), spaceAfter=8),
    ]

    if prose.get("overview"):
        story.append(Paragraph("Overview", styles["h2"]))
        story.append(Paragraph(escape(prose["overview"]), styles["body"]))
    if prose.get("highlights"):
        story.append(Paragraph("Key Highlights", styles["h2"]))
        story.append(ListFlowable(
            [ListItem(Paragraph(escape(h), styles["body"]), leftIndent=12) for h in prose["highlights"]],
            bulletColor=_VIOLET, bulletFontSize=8, start="square",
        ))

    story.append(PageBreak())
    story.append(Paragraph("Detailed Changes", styles["h2"]))

    for b in d["buckets"]:
        v = b["version"]
        header = escape(v["label"]) + (f" &mdash; {escape(v['oasys_label'])}" if v.get("oasys_label") else "")
        story.append(Paragraph(header, styles["vh"]))
        meta_bits = []
        if v.get("section"):
            meta_bits.append(escape(v["section"]))
        if v.get("release_date"):
            meta_bits.append(f"released {v['release_date']}")
        elif not v.get("released"):
            meta_bits.append("unreleased")
        if meta_bits:
            story.append(Paragraph(" · ".join(meta_bits), styles["vhmeta"]))

        if b.get("error"):
            story.append(Paragraph(f"<i>Could not load tickets: {escape(str(b['error']))}</i>", styles["body"]))
            continue
        if not (b["bugs"] or b["enhancements"] or b["other"]):
            story.append(Paragraph("<i>No bugs or enhancements recorded for this version.</i>", styles["body"]))
            continue

        if b["bugs"]:
            story.append(Paragraph(f"Bug Fixes ({len(b['bugs'])})", styles["bugh"]))
            for t in b["bugs"]:
                story.append(_ticket_line(t, styles))
        if b["enhancements"]:
            story.append(Paragraph(f"Enhancements ({len(b['enhancements'])})", styles["enhh"]))
            for t in b["enhancements"]:
                story.append(_ticket_line(t, styles))
        if b["other"]:
            story.append(Paragraph(f"Other ({len(b['other'])})", styles["bugh"]))
            for t in b["other"]:
                story.append(_ticket_line(t, styles))

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title="OASYS Release Notes", author="SoundHound AI · OASYS",
    )
    doc.build(story, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _safe(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-") or "version"


def create(source_key: str, dest_key: str) -> dict:
    """Generate the PDF and return {file_id, filename, download_path, ...}."""
    d = version_diff.diff(source_key, dest_key)
    prose = _prose(d)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:16]
    out_path = EXPORTS_DIR / f"{file_id}.pdf"
    build_pdf(d, prose, out_path)

    filename = f"OASYS-Release-Notes-{_safe(d['source']['label'])}-to-{_safe(d['destination']['label'])}.pdf"
    return {
        "file_id": file_id,
        "filename": filename,
        "download_path": f"/api/diff/release-notes/{file_id}",
        "range_keys": d["range_keys"],
        "total_bugs": d["total_bugs"],
        "total_enhancements": d["total_enhancements"],
        "had_prose": bool(prose.get("overview") or prose.get("highlights")),
    }


def path_for(file_id: str) -> Path | None:
    # file_id is our own hex token; still guard against traversal.
    if not re.fullmatch(r"[0-9a-f]{6,32}", file_id or ""):
        return None
    p = EXPORTS_DIR / f"{file_id}.pdf"
    return p if p.exists() else None
