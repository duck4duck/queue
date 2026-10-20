import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
import uvicorn

from app.core.config import settings
from app.core.logger import logger, setup_logger
from app.db.redis.redis_client import close_redis, get_redis_client
from app.db.postgres.database import engine, AsyncSessionLocal
from app.api.router import main_router
from app.schemas.exception import (
    UserNotFound,
    QueueException,
    UserAlreadyInQueue,
    UserNotInQueue,
    PositionEmpty,
    PositionTaken,
    InvalidPosition,
    Forbidden,
    QueueAlreadyExists,
    QueueNotFound,
    QueuePaused,
    SwapRequestNotFound,
    SwapRequestAlreadyExists,
    SwapRequestExpired,
    SwapRequestException,
    SubjectNotFound,
    SubjectAlreadyExists,
    InvalidRole,
)
from app.api.v1.exception_handler import (
    user_not_found_handler,
    user_already_in_queue_handler,
    user_not_in_queue_handler,
    position_empty_handler,
    position_taken_handler,
    invalid_position_handler,
    forbidden_handler,
    queue_already_exists_handler,
    queue_not_found_handler,
    queue_paused_handler,
    swap_request_not_found_handler,
    swap_request_already_exists_handler,
    swap_request_expired_handler,
    swap_request_exception_handler,
    subject_not_found_handler,
    subject_already_exists_handler,
    invalid_role_handler,
    queue_exception_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logger(settings.log_level)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}...")
    yield
    # Shutdown
    logger.info("Shutting down application...")
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
app.add_exception_handler(UserNotFound, user_not_found_handler)
app.add_exception_handler(UserAlreadyInQueue, user_already_in_queue_handler)
app.add_exception_handler(UserNotInQueue, user_not_in_queue_handler)
app.add_exception_handler(PositionEmpty, position_empty_handler)
app.add_exception_handler(PositionTaken, position_taken_handler)
app.add_exception_handler(InvalidPosition, invalid_position_handler)
app.add_exception_handler(Forbidden, forbidden_handler)
app.add_exception_handler(QueueAlreadyExists, queue_already_exists_handler)
app.add_exception_handler(QueueNotFound, queue_not_found_handler)
app.add_exception_handler(QueuePaused, queue_paused_handler)
app.add_exception_handler(SwapRequestNotFound, swap_request_not_found_handler)
app.add_exception_handler(SwapRequestAlreadyExists, swap_request_already_exists_handler)
app.add_exception_handler(SwapRequestExpired, swap_request_expired_handler)
app.add_exception_handler(SwapRequestException, swap_request_exception_handler)
app.add_exception_handler(SubjectNotFound, subject_not_found_handler)
app.add_exception_handler(SubjectAlreadyExists, subject_already_exists_handler)
app.add_exception_handler(InvalidRole, invalid_role_handler)
app.add_exception_handler(QueueException, queue_exception_handler)


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
import os
from fastapi.staticfiles import StaticFiles

_frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(_frontend_dir):
    app.mount("/test", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


@app.get("/health")
async def health_check():
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
    return {
        "status": "healthy" if is_healthy else "degraded",
        "postgres": db_status,
        "redis": redis_status,
        "version": settings.app_version,
    }


if __name__ == "__main__":
    uvicorn.run(app, port=8000, reload=True)
