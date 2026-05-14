from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import relationship
from .base import Base


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # tags are stored in a separate `tags` table and linked via item_tags association
    tag_objs = relationship("Tag", secondary="item_tags", back_populates="items")

    @property
    def tags(self):
        return [t.name for t in self.tag_objs]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    locations = relationship("ItemLocation", back_populates="item", cascade="all, delete-orphan")
