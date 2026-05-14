from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from .base import Base


class View(Base):
    __tablename__ = "views"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)

    containers = relationship("Container", back_populates="view")
