from fastapi import FastAPI
import uvicorn


app = FastAPI()


@app.get("/")
def hello():
    return {"message": "hello world!"}


if __name__ == "__main__":
    uvicorn.run(app, port=8000, reload=True)
