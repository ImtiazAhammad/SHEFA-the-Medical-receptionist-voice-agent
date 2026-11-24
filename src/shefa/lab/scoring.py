"""One bench run: the scenarios through the agent, each call judged, one scorecard.

`run_scorecard` is shared by `shefa lab score` (one model) and the bake-off (many models),
so both score a model the same way. It reads these fields from `args`: `scenarios` (paths
or None for the defaults), `tags`, `judge_model`, `caller_model`, `mishear`, `seed`,
`speech`, `out`, and optionally `clinic`.
"""

from __future__ import annotations

import contextlib
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from shefa.lab import judge as lab_judge
from shefa.lab import scorecard
from shefa.lab.mishear import Confusions
from shefa.lab.models import ollama_llm
from shefa.lab.runner import Lab
from shefa.lab.scenarios import Scenario, load_scenarios, select

if TYPE_CHECKING:
    from datetime import date

    from shefa.lab.runner import ScenarioResult

BENCH_DIR = Path("configs/lab/bench")
MAIN_SCENARIOS = Path("configs/lab/scenarios.yaml")
COLLECTOR_DB = Path("data/collector/collector.db")
DEFAULT_CLINIC = "configs/clinic.example.yaml"
CALLER_TEMPERATURE = 0.7  # a patient who varies a little from run to run
JUDGE_TEMPERATURE = 0.0  # a judge who gives the same call the same marks


def default_scenario_paths() -> list[str]:
    return [*(str(p) for p in sorted(BENCH_DIR.glob("*.yaml"))), str(MAIN_SCENARIOS)]


def select_scenarios(args: Any) -> list[Scenario]:
    """The scenarios `args` names, filtered by `args.tags`; ValueError says what is wrong."""
    scenarios: list[Scenario] = []
    seen: dict[str, str] = {}
    for path in getattr(args, "scenarios", None) or default_scenario_paths():
        try:
            loaded = load_scenarios(path)
        except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
            raise ValueError(f"Cannot read {path}: {error}") from error
        for scenario in loaded:
            if scenario.id in seen:
                raise ValueError(
                    f"duplicate scenario id {scenario.id!r} in {path} (also in {seen[scenario.id]})"
                )
            seen[scenario.id] = path
        scenarios += loaded
    tags = {tag.strip() for tag in (getattr(args, "tags", "") or "").split(",") if tag.strip()}
    chosen = select(scenarios, tags)
    if not chosen:
        raise ValueError(f"No scenario matches --tags {','.join(sorted(tags))}")
    return chosen


def transcript_of(result: ScenarioResult) -> list[tuple[str, str]]:
    """The call as the judge reads it: the greeting, then each line the caller and agent said."""
    lines: list[tuple[str, str]] = []
    for turn in result.turns:
        if turn.greeting:
            lines.append(("agent", turn.greeting))
        lines += [("patient", turn.said), ("agent", turn.reply)]
    return lines


def _confusions(args: Any) -> Confusions | None:
    """The speech-recognition mistakes to replay: saved once, then reused by every run."""
    path = Path(args.out) / "confusions.json"
    if path.exists():
        return Confusions.load(path)
    table = Confusions.from_collector_db(COLLECTOR_DB)
    if table.subs or table.drop_rate:
        path.parent.mkdir(parents=True, exist_ok=True)
        table.save(path)
    # An empty table is not saved: it may only mean the database was busy, and a saved
    # empty table would stop the real one from ever being built.
    return table


def _agreement(args: Any, judged: dict[str, Any]) -> dict[str, Any] | None:
    import json

    path = Path(args.out) / "human_labels.json"
    if not path.exists():
        return None
    human = json.loads(path.read_text(encoding="utf-8"))
    return lab_judge.agreement({k: v for k, v in judged.items() if v is not None}, human)


