# Ejemplo simple: contar líneas y escribir resultado
import sys

data = sys.stdin.buffer.read()
try:
    text = data.decode("utf-8")
    # ejemplo reduce: simplemente contar líneas y escribir la concatenación + estadística
    lines = text.splitlines()
    sys.stdout.write("\n".join(lines))
    sys.stdout.write(f"\n\n-- Total lines: {len(lines)}\n")
except Exception:
    # si binario, devolver tal cual
    sys.stdout.buffer.write(data)
