"""FastAPI application factory for the e-prescribing service.

create_app(session_factory=None) builds the FastAPI app and mounts the
prescription router. When no session factory is supplied it creates an
engine from DATABASE_URL, creates tables if missing, and uses that. Passing
a factory lets tests inject an in-memory database. The module-level
function app_from_env is the uvicorn entry point (uvicorn app.main:app_from_env
--factory). OpenAPI documentation is generated automatically by FastAPI.
"""
from fastapi import FastAPI

from app.db import Base, make_engine, make_session_factory
from app.routes import create_router


def create_app(session_factory=None) -> FastAPI:
    if session_factory is None:
        engine = make_engine()
        Base.metadata.create_all(engine)
        session_factory = make_session_factory(engine)
    app = FastAPI(title="NexaHealth E-Prescribing")
    app.include_router(create_router(session_factory))
    return app


def app_from_env() -> FastAPI:
    return create_app()
