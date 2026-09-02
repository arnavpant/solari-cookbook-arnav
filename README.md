# cubicle

**A computer-use benchmark for software that has no API.**

GnuCash on a Solari cloud desktop. Ten bookkeeping jobs, seven of them scored. The agent
gets pixels, a mouse and a keyboard — nothing else. Every score is a SQL assertion
against the database the application itself wrote.

---

## Why another benchmark

Every widely-cited computer-use benchmark — WebVoyager, Online-Mind2Web, Westworld —
tests agents on **modern websites**. Two things follow from that.

**The measurement is contaminated.** On a web page an agent can read the DOM. Even when
a harness nominally feeds it screenshots, nothing in the result distinguishes an agent
that *saw* a button from one that *parsed* it. A native GTK application has no DOM, no
accessibility bus, and nothing to parse. It is the only clean way to ask the question.

**The market nobody measures.** The stated value of computer use is in legacy systems,
dashboards and graphical interfaces where automation *cannot* rely on clean APIs. There
is no public benchmark for that. Meanwhile the leading published score on WebVoyager is
99% — saturated, and unable to discriminate between good and great.

cubicle is the missing half.

## Why grade against a database

Because three times during development, **the screen was right and the data was wrong**:

| What the screen showed | What the database held |
|---|---|
| GnuCash open, twelve transactions intact | GnuCash had *refused to open the book* and never touched the file |
| `03/14/20` — indistinguishable from a 2-digit year beside `04/18/26` | `2020-03-14`. Six years wrong. GnuCash silently truncates a 4-digit year |
| A split reading `Expenses:Utilities:Water` | `Imbalance-USD` — `Return` confirmed the cell but never committed the transaction |

Every one of those passes a screenshot. Every one fails a SQL assertion, instantly, with
the exact reason. That is the entire argument for how this benchmark scores.

**No LLM judge. No screenshot diffing. No human review.** Grading opens the GnuCash
SQLite book with Python's `sqlite3` and runs assertions. Money is compared as the exact
integer pair GnuCash stores (`4250/100`), never as a float. A score is a fact anyone can
re-derive from the committed artifact.

Every task additionally asserts **global book integrity** — for every transaction, the
splits must sum to zero. An agent that corrupts the book fails even when it satisfied the
task's own condition.

### A provider outage is not an agent failure

This one nearly produced a wrong published number. The harness originally treated an
HTTP 429 like any other bad reply — a wasted step. Run a benchmark that way and **a model
scores worse because its vendor throttled you**, which makes the leaderboard a
measurement of billing tiers rather than capability.

Provider failures now abandon the task with a distinct `provider_error` outcome. It
consumes no step budget and is excluded from the denominator: reported as *unscored*,
never as a zero. If a run says 2/5, five tasks actually ran.

## Results

The oracle is a scripted reference solution. It exists to prove every task is solvable,
which pre-empts the standard objection to any hard benchmark, and it is the validation
harness for the graders: if the oracle does the job correctly and a grader still fails
it, the grader is wrong.

| Agent | Score | Runs |
|---|---|---|
| Scripted oracle | **7 / 7** | reference — proves the suite is solvable |
| DeepSeek V4 Flash Vision | **0 / 7** | 2 |
| MiniMax-M3 | **0 / 7** | 2 |
| Gemini flash-lite | **unscored** | free tier is 20 requests/day — see below |
| **Pinetree-CUA** | **untested** | — |

Two models scored, each twice, plus five models measured on localization. Every model
here is a general vision model with no grounding post-training — **this is not a result
about frontier computer-use agents**, and nothing here should be read as one. The
methodology is the contribution; the numbers illustrate it.

### The step budget is not what fails an agent

A zero is only interesting if the agent had room to succeed. The oracle sets the floor:
it solves each task with perfect foreknowledge — exact coordinates, no looking, no
mistakes — so its action count is the fewest moves the task can possibly take. **Every
cap is at least three times that floor**, giving an agent two moves to look, backtrack or
recover for every one a perfect script needs.

| | t01 | t02 | t03 | t04 | t05 | t06 | t07 |
|---|---|---|---|---|---|---|---|
| oracle actions (floor) | 5 | 12 | 7 | 21 | 6 | 4 | 9 |
| step cap | 15 | 36 | 21 | 63 | 30 | 30 | 30 |
| headroom | 3.0x | 3.0x | 3.0x | 3.0x | 5.0x | 7.5x | 3.3x |

`tests/test_step_budget.py` enforces the ratio, so an oracle that grows without its cap
growing fails the suite rather than quietly making the benchmark harder.

This mattered. t02 originally allowed 15 steps against an oracle needing 12 — three
spare moves for an entire register entry — which made that task effectively unpassable
for reasons that had nothing to do with vision.

