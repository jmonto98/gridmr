import sys
data = sys.stdin.buffer.read()
try:
    text = data.decode("utf-8")
    out = text.upper()
    sys.stdout.buffer.write(out.encode("utf-8"))
except Exception:
    sys.stdout.buffer.write(data)
