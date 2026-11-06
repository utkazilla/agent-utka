import csv
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuMemory:
    name: str
    total_mib: int
    free_mib: int


def read_vram():
    """Report physical NVIDIA VRAM from the driver, or no reading."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            text=True, encoding="utf-8", errors="replace", timeout=4,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    devices = []
    for row in csv.reader(output.splitlines(), skipinitialspace=True):
        if len(row) != 3:
            continue
        name, total, free = row
        try:
            total, free = int(total), int(free)
        except ValueError:
            continue
        if name and 0 <= free <= total and total > 0:
            devices.append(GpuMemory(name, total, free))
    return devices
