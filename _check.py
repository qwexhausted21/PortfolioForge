import sys, pathlib
for name in sys.argv[1:]:
    p = pathlib.Path(name)
    t = p.read_text(encoding="utf-8", errors="replace")
    bad = t.count("[ADDRESS]") + t.count("[PERSON_NAME]") + t.count("[REDACTED]")
    print(f"{name}: bad={bad} lines={t.count(chr(10))+1} bytes={len(t)}")