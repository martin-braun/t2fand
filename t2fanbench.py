#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MILD = 30
STRONG = 60
COOLDOWN = 60
BASELINE = 30

CPUS = os.cpu_count() or 1
MILD_CPUS = max(1, CPUS // 4)

TEMP_PATH = Path.home() / ".cache" / "t2fanbench"


def log(message):
    now = time.localtime()
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    timestamp = (
        f"{months[now.tm_mon - 1]} {now.tm_mday:02d} "
        f"{now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"
    )
    print(f"{timestamp} [t2fanbench] {message}", flush=True)
    subprocess.run(["logger", "-t", "t2fanbench", message], check=False)


def run(name, level, seconds, *args):
    log(f"START component={name} level={level} duration={seconds}s")

    subprocess.run(
        [
            "stress-ng",
            *args,
            "--timeout",
            f"{seconds}s",
            "--temp-path",
            str(TEMP_PATH),
            "--metrics-brief",
        ]
    )

    log(f"END component={name} level={level}")


def cooldown():
    log(f"START cooldown duration={COOLDOWN}s")
    time.sleep(COOLDOWN)
    log("END cooldown")


def benchmark():
    log(f"START benchmark cpus={CPUS}")

    log(f"START baseline duration={BASELINE}s")
    time.sleep(BASELINE)
    log("END baseline")

    # CPU
    run(
        "cpu",
        "mild",
        MILD,
        "--cpu",
        str(MILD_CPUS),
        "--cpu-load",
        "40",
        "--cpu-method",
        "all",
    )

    run(
        "cpu",
        "strong",
        STRONG,
        "--cpu",
        "0",
        "--cpu-load",
        "100",
        "--cpu-method",
        "all",
    )

    cooldown()

    # RAM / memory bandwidth
    run(
        "memory",
        "mild",
        MILD,
        "--vm",
        "1",
        "--vm-bytes",
        "15%",
        "--vm-keep",
        "--memcpy",
        "1",
    )

    run(
        "memory",
        "strong",
        STRONG,
        "--vm",
        "2",
        "--vm-bytes",
        "50%",
        "--vm-keep",
        "--memcpy",
        str(max(2, CPUS // 2)),
    )

    cooldown()

    # Filesystem metadata / many files
    run(
        "filesystem",
        "mild",
        MILD,
        "--dentry",
        "1",
        "--dentries",
        "512",
    )

    run(
        "filesystem",
        "strong",
        STRONG,
        "--dentry",
        "4",
        "--dentries",
        "8192",
    )

    cooldown()

    # Storage reads/writes
    run(
        "storage",
        "mild",
        MILD,
        "--iomix",
        "1",
        "--iomix-bytes",
        "128M",
    )

    run(
        "storage",
        "strong",
        STRONG,
        "--iomix",
        "2",
        "--iomix-bytes",
        "1G",
    )

    cooldown()

    # GPU
    run(
        "gpu",
        "mild",
        MILD,
        "--gpu",
        "1",
        "--gpu-frag",
        "4",
        "--gpu-tex-size",
        "1024",
        "--gpu-upload",
        "1",
    )

    run(
        "gpu",
        "strong",
        STRONG,
        "--gpu",
        "1",
        "--gpu-frag",
        "64",
        "--gpu-tex-size",
        "4096",
        "--gpu-upload",
        "4",
    )

    cooldown()

    # Whole-system mixed load
    run(
        "mixed",
        "mild",
        MILD,
        "--cpu",
        str(MILD_CPUS),
        "--cpu-load",
        "40",
        "--vm",
        "1",
        "--vm-bytes",
        "15%",
        "--iomix",
        "1",
        "--iomix-bytes",
        "128M",
        "--gpu",
        "1",
        "--gpu-frag",
        "4",
        "--gpu-tex-size",
        "1024",
    )

    run(
        "mixed",
        "strong",
        STRONG,
        "--cpu",
        "0",
        "--cpu-load",
        "100",
        "--vm",
        "2",
        "--vm-bytes",
        "40%",
        "--iomix",
        "2",
        "--iomix-bytes",
        "512M",
        "--gpu",
        "1",
        "--gpu-frag",
        "64",
        "--gpu-tex-size",
        "4096",
    )

    cooldown()

    log("END benchmark")


def main():
    if shutil.which("stress-ng") is None:
        print(
            "error: stress-ng is required but was not found in PATH",
            file=sys.stderr,
        )
        return 1

    TEMP_PATH.mkdir(parents=True, exist_ok=True)
    benchmark()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
