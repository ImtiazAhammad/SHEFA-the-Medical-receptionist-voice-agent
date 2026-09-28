"""Tests for `sefa bench` latency measurement and ABORT thresholds (T6).

A benchmark that reports a single mean cannot tell a healthy pipeline from one
that is fast 90% of the time and unusable 10% of the time, and a patient on a
telephone feels the p95. The bar is an explicit abort, not a printed number
somebody has to notice.

Model load is reported as its own cold-start figure: folding a ~0.9s load into
the warm p95 would make the interactive number look bad for a reason that
disappears after the first call.
"""

from __future__ import annotations

import pytest

from sefa.bench import (
    BenchResult,
    Threshold,
    evaluate,
    percentile,
)


class TestPercentile:
    def test_p50_of_an_odd_length_sample(self):
        assert percentile([3.0, 1.0, 2.0], 50) == 2.0

    def test_p50_of_an_even_length_sample_takes_the_lower_rank(self):
        """Nearest-rank: no interpolation, so a slow tail is never averaged
        away into the gap below it."""
        assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0

    def test_p95_sorts_before_selecting(self):
        samples = [float(i) for i in range(1, 101)]

        assert percentile(samples, 95) == 95.0

    def test_p95_of_a_short_sample_is_the_max(self):
        assert percentile([0.1, 0.2], 95) == 0.2

    def test_a_single_sample(self):
        assert percentile([1.5], 95) == 1.5

    def test_an_empty_sample_is_zero(self):
        assert percentile([], 95) == 0.0

    def test_rejects_a_percentile_out_of_range(self):
        with pytest.raises(ValueError):
            percentile([1.0], 101)


class TestEvaluate:
    def _warm(self, samples: list[float], cold: float = 0.9) -> BenchResult:
        return BenchResult(warm_samples=samples, cold_start_seconds=cold, vram_fraction=0.1)

    def test_reports_p50_p95_and_cold_start_separately(self):
        result = self._warm([float(i) for i in range(1, 101)])

        report = evaluate(result)

        assert report.p50 == 50.0
        assert report.p95 == 95.0
        assert report.cold_start_seconds == 0.9

    def test_passes_when_every_threshold_is_met(self):
        report = evaluate(self._warm([0.4] * 20))

        assert report.passed is True
        assert report.failures == []

    def test_fails_on_a_slow_p50(self):
        report = evaluate(self._warm([1.5] * 20))

        assert report.passed is False
        assert any("p50" in failure for failure in report.failures)

    def test_fails_on_a_slow_p95(self):
        """A good p50 with a bad p95 is exactly the case a mean would hide."""
        report = evaluate(self._warm([0.2] * 94 + [5.0] * 6))

        assert report.passed is False
        assert any("p95" in failure for failure in report.failures)

    def test_fails_when_vram_is_over_budget(self):
        result = BenchResult(warm_samples=[0.4] * 20, cold_start_seconds=0.9, vram_fraction=0.93)

        report = evaluate(result)

        assert report.passed is False
        assert any("vram" in failure for failure in report.failures)

    def test_does_not_abort_on_cold_start(self):
        """Cold start is a separate line, not an abort condition: a restart is
        a one-off and the target is warm-call latency."""
        report = evaluate(self._warm([0.4] * 20, cold=12.0))

        assert report.passed is True
        assert report.cold_start_seconds == 12.0

    def test_reports_every_failure_at_once(self):
        result = BenchResult(warm_samples=[5.0] * 20, cold_start_seconds=0.9, vram_fraction=0.99)

        report = evaluate(result)

        assert len(report.failures) == 3

    def test_unavailable_vram_does_not_abort(self):
        result = BenchResult(warm_samples=[0.4] * 20, cold_start_seconds=0.9, vram_fraction=None)

        report = evaluate(result)

        assert report.passed is True
        assert report.vram_fraction is None

    def test_thresholds_are_configurable(self):
        report = evaluate(self._warm([1.0] * 20), thresholds=Threshold(p50_seconds=0.5))

        assert report.passed is False
        assert any("p50" in failure for failure in report.failures)

    def test_defaults_match_the_plan_targets(self):
        assert Threshold().p50_seconds == 1.2
        assert Threshold().p95_seconds == 2.0
        assert Threshold().vram_fraction == 0.8

    def test_an_empty_run_is_not_a_pass(self):
        """No samples means the benchmark did not run, which is not success."""
        report = evaluate(BenchResult(warm_samples=[], cold_start_seconds=None, vram_fraction=None))

        assert report.passed is False
        assert any("no" in failure.lower() for failure in report.failures)


