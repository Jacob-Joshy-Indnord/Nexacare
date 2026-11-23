"""Database plumbing for the e-prescribing service.

Provides the SQLAlchemy declarative Base shared by all models and two helpers.
make_engine(url) builds an engine; the default URL comes from DATABASE_URL
(PostgreSQL in deployment) and tests pass an in-memory SQLite URL. For SQLite
in-memory a static pool is used so every session shares one database.
make_session_factory(engine) returns a sessionmaker configured with
expire_on_commit disabled so returned objects stay readable after commit.
Keeping this in one module lets the app and tests swap databases without
touching business logic.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", "postgresql+psycopg://localhost/nexahealth")
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
