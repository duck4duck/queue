from app.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
