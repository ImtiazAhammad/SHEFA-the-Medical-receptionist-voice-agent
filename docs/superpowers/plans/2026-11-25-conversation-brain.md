# Conversation Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A second conversation engine (`pipeline.engine: agent`) in which the language model talks
naturally, from a versioned knowledge base and prompts, while code keeps control of facts, actions
and safety; plus the versioned config store the console will edit.

**Architecture:** A new package `shefa.brain`. Each turn it tracks the call (`state.py`), retrieves
knowledge (`knowledge.py`, `retrieve.py`), composes one prompt (`prompt.py`), streams one model call
that either speaks or opens with a `TOOL {...}` line (`tools.py`), checks every sentence before it
is spoken (`check.py`), and runs actions with the existing executor, keeping read-back and "yes"
before any booking change (`engine.py`). `VoicePipeline` calls it when the engine is `agent` and
falls back to today's guided engine when the model fails. Prompts and settings come from
`config_versions` (`config.py`), with `configs/` as seed and fallback.

**Tech Stack:** Python 3.13, SQLite (stdlib `sqlite3`), the existing OpenAI-compatible client
(gemma2-9b AWQ on vLLM, no native tool calls), `transformers` + `torch` on CPU for the optional
embedding model, pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-shefa-human-front-desk-design.md`, section 5 (and 8,
9). Inputs from sub-project 1: `docs/research/2026-11-25-local-model-bakeoff.md`.

## Global Constraints

- Code stays in charge of facts and actions; nothing unverified is said or booked; bookings,
  cancellations and moves keep the read-back and the caller's "yes". Only the talking is dynamic.
- No cloud models. The model is the configured one (gemma2-9b AWQ on vLLM, `shefa-llm`); thinking
  off. Everything fits one RTX 4060 Ti beside recognition and voice: the embedding model runs on
  the CPU.
- The new engine runs behind `pipeline.engine: agent | guided`, default `guided`. Do not change
  the default; flipping it is the founder's decision after the bench (Task 12).
- Errors: `MalformedLLMOutputError` is `shefa.pipeline.error_taxonomy.MalformedLLMOutputError`.
- The guided engine and its tests stay as they are and stay green.
- Per spec 5.1 step 6, checked before each sentence is spoken: every number, time, fee, name and
  date appears in the given facts or a tool result; no claim that a booking, cancellation or
  call-back happened unless a tool returned success; no medical advice; no other caller's data.
  One regeneration with the reason, then a safe fixed sentence.
- No reply over 2 sentences unless the caller asked for a list (bench hard check `brevity`).
- An information-only caller is never pushed toward booking.
- Never read or print `.env`, credentials or `configs/local.yaml`. Never `pkill -f`. No sudo.
- `ruff format` only new files; `ruff check` must pass on every touched file.
- The suite's 88% coverage floor holds (`uv run pytest -q`).
- Tables for the config store and knowledge base live in the platform database
  (`settings.storage.db_path`), never in a clinic's own file.

**Spec deviations (proposed; the founder confirms before Task 4):**
- Mood and goal come from code rules on the words (plus voice cues when sub-project 3 supplies
  them), not a classifier prompt: a second model call per turn costs latency on one card, and the
  label only steers tone. A classifier can replace `state.track` later behind the same signature.
- The running summary is built by code from `CallState`, not written by the model.
- `model.*`, `turn.*` keys are stored and versioned here; applying them at runtime (model switch
  with self-test) is sub-project 4. The brain reads `prompt.*`, `escalation.*` and `engine`.
- The knowledge base's "who made SHEFA" entry is not seeded (the repo does not say); the founder
  adds it with `shefa kb add`.

## Review Focus

1. **A booking read back while the caller answers with something other than yes or no** ("হ্যাঁ,
   তবে বিকেলে হলে ভালো"): nothing is booked; the change is understood as a new request. Test in
   Task 9.
2. **The model writes text before its `TOOL` line, or a broken `TOOL` line**: no JSON or the word
   TOOL is ever spoken; a broken line becomes one regeneration. Test in Task 8.
3. **An empty knowledge base or no embedding model on the machine**: retrieval runs on words
   alone; a question with no match gets the kind "not known" path, never an invented answer. Test in
   Task 3 and Task 8.
4. **A config value that is missing, or whose stored JSON is unreadable**: the call uses the
   default from `configs/`, logs once, and never fails. Test in Task 1.
5. **The model server stops answering mid-call**: that turn is answered by the guided engine,
   nothing is spoken twice, and later turns try the brain again. Test in Task 11.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/shefa/brain/__init__.py` | package; exports `Brain` |
| `src/shefa/brain/config.py` | `ConfigStore` (table `config_versions`), defaults, cached `snapshot()` |
| `src/shefa/brain/knowledge.py` | `KnowledgeStore` (tables `kb_entries`, `kb_history`), seeding |
| `src/shefa/brain/embed.py` | optional CPU embedding model (multilingual-e5-small) |
| `src/shefa/brain/retrieve.py` | BM25 + meaning search, merge, floors |
| `src/shefa/brain/state.py` | `CallState`, `Cues`, `track()` |
| `src/shefa/brain/prompt.py` | mood and goal cues, `compose()` |
| `src/shefa/brain/tools.py` | tool line protocol, argument validators, executor mapping |
| `src/shefa/brain/check.py` | sentence checker, `Grounds`, `Verdict` |
| `src/shefa/brain/safe.py` | the fixed safe sentences |
| `src/shefa/brain/engine.py` | `Brain.turn()`: one turn end to end, actions, pending read-back |
| `src/shefa/brain/greeting.py` | generated greeting, closing summary |
| `configs/prompts/brain/{persona,conduct,greeting,tools}.md` | seed prompts |
| `configs/knowledge/platform.yaml` | seed "About SHEFA" entries |
| `src/shefa/config/settings.py` | `PipelineConfig.engine`, `BrainConfig` |
| `src/shefa/pipeline/voice_pipeline.py` | engine dispatch, fallback, greeting |
| `src/shefa/cli.py` | `shefa config …`, `shefa kb …`, `--engine` on `lab score`/`bakeoff` |
| `configs/lab/bench/*.yaml` | emergency cases state the emergency in their first line |
| `docs/research/2026-11-2x-brain-vs-guided.md` | Task 12 results |

