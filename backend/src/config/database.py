import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
class Base(DeclarativeBase):
    pass
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)
def ensure_schema():
    """create_all covers new tables; existing installs only need this one
    additive column, which create_all will not add by itself."""
    inspector=inspect(engine)
    if 'audits' in inspector.get_table_names():
        columns={column['name'] for column in inspector.get_columns('audits')}
        if 'study_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE audits ADD COLUMN study_id INTEGER'))
def get_db():
    with Session() as db:
        yield db
