"""One bench run: the scenarios through the agent, each call judged, one scorecard.

`run_scorecard` is shared by `shefa lab score` (one model) and the bake-off (many models),
so both score a model the same way. It reads these fields from `args`: `scenarios` (paths
or None for the defaults), `tags`, `judge_model`, `caller_model`, `mishear`, `seed`,
`speech`, `out`, and optionally `clinic` and `side_base_url` (the OpenAI-compatible server
the caller and judge run on; default Ollama).
"""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from shefa.lab import judge as lab_judge
from shefa.lab import scorecard
from shefa.lab.mishear import Confusions
from shefa.lab.models import OLLAMA_URL, ollama_llm, split_candidate
from shefa.lab.runner import Lab
from shefa.lab.scenarios import Scenario, load_scenarios, select

if TYPE_CHECKING:
    from collections.abc import Callable
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
    """The call as the judge reads it: the greeting, then each line the caller and agent said.

    When SHEFA misheard a line, the caller's line shows both ("said: ...  (SHEFA heard: ...)"),
    so the judge can see whether the reply recovered from the mishearing.
    """
    lines: list[tuple[str, str]] = []
    for turn in result.turns:
        if turn.greeting:
            lines.append(("agent", turn.greeting))
        caller = turn.said
        if turn.heard and turn.heard != turn.said:
            caller = f"said: {turn.said}  (SHEFA heard: {turn.heard})"
        lines += [("patient", caller), ("agent", turn.reply)]
    return lines


def _confusions(args: Any) -> Confusions:
    """The speech-recognition mistakes to replay: saved once, then reused by every run.

    A saved file that cannot be read is a ValueError (the caller fixes or deletes it); the
    collector database being missing or busy just gives an empty table.
    """
    path = Path(args.out) / "confusions.json"
    if path.exists():
        try:
            return Confusions.load(path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise ValueError(
                f"Cannot read {path}: {error}. Fix it or delete it to build a new table."
            ) from error
    table = Confusions.from_collector_db(COLLECTOR_DB)
    if table.subs or table.drop_rate:
        path.parent.mkdir(parents=True, exist_ok=True)
        table.save(path)
    # An empty table is not saved: it may only mean the database was busy, and a saved
    # empty table would stop the real one from ever being built.
    return table


def _human_labels(args: Any) -> dict[str, dict[str, int]] | None:
    """The optional human scores `{scenario_id: {dimension: score}}`; ValueError if malformed."""
    path = Path(args.out) / "human_labels.json"
    if not path.exists():
        return None
    try:
        human = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    shaped = isinstance(human, dict) and all(
        isinstance(scores, dict)
        and all(
            isinstance(name, str)
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            for name, value in scores.items()
        )
        for scores in human.values()
    )
    if not shaped:
        raise ValueError(
            f"{path} must map each scenario id to {{dimension: score}}, "
            'for example {"bn-booking": {"warmth": 4}}'
        )
    return human


def validate_files(args: Any) -> None:
    """ValueError if the saved label or table file in `args.out` is unreadable.

    The check `run_scorecard` makes before it calls a model, for a caller (the bake-off)
    that wants to fail before the first of several runs rather than during one.
    """
    _human_labels(args)
    if not args.speech and float(args.mishear) > 0:
        _confusions(args)


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
    progress: Callable[[str], None] | None = print,
) -> dict[str, Any]:
    """Run the bench against `model` (None: the product's configured model) and score it.

    The three models can be passed in (tests, or a caller that already holds them); any it
    builds itself it closes. The product's registry is pointed at the model under test for
    the run and put back as found. With `model` None and no `agent_llm`, the configured model
    the registry builds for the run is closed afterwards too. `progress` gets one line per
    scenario (None: silent). ValueError, before any model is called, when `human_labels.json`
    or a saved `confusions.json` in `args.out` is unreadable.
    """
    from shefa.models.registry import registry
    from shefa.store import audit

    scenarios = scenarios if scenarios is not None else select_scenarios(args)
    out = Path(args.out)
    human = _human_labels(args)
    requested = float(args.mishear)
    # Real speech recognition makes its own mistakes, so none are replayed on top of it.
    mishear_rate = 0.0 if args.speech else requested
    table = _confusions(args) if mishear_rate > 0 else None
    if table is not None and not (table.subs or table.drop_rate):
        print(
            f"warning: no recognition errors found in {COLLECTOR_DB}; running without mishearing",
            file=sys.stderr,
        )
        mishear_rate = 0.0
    work = out / ".work"
    work.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    owned: list[Any] = []

    def build(given: Any, name: str, temperature: float) -> Any:
        if given is not None:
            return given
        built = ollama_llm(
            name,
            base_url=getattr(args, "side_base_url", None) or OLLAMA_URL,
            temperature=temperature,
        )
        owned.append(built)
        return built

    caller = build(caller_llm, args.caller_model, CALLER_TEMPERATURE)
    judge = build(judge_llm, args.judge_model, JUDGE_TEMPERATURE)
    if agent_llm is not None or model is None:
        agent = agent_llm
    else:
        served, think = split_candidate(model)  # "name+think": the model with reasoning on
        agent = ollama_llm(served, think=True) if think else ollama_llm(served)
    if agent is not None and agent is not agent_llm:
        owned.append(agent)
    previous_llm = registry._llm  # noqa: SLF001 - put back as found
    previous_audit = getattr(audit, "_default_audit_store", None)
    # Lab calls write audit rows like real calls; they go to the bench's own file, never to
    # the clinic's database.
    isolated = _isolate(work, getattr(args, "engine", None))
    audit.set_default_audit_store(audit.AuditStore(work / "audit.db"))
    try:
        if agent is not None:
            registry.use_llm(agent)  # None: the registry builds the configured model itself
        label = model or _configured_label()
        voice = await registry.get_tts() if args.speech else None
        stt = await registry.get_stt() if args.speech else None
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
            result = await lab.run(scenario)
            results.append(result)
            failed = [c.name for c in result.checks if not c.ok]
            failed += [c.name for t in result.turns for c in t.checks if not c.ok]
            if progress is not None:
                verdict = (
                    "pass" if result.passed else f"NEEDS WORK  {result.error or '; '.join(failed)}"
                )
                progress(f"  {scenario.id:<24} {verdict}")
        judged = await _judge_all(judge, results)
        meta = {
            "model": label,
            "judge_model": args.judge_model,
            "caller_model": args.caller_model,
            "mishear_rate": mishear_rate,  # what was applied; 0.0 when there was no table
            "mishear_requested": requested,
            "seed": int(args.seed),
            "speech": bool(args.speech),
            "tags": getattr(args, "tags", "") or "",
            "started": started,
            "engine": isolated.engine,
        }
        card = scorecard.build(results, judged, meta)
        if human is not None:
            card["judged"]["agreement"] = lab_judge.agreement(
                {k: v for k, v in judged.items() if v is not None}, human
            )
        return card
    finally:
        if agent is not None:
            registry.use_llm(previous_llm)
        elif previous_llm is None and registry._llm is not None:  # noqa: SLF001
            owned.append(registry._llm)  # noqa: SLF001 - the configured model this run caused
            registry.use_llm(None)
        audit.set_default_audit_store(previous_audit)
        isolated.restore()
        for built in owned:
            with contextlib.suppress(Exception):
                await built.close()


