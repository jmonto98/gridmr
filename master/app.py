from fastapi import FastAPI
import httpx
import os
from fastapi.responses import FileResponse

app = FastAPI(title="GridMR Master")

# Lista de workers desde variables de entorno
WORKERS = os.getenv("WORKERS", "").split(",")

@app.get("/workers")
async def get_workers():
    """Devuelve lista de workers configurados"""
    return {"workers": WORKERS}

@app.get("/reconstruct")
async def reconstruct_file():
    chunks = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for worker in WORKERS:
            resp = await client.get(f"{worker}/chunk")
            data = resp.json()
            chunks.append((data["id"], data["content"]))

    chunks.sort(key=lambda x: x[0])
    reconstructed = "\n".join([c[1] for c in chunks if c[0] != -1])

    file_path = "/app/reconstructed.txt"
    with open(file_path, "w") as f:
        f.write(reconstructed)

    return FileResponse(file_path, filename="reconstructed.txt")
