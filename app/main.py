from fastapi import FastAPI
import uvicorn
from app.api.router import main_router
from app.schemas.exception import UserNotFound
from app.schemas.exception import (
    UserNotFound,
    QueueException,
    UserAlreadyInQueue,
    UserNotInQueue,
    PositionEmpty,
    PositionTaken,
    InvalidPosition,
)

from app.api.v1.exception_handler import (
    user_not_found_handler,
    user_already_in_queue_handler,
    user_not_in_queue_handler,
    position_empty_handler,
    position_taken_handler,
    invalid_position_handler,
    queue_exception_handler,
)


app = FastAPI()
app.include_router(main_router)
app.add_exception_handler(UserNotFound,user_not_found_handler)
app.add_exception_handler(UserAlreadyInQueue,user_already_in_queue_handler)
app.add_exception_handler(UserNotInQueue,user_not_in_queue_handler)
app.add_exception_handler(PositionEmpty,position_empty_handler)
app.add_exception_handler(PositionTaken,position_taken_handler)
app.add_exception_handler(InvalidPosition,invalid_position_handler)
app.add_exception_handler(QueueException,queue_exception_handler)







@app.get("/")
def hello():
    return {"message": "hello world!"}


if __name__ == "__main__":
    uvicorn.run(app, port=8000, reload=True)
