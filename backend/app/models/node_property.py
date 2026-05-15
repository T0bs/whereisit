from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .node import Node
    from .property_key import PropertyKey


class NodeProperty(Base):
    __tablename__ = "node_properties"
    __table_args__ = (
        UniqueConstraint("node_id", "key_id", name="uq_node_property"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    key_id: Mapped[int] = mapped_column(
        ForeignKey("property_keys.id"), nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)

    node: Mapped["Node"] = relationship(back_populates="properties")
    key: Mapped["PropertyKey"] = relationship()