Re-running DeepSeek against the raised caps changed nothing: **still 0/7**, and it
consumed every step of every task — 36/36 on t02, 63/63 on t04. The zero is not a budget
artifact.

## The interesting part: they can read, they cannot point

A 0/7 is not a finding until you know *why*. So each model was shown a real cubicle
screenshot and asked where things are. Ground truth is exact and was read off that
screenshot, never guessed — the GnuCash account rows sit at y=217, 241 and 264, and a
row is 24px tall.

**Every model that answered named every account correctly.** Reading the screen is not
the problem.

Pointing at it is. `cubicle/localization.py` fits `y_predicted = scale * y_true + offset`
over the positions each model claims:

| model | Assets | Expenses | Income | scale | error | R² |
|---|---|---|---|---|---|---|
| **truth** | 217 | 241 | 264 | 1.000 | — | — |
| gemma-4-26b-a4b | 303 | 336 | 369 | 1.404 | **4.0 rows** | 1.000 |
| gemma-4-31b | 304 | 335 | 366 | 1.319 | **3.9 rows** | 1.000 |
| Gemini flash-lite | 304 | 334 | 365 | 1.298 | **3.9 rows** | 1.000 |
| nemotron-3-nano-omni | 300 | 330 | 360 | 1.276 | **3.7 rows** | 1.000 |
| DeepSeek V4 Flash Vision | 230 | 256 | 282 | 1.106 | 0.6 rows | 1.000 |
| MiniMax-M3 | 222 | 245 | 269 | ~1.0 | 0.2 rows | 0.999 |

Four models from four different labs place a row that is at **y=217** at **y≈300**. R² is
1.000 in every case: the error is not noise and not a constant offset but a **vertical
scale factor**, so it grows the further down the screen you look.

**It is not universal, and that matters more than the failures.** MiniMax-M3 has no
systematic stretch. A benchmark on which every model scores identically measures
nothing; this one separates them.

### One run is not a measurement

MiniMax-M3, ten runs, `temperature=0`:

```
scale  0.766  0.872  0.872  0.893  0.893  0.936  1.000  1.043  1.106  1.149
error  0.08 to 2.08 row heights
```

A single run would have supported either "points perfectly" or "two rows out". Both
would have been wrong. `--repeat N` reports the spread beside the mean for exactly this
reason. Meanwhile nemotron returned **byte-identical** coordinates on every run — so
"not deterministic at temperature 0" is itself a per-model property worth reporting.

## Knowing where a row is, and aiming at it, are separate failures

MiniMax-M3 describes the tree accurately and then, driving the same screen through the
benchmark, clicks at a mean **y=298**. Those two numbers came from two different prompts,
so the comparison was confounded — a better description prompt could explain all of it.

`scripts/describe_vs_act.py` is the control. Same model, same screenshot, same session,
alternating calls. The only thing that varies is what the model is asked to produce: a
number, or a `{"kind":"click",...}` action under the committed benchmark system prompt.
One target row, true y = **241**:

| condition | n | mean y | sd | range | error |
|---|---|---|---|---|---|
| **DESCRIBE** — asked for a coordinate | 13 | 267.0 | 10.7 | 239–280 | 1.0 rows |
| **ACT** — asked for a click | 11 | 299.1 | 11.2 | 291–332 | **2.4 rows** |

**The distributions do not overlap.** The highest describe answer is 280; the lowest act
answer is 291. Welch t = 7.2, gap +32px (+1.3 rows).

Asked where the row is, the model is about one row out. Asked to click it — same pixels,
seconds apart — the same model is 2.4 rows out, and consistently lower. The information
is present and does not survive the transition into an action.

A benchmark that only scored the task would have recorded 0/7 and attributed all of it
to vision.

### The second deficit: no feedback loop

`scripts/analyze_trace.py` on the DeepSeek run:

```
t01: 15 steps, 14 actions, 1 unparseable, 0 provider errors, screen moved 2x
     kinds: clickx14
     STUCK: 12/14 clicks in the y=330-339 band; the screen moved only 2 time(s)
```

That pattern is the run, not one bad task. **Five of seven tasks** end with the agent
locked into a ten-pixel band, clicking at a screen that mostly does not change. Given 63
steps on t04 instead of 30, it spent them the same way — this is the deficit a bigger
budget makes *worse*, not better.

MiniMax fails differently: it stops early and declares success, calling `done` on all
seven tasks after as few as one step. Neither model ever concluded that what it was
doing was not working.

### Two things that did not survive scrutiny

**Out-of-bounds clicks did not reproduce.** An earlier run showed 17 of 25 clicks on
`t05` landing outside the 720px screen, the furthest at y=801. The next run produced **0
out of 198 pointer actions**. One occurrence across two runs is an anecdote, not a
property, and it is no longer listed as a deficit. The harness still applies
out-of-bounds actions rather than correcting them, and still records them as
`off_screen`; it measures the agent, it does not help it.

