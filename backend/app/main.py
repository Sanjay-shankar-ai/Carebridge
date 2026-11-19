"""
CareBridge — Main FastAPI Application Entrypoint
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import uuid
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.middleware import MaxRequestSizeMiddleware, SecurityHeadersMiddleware, CorrelationIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager for startup and shutdown procedures.
    (e.g., database connection pool initialization, background schedulers)
    """
    import os
    import logging
    logger = logging.getLogger("carebridge.main")

    # Initialize LangSmith AI Observability
    try:
        from app.core.observability import init_observability
        init_observability()
    except Exception as obs_err:
        logger.warning(f"Observability initialization notice: {obs_err}")

    # 1. Startup operations: ensure database schema and demo accounts exist
    try:
        from app.database.session import sync_engine, get_sync_db, Base
        from app.models import User
        from app.database.seed import seed_database
        Base.metadata.create_all(bind=sync_engine)
        with get_sync_db() as db:
            if db.query(User).first() is None:
                logger.info("Database empty. Seeding initial healthcare cohort and user accounts...")
                seed_database(db, extended=True)
                db.commit()
    except Exception as e:
        logger.warning(f"Database startup initialization notice: {e}")

    # 2. Startup operations: initialize background surveillance scheduler
    if os.getenv("TESTING") != "1":
        from app.scheduler.manager import BackgroundSchedulerManager
        try:
            BackgroundSchedulerManager.start()
        except Exception as e:
            logger.warning(f"Could not start background scheduler: {e}")

    yield

    # Shutdown operations: stop background scheduler cleanly
    if os.getenv("TESTING") != "1":
        try:
            from app.scheduler.manager import BackgroundSchedulerManager
            BackgroundSchedulerManager.stop()
        except Exception:
            pass


def create_application() -> FastAPI:
    """Factory function to build and configure the FastAPI application instance."""
    import os
    is_prod = settings.is_production()
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Autonomous AI-First Healthcare Care-Coordination Platform",
        docs_url=None if (is_prod and not settings.DEBUG) else "/docs",
        redoc_url=None if (is_prod and not settings.DEBUG) else "/redoc",
        openapi_url=None if (is_prod and not settings.DEBUG) else "/openapi.json",
        lifespan=lifespan if os.getenv("TESTING") != "1" else None,
    )

    # 1. Defense-in-depth Security Headers & Request Body Size Limit
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(MaxRequestSizeMiddleware, max_size_bytes=5 * 1024 * 1024)
    app.add_middleware(CorrelationIDMiddleware)

    # 2. Strict CORS Configuration
    if is_prod:
        # Production: strict whitelisted origins, no wildcard regex
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o for o in settings.CORS_ORIGINS if o != "*"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "Last-Event-ID", "X-Bypass-Rate-Limit"],
        )
    else:
        # Development: allow localhost development origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 3. Global Production Exception Masking
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        incident_id = uuid.uuid4().hex[:8]
        logging.getLogger("carebridge.server").error(f"[Incident {incident_id}] Unhandled exception: {exc}", exc_info=True)
        if settings.DEBUG:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "InternalServerError", "message": str(exc), "incident_id": incident_id}
            )
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "InternalServerError", "message": f"An unexpected internal error occurred. Incident reference: {incident_id}"}
        )

    # Mount API v1 router
    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "Welcome to CareBridge Autonomous AI Care Coordinator API",
            "version": "0.1.0",
            "documentation": "/docs",
            "health_check": f"{settings.API_V1_STR}/health",
        }

    @app.get("/health", tags=["Health"])
    async def liveness_probe():
        return {"status": "alive", "service": settings.APP_NAME}

    @app.get("/health/outbox", tags=["Health"])
    async def root_outbox_health():
        from app.core.outbox_health import get_outbox_stats
        from app.database.session import get_sync_db
        db = get_sync_db()
        try:
            stats = get_outbox_stats(db)
            return {"status": "success", "data": stats}
        finally:
            db.close()

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
