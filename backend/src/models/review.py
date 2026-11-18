from sqlalchemy import Column,Integer,String,Text,ForeignKey
from src.config.database import Base
class ReleaseNote(Base):
    __tablename__='reviews'
    id=Column(Integer,primary_key=True)
    run_id=Column(Integer,ForeignKey('runs.id'),unique=True,nullable=False)
    note=Column(Text,nullable=False)
    author=Column(String(120),nullable=False)
    created_at=Column(String(40),nullable=False)
Review=ReleaseNote