**MiniMax's first 0/7 was not trustworthy.** 25 of its 50 steps were discarded as
malformed JSON — all complete objects, not truncation, and 20 of 25 corrupted the `y`
coordinate specifically (`{"kind":"double_click","x":164,267}` — the key simply
dropped). The design doc had always specified retry-once on a malformed reply; the
harness never did. Fixed, and re-run: **still 0/7**, with the mean click y unchanged at
298. The result survives the confound, which is the only reason it is quoted here.

Reproduce any of this with:

```bash
python scripts/localization_probe.py --repeat 4      # the table above
python scripts/describe_vs_act.py --repeat 8         # the control
```

Caveats that belong next to the numbers: three rows on one screenshot per model; the
control is one model and one target row; and describe-mode is itself prompt-sensitive
(asking for one row gives 267, asking for a list gives 245).

### Why Gemini is unscored, and what free tiers cost you

Gemini's free tier allows **20 requests per day, per model**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20`), and a full run needs ~150.
A single task is 15 to 63 steps, so one task can exhaust the day outright; the first
attempt lost 11 of 15 steps to HTTP 429. That is a quota limit, not a capability
result, so it is reported as unscored rather than as a low score.

This is why a provider error is a distinct outcome rather than a failed step. Running
the suite on free tiers, a run of 54 steps exhausted OpenRouter's
`free-models-per-day` allowance outright and four of five models then returned 429 for
the rest of the day. Scored naively, that afternoon would have published five zeros
that measured nothing but a billing tier.

No model number goes in this table until it has been measured. Whatever comes out is what
gets published, including a zero.

The top row is a standing invitation. Adding an agent takes one method.

## Add your agent

That is the whole interface.

```python
class Agent(Protocol):
    name: str
    def reset(self) -> None: ...
    def act(self, obs: Observation) -> Action: ...
```

`Observation` carries `screenshot_png`, `width`, `height`, `step`, `max_steps` and
`task_prompt`. `Action` is one of `click`, `double_click`, `type`, `key`, `scroll`,
`drag`, `done`.

**Or write no code at all.** Most models worth testing — OpenRouter, Groq, GitHub
Models, NVIDIA NIM, Mistral, Together — and Ollama on your own machine all speak the
same OpenAI-compatible API, so three environment variables are enough:

```bash
CUBICLE_VISION_BASE_URL=https://openrouter.ai/api/v1
CUBICLE_VISION_MODEL=qwen/qwen2.5-vl-72b-instruct:free
CUBICLE_VISION_API_KEY=sk-or-...

python scripts/check_vision.py                    # one call: does it work?
python scripts/run.py --agent vision --tasks all
```

A local Ollama endpoint needs no key at all. [`docs/free-models.md`](docs/free-models.md)
lists the free options and how to get one.

Every model receives a **byte-identical, committed system prompt**
(`cubicle/agents/system_prompt.txt`). Per-model prompt tuning would measure prompt
engineering rather than agent capability, and you should be able to see exactly what your
agent will be given.

## What the agent deliberately cannot do

The Solari desktop exposes a clipboard, a shell, a filesystem and a process list. **None
of them are reachable from an `Agent`.** An agent that can read the clipboard or run
`sqlite3` is routing around the vision requirement, and the benchmark would quietly stop
measuring what it claims to.

The harness uses those APIs. The agent gets pixels, mouse and keyboard.

Two related decisions, both about fairness rather than difficulty:

- **The window is maximized before the agent sees it.** GnuCash opens ~803px wide on a
  1280×720 screen, which pushes the register's Withdrawal and Balance columns off-screen.
  An agent that cannot see the amount column is being tested on the wrong thing.
- **Startup dialogs are dismissed by the harness.** Tip Of The Day appears on every
  launch. Steps spent closing chrome the harness put there are noise, not signal.

## The tasks

Ten tasks in three tiers, each with its own seed book and its own grader. The seven
scored tasks also have a scripted oracle recorded from real screenshots.

| | Task | What it tests |
|---|---|---|
| **easy** | `t01` create an account | a single dialog |
| | `t02` record a $42.50 expense | register entry, dates, transfer accounts |
| | `t03` rename an account | that it was *renamed*, not deleted and recreated |
| **medium** | `t04` split one bill across two accounts | the split editor — one transaction, three splits |
| | `t05` correct an existing amount | editing in place, not adding a second transaction |
| | `t06` clear only March | discrimination — the seed holds six non-March transactions as traps |
| | `t07` re-parent an account | tree navigation in a three-row viewport |
| **hard** | `t08` enter six transactions in order | drift — doing an easy thing six times without losing the thread |
| *(unscored)* | `t09` reconcile against a statement | noticing an *absence* — one statement line has no matching transaction |
| | `t10` month-end close | two chained edits, and not sweeping in the transaction next to them |