Tests: one `tests/unit/test_brain_<module>.py` per module, plus pipeline and CLI tests.

---

### Task 1: Settings and the config store

**Files:**
- Modify: `src/shefa/config/settings.py` (add `engine` to `PipelineConfig`; new `BrainConfig`,
  field `brain` on the root settings model)
- Create: `src/shefa/brain/__init__.py`, `src/shefa/brain/config.py`,
  `configs/prompts/brain/persona.md`, `conduct.md`, `greeting.md`, `tools.md`
- Modify: `src/shefa/cli.py` (`shefa config show|draft|publish|history`)
- Test: `tests/unit/test_brain_config.py`, `tests/unit/test_cli_config.py`

**Interfaces:**
- Produces:
  - `PipelineConfig.engine: Literal["agent", "guided"] = "guided"`
  - `BrainConfig` (field `settings.brain`): `kb_max_hits: int = 4`,
    `kb_min_words_score: float = 1.2`, `kb_min_meaning_score: float = 0.83`,
    `embedding_model: str = ""` (empty = words only), `config_cache_s: float = 5.0`,
    `history_turns: int = 6`, `greeting_timeout_s: float = 1.5`, `prompt_budget_tokens: int = 3000`,
    `disclosure: dict[str, str] = {}` (bn/en; Task 10 fills the default)
  - `KEYS: frozenset[str]` = `prompt.persona, prompt.conduct, prompt.greeting, prompt.tools,
    model.llm, model.llm.params, model.stt, model.tts.bn, model.tts.en, turn.settings,
    escalation.settings, engine` (spec 5.7; `turn.*`/`escalation.*`/`model.tts.<lang>` as these
    concrete keys)
  - `class ConfigStore(path: str | Path)` with
    `draft(key: str, value: Any, *, scope: str = "platform", author: str, note: str = "") -> int`
    (ValueError for a key not in `KEYS` or a scope that is neither `platform` nor a valid clinic id),
    `publish(version_id: int, *, author: str) -> None` (that row becomes `live`; the previous live
    row of the same key and scope becomes `archived`; publishing an archived row is the rollback),
    `live(key: str, scope: str = "platform") -> Any | None`,
    `versions(key: str, scope: str = "platform") -> list[dict[str, Any]]` (newest first),
    `live_values(scope: str = "platform") -> dict[str, Any]`
  - `default_config_store() -> ConfigStore` (at `settings.storage.db_path`) and
    `set_default_config_store(store: ConfigStore | None) -> None` (same pattern as
    `store.audit.set_default_audit_store`; also clears the snapshot cache)
  - `defaults() -> dict[str, Any]`: `prompt.*` from `configs/prompts/brain/*.md`, `engine` from
    `settings.pipeline.engine`, `escalation.settings` from `settings.escalation.model_dump()`
  - `snapshot(clinic_id: str = "") -> dict[str, Any]`: defaults, overlaid by platform live values,
    overlaid by the clinic's live values; cached for `settings.brain.config_cache_s` seconds
  - `call_config(session: CallSession) -> dict[str, Any]`: the snapshot stored once in
    `session.metadata["brain_config"]` at the first call, so a call keeps the versions live when it
    started

Table (exact): `config_versions(id INTEGER PRIMARY KEY, scope TEXT NOT NULL, key TEXT NOT NULL,
value_json TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft','live','archived')),
author TEXT NOT NULL, created_at REAL NOT NULL, note TEXT NOT NULL DEFAULT '')` with a unique
partial index on `(scope, key) WHERE status = 'live'`.

Seed prompt content (English instructions; the model answers in the caller's language):
- `persona.md`: SHEFA is the clinic's front-desk receptionist on the phone: polite, warm, calm,
  helpful; speaks like a trained Bangladeshi front-desk officer; plain spoken words, no lists, no
  symbols, no English words in a Bangla reply unless the caller used them; one or two short
  sentences per reply; one question at a time; vary the wording, never the same line twice in a
  call.
- `conduct.md`: the spec 5.4 conduct rules, one line each, in this order: acknowledge feelings
  first; never argue; apologise for the clinic's delays without blaming anyone; answer only from
  the facts given in this prompt or a tool result; when something is not in them, say kindly that
  you do not know and offer the desk's call-back; no medical advice, and urgent symptoms (chest
  pain, breathing trouble, heavy bleeding, fainting, a child very unwell, severe pain) get
  `hand_over` with reason `emergency` at once; never reveal another person's data; small talk
  briefly and warmly, then back to the caller's need; never offer a booking to a caller who only
  asked for information; a rude caller: stay calm, one polite boundary, then a second, then
  `hand_over`; anger for two turns or a request for a person: offer a person.
- `tools.md`: the protocol of Task 6, word for word with its parser.
- `greeting.md`: one warm welcome sentence naming the clinic, fitting the time of day, using the
  caller's name only when given; no questions about doctors; no facts.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_brain_config.py`)