async def _judge_all(
    judge_llm: Any, results: list[ScenarioResult]
) -> dict[str, lab_judge.JudgeScore | None]:
    judged: dict[str, lab_judge.JudgeScore | None] = {}
    for result in results:
        sid = result.scenario.id
        judged[sid] = None
        if not result.turns:
            continue  # nothing was said, so there is nothing to mark
        try:
            judged[sid] = await lab_judge.judge_call(
                judge_llm, result.scenario, transcript_of(result)
            )
        except Exception as error:  # noqa: BLE001 - one failed call never ends the run
            reason = " ".join(f"{type(error).__name__}: {error}".split())
            print(f"warning: judge call for {sid} failed ({reason}); unjudged", file=sys.stderr)
    return judged


async def run_scorecard(
    model: str | None,
    args: Any,
    *,
    scenarios: list[Scenario] | None = None,
    agent_llm: Any = None,
    caller_llm: Any = None,
    judge_llm: Any = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Run the bench against `model` (None: the product's configured model) and score it.

    The three models can be passed in (tests, or a caller that already holds them); any it
    builds itself it closes. The product's registry is pointed at the model under test for
    the run and put back as found.
    """
    from shefa.models.registry import registry
    from shefa.store import audit

    scenarios = scenarios if scenarios is not None else select_scenarios(args)
    out = Path(args.out)
    work = out / ".work"
    work.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    owned: list[Any] = []

    def build(given: Any, name: str, temperature: float) -> Any:
        if given is not None:
            return given
        built = ollama_llm(name, temperature=temperature)
        owned.append(built)
        return built

    caller = build(caller_llm, args.caller_model, CALLER_TEMPERATURE)
    judge = build(judge_llm, args.judge_model, JUDGE_TEMPERATURE)
    agent = agent_llm if agent_llm is not None or model is None else ollama_llm(model)
    if agent is not None and agent is not agent_llm:
        owned.append(agent)
    previous_llm = registry._llm  # noqa: SLF001 - put back as found
    previous_audit = getattr(audit, "_default_audit_store", None)
    # Lab calls write audit rows like real calls; they go to the bench's own file, never to
    # the clinic's database.
    audit.set_default_audit_store(audit.AuditStore(work / "audit.db"))
    try:
        if agent is not None:
            registry.use_llm(agent)  # None: the registry builds the configured model itself
        label = model or _configured_label()
        voice = await registry.get_tts() if args.speech else None
        stt = await registry.get_stt() if args.speech else None
        mishear_rate = 0.0 if args.speech else float(args.mishear)
        table = _confusions(args) if mishear_rate > 0 else None
        lab = Lab(
            clinic_file=getattr(args, "clinic", DEFAULT_CLINIC),
            work_dir=work,
            voice=voice,
            stt=stt,
            patient_llm=caller,
            today=today,
            mishear=table,
            mishear_rate=mishear_rate,
            seed=int(args.seed),
        )
        results: list[ScenarioResult] = []
        for scenario in scenarios:
            print(f"  {scenario.id:<24} ", end="", flush=True)
            result = await lab.run(scenario)
            results.append(result)
            failed = [c.name for c in result.checks if not c.ok]
            failed += [c.name for t in result.turns for c in t.checks if not c.ok]
            print("pass" if result.passed else f"NEEDS WORK  {result.error or '; '.join(failed)}")
        judged = await _judge_all(judge, results)
        meta = {
            "model": label,
            "judge_model": args.judge_model,
            "caller_model": args.caller_model,
            "mishear_rate": mishear_rate,
            "seed": int(args.seed),
            "speech": bool(args.speech),
            "tags": getattr(args, "tags", "") or "",
            "started": started,
        }
        card = scorecard.build(results, judged, meta)
        agreement = _agreement(args, judged)
        if agreement is not None:
            card["judged"]["agreement"] = agreement
        return card
    finally:
        if agent is not None:
            registry.use_llm(previous_llm)
        audit.set_default_audit_store(previous_audit)
        for built in owned:
            with contextlib.suppress(Exception):
                await built.close()


def _configured_label() -> str:
    from shefa.config.settings import settings

    pipeline = settings.pipeline
    _, adapter = settings.models.resolve_llm_adapter(pipeline.llm.provider)
    return f"{pipeline.llm.provider} {getattr(adapter, 'model', '')}".strip()
