from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.exception import AppException


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Generic exception handler for all application-level exceptions."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.msg})