class TestFormatting:
    def test_renders_the_cold_start_on_its_own_line(self):
        report = evaluate(BenchResult([0.4] * 10, 0.93, 0.1))

        text = report.render()

        assert "cold" in text.lower()
        assert "0.93" in text

    def test_marks_an_abort(self):
        text = evaluate(BenchResult([5.0] * 10, 0.9, 0.1)).render()

        assert "ABORT" in text

    def test_marks_a_pass(self):
        text = evaluate(BenchResult([0.4] * 10, 0.9, 0.1)).render()

        assert "PASS" in text
        assert "ABORT" not in text

    def test_says_so_when_vram_is_unavailable(self):
        text = evaluate(BenchResult([0.4] * 10, 0.9, None)).render()

        assert "unavailable" in text.lower()


class TestVram:
    """No CUDA device, or a driver that will not answer, is neither pass nor fail."""

    def test_returns_none_when_nvidia_smi_is_absent(self, monkeypatch):
        import sefa.bench as bench

        def missing(*args, **kwargs):
            raise FileNotFoundError("nvidia-smi")

        monkeypatch.setattr(bench, "_run", missing)

        assert bench.read_vram_fraction() is None

    def test_returns_none_on_unparseable_output(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(bench, "_run", _sequence("N/A\n"))

        assert bench.read_vram_fraction() is None

    def test_returns_none_when_total_is_zero(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(bench, "_run", _sequence("0\n", "0\n"))

        assert bench.read_vram_fraction() is None

    def test_returns_none_on_empty_output(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(bench, "_run", _sequence("\n", "\n", "\n"))

        assert bench.read_vram_fraction() is None

    def test_survives_a_non_zero_exit(self, monkeypatch):
        import subprocess

        import sefa.bench as bench

        def failing(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "nvidia-smi")

        monkeypatch.setattr(bench, "_run", failing)

        assert bench.read_vram_fraction() is None

    def test_reads_the_first_gpu_when_several_are_present(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(
            bench, "_run", _sequence("8192\n16380\n", "0\n", "100\n")
        )

        assert bench.read_vram_fraction() == pytest.approx(100 / 8192)


class TestMeasure:
    """Cold start must be attributed to the first call, not averaged in."""

    @pytest.mark.asyncio
    async def test_separates_the_first_call_from_the_rest(self, monkeypatch):
        import sefa.bench as bench

        class TimedTTS:
            def __init__(self):
                self.calls = 0

            async def synthesize(self, text, language="en"):
                self.calls += 1
                return object()

        sleeps = iter([0.0, 0.90, 0.10, 0.12, 0.14, 0.16, 0.20, 0.22])
        monkeypatch.setattr(bench.time, "perf_counter", lambda: next(sleeps))

        result = await bench.measure(TimedTTS(), ["first", "a", "b", "c"], vram=False)

        assert result.cold_start_seconds == pytest.approx(0.90)
        assert result.warm_samples == pytest.approx([0.02, 0.02, 0.02])

    @pytest.mark.asyncio
    async def test_a_single_call_is_reported_as_both_cold_and_warm(self):
        import sefa.bench as bench

        class TimedTTS:
            async def synthesize(self, text, language="en"):
                return object()

        result = await bench.measure(TimedTTS(), ["only"], vram=False)

        assert result.cold_start_seconds is not None
        assert len(result.warm_samples) == 1

    @pytest.mark.asyncio
    async def test_no_texts_yields_no_samples(self):
        import sefa.bench as bench

        result = await bench.measure(object(), [], vram=False)

        assert result.warm_samples == []
        assert evaluate(result).passed is False


class TestVramAttribution:
    """VRAM must be this process's, not the whole machine's.

    `nvidia-smi` machine totals include every other tenant. A shared GPU box
    running something else would push the pipeline over a memory budget it never
    approached, and an always-red ABORT is worse than no gate: it teaches people
    to ignore the one signal meant to catch a VRAM blowup.
    """

    def test_counts_only_this_process(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)
        # Another process holds 13722 MiB of a 16380 MiB card.
        monkeypatch.setattr(bench, "_run", _sequence("16380\n", "3526, 13722\n4242, 256\n"))

        assert bench.read_vram_fraction() == pytest.approx(256 / 16380)

    def test_reports_zero_when_this_process_uses_no_gpu(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)
        monkeypatch.setattr(bench, "_run", _sequence("16380\n", "3526, 13722\n"))

        assert bench.read_vram_fraction() == 0.0

    def test_falls_back_to_the_machine_total_without_pid_attribution(self, monkeypatch):
        import sefa.bench as bench

        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)
        monkeypatch.setattr(bench, "_run", _sequence("16380\n", "no such field\n", "14013\n"))

        assert bench.read_vram_fraction() == pytest.approx(14013 / 16380)

    def test_a_cpu_only_run_does_not_abort(self, monkeypatch):
        """Piper runs on CPU by default; a CPU-only process uses no VRAM."""
        import sefa.bench as bench

        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)
        monkeypatch.setattr(bench, "_run", _sequence("16380\n", "3526, 13722\n"))

        report = evaluate(
            BenchResult(warm_samples=[0.1] * 20, cold_start_seconds=0.9, vram_fraction=0.0)
        )

        assert report.passed is True


def _sequence(*outputs: str):
    """Stand in for `_run`, which returns stdout text rather than a Completed."""
    calls = iter(outputs)

    def run(*args, **kwargs):
        return next(calls)

    return run


class TestNvidiaSmiInvocation:
    """Pin the actual subprocess contract, not just the parsing of its output.

    Every other VRAM test replaces `_run`, which means the query strings and the
    timeout/check flags are never exercised. A typo in a flag makes
    `nvidia-smi` exit non-zero, `check=True` turns that into an exception, and
    the reader silently reports "no GPU" — a benchmark that can never abort.
    """

    def test_run_passes_a_timeout_and_raises_on_failure(self, monkeypatch):
        import sefa.bench as bench

        captured = {}

        class Completed:
            stdout = "16380\n"

        def run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return Completed()

        monkeypatch.setattr(bench.subprocess, "run", run)

        assert bench._run(["nvidia-smi", "--query-gpu=memory.total"]) == "16380\n"
        assert captured["kwargs"]["timeout"] == 10
        assert captured["kwargs"]["check"] is True
        assert captured["kwargs"]["text"] is True

    def test_the_queries_ask_nvidia_smi_for_csv_without_units(self, monkeypatch):
        """A wrong flag makes nvidia-smi exit non-zero, which reads as 'no GPU'."""
        import sefa.bench as bench

        seen: list[list[str]] = []

        class Completed:
            stdout = "16380\n4242, 256\n256\n"

        monkeypatch.setattr(
            bench.subprocess, "run", lambda args, **kw: (seen.append(args), Completed())[1]
        )
        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)

        bench.read_vram_fraction()

        # Total and per-process; the machine-used fallback is not needed here
        # because this pid is attributed, so only two queries run.
        assert [args[1] for args in seen] == [
            "--query-gpu=memory.total",
            "--query-compute-apps=pid,used_memory",
        ]
        for args in seen:
            assert args[0] == "nvidia-smi"
            assert "--format=csv,nounits,noheader" in args

    def test_the_fallback_query_uses_the_same_format(self, monkeypatch):
        import sefa.bench as bench

        seen: list[list[str]] = []

        class Completed:
            stdout = "16380\nunattributable\n256\n"

        monkeypatch.setattr(
            bench.subprocess, "run", lambda args, **kw: (seen.append(args), Completed())[1]
        )
        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)

        bench.read_vram_fraction()

        assert seen[-1][1] == "--query-gpu=memory.used"

    def test_a_non_zero_exit_propagates(self, monkeypatch):
        import subprocess

        import sefa.bench as bench

        def run(args, **kwargs):
            raise subprocess.CalledProcessError(1, args)

        monkeypatch.setattr(bench.subprocess, "run", run)

        with pytest.raises(subprocess.CalledProcessError):
            bench._run(["nvidia-smi"])

    def test_skips_a_malformed_compute_app_line(self, monkeypatch):
        """A driver that emits a header or a warning must not crash the parse."""
        import sefa.bench as bench

        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)
        monkeypatch.setattr(
            bench,
            "_run",
            _sequence("16380\n", "no running processes found\n3526, 13722\n4242, 512\n"),
        )

        assert bench.read_vram_fraction() == pytest.approx(512 / 16380)

    @pytest.mark.parametrize("empty", ["", "\n", "   \n"])
    def test_empty_driver_output_is_not_a_crash(self, monkeypatch, empty):
        import sefa.bench as bench

        monkeypatch.setattr(bench, "_run", _sequence(empty, empty, empty))

        assert bench.read_vram_fraction() is None


