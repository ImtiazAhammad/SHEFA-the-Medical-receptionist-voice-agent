"""Latency benchmark with explicit abort thresholds.

A patient on a telephone feels the p95, not the mean, so that is what the bar
is set on. A mean can be healthy while a meaningful slice of calls is unusable.

Cold start is reported on its own line and deliberately does not abort: reloading
the voice is a one-off after a restart, and folding it into the warm p95 would
make the interactive number look bad for a reason that disappears after the
first call. It is printed so nobody mistakes a fast warm run for a fast start.
"""

from __future__ import annotations

import math
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_P50_SECONDS = 1.2
DEFAULT_P95_SECONDS = 2.0
DEFAULT_VRAM_FRACTION = 0.8


@dataclass(frozen=True)
class Threshold:
    p50_seconds: float = DEFAULT_P50_SECONDS
    p95_seconds: float = DEFAULT_P95_SECONDS
    vram_fraction: float = DEFAULT_VRAM_FRACTION


@dataclass
class BenchResult:
    warm_samples: list[float] = field(default_factory=list)
    cold_start_seconds: float | None = None
    vram_fraction: float | None = None


@dataclass
class BenchReport:
    p50: float
    p95: float
    cold_start_seconds: float | None
    vram_fraction: float | None
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def render(self) -> str:
        cold = (
            f"{self.cold_start_seconds:.2f}s"
            if self.cold_start_seconds is not None
            else "unavailable"
        )
        vram = (
            f"{self.vram_fraction * 100:.0f}%"
            if self.vram_fraction is not None
            else "unavailable"
        )
        lines = [
            f"sefa bench  warm p50 {self.p50:.3f}s  p95 {self.p95:.3f}s",
            f"cold start {cold}   vram {vram}",
            "PASS" if self.passed else "ABORT",
        ]
        lines.extend(f"  - {failure}" for failure in self.failures)
        return "\n".join(lines)


def percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile of an unsorted sample set.

    Nearest-rank rather than linear interpolation: interpolating between the
    last fast sample and the first slow one lands *between* them, so a run where
    6% of calls take 5s reports a p95 of 0.44s and passes. For a gate whose
    whole job is catching a slow tail, diluting the tail into the gap below it
    is the wrong trade. This is the same method used for latency SLOs.
    """
    if not 0 <= pct <= 100:
        raise ValueError(f"percentile must be 0-100, got {pct}")
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = min(max(1, math.ceil(pct / 100.0 * len(ordered))), len(ordered))
    return ordered[rank - 1]


def evaluate(result: BenchResult, thresholds: Threshold | None = None) -> BenchReport:
    limits = thresholds or Threshold()
    failures: list[str] = []

    if not result.warm_samples:
        failures.append("no warm samples collected; the benchmark did not run")

    p50 = percentile(result.warm_samples, 50)
    p95 = percentile(result.warm_samples, 95)

    if result.warm_samples and p50 > limits.p50_seconds:
        failures.append(f"p50 {p50:.3f}s exceeds {limits.p50_seconds:.2f}s")
    if result.warm_samples and p95 > limits.p95_seconds:
        failures.append(f"p95 {p95:.3f}s exceeds {limits.p95_seconds:.2f}s")
    if result.vram_fraction is not None and result.vram_fraction > limits.vram_fraction:
        failures.append(
            f"vram {result.vram_fraction * 100:.0f}% exceeds "
            f"{limits.vram_fraction * 100:.0f}%"
        )

    return BenchReport(
        p50=p50,
        p95=p95,
        cold_start_seconds=result.cold_start_seconds,
        vram_fraction=result.vram_fraction,
        failures=failures,
    )


def _run(args: list[str]) -> str:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return completed.stdout


def read_vram_fraction() -> float | None:
    """Fraction of total VRAM in use *by this process*, or None without a GPU.

    Machine totals from `nvidia-smi` include every other tenant on the card, so
    a shared GPU running something unrelated would report the pipeline as over
    budget for memory it never allocated. An always-red gate is worse than none:
    it teaches people to ignore the signal meant to catch a real blowup. So the
    per-process figure is used when the driver exposes it.
    """
    try:
        total_mb = _total_vram_mb()
        if total_mb is None:
            return None
        used_mb = _process_vram_mb()
        if used_mb is None:
            used_mb = _machine_used_vram_mb()
            if used_mb is None:
                return None
    except (FileNotFoundError, subprocess.SubprocessError, OSError, ValueError):
        return None

    return used_mb / total_mb


def _total_vram_mb() -> float | None:
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=memory.total",
            "--format=csv,nounits,noheader",
        ]
    )
    first = output.strip().splitlines()
    if not first:
        return None
    total = float(first[0].strip())
    return total or None


def _process_vram_mb() -> float | None:
    """This process's own GPU memory.

    Returns 0.0 when the driver answers but this pid is not among the compute
    apps — that is a CPU-only process, which is the default Piper setup. None
    means the driver could not attribute memory at all, and only then may the
    caller fall back to the machine total.
    """
    output = _run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,nounits,noheader",
        ]
    )
    own_pid = os.getpid()
    attributed = False
    for line in output.strip().splitlines():
        try:
            pid, used = (part.strip() for part in line.split(","))
        except ValueError:
            continue
        if not pid.isdigit():
            # The driver rejected the query; attribution is unavailable.
            return None
        attributed = True
        if int(pid) == own_pid:
            return float(used)
    return 0.0 if attributed else None


def _machine_used_vram_mb() -> float | None:
    output = _run(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,nounits,noheader",
        ]
    )
    first = output.strip().splitlines()
    if not first:
        return None
    return float(first[0].strip())


async def measure(
    tts: Any,
    texts: list[str],
    vram: bool = True,
) -> BenchResult:
    """Time `texts` on a live adapter, separating the first call from the rest."""
    if not texts:
        return BenchResult(vram_fraction=read_vram_fraction() if vram else None)

    cold_started = time.perf_counter()
    await tts.synthesize(texts[0])
    cold = time.perf_counter() - cold_started

    warm: list[float] = []
    for text in texts[1:]:
        started = time.perf_counter()
        await tts.synthesize(text)
        warm.append(time.perf_counter() - started)

    if not warm:
        warm.append(cold)

    return BenchResult(
        warm_samples=warm,
        cold_start_seconds=cold,
        vram_fraction=read_vram_fraction() if vram else None,
    )
