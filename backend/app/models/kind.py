from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Kind(Base):
    __tablename__ = "kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
