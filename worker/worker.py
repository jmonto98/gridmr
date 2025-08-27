import os
import tempfile
import subprocess
from fastapi import FastAPI, File, UploadFile, Request, Form
from starlette.responses import Response

app = FastAPI()
DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

@app.post("/process_split")
async def process_split(split: UploadFile = File(...), map_script: UploadFile | None = File(None)):
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
        # Execute map script: expects script to read stdin and write stdout
        proc = subprocess.run(["python", map_path], stdin=open(split_path, "rb"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            return Response(content=f"Map error: {proc.stderr.decode('utf-8')}", status_code=500)
        return Response(content=proc.stdout, media_type="application/octet-stream")
    else:
        # No map script: identity return
        return Response(content=split_bytes, media_type="application/octet-stream")

@app.get("/")
def root():
    return {"status": "worker up"}
