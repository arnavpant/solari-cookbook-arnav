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
| DeepSeek V4 Flash Vision | running |
| Gemini | **unscored** — see below |
| **Pinetree-CUA** | **untested** |

**Why Gemini is unscored.** Its free tier allows **20 requests per day, per model**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20`), and cubicle needs ~150 to
complete. A single 15-step task nearly exhausts the daily allowance; our first attempt
lost 11 of 15 steps to HTTP 429. That is a quota limit, not a capability result, so it
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

`pytest` runs 143 tests with no network and no credit: seeds, graders, the harness and
the action parser are all exercised against an in-memory fake desktop.

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
Research notes, including the competitive landscape and verified Solari API surface, are
in [`docs/research/`](docs/research/).

## Built with

[Solari](https://www.getsolari.com) — cloud browsers, sandboxes and desktops behind one
API key. This repo is a fork of [solari-cookbook](https://github.com/solari-sdk/solari-cookbook);
the original examples are still under [`examples/`](examples/).

MIT licensed.