**The hard tier is not scored yet, deliberately.** Its seeds, prompts and graders are
finished and proven offline against 18 synthetic mutations, but no oracle has been
recorded for it — and this suite does not guess coordinates. Until a machine has been
shown completing a task, that task is not proven solvable, and an unproven task has no
business in a published denominator. `--tasks all` runs the seven scored tasks; t08-t10
must be named explicitly, and the oracle agent refuses them outright.

The near-miss cases are the point. Each grader rejects the specific plausible wrong
answer: entering the transaction twice, splitting one bill into two, leaving the wrong
$250 and adding a second $520, clearing the whole register instead of just March.

## Reproduce it

Reproduces on Solari's **$20 Starter plan** — a full run is about two desktop-hours on a
1 vCPU / 2 GB machine.

```bash
pip install -e ".[dev]"
cp .env.example .env          # add SOLARI_API_KEY

python scripts/setup_desktop.py          # installs GnuCash; prints CUBICLE_SESSION_ID
python scripts/run.py --agent oracle --tasks all
python -m cubicle.report                 # -> report.html
```

`pytest` runs 185 tests with no network and no credit: seeds, graders, the harness and
the action parser are all exercised against an in-memory fake desktop.

**You do not have to take the numbers on trust.** Every run's scores and traces are
committed under [`results/`](results/) — one `actions.jsonl` per task, holding each step's
action, its coordinates, and whether the screen changed since the previous one. Every
claim above is re-derivable from those files without a Solari account:

```bash
python scripts/analyze_trace.py results/20260901-165209-deepseek
```

The per-step screenshots are not committed — they are large, and re-running regenerates
them. What is committed is what the assertions are made from.

## Gotchas

Nineteen things that cost an afternoon if you meet them cold, with evidence for each and
an honest split between *we hit this* and *the docs say this*, are in
[`docs/research/05-gotchas.md`](docs/research/05-gotchas.md). The worst:

1. **Sending an API key as a `?key=` URL parameter leaks it into your logs.** httpx puts
   the full URL into `HTTPStatusError`, so the first failed call writes your key into
   whatever you log — for us, the very trace files this README invites you to publish.
   Use a header.
2. **GnuCash cannot open *any* SQLite book without `libdbd-sqlite3`.** It reports
   "No suitable backend was found", which reads exactly like a corrupt file and is not.
3. **`pkg.install` does not run `apt-get update`.** A fresh desktop has *empty* package
   lists, so the first install of anything fails — and it returns `exitCode=100` **without
   raising**.
4. **Gemini's free tier is 20 requests per *day*, per model** — not per minute. No
   throttle can fix it, and the guidance talks in RPM, so you tune the wrong dial.
5. **An empty CA store breaks only `connect()`.** Creating a desktop succeeds and every
   HTTP call works, because `httpx` bundles certifi; only the WebSocket dies. Point
   `SSL_CERT_FILE` at `certifi.where()`.
6. **`process.list()` returns every process with `name=''`.** You cannot find a process
   by name through the SDK. Use `pgrep`.
7. **`pkill -f <name>` kills your own shell**, because `-f` matches the full command line
   and your command line mentions the thing you are killing. Use `pkill -x`.

## How it is put together

```
cubicle/
  types.py       Observation, Action, Verdict, TaskResult, Task
  agent.py       the Agent protocol - the entire pluggable surface
  harness.py     the run loop: step caps, tracing, failure classification
  desktop.py     Solari lifecycle, per-task reset, action application
  grading.py     sqlite3 helpers and the global integrity check
  report.py      results.json -> a self-contained report.html
  tasks/         one module per task: prompt, seed, grader, oracle
  agents/        oracle, Gemini, DeepSeek, and one shared system prompt
```

Per-task isolation is done in software — kill GnuCash, wipe `~/.config/gnucash`, rewrite
the seed. Solari's `revert()` is documented but returns `Not revertable` on desktops, and
`create(fromSnapshot=...)` does not exist in the Python SDK; both were verified rather
than assumed. Wiping the config directories matters as much as replacing the book, or
window geometry and recent-file state leak between tasks.

Design doc: [`docs/superpowers/specs/2026-09-01-cubicle-design.md`](docs/superpowers/specs/2026-09-01-cubicle-design.md).
Research notes — the verified Solari API surface, the probe findings behind it and the
gotchas — are in [`docs/research/`](docs/research/).

## Built with

[Solari](https://www.getsolari.com) — cloud browsers, sandboxes and desktops behind one
API key. This repo is a fork of [solari-cookbook](https://github.com/solari-sdk/solari-cookbook);
the original examples are still under [`examples/`](examples/).

MIT licensed.
