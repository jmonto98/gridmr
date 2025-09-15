#!/usr/bin/env python3
import os
import json
import pathlib
from dotenv import load_dotenv

# -------------------------------------------------------------------
# Configuración
# -------------------------------------------------------------------
load_dotenv()  # lee las variables de .env si quieres manejar capacidades ahí

# 1️⃣ Ajusta aquí la carpeta donde están tus libros originales (.txt)
BOOKS_DIR = pathlib.Path("books")

# 2️⃣ Carpeta de salida donde está tu estructura de proyecto
MASTER_MANIFESTS = pathlib.Path("master/gridfs/manifests")
WORKERS_BASE = pathlib.Path("chunks")   # donde tienes subcarpetas w1, w2, ...

# 3️⃣ Capacidades de los workers
#    Usa .env o escribe aquí los valores
WORKER_IDS = ["worker1", "worker2", "worker3", "worker4"]
CAPACITIES = [
    int(os.getenv("WORKER1_CAPACITY", 3)),
    int(os.getenv("WORKER2_CAPACITY", 3)),
    int(os.getenv("WORKER3_CAPACITY", 3)),
    int(os.getenv("WORKER4_CAPACITY", 2)),
]
assert len(WORKER_IDS) == len(CAPACITIES)

# -------------------------------------------------------------------
def split_by_lines(text: str, N: int):
    """Divide el texto en N partes (por líneas) lo más balanceadas posible."""
    lines = text.splitlines(keepends=True)
    total = len(lines)
    base, rem = divmod(total, N)
    chunks, idx = [], 0
    for i in range(N):
        take = base + (1 if i < rem else 0)
        chunk = "".join(lines[idx: idx + take])
        chunks.append(chunk)
        idx += take
    return chunks


def prepare_book(book_path: pathlib.Path):
    """
    Divide un libro en fragmentos según la capacidad total de los workers
    y copia cada fragmento en la carpeta de build de su worker.
    """
    file_key = book_path.stem.replace(" ", "_")
    text = book_path.read_text(encoding="utf-8", errors="ignore")

    total_capacity = sum(CAPACITIES)
    chunks = split_by_lines(text, total_capacity)

    manifest = {"file_key": file_key, "chunks": []}
    current = 1
    for wid, cap in zip(WORKER_IDS, CAPACITIES):
        for _ in range(cap):
            if current > total_capacity:
                break
            chunk_id = f"F{str(current).zfill(8)}"
            # carpeta destino: workers/wX/data/<file_key>/
            dest_dir = WORKERS_BASE / wid / file_key
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / f"chunk_{chunk_id}.txt").write_text(
                chunks[current-1],
                encoding="utf-8"
            )
            manifest["chunks"].append({
                "chunk_id": chunk_id,
                "file_key": file_key,
                "primary_worker": f"http://{wid}:800{wid[-1]}"  # p.ej. http://w1:8001
            })
            current += 1

    MASTER_MANIFESTS.mkdir(parents=True, exist_ok=True)
    (MASTER_MANIFESTS / f"{file_key}.manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )
    print(f"✔ {file_key}: {total_capacity} partes distribuidas.")


def main():
    txt_files = sorted(BOOKS_DIR.glob("*.txt"))
    if not txt_files:
        print("No se encontraron archivos .txt en", BOOKS_DIR)
        return
    for book in txt_files:
        prepare_book(book)
    print("✅ Todos los libros han sido procesados.")


if __name__ == "__main__":
    main()
