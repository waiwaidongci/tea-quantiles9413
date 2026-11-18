from sqlalchemy import Column,Integer,String,JSON,Text,ForeignKey
from src.config.database import Base

class ProtectedPolicy(Base):
    """A batch's immutable protected-release settings and privacy ledger.

    Epsilon is stored in integer millionths so the budget check is an exact
    conditional UPDATE rather than a floating-point comparison.
    """
    __tablename__='protection_policies'
    id=Column(Integer,primary_key=True)
    study_id=Column(Integer,ForeignKey('studies.id'),unique=True,nullable=False)
    field=Column(String(40),nullable=False)
    bins=Column(JSON,nullable=False)
    total_epsilon_units=Column(Integer,nullable=False)
    spent_epsilon_units=Column(Integer,nullable=False,default=0)
    created_at=Column(String(40),nullable=False)

class ProtectedRelease(Base):
    __tablename__='protected_releases'
    id=Column(Integer,primary_key=True)
    study_id=Column(Integer,ForeignKey('studies.id'),nullable=False)
    policy_id=Column(Integer,ForeignKey('protection_policies.id'),nullable=False)
    name=Column(String(120),nullable=False)
    epsilon_units=Column(Integer,nullable=False)
    spent_after_units=Column(Integer,default=0,nullable=False)
    total_epsilon_units=Column(Integer,default=0,nullable=False)
    noise_seed=Column(String(40),nullable=False,default='')
    fingerprint=Column(String(64),unique=True,nullable=False)
    snapshot=Column(JSON,nullable=False)
    snapshot_checksum=Column(String(64),nullable=False)
    status=Column(String(20),default='pending',nullable=False)
    result=Column(JSON,nullable=True)
    result_checksum=Column(String(64),default='',nullable=False)
    error=Column(Text,default='',nullable=False)
    archive_checksum=Column(String(64),default='',nullable=False)
    created_at=Column(String(40),nullable=False)
    generated_at=Column(String(40),default='',nullable=False)
    available_at=Column(String(40),default='',nullable=False)
