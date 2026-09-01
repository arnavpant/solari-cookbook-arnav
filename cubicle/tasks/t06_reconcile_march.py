"""t06 - clear only March.

The whole point is the discrimination. The seed deliberately holds six March
transactions and six outside March, so an agent that just marks the entire register -
the fast wrong answer - fails.

Why "cleared" and not "reconciled": the register's R column toggles a split to 'c'
(cleared). Reaching 'y' (reconciled) requires GnuCash's separate Reconcile dialog,
which demands a statement ending balance and is a different task entirely. Verified on
a live desktop: one click on R stored reconcile_state='c'. Clearing is a real
bookkeeping action - you clear an item when the bank confirms it - and it keeps this
task in the medium tier where it belongs.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import account_by_name, open_book
from cubicle.tasks._common import play
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, open the Assets:Checking account register.\n"
    "Mark every transaction dated in March 2026 as cleared, by clicking the 'R' "
    "column on each one so that it changes from 'n' to 'c'.\n"
    "Do NOT mark transactions from any other month.\n"
    "When exactly the March transactions are cleared, respond with the done action."
)


def _checking_splits(con):
    checking = account_by_name(con, "Checking")
    if checking is None:
        return None, Verdict(False, "the 'Checking' account is missing")
    rows = con.execute(
        "SELECT s.reconcile_state, t.post_date, t.description "
        "FROM splits s JOIN transactions t ON t.guid = s.tx_guid "
        "WHERE s.account_guid = ?",
        (checking["guid"],),
    ).fetchall()
    return rows, None


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)
    rows, bad = _checking_splits(con)
    if bad:
        return bad

    march = [r for r in rows if str(r["post_date"]).startswith("2026-03")]
    other = [r for r in rows if not str(r["post_date"]).startswith("2026-03")]

    if len(march) != 6:
        return Verdict(False, f"expected 6 March splits in Checking, found {len(march)}")

    missed = [r["description"] for r in march if r["reconcile_state"] not in ("c", "y")]
    if missed:
        return Verdict(False, f"March transactions not cleared: {', '.join(sorted(missed))}")

    overreached = [r["description"] for r in other if r["reconcile_state"] in ("c", "y")]
    if overreached:
        return Verdict(
            False, "cleared transactions outside March: " + ", ".join(sorted(overreached))
        )

    return Verdict(True)


def oracle(cd) -> None:
    """Recorded 2026-09-01 at 1280x720, maximized.

    Each R toggle needs its own Return. Clicking R on a second row before committing
    the first silently discards the first edit - six clicks followed by one Return
    cleared nothing at all. Commit per row and the row positions stay stable.

    The six March rows sit at y = 291, 315, 339, 363, 387, 411 in the Checking register.
    """
    from cubicle.types import Action

    steps = [
        (Action(kind="click", x=13, y=217), 1.2),          # expand Assets
        (Action(kind="double_click", x=75, y=241), 3.0),   # open the Checking register
    ]
    for y in (291, 315, 339, 363, 387, 411):               # the six March 2026 rows
        steps.append((Action(kind="click", x=966, y=y), 0.6))   # the R column
        steps.append((Action(kind="key", text="Return"), 0.8))  # commit this row
    play(cd, steps)


TASK = Task(
    task_id="t06",
    tier="medium",
    max_steps=30,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
