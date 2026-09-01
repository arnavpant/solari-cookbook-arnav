# cubicle

**A computer-use benchmark for software that has no API.**

GnuCash on a Solari cloud desktop. Seven bookkeeping jobs. The agent gets pixels, a mouse
and a keyboard — nothing else. Every score is a SQL assertion against the database the
application itself wrote.

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

| Agent | Score |
|---|---|
| Scripted oracle | **7 / 7** — reference, proves the suite is solvable |
| DeepSeek V4 Flash Vision | **0 / 7** |
| Gemini | **unscored** — see below |
| **Pinetree-CUA** | **untested** |

Seven tasks, one model, two runs. DeepSeek V4 Flash Vision and Gemini flash-lite are
small vision models with no grounding post-training — **this is not a result about
frontier computer-use agents**, and nothing here should be read as one. The methodology
is the contribution; the number is an illustration of it.

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

A 0/7 is not a finding until you know *why*. So we asked the models to describe a real
cubicle screenshot and say where things are. Ground truth is exact — the GnuCash account
rows sit at y=217, 241 and 264, and a row is 24px tall.

**Every model named every account correctly.** Reading the screen is not the problem.

| | Assets | Expenses | Income | vertical scale | mean error |
|---|---|---|---|---|---|
| **truth** | 217 | 241 | 264 | 1.000 | — |
| DeepSeek V4 Flash Vision | 230 | 256 | 282 | 1.106 | 15px — **0.6 rows** |
| Gemini flash-lite | 304 | 334 | 365 | 1.298 | 94px — **3.9 rows** |

The error is not noise and not a constant offset. It is a **vertical scale factor**, so
it grows the further down the screen you look. Both models stretch the y axis.

This explains the whole run. Gemini flash-lite believed Income was at y=365 and Expenses
at y=334 — and the agent clicked **y=335**. It was not clicking at random. It was clicking
an account row, in its own broken coordinate space.

`scripts/analyze_trace.py` shows the consequence:

```
t01: 15 steps, 14 actions, 1 unparseable, 0 provider errors, screen moved 2x
     kinds: clickx14
     STUCK: 12/14 clicks in the y=330-339 band; the screen moved only 2 time(s)
```

That pattern is the run, not one bad task. **Five of the seven tasks** end with the agent
locked into a ten-pixel horizontal band — y=330-339 on t01 and t03, y=300-309 on t05 and
t06, y=420-429 on t07 — clicking repeatedly at a screen that mostly does not change.

Two deficits, and only the first is the one people usually talk about:

1. **Localization.** Reading a GUI is solved. Pointing at it, to the ~10px precision a
   24px row demands, is not.
2. **No feedback loop.** Twenty-four clicks inside one 10px band on `t05`, with the
   screen changing twice in thirty steps, and the model never concluded that what it was
   doing wasn't working. This is the deficit a bigger step budget makes *worse*, not
   better: given 63 steps on t04 it spent them the same way it spent 30.

### One thing that did not reproduce

An earlier run showed what looked like a third deficit: on `t05`, **17 of 25 clicks
landed outside the 720px-tall screen**, the furthest at y=801 — not a mis-aimed click but
a coordinate that cannot exist. It is not in the current run. The same model on the same
tasks produced **0 out-of-bounds clicks in 198 pointer actions**.

One occurrence across two runs is an anecdote, not a property of the model, and it is
written up here as such rather than quietly dropped. The harness
still applies out-of-bounds actions rather than correcting them, and still records them
as `off_screen`. It measures the agent; it does not help it.

Reproduce with `python scripts/vision_probe.py <screenshot.png>`. Caveat: three rows on
one screenshot per model. It is a sharp signal, not a measured constant.

**Why Gemini is unscored.** Its free tier allows **20 requests per day, per model**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20`), and cubicle needs ~150 to
complete. A single task is 15 to 63 steps, so one task can exhaust the day's allowance
outright; our first attempt lost 11 of 15 steps to HTTP 429. That is a quota limit, not a capability result, so it
is reported as unscored rather than as a low score. Running Gemini here requires billing
enabled on the Google Cloud project.

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

Seven tasks in two tiers, each with its own seed book, its own grader, and a scripted
oracle recorded from real screenshots.

| | Task | What it tests |
|---|---|---|
| **easy** | `t01` create an account | a single dialog |
| | `t02` record a $42.50 expense | register entry, dates, transfer accounts |
| | `t03` rename an account | that it was *renamed*, not deleted and recreated |
| **medium** | `t04` split one bill across two accounts | the split editor — one transaction, three splits |
| | `t05` correct an existing amount | editing in place, not adding a second transaction |
| | `t06` clear only March | discrimination — the seed holds six non-March transactions as traps |
| | `t07` re-parent an account | tree navigation in a three-row viewport |

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

`pytest` runs 148 tests with no network and no credit: seeds, graders, the harness and
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
