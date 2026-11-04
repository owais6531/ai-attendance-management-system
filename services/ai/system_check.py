"""Can the machine running this app also run a local AI model? Only reads system facts; installs nothing."""
import ctypes
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

MIN_RAM_GB = 8
MIN_DISK_GB = 6  # about: Ollama itself plus a small 2 GB model
MIN_CPU_CORES = 4


def total_ram_gb() -> Optional[float]:
    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            total = status.ullTotalPhys
        else:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return round(total / 1024 ** 3, 1)
    except (AttributeError, OSError, ValueError):
        return None


def free_disk_gb() -> Optional[float]:
    try:
        return round(shutil.disk_usage(Path.home()).free / 1024 ** 3, 1)
    except (OSError, RuntimeError):
        return None


def _line(label: str, have: Optional[float], need: float, unit: str) -> Dict[str, Any]:
    ok = None if have is None else have >= need
    return {"label": label, "have": have, "need": need, "unit": unit, "ok": ok}


def check() -> Dict[str, Any]:
    lines = [_line("Memory (RAM)", total_ram_gb(), MIN_RAM_GB, "GB"),
             _line("Free disk space", free_disk_gb(), MIN_DISK_GB, "GB"),
             _line("CPU cores", os.cpu_count(), MIN_CPU_CORES, "")]
    if any(line["ok"] is False for line in lines):
        verdict = "low"
        message = "This computer is below the minimum for local AI. Use your own API key instead (option 2)."
    elif any(line["ok"] is None for line in lines):
        verdict = "unknown"
        message = "Some details could not be read. Compare your computer with the minimums below."
    else:
        verdict = "ok"
        message = "This computer can run local AI. It stays free and your data stays here."
    return {"os": platform.system(), "lines": lines, "verdict": verdict, "message": message}
