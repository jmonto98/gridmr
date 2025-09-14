import os
import uuid
import json
import pathlib
import asyncio
from typing import List, Optional

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="GridMR Master")

# --- Directorios ---
GRIDFS_DIR = pathlib.Path("/app/gridfs")
MANIFEST_DIR = GRIDFS_DIR / "manifests"
RESULTS_DIR = GRIDFS_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

WORKERS = [w for w in os.getenv("WORKERS", "").split(",") if w]
JOBS = {}

# -------------------------------------------------------------
# Schemas
# -------------------------------------------------------------
class JobPayload(BaseModel):
    file_key: str
    operation: List[str]
    category: List[str]
    target: Optional[str] = None


# -------------------------------------------------------------
# Utilidades
# -------------------------------------------------------------
def clear_results_dir():
    for f in RESULTS_DIR.glob("*"):
        f.unlink(missing_ok=True)


async def call_worker_map(worker_url, payload):
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{worker_url}/job/run", json=payload)
        r.raise_for_status()
        return r.json()


def aggregate_results(all_worker_responses, operation, category, target):
    """
    Combina los resultados parciales de todos los workers.
    """
    final = {"operations": {}}
    # Inicializa estructura de salida
    for op in operation:
        final["operations"].setdefault(op, {})
        for cat in category:
            if op == "cont":
                if target:
                    final["operations"][op][cat] = {"target": target, "count": 0}
                else:
                    if cat == "palabras":
                        final["operations"][op][cat] = {"total_words": 0}
                    elif cat in ("vocales", "letras"):
                        final["operations"][op][cat] = {}
            elif op == "prom":
                final["operations"][op][cat] = {"total_lines": 0}
                if cat == "palabras":
                    final["operations"][op][cat].update(
                        {"total_words": 0, "total_word_length": 0}
                    )
                elif cat == "vocales":
                    final["operations"][op][cat].update({"total_vowels": 0})
                elif cat == "letras":
                    final["operations"][op][cat].update({"total_letters": 0})

    # Acumula parciales
    for wresp in all_worker_responses:
        for chunk in wresp.get("processed", []):
            if "error" in chunk:
                continue
            cres_all = chunk.get("results", {})
            for op in operation:
                for cat in category:
                    cres = cres_all.get(op, {}).get(cat)
                    if not cres:
                        continue
                    if op == "cont":
                        if target:
                            final["operations"][op][cat]["count"] += int(cres.get("count", 0))
                        else:
                            if cat == "palabras":
                                final["operations"][op][cat]["total_words"] += int(cres.get("total_words", 0))
                            elif cat in ("vocales", "letras"):
                                container = final["operations"][op][cat]
                                for k, v in cres.items():
                                    container[k] = container.get(k, 0) + int(v)
                    elif op == "prom":
                        info = final["operations"][op][cat]
                        info["total_lines"] += int(cres.get("lines", 0))
                        if cat == "palabras":
                            info["total_words"] += int(cres.get("total_words", 0))
                            info["total_word_length"] += int(cres.get("total_word_length", 0))
                        elif cat == "vocales":
                            info["total_vowels"] += int(cres.get("total_vowels", 0))
                        elif cat == "letras":
                            info["total_letters"] += int(cres.get("total_letters", 0))

    # Calcula promedios
    for op in operation:
        if op != "prom":
            continue
        for cat in category:
            info = final["operations"][op][cat]
            lines = info.get("total_lines", 0)
            if lines == 0:
                info["avg"] = None
            else:
                if cat == "palabras":
                    info["avg_words_per_line"] = info["total_words"] / lines
                    info["avg_word_length"] = (
                        info["total_word_length"] / info["total_words"]
                        if info["total_words"] > 0 else 0
                    )
                elif cat == "vocales":
                    info["avg_vowels_per_line"] = info["total_vowels"] / lines
                elif cat == "letras":
                    info["avg_letters_per_line"] = info["total_letters"] / lines
    return final


async def run_job(job_id, file_key, operation, category, target):
    clear_results_dir()

    manifest_path = MANIFEST_DIR / f"{file_key}.manifest.json"
    if not manifest_path.exists():
        JOBS[job_id] = {"status": "error", "error": "manifest_missing"}
        return
    manifest = json.loads(manifest_path.read_text())

    assignments = {}
    for ch in manifest["chunks"]:
        w = ch["primary_worker"]
        assignments.setdefault(w, []).append(ch["chunk_id"])

    tasks = []
    for w, chunk_ids in assignments.items():
        payload = {
            "job_id": job_id,
            "file_key": file_key,
            "chunk_ids": chunk_ids,
            "operation": operation,
            "category": category,
            "target": target
        }
        tasks.append(call_worker_map(w, payload))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    worker_resps = [r for r in results if not isinstance(r, Exception)]

    final_json = aggregate_results(worker_resps, operation, category, target)
    out_path = RESULTS_DIR / f"{job_id}.json"
    out_path.write_text(json.dumps(final_json, indent=2, ensure_ascii=False))
    JOBS[job_id] = {"status": "finished", "result_file": str(out_path), "result": final_json}


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/workers")
async def get_workers():
    info = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for worker in WORKERS:
            try:
                r = await client.get(f"{worker}/info")
                d = r.json()
                info.append({"url": worker, "id": d.get("id"), "capacity": d.get("capacity")})
            except Exception as e:
                info.append({"url": worker, "error": str(e), "capacity": 0})
    ranking = sorted([w for w in info if "capacity" in w], key=lambda x: x["capacity"], reverse=True)
    return {"workers": info, "ranking": ranking}


@app.get("/files")
async def list_files():
    files = []
    for p in MANIFEST_DIR.glob("*.manifest.json"):
        try:
            m = json.loads(p.read_text())
            files.append({"file_key": m.get("file_key"), "chunks": len(m.get("chunks", []))})
        except Exception:
            continue
    return {"files": files}


@app.post("/job")
async def create_job(body: JobPayload, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "running", "file_key": body.file_key}
    background_tasks.add_task(
        asyncio.create_task,
        run_job(job_id, body.file_key, body.operation, body.category, body.target),
    )
    return {"job_id": job_id, "status": "started"}


@app.get("/job/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/results/{job_id}")
async def download_result(job_id: str):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "finished":
        raise HTTPException(404, "result not ready")
    return FileResponse(job["result_file"], filename=f"{job_id}.json")