```python
def test_a_published_draft_is_live_and_the_old_live_is_archived(tmp_path):
    store = ConfigStore(tmp_path / "p.db")
    a = store.draft("prompt.persona", "A", author="founder")
    store.publish(a, author="founder")
    b = store.draft("prompt.persona", "B", author="founder")
    assert store.live("prompt.persona") == "A"  # a draft is not live
    store.publish(b, author="founder")
    assert store.live("prompt.persona") == "B"
    assert [v["status"] for v in store.versions("prompt.persona")] == ["live", "archived"]

def test_publishing_an_archived_version_rolls_back(tmp_path): ...  # live goes back to "A"

def test_unknown_keys_and_scopes_are_refused(tmp_path):
    with pytest.raises(ValueError): ConfigStore(tmp_path / "p.db").draft("prompt.typo", "x", author="f")
    with pytest.raises(ValueError): ConfigStore(tmp_path / "p.db").draft("engine", "agent", scope="Bad Id!", author="f")

def test_the_snapshot_layers_clinic_over_platform_over_defaults(tmp_path, monkeypatch): ...
    # platform engine "agent", clinic "alo" engine "guided" -> snapshot("alo")["engine"] == "guided",
    # snapshot("")["engine"] == "agent", and an unset key equals defaults()

def test_an_unreadable_stored_value_falls_back_to_the_default(tmp_path, caplog): ...
    # write value_json "{oops" directly with sqlite3; snapshot()["prompt.persona"] == defaults()[...]
    # and exactly one warning is logged across two snapshot() calls

def test_a_call_keeps_the_config_it_started_with(tmp_path, monkeypatch): ...
    # call_config(session) once; publish a new persona; call_config(session) returns the old one
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_brain_config.py -q` → fails (module missing).
- [ ] **Step 3:** Implement the settings fields, prompt files, `config.py`. One `sqlite3`
  connection per call, `check_same_thread=False`, schema created on open (same pattern as
  `store/calls.py`).
- [ ] **Step 4:** CLI test: `shefa config draft prompt.persona --file p.md --note n` prints the
  new version id; `shefa config publish <id>` makes it live; `shefa config show` prints each key's
  live version id or `default`; author is the OS user name. Implement in `cli.py`.
- [ ] **Step 5:** `uv run pytest tests/unit/test_brain_config.py tests/unit/test_cli_config.py -q`
  passes; `uv run ruff check src/shefa/brain src/shefa/cli.py src/shefa/config/settings.py`.
- [ ] **Step 6:** Commit `brain: versioned config store with prompt seeds`.

---

### Task 2: Knowledge base store and seeding

