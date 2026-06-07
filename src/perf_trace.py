import time
import threading

_traces: list[str] = []
_lock = threading.Lock()
_enabled = True


def trace(name: str) -> float:
    global _enabled
    if not _enabled:
        return 0.0
    ts = time.perf_counter()
    with _lock:
        _traces.append(f"  {name}")
    return ts


def end(start: float, name: str):
    global _enabled
    if not _enabled or start == 0.0:
        return
    elapsed = (time.perf_counter() - start) * 1000
    with _lock:
        _traces.append(f"{name}: {elapsed:6.1f} ms")


def flush(path: str):
    global _traces
    with _lock:
        lines = _traces[:]
        _traces.clear()
    if lines:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n--- flush @ {time.strftime('%H:%M:%S')} ---\n")
            f.write("\n".join(lines) + "\n")


def disable():
    global _enabled
    _enabled = False
