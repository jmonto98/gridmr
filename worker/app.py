from fastapi import FastAPI
import os

app = FastAPI(title="GridMR Worker")

WORKER_ID = int(os.getenv("WORKER_ID", 0))
WORKER_CAPACITY = int(os.getenv("WORKER_CAPACITY", 1))
CHUNK_PATH = "/data/chunk.txt"

@app.get("/info")
def info():
    return {
        "id": WORKER_ID,
        "capacity": WORKER_CAPACITY
    }

@app.get("/chunk")
def get_chunk():
    try:
        with open(CHUNK_PATH, "r") as f:
            content = f.read()
        return {"id": WORKER_ID, "content": content}
    except Exception as e:
        return {"id": WORKER_ID, "error": str(e)}