**Files:**
- Create: `src/shefa/brain/knowledge.py`, `configs/knowledge/platform.yaml`
- Modify: `src/shefa/cli.py` (`shefa kb seed|list|add|deactivate`)
- Test: `tests/unit/test_brain_knowledge.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Entry: id: int; scope: str; topic: str; tags: tuple[str, ...];
    text_bn: str; text_en: str; active: bool; version: int`
  - `Entry.text(language: str) -> str` (the caller's language, else the other one)
  - `class KnowledgeStore(path)`: `add(scope, topic, *, text_bn, text_en, tags=(), author) -> int`;
    `update(entry_id, *, author, **fields) -> Entry` (version + 1; the previous row copied to
    `kb_history`); `deactivate(entry_id, *, author) -> None`;
    `entries(scopes: Iterable[str], *, active_only: bool = True) -> list[Entry]`;
    `stamp() -> float` (latest change time, for cache invalidation)
  - `default_knowledge_store() -> KnowledgeStore` (at `settings.storage.db_path`) and
    `set_default_knowledge_store(store: KnowledgeStore | None) -> None`
  - `seed(store, *, clinic_id: str, platform_file: Path) -> int`: adds, once per topic and scope,
    every `settings.facilities` topic the clinic wrote (scope = clinic id, or `default` when there
    is one clinic; tags = the Bangla and English topic names from `pipeline.facilities.TOPICS` when
    the key is there, else the key itself; all keys listed under `Settings.facilities` count) and
    every platform entry in `platform_file`; returns how many were added

`configs/knowledge/platform.yaml` entries (topic, text_bn, text_en), facts the repo supports only:
`what_shefa_is` (an automated phone receptionist for the clinic that answers questions about the
clinic and its doctors and books, moves and cancels appointments), `what_shefa_cannot_do` (no
medical advice, diagnosis or medicine; a person at the desk handles those and anything it cannot),
`call_notes` (the call's words are written down for the booking, as the greeting says),
`talk_to_person` (the caller can ask for a person at any time).

- [ ] **Step 1: Failing tests:** add/update keeps history and bumps version; `entries(["platform",
  "alo"])` never returns another clinic's entry; deactivated entries are hidden unless
  `active_only=False`; `seed` twice adds nothing the second time; a facilities topic the clinic did
  not write is not seeded; `Entry.text("bn")` falls back to English when Bangla is empty.
- [ ] **Step 2:** run → fail. **Step 3:** implement. **Step 4:** CLI test for `shefa kb add
  --scope platform --topic about --bn … --en …` and `shefa kb list`. **Step 5:** pass + ruff.
- [ ] **Step 6:** Commit `brain: knowledge base store, seeded from facilities and About SHEFA`.

---

### Task 3: Retrieval

**Files:**
- Create: `src/shefa/brain/embed.py`, `src/shefa/brain/retrieve.py`
- Modify: `src/shefa/cli.py` (`shefa kb fetch-embedder`: downloads `settings.brain.embedding_model`,
  default name `intfloat/multilingual-e5-small`, with `huggingface_hub.snapshot_download`)
- Test: `tests/unit/test_brain_retrieve.py`

**Interfaces:**
- Consumes: `Entry`, `KnowledgeStore.entries/stamp` (Task 2); `shefa.clinic.names.tokens`, `fold`.
- Produces:
  - `class Embedder` with `encode_queries(texts: list[str]) -> np.ndarray` and
    `encode_passages(texts: list[str]) -> np.ndarray` (L2-normalised rows; e5 prefixes `query: ` /
    `passage: `; mean pooling; CPU; `torch.inference_mode`)
  - `load_embedder(name: str) -> Embedder | None`: None when `name` is empty or the model is not
    already on disk (`local_files_only=True`); logs once; never downloads during a call
  - `@dataclass(frozen=True) class Hit: entry: Entry; score: float; how: str` (`words`,
    `meaning` or `both`)
  - `class Retriever(entries: list[Entry], embedder: Embedder | None = None)` with
    `search(query: str, k: int | None = None) -> list[Hit]`
  - `retriever_for(clinic_id: str) -> Retriever`: entries for `["platform", clinic_id or
    "default"]`, rebuilt when `stamp()` changes; one shared embedder

Algorithm (not determined by the signature): BM25 (k1 = 1.5, b = 0.75) over
`fold(token)` for the tokens of topic + tags + text_bn + text_en. Meaning score = cosine of
query and entry vectors. An entry qualifies when its BM25 score ≥ `kb_min_words_score` or its
cosine ≥ `kb_min_meaning_score`. Rank qualifying entries by reciprocal-rank fusion
(`1/(60 + rank_words) + 1/(60 + rank_meaning)`, a missing rank contributing 0); keep
`k or settings.brain.kb_max_hits`.

- [ ] **Step 1: Failing tests** (with a fake embedder returning fixed vectors):
  `পার্কিং আছে?` finds the parking entry by words; an English question finds a Bangla-only
  entry through the fake embedder (`how == "meaning"`); `ক্রিকেট খেলা দেখেছেন?` finds nothing;
  `Retriever([], None).search("কিছু")` is `[]`; with no embedder the results equal words-only
  ranking; at most 4 hits; `load_embedder("")` is None and `load_embedder("no/such-model")` is
  None without network access (monkeypatch `snapshot_download` to raise if called).
- [ ] **Step 2–5:** fail, implement, pass, ruff.
- [ ] **Step 6:** Commit `brain: knowledge retrieval by words and meaning`.

---

### Task 4: Call state

**Files:** Create `src/shefa/brain/state.py`; Test `tests/unit/test_brain_state.py`

**Interfaces:**
- Consumes: `pipeline.grounding.parse_date/parse_time/parse_period`,
  `pipeline.guided.wants_to_book`, `clinic.names.best_matches`, `default_clinic_store()`.
- Produces:
  - `GOALS = ("information", "booking", "change", "lookup", "complaint", "small_talk", "unknown")`
  - `MOODS = ("calm", "anxious", "upset", "angry", "confused", "rushed", "chatty", "quiet")`
  - `@dataclass class Cues: loudness_ratio: float | None = None; words_per_s: float | None = None;
    interrupted: bool = False` (filled by sub-project 3; text-only turns pass None)
  - `@dataclass class CallState: goal: str = "unknown"; mood: str = "calm"; language: str = "bn";
    booking: dict[str, str] (keys among doctor_id, doctor, date, time, period, name);
    repeats: int = 0; angry_turns: int = 0; boundaries: int = 0; last_offer: str = "";
    pending: dict[str, Any] | None = None; done: list[dict[str, Any]]; asked_list: bool = False;
    turn: int = 0`
  - `track(state: CallState, said: str, *, previous: str = "", cues: Cues | None = None,
    today: date) -> CallState` (returns the updated state; does not mutate its input)
  - `summary(state: CallState) -> str` (one short English line of what is known so far, e.g.
    `Booking so far: doctor Dr. Rahman, date 2026-11-29. Done: booked Dr. Rahman 2026-11-29 18:00.`)
  - `load(session) -> CallState`, `save(session, state) -> None` (JSON-safe dict in
    `session.metadata["brain"]`)

Rules the tests pin (implement as small word lists; Bangla and English):
- goal: booking words (`wants_to_book`) → `booking`; cancel/move words → `change`; "my
  appointment / আমার সিরিয়াল / কবে আমার" → `lookup`; complaint words (অভিযোগ, complain, রাগ করে
  বলছি) → `complaint`; a question about fee, time, address, doctor, facilities without booking
  words → `information`; greeting or chatter only → `small_talk`. A later turn moves the goal only
  when it names a new one (an information caller who says "বুক করে দিন" becomes `booking`).
- booking slots: doctor by `best_matches`, date by `parse_date`, time by `parse_time`, period by
  `parse_period`; earlier values kept unless the caller gives a new one.
- mood: anger words (ফালতু, বাজে, কী সার্ভিস, ridiculous, useless) or two `!` → `angry`; worry
  (ভয়, চিন্তা, টেনশন, worried, scared) → `anxious`; distress (কান্না, খুব কষ্ট, upset) → `upset`;
  the caller repeating a question (difflib ratio ≥ 0.8 with `previous`) → `confused` and
  `repeats + 1`; hurry words (তাড়াতাড়ি, জলদি, quick, hurry) → `rushed`; more than 40 words →
  `chatty`; two consecutive turns of 2 words or fewer → `quiet`; else `calm`.
  `cues.loudness_ratio ≥ 1.5` turns `calm` into `upset`. `angry_turns` counts consecutive angry
  turns.
- `asked_list`: সব ডাক্তার, কোন কোন, কী কী, list, all the.

- [ ] Steps: one test per rule above (parametrised where the rule has word lists), plus "a
  talkative caller giving doctor, day and name in one breath keeps all three" and "track does not
  mutate its input"; fail → implement → pass → ruff → commit `brain: call state tracking`.

---

### Task 5: Prompt composition

**Files:** Create `src/shefa/brain/prompt.py`; Test `tests/unit/test_brain_prompt.py`

**Interfaces:**
- Consumes: `CallState`, `summary` (Task 4); `Hit` (Task 3); config snapshot (Task 1);
  `shefa.clinic.brief.directory_brief(...)` (existing; the directory block `system_prompt` gets).
- Produces:
  - `MOOD_CUES: dict[str, str]`, exact text:
    - calm: `""`
    - anxious: `"The caller is worried: reassure them in a few words first; be clear and calm."`
    - upset: `"The caller is upset: acknowledge it in a few words before anything else; keep sentences short."`
    - angry: `"The caller is angry: apologise briefly for the trouble, do not argue, and get to what they need."`
    - confused: `"The caller is confused: use very simple words, one thing at a time, and offer two clear choices."`
    - rushed: `"The caller is in a hurry: answer at once in one short sentence."`
    - chatty: `"The caller is chatty: reply warmly in a few words, then bring them back to what they need."`
    - quiet: `"The caller says little: ask one simple question to help them."`
  - `GOAL_CUES["information"] = "The caller only wants information: answer it, and do not offer a booking unless they ask for one."`
    (other goals: `""`)
  - `compose(state: CallState, config: dict[str, Any], hits: list[Hit], directory: str,
    history: list[dict[str, str]], *, tool_note: str = "", correction: str = "",
    boundary_note: str = "") -> list[dict[str, str]]`

Message layout (gemma2 reads one leading system message best; `_speak_tool_result` explains why):
one `system` message = persona, conduct, tools prompt, then `Caller now:` mood cue + goal cue,
`Language: reply in Bangla|English`, `Known so far:` summary, `Facts you may use:` one line per
hit as `[kb:<id>] <entry.text(language)>` or `Facts you may use: none for this question.`,
the directory block, then `tool_note` and `correction` when given; then the last
`settings.brain.history_turns` user/assistant turns.

Budget: the whole prompt stays within `settings.brain.prompt_budget_tokens` (new `BrainConfig`
field, default 3000: vLLM serves `max_model_len` 4096 and a reply reserves 512), estimated as
`ceil(len(text) / 2)` per message (conservative for Bangla). Over budget, trim in this order until
it fits: history from the oldest down to the last 2 turns; the directory block to
`directory_brief(..., full=False)` limited to the doctors in `state.booking` or the hits; the hits
from 4 down to 2. Persona, conduct, tools and the cues are never trimmed.

- [ ] Steps: tests that the angry cue and the information cue appear for those states; a long
  call with a long directory stays under the budget and keeps persona, conduct and the last 2
  turns; hit ids and
  texts appear in the caller's language; "none for this question" with no hits; history is cut to
  6 turns; `correction` text appears last in the system message; the prompt seeds from the config
  snapshot (a published persona replaces the seed); fail → implement → pass → commit
  `brain: prompt composition with mood and goal cues`.

---

### Task 6: Tool protocol and argument validators

**Files:** Create `src/shefa/brain/tools.py`; Test `tests/unit/test_brain_tools.py`

**Interfaces:**
- Consumes: `tools.executor.execute_tool/preview_action/missing_arguments`; grounding parsers;
  `clinic.names.best_matches`; `pipeline.guided._symptom_department` (make it public as
  `symptom_department`, keeping the old name as an alias); `shefa.phone_words` (phone parsing).
- Produces:
  - `TOOL_NAMES = ("find_doctors", "free_times", "book", "lookup_booking", "cancel_booking",
    "reschedule_booking", "request_callback", "hand_over", "end_call")`
  - `CONFIRMED = frozenset({"book", "cancel_booking", "reschedule_booking"})`
  - `@dataclass(frozen=True) class ToolCall: name: str; args: dict[str, Any]`
  - `class ToolLineError(ValueError)`
  - `TOOL_PREFIX = "TOOL "`; `parse_tool_line(line: str) -> ToolCall` (raises `ToolLineError` for
    bad JSON, an unknown name or non-dict args)
  - `@dataclass(frozen=True) class Resolved: tool: str; executor: str | None; args: dict[str, Any]`
  - `@dataclass(frozen=True) class ToolProblem: message: str` (English, for the model: what was
    wrong and what to ask, e.g. `No doctor matches "Hasan". Doctors in Medicine: Dr. Hossain. Ask the caller which one.`)
  - `resolve(call: ToolCall, session: CallSession, state: CallState, *, today: date)
    -> Resolved | ToolProblem`

Protocol (the text of `configs/prompts/brain/tools.md`, matched exactly by the parser): when you
need to look something up or act, your reply is one line and nothing else:
`TOOL {"name": "<tool>", "args": {...}}`. Tools and args:
`find_doctors {"specialty"|"symptom"|"name": str}`; `free_times {"doctor": str, "day": str,
"period"?: str}`; `book {"doctor": str, "day": str, "time": str, "name": str}`;
`lookup_booking {}`; `cancel_booking {"which"?: str}`; `reschedule_booking {"which"?: str, "day":
str, "time": str}`; `request_callback {"reason": str}`; `hand_over {"reason": "emergency" |
"asked_for_person" | "rude" | "angry" | "cannot_help"}`; `end_call {}`. Days and times may be the
caller's own words ("কাল", "বিকেলে", "৫টা").

Mapping: `find_doctors` → `list_doctors` (specialty/symptom resolved to a department) or
`get_doctor_info` (name); `free_times` → `check_appointment_slots` with `doctor_id`, ISO `date`
and optional period filter; `book` → `book_appointment`; `lookup_booking` → `list_my_appointments`;
`cancel_booking` → `cancel_appointment`; `reschedule_booking` → `reschedule_appointment`;
`request_callback`, `end_call` → `executor=None` (the engine runs them); `hand_over` →
`transfer_to_human`. Unresolvable arguments → `ToolProblem`; an unidentified caller for an
identity tool → `ToolProblem("The caller is not identified: ask for their phone number.")`.

- [ ] Steps: tests for each mapping; `parse_tool_line` on good lines, extra spaces, a missing
  brace, an unknown tool; `free_times` with "কাল বিকেলে" resolves tomorrow's ISO date and the
  afternoon period; an unknown doctor gives a `ToolProblem` naming the department's doctors;
  `book` with no name gives `ToolProblem` asking for the patient's name; fail → implement → pass →
  commit `brain: tool line protocol and argument validators`.

---

### Task 7: Sentence checker and safe sentences

**Files:** Create `src/shefa/brain/check.py`, `src/shefa/brain/safe.py`;
Test `tests/unit/test_brain_check.py`

**Interfaces:**
- Consumes: `pipeline.replycheck.gives_medical_advice`, `fits_language`; `bangla.bn_number`.
- Produces:
  - `@dataclass class Grounds: texts: list[str]; succeeded: set[str]; caller: str` and
    `Grounds.add(text: str)`. The caller's words never ground a fact (a caller's guess "ফি ৫০০ তো?"
    must not become "হ্যাঁ, ৫০০ টাকা"); `caller` is used only for the `parrots` rule. `succeeded` holds tool names whose result had no error this call
    (`book`, `cancel_booking`, `reschedule_booking`, `request_callback`, `hand_over`).
  - `@dataclass(frozen=True) class Verdict: ok: bool; kind: str = ""; reason: str = ""`,
    kinds `fact`, `unsupported`, `claim`, `medical`, `privacy`, `push`, `language`
  - `numbers_in(text: str) -> set[str]`: ASCII and Bangla digits normalised to ASCII without
    leading zeros, plus Bangla number words read through a table built from `bn_number(n)` for
    n in 0–1000 and every hundred to 100000 (longest match first), matched after stripping the
    suffixes টা, টায়, টার, টি, য়, এ, র (so "ছয়টায়" reads 6). Number words for 1 and 2 are ignored
    ("এক মিনিট", "একটু", "দুই একটা"); digits are always read. A clock time in a ground text
    (`18:00`) also grounds its 12-hour hour (6), so "সন্ধ্যা ছয়টায়" passes and "সাতটায়" fails.
  - `check_sentence(sentence: str, grounds: Grounds, *, goal: str, language: str) -> Verdict`
  - `safe.sentence(kind: str, language: str) -> str`