class TestVramFallbackLadder:
    """Each rung of "we could not measure it" has to land on None, not a guess.

    Returning a fabricated 0.0 would quietly turn the VRAM gate off; returning
    a machine-wide total would blame the pipeline for another tenant. The only
    honest answer when nothing can be attributed is "unmeasured".
    """

    def test_unattributable_process_and_empty_machine_reading_is_unmeasured(self, monkeypatch):
        import sefa.bench as bench

        # Total is fine, per-process is unattributable, machine-used is empty.
        monkeypatch.setattr(bench, "_run", _sequence("16380\n", "no field\n", "\n"))

        assert bench.read_vram_fraction() is None

    def test_a_header_row_falls_back_to_the_machine_total(self, monkeypatch):
        """A driver that echoes a header row rather than failing the query.

        Header rows are why `pid.isdigit()` is checked: without it the header
        parses as a process and every box reports its VRAM as that header's
        `used_memory`, which is not a number at all.
        """
        import sefa.bench as bench

        monkeypatch.setattr(bench.os, "getpid", lambda: 4242)
        monkeypatch.setattr(
            bench, "_run", _sequence("16380\n", "pid, used_memory\n3526, 13722\n", "256\n")
        )

        assert bench.read_vram_fraction() == pytest.approx(256 / 16380)
