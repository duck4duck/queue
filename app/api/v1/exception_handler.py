from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.exception import (
    UserNotFound,
    QueueException,
    UserAlreadyInQueue,
    UserNotInQueue,
    PositionEmpty,
    PositionTaken,
    InvalidPosition,
)


async def user_not_found_handler(request: Request, exception: UserNotFound):
    return JSONResponse(status_code=404, content={"detail": exception.msg})


async def user_already_in_queue_handler(request: Request, exc: UserAlreadyInQueue):
    return JSONResponse(status_code=409, content={"detail": exc.msg})


async def user_not_in_queue_handler(request: Request, exc: UserNotInQueue):
    return JSONResponse(status_code=404, content={"detail": exc.msg})


async def position_taken_handler(request: Request, exc: PositionTaken):
    return JSONResponse(status_code=409, content={"detail": exc.msg})


async def position_empty_handler(request: Request, exc: PositionEmpty):
    return JSONResponse(status_code=404, content={"detail": exc.msg})


async def invalid_position_handler(request: Request, exc: InvalidPosition):
    return JSONResponse(status_code=400, content={"detail": exc.msg})


async def queue_exception_handler(request: Request, exc: QueueException):
    return JSONResponse(status_code=500, content={"detail": exc.msg})
