from fastapi import FastAPI
import httpx
import os

app = FastAPI(title="GridMR Master")

# Lista de workers desde variables de entorno
WORKERS = os.getenv("WORKERS", "").split(",")

@app.get("/workers")
async def get_workers():
    """Devuelve lista de workers configurados"""
    return {"workers": WORKERS}

@app.get("/reconstruct")
async def reconstruct_file():
    """Recupera chunks de los workers y reconstruye el archivo final"""
    chunks = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for worker in WORKERS:
            try:
                resp = await client.get(f"{worker}/chunk")
                data = resp.json()
                chunks.append((data["id"], data["content"]))
            except Exception as e:
                # Simulamos que otro worker puede recuperar el chunk
                chunks.append((-1, f"[Error recuperando de {worker}: {e}]"))

    # Ordenar por posición
    chunks.sort(key=lambda x: x[0])

    # Concatenar
    reconstructed = "\n".join([c[1] for c in chunks if c[0] != -1])

    # Guardar temporalmente
    with open("reconstructed.txt", "w") as f:
        f.write(reconstructed)

    return {
        "status": "ok",
        "file": "reconstructed.txt",
        "content_preview": reconstructed[:200]  # solo primeras líneas
    }
