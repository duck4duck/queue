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


async def forbidden_handler(request: Request, exc: Forbidden):
    return JSONResponse(status_code=403, content={"detail": exc.msg})


async def queue_already_exists_handler(request: Request, exc: QueueAlreadyExists):
    return JSONResponse(status_code=409, content={"detail": exc.msg})


async def queue_not_found_handler(request: Request, exc: QueueNotFound):
    return JSONResponse(status_code=404, content={"detail": exc.msg})


async def queue_paused_handler(request: Request, exc: QueuePaused):
    return JSONResponse(status_code=403, content={"detail": exc.msg})


async def swap_request_not_found_handler(request: Request, exc: SwapRequestNotFound):
    return JSONResponse(status_code=404, content={"detail": exc.msg})


async def swap_request_already_exists_handler(request: Request, exc: SwapRequestAlreadyExists):
    return JSONResponse(status_code=409, content={"detail": exc.msg})


async def swap_request_expired_handler(request: Request, exc: SwapRequestExpired):
    return JSONResponse(status_code=400, content={"detail": exc.msg})


async def swap_request_exception_handler(request: Request, exc: SwapRequestException):
    return JSONResponse(status_code=400, content={"detail": exc.msg})


async def subject_not_found_handler(request: Request, exc: SubjectNotFound):
    return JSONResponse(status_code=404, content={"detail": exc.msg})


async def subject_already_exists_handler(request: Request, exc: SubjectAlreadyExists):
    return JSONResponse(status_code=409, content={"detail": exc.msg})


async def invalid_role_handler(request: Request, exc: InvalidRole):
    return JSONResponse(status_code=400, content={"detail": exc.msg})


async def queue_exception_handler(request: Request, exc: QueueException):
    return JSONResponse(status_code=500, content={"detail": exc.msg})
