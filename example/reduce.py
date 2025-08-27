import sys
data = sys.stdin.buffer.read()
try:
    text = data.decode("utf-8")
    lines = text.splitlines()
    sys.stdout.write("\n".join(lines))
    sys.stdout.write(f"\n\n-- Total lines: {len(lines)}\n")
except Exception:
    sys.stdout.buffer.write(data)
