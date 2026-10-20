from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, BigInteger

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="student", server_default="student")