Rules: `fact`: a number in the sentence not in `numbers_in` of any ground text or the caller's
words; or a doctor title (`ডাক্তার|ডাঃ|ডা\.|Dr\.?|Doctor`) followed by a name word whose `fold`
is in no ground text. `unsupported`: `replycheck.unsupported_claim(sentence)` (the "হ্যাঁ, পার্কিং
আছে" made-up yes) or `replycheck.parrots(sentence, grounds.caller)`. `claim`: a success claim (booked / বুক হয়েছে / সিরিয়াল দেওয়া হয়েছে /
cancelled / বাতিল করা হয়েছে / moved / পরিবর্তন করা হয়েছে / call you back / ফোন করবে /
transferred / সংযোগ দিচ্ছি) without the matching tool in `succeeded`. `medical`:
`gives_medical_advice`. `privacy`: a run of 7+ digits not in grounds (a phone number). `push`:
`goal == "information"` and a booking offer (বুক করবেন, সিরিয়াল নেবেন, অ্যাপয়েন্টমেন্ট নেবেন,
book an appointment, shall I book, would you like to book). `language`: `not fits_language`.
Reasons are English and name the offending part (`the number 700 is not in the facts`).

Safe sentences (exact copy):
- `fact`: `pipeline.clinic_questions.unsure(language)`
- `medical`: `settings.escalation.medical_refusal[language]`
- `claim`: bn `দুঃখিত, এটা এখনো করা হয়নি। আপনি চাইলে আমি এখনই করে দিতে পারি।` /
  en `Sorry, that has not been done yet. I can do it for you now if you like.`
