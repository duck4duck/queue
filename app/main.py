import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import settings
from app.core.logger import logger, setup_logger
from app.db.redis.redis_client import close_redis, get_redis_client
from app.db.postgres.database import engine, AsyncSessionLocal
from app.repositories.queue_repository import QueueRepository
from app.api.ws_manager import manager
from app.api.router import main_router
from app.schemas.exception import AppException
from app.api.v1.exception_handler import app_exception_handler


async def queue_expiration_loop():
    """Background task checking and removing expired queues every 15 seconds."""
    while True:
        try:
            await asyncio.sleep(15)
            r = get_redis_client()
            repo = QueueRepository(r)
            deleted_subjects = await repo.cleanup_expired_queues()
            for subject in deleted_subjects:
                logger.info(f"Auto-deleted expired queue: {subject}")
                await manager.broadcast_room_and_all(
                    subject, {"event": "queue_deleted", "subject": subject}
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in queue_expiration_loop: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logger(settings.log_level)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}...")
    cleanup_task = asyncio.create_task(queue_expiration_loop())
    yield
    # Shutdown
    logger.info("Shutting down application...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await close_redis()
    await engine.dispose()
    logger.info("Application successfully stopped.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# ──────────────────── CORS Middleware ────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────── Request Logging Middleware ────────────────────
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    try:
        response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} "
            f"({process_time_ms:.2f}ms) | IP: {client_ip}"
        )
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
        return response
    except Exception as exc:
        process_time_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path} "
            f"({process_time_ms:.2f}ms) | IP: {client_ip}: {exc}",
            exc_info=True,
        )
        raise exc


# ──────────────────── Routers ────────────────────
app.include_router(main_router)

# ──────────────────── Exception Handlers ────────────────────
app.add_exception_handler(AppException, app_exception_handler)


# ──────────────────── Health & Root Endpoints ────────────────────
@app.get("/")
def hello():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "online",
        "frontend": "/test",
        "docs": "/docs",
    }


# ──────────────────── Static Frontend for Testing ────────────────────
_frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(_frontend_dir):
    app.mount("/test", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


@app.get("/health")
async def health_check(response: Response):
    """Health check endpoint: verifies PostgreSQL and Redis availability."""
    db_status = "ok"
    redis_status = "ok"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    try:
        r = get_redis_client()
        await r.ping()
    except Exception as e:
        redis_status = f"error: {str(e)}"

    is_healthy = db_status == "ok" and redis_status == "ok"
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "healthy" if is_healthy else "degraded",
        "postgres": db_status,
        "redis": redis_status,
        "version": settings.app_version,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)
