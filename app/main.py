from fastapi import FastAPI
import uvicorn
from app.api.router import main_router
from app.schemas.exception import UserNotFound

app = FastAPI()
app.include_router(main_router)


@app.get("/")
def hello():
    return {"message": "hello world!"}


if __name__ == "__main__":
    uvicorn.run(app, port=8000, reload=True)
