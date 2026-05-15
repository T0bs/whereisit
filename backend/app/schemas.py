from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KindRef(BaseModel):
    """Nested kind info on a node response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    label: str


class TagRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PropertyRef(BaseModel):
    """A node's property in {key, value, value_type} form."""

    key: str
    value: str
    value_type: str


class NodeSummary(BaseModel):
    """Lightweight node shape for lists, children, path."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind_id: int
    parent_id: Optional[int] = None
    can_contain: bool
    quantity: int
    created_at: datetime
    updated_at: datetime


class NodeOut(BaseModel):
    """Full node response with kind, tags and properties expanded."""

    id: int
    name: str
    kind: KindRef
    parent_id: Optional[int] = None
    can_contain: bool
    description: Optional[str] = None
    quantity: int
    width: Optional[float] = None
    height: Optional[float] = None
    depth: Optional[float] = None
    weight: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    tags: List[TagRef] = Field(default_factory=list)
    properties: List[PropertyRef] = Field(default_factory=list)


class NodeCreate(BaseModel):
    """POST /nodes body — kind by slug, parent_id optional."""

    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(description="Kind slug (e.g. 'drawer', 'tool')")
    parent_id: Optional[int] = None
    can_contain: bool = False
    description: Optional[str] = None
    quantity: int = Field(default=1, ge=0)
    width: Optional[float] = None
    height: Optional[float] = None
    depth: Optional[float] = None
    weight: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None


class NodeUpdate(BaseModel):
    """PATCH /nodes/{id} body — all fields optional; parent_id=null moves to root."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    kind: Optional[str] = None
    parent_id: Optional[int] = None
    can_contain: Optional[bool] = None
    description: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    width: Optional[float] = None
    height: Optional[float] = None
    depth: Optional[float] = None
    weight: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None


class TreeNode(BaseModel):
    """Recursive tree node response for GET /nodes/{id}/tree."""

    id: int
    name: str
    kind: KindRef
    parent_id: Optional[int] = None
    can_contain: bool
    quantity: int
    children: List["TreeNode"] = Field(default_factory=list)


TreeNode.model_rebuild()
