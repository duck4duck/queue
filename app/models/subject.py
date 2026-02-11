from app.models.user import Base
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column
from sqlalchemy import String,BigInteger



class Subject(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    name:Mapped[str] = mapped_column(String)