- `privacy`: bn `দুঃখিত, অন্য কারো তথ্য আমি জানাতে পারি না।` / en `Sorry, I can't share anyone else's details.`
- `unsupported`: same as `fact`
- `push` and `language` are not spoken over: the sentence is dropped and the reply continues
  (Task 8); when nothing at all passes after the regeneration, bn `জি, বলুন, আর কীভাবে সাহায্য
  করতে পারি?` / en `Yes, how else can I help you?`

- [ ] Steps: one test per kind (pass and fail), including: `ফি সাতশো টাকা` fails with grounds
  `fee 500` and passes with `fee 700`; `৫০০` and `500` and `পাঁচশো` all match `500`; a doctor named
  in the directory passes and an invented `ডাক্তার করিম` fails; `আপনার সিরিয়াল বুক হয়েছে` fails
  without `book` in `succeeded`; an information caller offered a booking fails as `push`, a
  booking caller does not; `হ্যাঁ, আমাদের পার্কিং আছে।` with no parking fact fails as
  `unsupported`; caller asks `ফি ৫০০ তো?`, reply `হ্যাঁ, ৫০০ টাকা।` with no fee fact fails as
  `fact`; grounds `18:00` passes `সন্ধ্যা ছয়টায়` and fails `সাতটায়`; `এক মিনিট দেখছি` and
  `একটু অপেক্ষা করুন` pass with no grounds; fail → implement → pass → commit
  `brain: sentence checker and safe sentences`.

---

### Task 8: The turn loop: generate, check, regenerate

**Files:** Create `src/shefa/brain/engine.py`; Test `tests/unit/test_brain_engine.py`

**Interfaces:**
- Consumes: Tasks 1–7; `llm.generate_stream(messages) -> AsyncIterator[str]` (existing client,
  already filtered for reasoning); `split_complete_sentences` and `tidy` from the pipeline.
- Produces:
  - `Speak = Callable[[str], Awaitable[None]]`
  - `class Brain` with `async turn(session: CallSession, said: str, llm: Any, speak: Speak, *,
    today: date | None = None, cues: Cues | None = None) -> str` (returns what was spoken, joined)
  - `MAX_SENTENCES = 2`
  - a per-turn trace appended to `session.metadata["brain_trace"]`: `{"turn", "mood", "goal",
    "hits": [ids], "tool": name|None, "verdicts": [kind…], "regenerated": bool, "safe": kind|None,
    "ms": int}`

Flow of `turn` (this task: no tools yet; Task 9 adds actions):
1. `state = track(load(session), said, previous=<last user turn>, cues, today)`.
2. `hits = retriever_for(clinic).search(said)`; grounds = hit texts + directory block + caller's
   words + earlier tool results this call (kept in `session.metadata["brain_grounds"]`).
3. `messages = compose(...)`; stream. Hold the first characters until they cannot start
   `TOOL_PREFIX`; a reply that starts with it is a tool line (Task 9), never spoken. Text before a
   `TOOL` line anywhere in the reply is dropped and the line is treated as a tool call; a broken
   line is a `ToolLineError` → one regeneration with correction
   `Your tool line was not valid JSON. Write it again exactly as the protocol says.`
4. Each complete sentence is checked; a passing sentence is spoken at once (`speak`). Stop after
   `MAX_SENTENCES` spoken sentences unless `state.asked_list`.
5. A `push` or `language` sentence is dropped and the stream continues. Any other failing
   sentence stops the stream. If nothing was spoken yet: regenerate once with
   correction `Your last reply was not used because <reason>. Say it again without that.`; a
   second failure speaks `safe.sentence(kind, language)`. If something was spoken already, stop
   there (no regeneration).
