from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column
from sqlalchemy import String,BigInteger

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name:Mapped[str] = mapped_column(String)
    tg_id:Mapped[int] = mapped_column(BigInteger,unique=True)
    photo_url:Mapped[String] = mapped_column(String)



