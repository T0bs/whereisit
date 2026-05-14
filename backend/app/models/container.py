from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from .base import Base

from .view import View


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

    view_id = Column(Integer, ForeignKey("views.id"), nullable=True)
    view = relationship("View", back_populates="containers")