6. Empty output → one regeneration, then `settings.escalation.repeat_prompt`.
7. `save(session, state)`, trace, return.

- [ ] **Step 1: Failing tests** with a scripted fake LLM (a list of replies, one per call) and a
  recording `speak`: a grounded two-sentence reply is spoken sentence by sentence; a third
  sentence is not spoken; with `asked_list` it is; an invented fee triggers one regeneration and
  the corrected reply is spoken; two invented fees speak the `fact` safe sentence; a sentence that
  fails after one was spoken stops the reply with no regeneration; `TOOL` text or JSON is never
  passed to `speak` (including `"জি। TOOL {…}"`); a question with no knowledge-base match and an
  invented answer ends in `unsure()`; the trace records hits, verdicts and `regenerated`.
- [ ] **Step 2–5:** fail, implement, pass, ruff.
- [ ] **Step 6:** Commit `brain: turn loop with per-sentence checking`.

---

### Task 8b: Live gate on the real model

**Files:** Create `scripts/brain_probe.py`, `docs/research/2026-11-2x-brain-probe.md`

No downtime: today's vLLM (`shefa-llm`, gemma2-9b AWQ) is up. The script runs 20 typed turns
through `Brain.turn` on a fresh `CallSession` each (with stores pointed at a temporary folder and
seeded): 6 knowledge questions (fee, parking, address, a fact not in the base, About SHEFA, a
doctor's days), 6 turns that need a tool (find a doctor by symptom, free times tomorrow evening,
"my appointment", book with all details, cancel, a call-back request), 4 mood turns (angry,
anxious, rushed, rude), 4 English. For each it records: did a tool turn produce a valid `TOOL`
line (parsed with `parse_tool_line`; Task 9 is not built yet, so the line is only parsed), checker
verdicts and regenerations, estimated prompt tokens, time to the first spoken sentence, and the
spoken text.

