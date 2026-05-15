from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .tag import node_tags

if TYPE_CHECKING:
    from .kind import Kind
    from .tag import Tag
    from .node_property import NodeProperty


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind_id: Mapped[int] = mapped_column(ForeignKey("kinds.id"), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("nodes.id"), nullable=True
    )
    can_contain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    width: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depth: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gps_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gps_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    kind: Mapped["Kind"] = relationship()
    parent: Mapped[Optional["Node"]] = relationship(
        remote_side="Node.id", back_populates="children"
    )
    children: Mapped[List["Node"]] = relationship(back_populates="parent")
    tags: Mapped[List["Tag"]] = relationship(
        secondary=node_tags, back_populates="nodes"
    )
    properties: Mapped[List["NodeProperty"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
