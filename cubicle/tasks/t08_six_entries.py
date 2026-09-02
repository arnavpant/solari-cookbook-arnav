"""t08 - enter six transactions, in order.

The cheapest honest probe of a long-horizon claim. There is nothing clever in any one
of these six entries; t02 already proved a single entry is within reach. The whole
difficulty is doing the same unremarkable thing six times without drifting - losing
the place in the list, repeating an entry, or carrying the previous row's amount into
the next one.

That is deliberately the failure mode this grader can see. It reports the first entry
that is wrong *by name*, so a run log says "stopped after four" rather than "failed".
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book
from cubicle.tasks._common import check_date, check_split, check_split_count, exactly_one_txn
from cubicle.types import Task, Verdict

# (post date, description, expense account, amount in cents). All paid from Checking.
# May 2026 on purpose: the seed's existing entries run February to April, so nothing
# here collides with t06's March discrimination or with any other task's fixtures.
ENTRIES = (
    ("2026-05-04", "Supplier invoice 2201", "Office Supplies", 4500),
    ("2026-05-06", "Cloud backup", "Technology", 1250),
    ("2026-05-08", "May water bill", "Water", 2875),
    ("2026-05-12", "Courier run", "Misc", 740),
    ("2026-05-15", "Monitor arm", "Technology", 6320),
    ("2026-05-20", "Envelopes", "Office Supplies", 1560),
)


def _prompt() -> str:
    lines = "\n".join(
        f"  {i}. {day}  {desc}  ${cents / 100:.2f}  ->  Expenses:{account}"
        for i, (day, desc, account, cents) in enumerate(ENTRIES, 1)
    )
    return (
        "In GnuCash, open the Assets:Checking account register and record these six\n"
        "transactions. Each one is paid from Assets:Checking. Enter them in the order\n"
        "listed, using the description exactly as written.\n\n"
        f"{lines}\n\n"
        "When all six are entered, respond with the done action."
    )


PROMPT = _prompt()


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    for day, desc, account, cents in ENTRIES:
        txn, bad = exactly_one_txn(con, desc)
        if bad:
            return bad
        for check in (
            check_date(txn, day),
            check_split_count(con, txn["guid"], 2),
            check_split(con, txn["guid"], account, cents),
            check_split(con, txn["guid"], "Checking", -cents),
        ):
            if check:
                # Name the entry. "Monitor arm: Technology split is 6321/100" tells you
                # which of the six drifted; the bare message does not.
                return Verdict(False, f"{desc}: {check.reason}")

    return Verdict(True)


def oracle(cd) -> None:
    raise NotImplementedError(
        "t08's oracle is not recorded yet. Every coordinate in this suite was read off a "
        "real screenshot at 1280x720 - none are guessed - so recording it needs a live "
        "desktop. See scripts/setup_desktop.py."
    )


TASK = Task(
    task_id="t08",
    tier="hard",
    # The 3x-oracle rule cannot be applied until the oracle is recorded. 60 is the cap
    # the design doc specifies for the hard tier; it is revisited, not assumed, once a
    # floor exists. tests/test_step_budget.py names this task as exempt meanwhile.
    max_steps=60,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
