import os
import json
import pathlib
import re
import unicodedata
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="GridMR Worker")

WORKER_ID = os.getenv("WORKER_ID", "w?")
CAPACITY = int(os.getenv("WORKER_CAPACITY", "1"))
DATA_DIR = pathlib.Path("/data")

# --------- MODELS ----------
class RunRequest(BaseModel):
    file_key: str
    operation: str      # "cont" | "prom"
    category: str       # "palabras" | "vocales" | "letras"
    target: Optional[str] = None

# --------- HELPERS ----------
def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()

def words(s: str):
    return re.findall(r"[a-z]+", normalize_text(s))

def letters(s: str):
    return re.findall(r"[a-z]", normalize_text(s))

def vowels(s: str):
    return [ch for ch in normalize_text(s) if ch in "aeiou"]

def process_chunk(text: str, operation: str, category: str, target: Optional[str]):
    lines = text.splitlines()
    w = words(text)
    l = letters(text)
    v = vowels(text)
    res = {}

    if operation == "cont":
        if category == "palabras":
            if target:
                t = normalize_text(target)
                res["palabras"] = {"target": target,
                                   "count": sum(1 for x in w if x == t)}
            else:
                res["palabras"] = {"total_words": len(w)}
        elif category == "vocales":
            from collections import Counter
            if target:
                t = normalize_text(target)
                res["vocales"] = {"target": t,
                                  "count": sum(1 for x in v if x == t)}
            else:
                res["vocales"] = dict(Counter(v))
        elif category == "letras":
            from collections import Counter
            if target:
                t = normalize_text(target)
                res["letras"] = {"target": t,
                                 "count": sum(1 for x in l if x == t)}
            else:
                res["letras"] = dict(Counter(l))
    elif operation == "prom":
        if category == "palabras":
            total_words = len(w)
            total_word_length = sum(len(x) for x in w)
            res["palabras"] = {
                "lines": len(lines),
                "total_words": total_words,
                "total_word_length": total_word_length
            }
        elif category == "vocales":
            res["vocales"] = {
                "lines": len(lines),
                "total_vowels": len(v)
            }
        elif category == "letras":
            res["letras"] = {
                "lines": len(lines),
                "total_letters": len(l)
            }
    return res

# --------- ENDPOINTS ----------
@app.get("/info")
def info():
    """Id, capacidad y lista de chunks locales."""
    chunks = []
    for book_dir in DATA_DIR.iterdir():
        if book_dir.is_dir():
            for f in book_dir.glob("chunk_*.txt"):
                chunks.append({
                    "file_key": book_dir.name,
                    "chunk_id": f.stem.replace("chunk_", "")
                })
    return {"id": WORKER_ID, "capacity": CAPACITY, "chunks": chunks}

@app.post("/run")
def run(req: RunRequest):
    """Procesa TODOS los chunks que existan en /data/<file_key>/."""
    book_path = DATA_DIR / req.file_key
    if not book_path.exists():
        return {"worker_id": WORKER_ID, "error": "file_key_not_found"}

    processed = []
    for chunk_file in sorted(book_path.glob("chunk_*.txt")):
        text = chunk_file.read_text(encoding="utf-8", errors="ignore")
        chunk_id = chunk_file.stem.replace("chunk_", "")
        processed.append({
            "chunk_id": chunk_id,
            "results": process_chunk(text, req.operation, req.category, req.target)
        })
    return {"worker_id": WORKER_ID, "processed": processed}
