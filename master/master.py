import os
import asyncio
import aiohttp
import tempfile
import subprocess
from fastapi import FastAPI, UploadFile, File, Form
from typing import List, Dict, Any
from starlette.responses import FileResponse, JSONResponse

app = FastAPI()

WORKERS_RAW = os.environ.get("WORKERS", "http://worker1:8001,http://worker2:8001,http://worker3:8001")
WORKERS = [w.strip().rstrip("/") for w in WORKERS_RAW.split(",") if w.strip()]
WORKER_STATUS_PATH = os.environ.get("WORKER_STATUS_PATH", "/status")
WORKER_PROCESS_PATH = os.environ.get("WORKER_PROCESS_PATH", "/process_split")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
WORKER_REQUEST_TIMEOUT = int(os.environ.get("WORKER_REQUEST_TIMEOUT", "20"))

DATA_DIR = "/data"
os.makedirs(DATA_DIR, exist_ok=True)

async def fetch_status(session: aiohttp.ClientSession, worker_base: str) -> Dict[str, Any]:
    url = f"{worker_base}{WORKER_STATUS_PATH}"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                j = await resp.json()
                # expect {'capacity':int, 'available_slots':int}
                return {"worker": worker_base, "ok": True, "status": j}
            else:
                return {"worker": worker_base, "ok": False, "status": None}
    except Exception:
        return {"worker": worker_base, "ok": False, "status": None}

async def get_workers_statuses() -> List[Dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_status(session, w) for w in WORKERS]
        return await asyncio.gather(*tasks)

def split_text_equally_lines(content: str, parts: int) -> List[bytes]:
    lines = content.splitlines(keepends=True)
    n = len(lines)
    if n == 0:
        return [b"" for _ in range(parts)]
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

async def send_split_to_worker(session: aiohttp.ClientSession, worker_base: str, split_bytes: bytes, map_script: bytes | None, part_index: int, attempt: int = 1):
    url = f"{worker_base}{WORKER_PROCESS_PATH}"
    data = aiohttp.FormData()
    data.add_field("split", split_bytes, filename=f"split_{part_index}.bin", content_type="application/octet-stream")
    if map_script:
        data.add_field("map_script", map_script, filename="map.py", content_type="text/x-python")
    try:
        timeout = aiohttp.ClientTimeout(total=WORKER_REQUEST_TIMEOUT)
        async with session.post(url, data=data, timeout=timeout) as resp:
            if resp.status == 200:
                return {"ok": True, "worker": worker_base, "part_index": part_index, "bytes": await resp.read()}
            elif resp.status in (503, 429):
                # worker busy -> let caller handle retry
                return {"ok": False, "worker": worker_base, "part_index": part_index, "error": f"worker busy status={resp.status}"}
            else:
                txt = await resp.text()
                return {"ok": False, "worker": worker_base, "part_index": part_index, "error": f"status {resp.status} - {txt}"}
    except Exception as e:
        return {"ok": False, "worker": worker_base, "part_index": part_index, "error": str(e)}

@app.post("/submit_job")
async def submit_job(
    file: UploadFile = File(...),
    map_script: UploadFile | None = File(None),
    reduce_script: UploadFile | None = File(None),
    n_splits: int = Form(None)
):
    content = await file.read()
    map_bytes = await map_script.read() if map_script else None
    reduce_bytes = await reduce_script.read() if reduce_script else None

    # Ask workers for status
    statuses = await get_workers_statuses()
    worker_slots = {}
    for s in statuses:
        if s["ok"] and s["status"]:
            avail = max(0, int(s["status"].get("available_slots", 0)))
            worker_slots[s["worker"]] = avail
        else:
            worker_slots[s["worker"]] = 0

    total_slots = sum(worker_slots.values())
    if total_slots == 0:
        worker_slots = {w: 1 for w in WORKERS}

    parts = n_splits if n_splits and n_splits > 0 else sum(worker_slots.values())
    parts = max(1, parts)

    # decide text vs binary
    try:
        decoded = content.decode("utf-8")
        is_text = True
    except Exception:
        is_text = False

    if is_text:
        splits = split_text_equally_lines(decoded, parts)
    else:
        splits = split_bytes_equally(content, parts)

    queue = [{"part_index": i, "data": splits[i]} for i in range(len(splits))]
    mapped_results = [None] * len(queue)
    retries = {i: 0 for i in range(len(queue))}

    async with aiohttp.ClientSession() as session:
        pending = set(range(len(queue)))
        dynamic_slots = worker_slots.copy()

        while pending:
            statuses = await get_workers_statuses()
            for s in statuses:
                if s["ok"] and s["status"]:
                    dynamic_slots[s["worker"]] = max(0, int(s["status"].get("available_slots", 0)))
                else:
                    dynamic_slots[s["worker"]] = 0

            available_workers = [w for w, slots in dynamic_slots.items() if slots > 0]
            if not available_workers:
                await asyncio.sleep(0.5)
                continue

            for part_idx in list(pending):
                chosen = None
                for w in available_workers:
                    if dynamic_slots.get(w, 0) > 0:
                        chosen = w
                        break
                if not chosen:
                    break

                resp = await send_split_to_worker(
                    session, chosen, queue[part_idx]["data"], map_bytes, part_idx, attempt=retries[part_idx]+1
                )
                if resp.get("ok"):
                    mapped_results[part_idx] = resp
                    pending.remove(part_idx)
                    dynamic_slots[chosen] = dynamic_slots.get(chosen, 1) - 1
                else:
                    retries[part_idx] += 1
                    if retries[part_idx] >= MAX_RETRIES:
                        raise RuntimeError(f"Part {part_idx} failed after {MAX_RETRIES} retries: {resp.get('error')}")
                    await asyncio.sleep(0.2 * retries[part_idx])
            await asyncio.sleep(0.1)

    # guardar resultados y armar inter_files con worker
    inter_files = []
    for resp in mapped_results:
        i = resp["part_index"]
        worker = resp["worker"]
        b = resp["bytes"]

        path = os.path.join(DATA_DIR, f"mapped_part_{i}.bin")
        with open(path, "wb") as f:
            f.write(b)

        inter_files.append({"path": path, "worker": worker})

    concatenated_path = os.path.join(DATA_DIR, "mapped_concatenated.bin")
    with open(concatenated_path, "wb") as out:
        for f in inter_files:
            with open(f["path"], "rb") as ip:
                out.write(ip.read())

    final_output_path = os.path.join(DATA_DIR, "final_output.bin")

    if reduce_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
            tmp.write(reduce_bytes)
            tmp.flush()
            tmp_path = tmp.name

        with open(concatenated_path, "rb") as stdin_f, open(final_output_path, "wb") as stdout_f:
            proc = subprocess.run(
                ["python", tmp_path],
                stdin=stdin_f,
                stdout=stdout_f,
                stderr=subprocess.PIPE
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Reduce script failed: {proc.stderr.decode('utf-8', errors='ignore')}")
    else:
        os.replace(concatenated_path, final_output_path)

    return {
        "message": "job completed",
        "output_path": final_output_path,
        "mapped_parts": inter_files
    }

@app.get("/download_output")
def download_output():
    path = os.path.join(DATA_DIR, "final_output.bin")
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "no output yet"})
    return FileResponse(path, media_type="application/octet-stream", filename="final_output.bin")

@app.get("/")
def root():
    return {"status": "master up", "workers": WORKERS}
