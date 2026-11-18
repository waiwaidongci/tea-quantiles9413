from sqlalchemy import Column,Integer,String,Text
from src.config.database import Base
class Audit(Base):
    __tablename__='audits'
    id=Column(Integer,primary_key=True)
    actor=Column(String(120),nullable=False)
    action=Column(String(40),nullable=False)
    detail=Column(Text,nullable=False)
    created_at=Column(String(40),nullable=False)
