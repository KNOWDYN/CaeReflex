"""Compact contracts and metadata queries for Gate 6C spatial graphs."""
from __future__ import annotations

import json
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from caereflex.spatial.contracts import (
    CoordinateFrame,
    SpatialArrayLink,
    SpatialArrayRole,
    SpatialDomain,
    SpatialEntity,
    SpatialEntityKind,
    SpatialEvidenceStatus,
    SpatialGraph,
    SpatialRelation,
    SpatialRelationKind,
    SpatialReviewStatus,
)

SPATIAL_QUERY_VERSION = "caereflex.spatial-query/1.0"
_E = TypeVar("_E", bound=Enum)


class SpatialQueryError(RuntimeError):
    """Raised when a bounded query is invalid or exceeds policy."""


class SpatialTraversalDirection(str, Enum):
    outgoing = "outgoing"
    incoming = "incoming"
    both = "both"


class SpatialBoundsMode(str, Enum):
    intersects = "intersects"
    contains = "contains"
    within = "within"


class SpatialQueryLimits(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    max_results: int = 100
    max_offset: int = 100_000
    max_scan_rows: int = 10_000
    max_depth: int = 8
    max_relations_scanned: int = 20_000
    max_serialized_bytes: int = 2 * 1024 * 1024

    @field_validator(
        "max_results", "max_scan_rows", "max_depth", "max_relations_scanned", "max_serialized_bytes"
    )
    @classmethod
    def positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("spatial query limits must be positive")
        return value

    @field_validator("max_offset")
    @classmethod
    def non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_offset must be non-negative")
        return value


class SpatialQueryDiagnostic(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class SpatialQueryResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    query_version: str = SPATIAL_QUERY_VERSION
    graph_id: str | None = None
    operation: str
    graph: SpatialGraph | None = None
    graphs: list[SpatialGraph] = Field(default_factory=list)
    frames: list[CoordinateFrame] = Field(default_factory=list)
    entities: list[SpatialEntity] = Field(default_factory=list)
    relations: list[SpatialRelation] = Field(default_factory=list)
    array_links: list[SpatialArrayLink] = Field(default_factory=list)
    returned_count: int = 0
    scanned_count: int = 0
    truncated: bool = False
    next_offset: int | None = None
    diagnostics: list[SpatialQueryDiagnostic] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def count_items(self) -> "SpatialQueryResult":
        self.returned_count = (1 if self.graph is not None else 0) + sum(
            len(items) for items in (self.graphs, self.frames, self.entities, self.relations, self.array_links)
        )
        return self


