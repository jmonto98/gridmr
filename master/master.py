import os
import tempfile
import asyncio
import aiohttp
from fastapi import FastAPI, UploadFile, File, Form
from typing import List
from starlette.responses import FileResponse

app = FastAPI()

# Workers list from env var or default (comma separated)
WORKERS = os.environ.get("WORKERS", "http://worker1:8001/process_split,http://worker2:8001/process_split,http://worker3:8001/process_split")
WORKER_URLS = [w.strip() for w in WORKERS.split(",") if w.strip()]

DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

def split_text_equally_lines(content: str, parts: int) -> List[bytes]:
    lines = content.splitlines(keepends=True)
    n = len(lines)
    if n == 0:
        return [b"" for _ in range(parts)]
    # assign nearly-equal number of lines per part
    base = n // parts
    extra = n % parts
    res = []
    idx = 0
    for i in range(parts):
        count = base + (1 if i < extra else 0)
        part_lines = lines[idx: idx + count]
        idx += count
        res.append("".join(part_lines).encode("utf-8"))
    return res

def split_bytes_equally(content: bytes, parts: int) -> List[bytes]:
    total = len(content)
    base = total // parts
    extra = total % parts
    res = []
    idx = 0
    for i in range(parts):
        size = base + (1 if i < extra else 0)
        res.append(content[idx: idx + size])
        idx += size
    return res

async def send_split(worker_url: str, split_bytes: bytes, map_script_bytes: bytes = None, split_index: int = 0):
    # send multipart/form-data: fields split (file) and optional map_script
    data = aiohttp.FormData()
    data.add_field("split", split_bytes, filename=f"split_{split_index}.bin", content_type="application/octet-stream")
    if map_script_bytes:
        data.add_field("map_script", map_script_bytes, filename="map.py", content_type="text/x-python")
    async with aiohttp.ClientSession() as session:
        async with session.post(worker_url, data=data) as resp:
            resp.raise_for_status()
            return await resp.read()

@app.post("/submit_job")
async def submit_job(
    file: UploadFile = File(...),
    map_script: UploadFile | None = File(None),
    reduce_script: UploadFile | None = File(None),
    n_workers: int = Form(None)
):
    # Read inputs
    content = await file.read()
    map_bytes = await map_script.read() if map_script else None
    reduce_bytes = await reduce_script.read() if reduce_script else None

    workers = WORKER_URLS.copy()
    if n_workers:
        # allow overriding number of splits/workers
        workers = workers[:n_workers]
    parts = max(1, len(workers))

    # Decide text vs binary split
    is_text = False
    try:
        decoded = content.decode("utf-8")
        is_text = True
    except Exception:
        is_text = False

    if is_text:
        splits = split_text_equally_lines(decoded, parts)
    else:
        splits = split_bytes_equally(content, parts)

    # send to workers concurrently
    tasks = []
    for i, split_data in enumerate(splits):
        worker_url = workers[i % len(workers)]
        tasks.append(send_split(worker_url, split_data, map_bytes, i))

    results = await asyncio.gather(*tasks)

    # store intermediate mapped results
    inter_files = []
    for i, r in enumerate(results):
        path = os.path.join(DATA_DIR, f"mapped_part_{i}.bin")
        with open(path, "wb") as f:
            f.write(r)
        inter_files.append(path)

    # Concatenate mapped parts
    concatenated_path = os.path.join(DATA_DIR, "mapped_concatenated.bin")
    with open(concatenated_path, "wb") as out:
        for p in inter_files:
            with open(p, "rb") as ip:
                out.write(ip.read())

    final_output_path = os.path.join(DATA_DIR, "final_output.bin")

    if reduce_bytes:
        # run reduce script locally: it should read stdin and write stdout
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
            tmp.write(reduce_bytes)
            tmp.flush()
            tmp_path = tmp.name

        with open(concatenated_path, "rb") as stdin_f, open(final_output_path, "wb") as stdout_f:
            proc = subprocess.run(["python", tmp_path], stdin=stdin_f, stdout=stdout_f, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                raise RuntimeError(f"Reduce script failed: {proc.stderr.decode('utf-8')}")
    else:
        # if no reducer, final is concatenation of mapped outputs
        os.replace(concatenated_path, final_output_path)

    return {"message": "job completed", "output_path": final_output_path, "mapped_parts": inter_files}

@app.get("/download_output")
def download_output():
    path = os.path.join(DATA_DIR, "final_output.bin")
    if not os.path.exists(path):
        return {"error": "no output yet"}
    return FileResponse(path, media_type="application/octet-stream", filename="final_output.bin")

@app.get("/")
def root():
    return {"status": "master up", "workers": WORKER_URLS}
