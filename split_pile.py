# split_file.py
import os
from dotenv import load_dotenv

def split_file(input_file, num_workers=4):
    # Cargar variables de .env
    load_dotenv()

    # Leer capacidades de cada worker
    capacities = []
    for i in range(1, num_workers + 1):
        cap = int(os.getenv(f"WORKER{i}_CAPACITY", 1))
        capacities.append(cap)

    total_capacity = sum(capacities)

    # Leer archivo completo
    with open(input_file, "r") as f:
        data = f.read()

    size = len(data)
    start = 0

    # Crear cada chunk proporcional a la capacidad
    for i in range(num_workers):
        portion = int(size * (capacities[i] / total_capacity))
        end = start + portion if i < num_workers - 1 else size
        chunk_data = data[start:end]

        out_path = f"worker/data/chunk{i+1}.txt"
        with open(out_path, "w") as out:
            out.write(chunk_data)

        print(f"Worker {i+1} ({capacities[i]}): {out_path} con {len(chunk_data)} bytes")

        start = end

if __name__ == "__main__":
    split_file("sample_file.txt", num_workers=4)
