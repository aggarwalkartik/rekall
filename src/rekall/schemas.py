"""Data models for Rekall."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class Memory(BaseModel):
    id: str
    content: str
    type: str  # instinct | decision | fact | session
    source: str | None = None  # user-explicit | extracted | imported | observed
    confidence: float = 1.0
    evidence_count: int = 1
    domain: str | None = None
    project: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_seen_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "active"
    deleted_at: str | None = None
    meta: str | None = None  # JSON blob


class Document(BaseModel):
    id: str
    title: str
    content: str
    type: str  # research | reference | session | project | idea
    source_path: str | None = None
    project: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "active"
    deleted_at: str | None = None
    meta: str | None = None


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    chunk_index: int


class RecallResult(BaseModel):
    id: str
    content: str
    type: str
    confidence: float | None = None
    score: float
    source_document: str | None = None
    source_title: str | None = None
