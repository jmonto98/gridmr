import os
import tempfile
import subprocess
import asyncio
from fastapi import FastAPI, File, UploadFile, HTTPException
from starlette.responses import Response, JSONResponse

app = FastAPI()
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

# CAPACITY from env (default 1)
CAPACITY = int(os.environ.get("CAPACITY", "1"))
# Async semaphore to limit concurrent processing to CAPACITY
semaphore = asyncio.Semaphore(CAPACITY)

@app.get("/status")
async def status():
    # available_slots = current semaphore value
    # asyncio.Semaphore doesn't expose value directly, but has _value (private).
    # We will compute approx available slots as CAPACITY - (CAPACITY - semaphore._value) => semaphore._value
    # It's OK for prototype; for production expose properly via tracking variable.
    try:
        available = semaphore._value  # acceptable for this controlled prototype
    except Exception:
        available = 0
    return {"capacity": CAPACITY, "available_slots": available}

@app.post("/process_split")
async def process_split(split: UploadFile = File(...), map_script: UploadFile | None = File(None)):
    # Try to acquire a slot immediately; if no slot available, return 503
    try:
        # small immediate timeout to avoid blocking forever
        await asyncio.wait_for(semaphore.acquire(), timeout=0.1)
    except asyncio.TimeoutError:
        # busy
        return JSONResponse(status_code=503, content={"error": "worker busy", "capacity": CAPACITY})

    try:
        # Save split locally
        split_bytes = await split.read()
        with tempfile.NamedTemporaryFile(delete=False) as tf_split:
            tf_split.write(split_bytes)
            tf_split.flush()
            split_path = tf_split.name

        if map_script:
            map_bytes = await map_script.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tf_map:
                tf_map.write(map_bytes)
                tf_map.flush()
                map_path = tf_map.name

            proc = await asyncio.to_thread(
                subprocess.run,
                ["python", map_path],
                stdin=open(split_path, "rb"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            if proc.returncode != 0:
                return JSONResponse(
                    status_code=500,
                    content={"error": "map error", "stderr": proc.stderr.decode("utf-8", errors="ignore")}
                )

            return Response(content=proc.stdout, media_type="application/octet-stream")

        else:
            # identity
            return Response(content=split_bytes, media_type="application/octet-stream")
    finally:
        semaphore.release()

@app.get("/")
def root():
    return {"status": "worker up", "capacity": CAPACITY}
