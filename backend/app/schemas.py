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
    suggested_parent_id: Optional[int] = None
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
    suggested_parent_id: Optional[int] = None
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


class TagCreate(BaseModel):
    """POST /tags body and POST /nodes/{id}/tags body."""

    name: str = Field(min_length=1, max_length=100)


class KindCreate(BaseModel):
    """POST /kinds body. Label defaults to titlecased slug when creating new."""

    slug: str = Field(min_length=1, max_length=50)
    label: Optional[str] = Field(default=None, max_length=100)


class PropertyValueSet(BaseModel):
    """PUT /nodes/{id}/properties/{key} body.

    `value_type` is only consulted when the property key is first created —
    once set, a key's type is sticky across all nodes that use it.
    """

    value: object
    value_type: Optional[str] = None


class SearchResult(BaseModel):
    """One row in the /search response.

    `score` and `match_reason` are mode-dependent — keyword mode fills them
    from the FULLTEXT relevance score; semantic/hybrid modes (M11) will use
    the same fields with different meanings.

    `path` is the full ancestor chain root→self (inclusive), so a client can
    display 'Garage > Workbench > Drawer A > Claw hammer' without follow-up
    requests.
    """

    id: int
    name: str
    kind: KindRef
    parent_id: Optional[int] = None
    can_contain: bool
    quantity: int
    score: Optional[float] = None
    match_reason: Optional[str] = None
    path: List["NodeSummary"] = Field(default_factory=list)


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
