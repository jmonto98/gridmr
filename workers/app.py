import os
import json
import pathlib
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="GridMR Worker")

WORKER_ID = os.getenv("WORKER_ID", "unknown")
CAPACITY = int(os.getenv("WORKER_CAPACITY", "1"))

DATA_DIR = pathlib.Path("/data")
RESULTS_DIR = DATA_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class JobRequest(BaseModel):
    job_id: str
    file_key: str
    chunk_ids: List[str]
    operation: List[str]
    category: List[str]
    target: Optional[str] = None


@app.get("/info")
def info():
    return {"id": WORKER_ID, "capacity": CAPACITY}


def process_chunk(text: str, operation: List[str], category: List[str], target: Optional[str]):
    import re
    from collections import Counter
    results = {op: {} for op in operation}
    lines = text.splitlines()
    words = re.findall(r"[a-zA-Z]+", text.lower())
    letters = re.findall(r"[a-zA-Z]", text.lower())
    vowels = re.findall(r"[aeiou]", text.lower())

    for op in operation:
        for cat in category:
            if op == "cont":
                if target:
                    if cat == "palabras":
                        results[op][cat] = {"target": target, "count": sum(1 for w in words if w == target.lower())}
                    elif cat == "vocales":
                        results[op][cat] = {"target": target, "count": sum(1 for v in vowels if v == target.lower())}
                    elif cat == "letras":
                        results[op][cat] = {"target": target, "count": sum(1 for l in letters if l == target.lower())}
                else:
                    if cat == "palabras":
                        results[op][cat] = {"total_words": len(words)}
                    elif cat == "vocales":
                        results[op][cat] = dict(Counter(vowels))
                    elif cat == "letras":
                        results[op][cat] = dict(Counter(letters))
            elif op == "prom":
                if cat == "palabras":
                    results[op][cat] = {
                        "lines": len(lines),
                        "total_words": len(words),
                        "total_word_length": sum(len(w) for w in words)
                    }
                elif cat == "vocales":
                    results[op][cat] = {"lines": len(lines), "total_vowels": len(vowels)}
                elif cat == "letras":
                    results[op][cat] = {"lines": len(lines), "total_letters": len(letters)}
    return results


@app.post("/job/run")
def run_job(req: JobRequest):
    processed = []
    for chunk_id in req.chunk_ids:
        chunk_file = DATA_DIR / req.file_key / f"chunk_{chunk_id}.txt"
        if not chunk_file.exists() or chunk_file.is_dir():
            processed.append({"chunk_id": chunk_id, "error": "chunk_not_found"})
            continue
        text = chunk_file.read_text(encoding="utf-8", errors="ignore")
        results = process_chunk(text, req.operation, req.category, req.target)

        out_name = RESULTS_DIR / f"{WORKER_ID}_{chunk_id}.json"
        out_name.write_text(
            json.dumps({"chunk_id": chunk_id, "results": results}, indent=2, ensure_ascii=False)
        )
        processed.append({"chunk_id": chunk_id, "results": results})

    return {"worker_id": WORKER_ID, "processed": processed}
