"""t05 - find an existing transaction and correct its amount.

Tests search/navigation, not just data entry. The failure mode this catches is an agent
that enters a NEW $520 transaction instead of editing the existing $250 one, which
leaves the books wrong in a way that looks superficially right.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book
from cubicle.tasks._common import check_split, check_split_count, exactly_one_txn, play
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, find the existing transaction described 'Invoice 1041'.\n"
    "It was entered with the wrong amount. Change it from $250.00 to $520.00.\n"
    "Edit the existing transaction - do not add a second one.\n"
    "When it is corrected, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    txn, bad = exactly_one_txn(con, "Invoice 1041")
    if bad:
        return bad

    for check in (
        check_split_count(con, txn["guid"], 2),
        check_split(con, txn["guid"], "Technology", 52000),
        check_split(con, txn["guid"], "Checking", -52000),
    ):
        if check:
            return check

    return Verdict(True)


def oracle(cd) -> None:
    """Recorded 2026-09-01 at 1280x720, maximized.

    Invoice 1041 is dated 03/19/26, which sorts it to row y=387 in the Checking
    register. Editing the Withdrawal cell in place is what keeps this a correction
    rather than a second transaction.
    """
    from cubicle.types import Action

    play(cd, [
        (Action(kind="click", x=13, y=217), 1.2),          # expand Assets
        (Action(kind="double_click", x=75, y=241), 3.0),   # open the Checking register
        (Action(kind="click", x=1122, y=387), 1.0),        # Withdrawal cell, Invoice 1041
        (Action(kind="key", text="ctrl+a"), 0.4),
        (Action(kind="type", text="520.00"), 0.6),
        (Action(kind="key", text="Return"), 2.5),
    ])


TASK = Task(
    task_id="t05",
    tier="medium",
    max_steps=30,
    prompt=PROMPT,
    seed=lambda: seed_bytes("t05"),
    grade=grade,
    oracle=oracle,
)