class _Isolated:
    """What `_isolate` changed, to put back as it was found."""

    def __init__(self, engine: str, undo: list[Callable[[], None]]) -> None:
        self.engine = engine
        self._undo = undo

    def restore(self) -> None:
        for step in reversed(self._undo):
            step()


def _isolate(work: Path, engine: str | None) -> _Isolated:
    """Point the run at its own stores in `work` and set the engine (None: the configured one).

    The lab never reads production's prompts, knowledge base or call log and never writes to
    them: the config store, the knowledge base (seeded fresh from the clinic's facilities and
    the platform file) and the call log get files of their own, and `storage.db_path`, which
    every default falls back to, points into `work` for the run. With no live rows in the
    lab's config store, the engine is the setting `--engine` gave. The previous stores are read
    from the module globals, never through `default_*_store()`, which would open the live file.
    """
    from shefa import call_log
    from shefa.brain import config as brain_config
    from shefa.brain import knowledge
    from shefa.config.settings import settings

    undo: list[Callable[[], None]] = []
    try:
        return _isolated(work, engine, undo, call_log, brain_config, knowledge, settings)
    except BaseException:
        _Isolated("", undo).restore()  # half done is put back before the error goes on
        raise


def _isolated(
    work: Path,
    engine: str | None,
    undo: list[Callable[[], None]],
    call_log: Any,
    brain_config: Any,
    knowledge: Any,
    settings: Any,
) -> _Isolated:
    old_path, old_engine = settings.storage.db_path, settings.pipeline.engine

    def put_back_settings() -> None:
        settings.storage.db_path = old_path
        settings.pipeline.engine = old_engine

    undo.append(put_back_settings)
    settings.storage.db_path = str(work / "platform.db")
    if engine is not None:
        settings.pipeline.engine = engine
    for name in ("config.db", "knowledge.db", "calls.db"):
        for leftover in work.glob(f"{name}*"):
            leftover.unlink()  # every run starts from the files the lab itself seeds

    old_config = brain_config._default_config_store  # noqa: SLF001 - put back as found
    brain_config.set_default_config_store(brain_config.ConfigStore(work / "config.db"))
    undo.append(lambda: brain_config.set_default_config_store(old_config))

    old_knowledge = knowledge._default_knowledge_store  # noqa: SLF001
    store = knowledge.KnowledgeStore(work / "knowledge.db")
    knowledge.seed(store, clinic_id="", platform_file=knowledge.PLATFORM_FILE)
    knowledge.set_default_knowledge_store(store)
    undo.append(lambda: knowledge.set_default_knowledge_store(old_knowledge))

    old_calls = call_log._store  # noqa: SLF001
    calls = call_log.CallsStore(work / "calls.db")
    call_log.set_default_calls_store(calls)

    def put_back_calls() -> None:
        call_log.set_default_calls_store(old_calls)
        calls.close()

    undo.append(put_back_calls)
    return _Isolated(settings.pipeline.engine, undo)


def _configured_label() -> str:
    from shefa.config.settings import settings

    pipeline = settings.pipeline
    _, adapter = settings.models.resolve_llm_adapter(pipeline.llm.provider)
    return f"{pipeline.llm.provider} {getattr(adapter, 'model', '')}".strip()
