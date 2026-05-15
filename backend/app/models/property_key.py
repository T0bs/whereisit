from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PropertyKey(Base):
    __tablename__ = "property_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value_type: Mapped[str] = mapped_column(
        Enum("string", "int", "float", "bool", name="value_type_enum"),
        nullable=False,
        default="string",
        server_default="string",
    )
