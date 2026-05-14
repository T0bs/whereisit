from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    ForeignKey,
    DateTime,
    func,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.mysql import JSON

Base = declarative_base()


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    locations = relationship("ItemLocation", back_populates="item", cascade="all, delete-orphan")


class Container(Base):
    __tablename__ = "containers"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    width = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    depth = Column(Float, nullable=True)
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    parent_id = Column(Integer, ForeignKey("containers.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parent = relationship("Container", remote_side=[id], backref="children")
    items = relationship("ItemLocation", back_populates="container", cascade="all, delete-orphan")


class ItemLocation(Base):
    __tablename__ = "item_locations"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    container_id = Column(Integer, ForeignKey("containers.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    placed_at = Column(DateTime(timezone=True), server_default=func.now())

    item = relationship("Item", back_populates="locations")
    container = relationship("Container", back_populates="items")
