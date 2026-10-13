"""FastAPI application factory.

    uvicorn faultline.api.main:app_factory --factory   (reads FAULTLINE_* environment variables)
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import API_VERSION, Settings, repo_root
from ..core.errors import ErrorCode, FaultlineError
from ..storage.db import connect
from ..storage.migrate import migrate
from .routers import analysis, findings, jobs, projects, system, worlds


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = connect(settings.db_path)
        migrate(conn)
        conn.close()
        yield

    app = FastAPI(title="Faultline", version=API_VERSION, lifespan=lifespan,
                  description="Witnesses, not warnings.")
    app.state.settings = settings

    @app.middleware("http")
    async def _correlate(request: Request, call_next):
        """Every request gets a correlation id (the caller's X-Request-ID, if it is a sane value) that appears on its log lines and in the response."""
        import re
        import time

        from ..core.ids import new_id
        from ..core.logging import correlated
        rid = request.headers.get("x-request-id", "")
        rid = rid if re.fullmatch(r"[A-Za-z0-9_.-]{6,64}", rid) else new_id("req")
        t0 = time.monotonic()
        with correlated(rid):
            response = await call_next(request)
            logging.getLogger("faultline.api").info("%s %s -> %d in %d ms", request.method, request.url.path, response.status_code,
                                                    int((time.monotonic() - t0) * 1000), extra={"fl": {"phase": "request", "status": response.status_code}})
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(FaultlineError)
    async def _faultline_error(_: Request, exc: FaultlineError) -> JSONResponse:
        return JSONResponse(exc.to_dict(), status_code=exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": ErrorCode.VALIDATION_ERROR.value,
                                       "message": "request validation failed", "details": {"errors": errors}}},
                            status_code=422)

    app.include_router(system.router)
    app.include_router(jobs.router)
    app.include_router(findings.router)
    app.include_router(projects.router)
    app.include_router(worlds.router)
    app.include_router(analysis.router)

    dist = Path(repo_root() / "frontend" / "dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app


def app_factory() -> FastAPI:
    return create_app()
