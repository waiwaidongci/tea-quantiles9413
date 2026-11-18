import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix='tea-tests-'))
os.environ.setdefault('DATABASE_URL', f'sqlite+pysqlite:///{_TMP / "test.db"}')
os.environ.setdefault('REDIS_URL', 'fakeredis://')
os.environ.setdefault('JWT_SECRET', 'test-secret-for-protected-releases')
os.environ.setdefault('ARTIFACT_DIR', str(_TMP / 'artifacts'))

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.config.database import Base
from src.models import user, study, observation, run, review, audit, protected  # noqa: F401

DATABASE_URL = os.environ['DATABASE_URL']

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False}, pool_pre_ping=True)


@event.listens_for(engine, 'connect')
def _sqlite_pragmas(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.close()


Session = sessionmaker(bind=engine, expire_on_commit=False)

import src.config.database as database


@pytest.fixture(autouse=True)
def clean_schema(monkeypatch):
    monkeypatch.setattr(database, 'engine', engine)
    monkeypatch.setattr(database, 'Session', Session)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    with Session() as session:
        yield session
