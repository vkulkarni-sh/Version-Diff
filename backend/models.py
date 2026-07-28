"""Pydantic models for the OASYS Version Diff API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Version(BaseModel):
    """One release version, as surfaced to the dropdowns."""
    key: str                              # stable id, e.g. "Core-6.20.7"
    label: str                            # display label from the Confluence page
    oasys_label: Optional[str] = None     # e.g. "OASYS 1.1.0" when known
    jira_version_id: Optional[str] = None
    released: bool = False
    release_date: Optional[str] = None
    url: Optional[str] = None             # Jira release link from the page


class Ticket(BaseModel):
    key: str
    summary: str = ""
    status: str = ""
    issuetype: str = ""
    priority: str = ""
    category: str = "other"               # bug | enhancement | other
    url: str = ""


class VersionBucket(BaseModel):
    """Tickets fixed in a single version, grouped."""
    version: Version
    bugs: list[Ticket] = []
    enhancements: list[Ticket] = []
    other: list[Ticket] = []
    error: Optional[str] = None           # set if Jira lookup for this version failed


class DiffRequest(BaseModel):
    source: str = Field(..., description="Source version key")
    destination: str = Field(..., description="Destination version key")
    refresh: bool = Field(default=False, description="Bypass ticket cache and re-pull from Jira")


class DiffResponse(BaseModel):
    source: Version
    destination: Version
    range_keys: list[str]                 # keys in range, in order
    buckets: list[VersionBucket]
    total_bugs: int = 0
    total_enhancements: int = 0
    total_other: int = 0


class SummaryRequest(BaseModel):
    source: str
    destination: str


class SummaryResponse(BaseModel):
    summary: str