Gate: valid tool lines on at least 5 of 6 tool turns; regeneration on at most 4 of 20 turns; no
prompt over the budget; first spoken sentence p95 at most 1100 ms on non-tool turns (leaving the
voice's ~85 ms inside 1.2 s). Write the numbers and every reply to the doc and commit. If the gate
fails, stop before Task 9 and rule on the fix (protocol wording, few-shot examples in `tools.md`,
or a JSON-only router call for tool turns) in the ledger, then re-run the gate.

---

### Task 9: Actions and the read-back

**Files:** Modify `src/shefa/brain/engine.py`; Test `tests/unit/test_brain_actions.py`

**Interfaces:**
- Consumes: `resolve` (Task 6); `execute_tool`, `preview_action`; `pipeline.confirm.yes_no,
  leading_yes, read_back, declined_text, reask_text`; `pipeline.guided.changes_request`;
  `pipeline.actions.confirmation_text/error_text/need_text` (existing renderers);
  `call_log.default_calls_store().add_callback`;
  `pipeline.language_detector.escalation_prompt` (emergency text).
- Produces: `Brain.turn` handles `ToolCall`s and `state.pending`; `state.done` gets
  `{"tool", "result"}` for each success.

Behaviour:
- Information tools (`find_doctors`, `free_times`, `lookup_booking`): execute; add the result to
  grounds; a second model call with `tool_note = "Result of <tool>: <compact result>"` speaks it
  (checked as in Task 8). A `ToolProblem` or tool error goes to the second call as
  `tool_note = "Tool problem: <message>"`; nothing claims success.
- `CONFIRMED` tools: `preview_action`; on success set `state.pending = {tool, executor, args,
  asked: False}` and speak `read_back(...)` (code text, no model call). On a preview error speak
  `error_text(...)`.
- At the start of a turn with `state.pending`: a yes (`yes_no` True, or `leading_yes` and not
  `changes_request`) executes it and speaks `confirmation_text(...)`, adds the tool to
  `grounds.succeeded`; a no speaks `declined_text`; a reply of 3 words or fewer that is neither,
  when not yet asked, speaks `reask_text` once; anything else voids the pending action and the
  turn continues through the model as a new request.
- `request_callback`: `add_callback(call_sid, phone, language, reason)`; success → grounds; the
  model speaks the result.
- `hand_over`: `execute_tool("transfer_to_human", …)`; `session.state = "escalated"`;
  `session.metadata["handover_reason"] = reason`; speaks the emergency escalation text when the
  reason is `emergency`, else `guided.handover_text(language)`.
- `end_call`: speaks the closing (Task 10) and sets `session.state = "completed"`.
- `session.metadata["actions"]` gets the executor tool names that ran, as the guided engine does,
  so the bench's checks and the call log work unchanged.

- [ ] Steps: tests for each bullet with a fake executor, including Review Focus 1
  (`"হ্যাঁ, তবে বিকেলে হলে ভালো"` after a read-back books nothing and voids the pending action);
  booking happens only on the turn after the read-back; a tool error is never followed by a success
  claim; `hand_over(emergency)` speaks the emergency text and ends the turn escalated; fail →
  implement → pass → commit `brain: actions with read-back before every booking change`.

---

### Task 10: Greeting and closing

**Files:** Create `src/shefa/brain/greeting.py`; Modify `configs/default.yaml` (add
`brain.disclosure`); Test `tests/unit/test_brain_greeting.py`

**Interfaces:**
- Produces:
  - `async greeting(llm: Any, config: dict[str, Any], *, clinic_name: str, language: str,
    now: datetime, caller_name: str | None) -> str`: one generated welcome sentence from
    `prompt.greeting` (checked: no numbers, no doctor names, fits the language), then the fixed
    disclosure `settings.brain.disclosure[language]`; on timeout
    (`settings.brain.greeting_timeout_s`), error or a failed check, the fixed
    `settings.languages.default_greeting[language]`
  - `closing(state: CallState, language: str) -> str`: when `state.done` holds a booking or a move,
    one sentence summarising it (bn `আপনার সিরিয়াল {doctor}-এর কাছে {spoken_date} {spoken_time}।
    ভালো থাকবেন।`, en `Your appointment is with {doctor} on {date} at {time}. Take care.`, using
    `shefa.spoken`); otherwise bn `ফোন করার জন্য ধন্যবাদ, ভালো থাকবেন।` / en `Thank you for calling. Take care.`

`brain.disclosure` default: the existing `languages.default_greeting` text without its first
(welcome) sentence, per language, copied verbatim from `configs/default.yaml`.

- [ ] Steps: tests that the greeting ends with the disclosure, names the clinic (from the fake
  model) and falls back on timeout and on a reply with a number; closing summaries for a booking,
  a move and nothing done; fail → implement → pass → commit
  `brain: generated greeting with fixed disclosure, closing summary`.

---

### Task 11: Wire the engine into the pipeline and the lab

**Files:**
- Modify: `src/shefa/pipeline/voice_pipeline.py` (`_generate_reply`, greeting in
  `process_audio_stream` and `handle_text`), `src/shefa/lab/scoring.py`, `src/shefa/lab/bakeoff.py`,
  `src/shefa/cli.py` (`--engine agent|guided` on `lab score` and `lab bakeoff`)
- Test: `tests/unit/test_pipeline_brain.py`, additions to `tests/unit/test_lab_scoring.py`

**Interfaces:**
- Consumes: `Brain`, `call_config`, `greeting`.
- Produces: `VoicePipeline._engine(session) -> str` (`call_config(session)["engine"]`);
  scorecard `meta["engine"]`.

Behaviour: with engine `agent`, `_generate_reply` calls `Brain.turn(session, said, llm, speak)`
where `speak` emits through `self._emit(tts, sentence, language, put_playback)`. The emergency and
other-language checks before it stay as they are. On `asyncio.TimeoutError`, `openai.APIError` (the
client's errors: `APIConnectionError`, `APITimeoutError`, `InternalServerError` and the rest),
`ConnectionError` or `MalformedLLMOutputError` from the brain before anything was spoken, the turn
is answered by the guided path (`self._reply`) and `session.metadata["brain_fallbacks"]` is
incremented; if something was already spoken the turn ends with what was said. The next turn tries
the brain again. The greeting uses `greeting()` when the engine is `agent`. `--engine` sets
`settings.pipeline.engine` for the run (restored after) and is recorded in the scorecard meta.
The lab never reads production's prompts or knowledge base: like the audit store, `run_scorecard`
points `set_default_config_store` and `set_default_knowledge_store` at files in its work folder,
seeds the knowledge base there with `seed(...)`, and puts the defaults back afterwards. With no
live rows there, `--engine` is what the calls use.

- [ ] Steps: tests: engine `guided` behaves exactly as before (an existing handle_text test
  re-run with the setting explicit); engine `agent` routes a typed turn through a fake brain; a
  brain that raises `openai.APIConnectionError` before speaking gets the guided reply, a brain that
  raised after speaking does not (Review Focus 5); `lab score --engine agent` records
  `meta["engine"] == "agent"`; a live `engine = guided` row in the production config store does
  not change a lab run with `--engine agent`; full suite green; commit
  `pipeline: agent engine behind pipeline.engine, guided fallback`.

---

### Task 12: Bench the brain against the guided engine

**Files:**
- Modify: `configs/lab/bench/*.yaml`: every `goal: emergency` scenario gets `turns:` with one
  first line that states the emergency in the persona's words (e.g. goals-emergency-chest-pain-father:
  `আমার বাবার হঠাৎ বুকে প্রচণ্ড ব্যথা, ঘামছেন, কী করব?`), so turn 1 is a fair test
- Create: `docs/research/2026-11-2x-brain-vs-guided.md`

Run (no downtime: agent on vLLM, caller and judge on a CPU-only Ollama on :11435 as in the
bake-off): `PYTHONUNBUFFERED=1 uv run shefa lab score --engine guided --side-base-url
http://127.0.0.1:11435/v1 --caller-model hf.co/unsloth/gemma-3-4b-it-GGUF:Q4_K_M --judge-model
hf.co/unsloth/gemma-3-4b-it-GGUF:Q4_K_M --out data/bench`, then the same with `--engine agent`,
then `shefa lab compare` on the two scorecards. Run each engine twice (the bake-off saw two-case
swings between runs of the same setup) and average.

The bar, decided before the runs: the agent engine has no hard-check failure that the classification
finds to be an engine fault; its judged mean averaged over the two runs is above the guided
engine's for every caller type by at least 0.2 (one caller type has about 10 calls); and its full
pass is not lower than guided's by more than 2 calls in either run.

- [ ] Steps: edit the scenarios and run the lab's scenario-file test; run both scorecards; write
  the results (full/task/hard/judged per caller type, every hard-check failure of the agent engine
  read and classified as engine fault or check fault, latency per turn) against the spec's success
  bar (zero hard-check failures; judged score above guided on every caller type); commit
  `bench: brain vs guided`. Do not change `pipeline.engine`'s default; report to the founder with a
  recommendation.

---

## Self-review notes

- Gate before actions: Task 8b checks gemma2 holds the protocol before Tasks 9–11 build on it.
- Spec 5.1 steps 1–7 → Tasks 4, 3, 5, 8, 7/8, 8 (speak is section 6's streaming, already sentence by
  sentence). 5.2 → 6, 9. 5.3 → 2, 3. 5.4 → 4, 5, 1 (conduct text). 5.5 → 4 (slots kept), 9
  (read-back), conduct (no two-strike handover; `hand_over` only on request, conduct or checker).
  5.6 → 10. 5.7 → 1. Section 8: model failure → 11; checker twice → 8; retrieval empty → 3, 8; tool
  error → 9. Section 9 → unit tests per module, bench in 12.
- Bake-off targets: brevity → Task 8 sentence cap; info callers pushed → Task 7 `push` + Task 5 cue;
  lookups/reschedules → Task 6/9 tools; emergencies said later → conduct `hand_over` + Task 12
  scenario fix.
