import os
import json
import pathlib
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from collections import Counter

app = FastAPI(title="GridMR Master")

MANIFEST_DIR = pathlib.Path("/app/gridfs/manifests")
WORKERS = [w for w in os.getenv("WORKERS", "").split(",") if w]

class JobRequest(BaseModel):
    file_key: str
    operation: str      # "cont" | "prom"
    category: str       # "palabras" | "vocales" | "letras"
    target: Optional[str] = None

# ------------------ HELPERS ------------------
async def call_worker(worker_url, payload):
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{worker_url}/run", json=payload)
        r.raise_for_status()
        return r.json()

def aggregate(responses, operation: str, category: str, target: Optional[str]):
    final = {"operation": operation, "category": category}
    if target:
        final["target"] = target

    if operation == "cont":
        if target:
            total = sum(
                chunk["results"].get(category, {}).get("count", 0)
                for r in responses for chunk in r.get("processed", [])
                if not chunk.get("error")
            )
            final["count"] = total
        else:
            if category == "palabras":
                total = sum(
                    chunk["results"]["palabras"].get("total_words", 0)
                    for r in responses for chunk in r.get("processed", [])
                    if not chunk.get("error")
                )
                final["total_words"] = total
            else:
                counts = Counter()
                for r in responses:
                    for chunk in r.get("processed", []):
                        if chunk.get("error"): continue
                        counts.update(chunk["results"][category])
                final["counts"] = dict(counts)

    elif operation == "prom":
        lines = 0
        if category == "palabras":
            total_words = total_word_len = 0
            for r in responses:
                for c in r.get("processed", []):
                    if c.get("error"): continue
                    d = c["results"]["palabras"]
                    lines += d["lines"]
                    total_words += d["total_words"]
                    total_word_len += d["total_word_length"]
            final["avg_words_per_line"] = round(total_words / lines, 2) if lines else 0
            final["avg_word_length"] = round(total_word_len / total_words, 2) if total_words else 0
        elif category == "vocales":
            total_vowels = 0
            for r in responses:
                for c in r.get("processed", []):
                    if c.get("error"): continue
                    d = c["results"]["vocales"]
                    lines += d["lines"]
                    total_vowels += d["total_vowels"]
            final["avg_vowels_per_line"] = round(total_vowels / lines, 2) if lines else 0
        elif category == "letras":
            total_letters = 0
            for r in responses:
                for c in r.get("processed", []):
                    if c.get("error"): continue
                    d = c["results"]["letras"]
                    lines += d["lines"]
                    total_letters += d["total_letters"]
            final["avg_letters_per_line"] = round(total_letters / lines, 2) if lines else 0
    return final

# ------------------ ENDPOINTS ------------------
@app.get("/workers")
async def get_workers():
    """Consulta a cada worker su info: id, capacidad, chunks."""
    out = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for w in WORKERS:
            try:
                r = await client.get(f"{w}/info")
                out.append(r.json())
            except Exception as e:
                out.append({"url": w, "error": str(e)})
    return {"workers": out}

@app.get("/files")
def list_files():
    """Lista los libros disponibles en los manifests."""
    files = []
    for m in MANIFEST_DIR.glob("*.manifest.json"):
        try:
            j = json.loads(m.read_text())
            files.append({
                "file_key": j.get("file_key"),
                "chunks": len(j.get("chunks", []))
            })
        except Exception:
            continue
    return {"files": files}

@app.post("/job")
async def run_job(req: JobRequest):
    """Envía la tarea a los workers y devuelve el resultado agregado."""
    manifest_path = MANIFEST_DIR / f"{req.file_key}.manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")

    manifest = json.loads(manifest_path.read_text())
    assignments = {}
    for ch in manifest["chunks"]:
        w = ch["primary_worker"]
        assignments.setdefault(w, []).append(ch["chunk_id"])

    tasks = []
    for w in set(ch["primary_worker"] for ch in manifest["chunks"]):
        payload = {
            "file_key": req.file_key,
            "operation": req.operation,
            "category": req.category,
            "target": req.target
        }
        tasks.append(call_worker(w, payload))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    responses = [r for r in results if not isinstance(r, Exception)]

    return aggregate(responses, req.operation, req.category, req.target)
