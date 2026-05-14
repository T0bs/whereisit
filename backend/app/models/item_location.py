from sqlalchemy import Column, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .base import Base


class ItemLocation(Base):
    __tablename__ = "item_locations"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    placed_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("Item", back_populates="locations")
    container = relationship("Container", back_populates="items")
