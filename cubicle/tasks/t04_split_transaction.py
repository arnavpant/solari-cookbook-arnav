"""t04 - a split transaction. One payment, two expense categories.

The first task that cannot be done in the simple two-column register view; the agent
has to open the split editor.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book
from cubicle.tasks._common import check_split, check_split_count, exactly_one_txn, play
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, record a single utility bill paid from Assets:Checking, split across "
    "two expense accounts:\n"
    "  Description: Utilities March\n"
    "  Total paid:  $120.00 from Assets:Checking\n"
    "  $80.00 to Expenses:Utilities:Electric\n"
    "  $40.00 to Expenses:Utilities:Water\n"
    "This must be ONE transaction with three splits, not two separate transactions.\n"
    "When it is recorded, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    txn, bad = exactly_one_txn(con, "Utilities March")
    if bad:
        return bad

    for check in (
        check_split_count(con, txn["guid"], 3),
        check_split(con, txn["guid"], "Electric", 8000),
        check_split(con, txn["guid"], "Water", 4000),
        check_split(con, txn["guid"], "Checking", -12000),
    ):
        if check:
            return check

    return Verdict(True)


def oracle(cd) -> None:
    """Recorded 2026-09-01 at 1280x720, maximized. Much the fiddliest of the suite.

    Four things had to be learned the hard way:

    1. Enter the TOTAL in the basic row before opening Split. Opening Split on an empty
       row pre-fills the first split's account with the register's own account
       (Assets:Checking), and typing there APPENDS rather than replaces - producing
       'Expenses:Utilities:ElectricAssets:Checking' and a "create this account?" prompt.
    2. Down does not create a new split line. GnuCash only adds the next line once the
       current one is committed with Return.
    3. Committing the Electric split re-sorts the transaction into date order, so the
       split rows MOVE from y=531/555 up to y=411/435/459. The remaining 40.00 lands in
       an auto-created Imbalance-USD split, which is the row to retarget.
    4. Return confirms the cell but does NOT commit the transaction. The screen shows
       'Expenses:Utilities:Water' while the database still says Imbalance-USD. Only the
       Enter toolbar button commits. This is gotcha 10 all over again: the screen was
       right and the data was wrong.
    """
    from cubicle.types import Action

    play(cd, [
        (Action(kind="click", x=13, y=217), 1.2),          # expand Assets
        (Action(kind="double_click", x=75, y=241), 3.0),   # open the Checking register
        (Action(kind="type", text="03/20/26"), 0.5),
        (Action(kind="key", text="Tab"), 0.3),             # -> Num
        (Action(kind="key", text="Tab"), 0.3),             # -> Description
        (Action(kind="type", text="Utilities March"), 0.6),
        (Action(kind="key", text="Tab"), 0.3),             # -> Transfer
        (Action(kind="key", text="Tab"), 0.3),             # -> Deposit
        (Action(kind="key", text="Tab"), 0.3),             # -> Withdrawal
        (Action(kind="type", text="120.00"), 0.5),         # the total, before splitting
        (Action(kind="click", x=657, y=115), 2.0),         # Split in the toolbar
        (Action(kind="click", x=840, y=555), 0.8),         # the blank split's Account cell
        (Action(kind="type", text="Expenses:Utilities:Electric"), 0.8),
        (Action(kind="key", text="Tab"), 0.4),             # -> Deposit
        (Action(kind="type", text="80.00"), 0.5),
        (Action(kind="key", text="Return"), 2.0),          # commit split; rows re-sort
        (Action(kind="click", x=840, y=435), 0.8),         # the Imbalance-USD Account cell
        (Action(kind="key", text="ctrl+a"), 0.4),
        (Action(kind="type", text="Expenses:Utilities:Water"), 0.8),
        (Action(kind="key", text="Return"), 1.0),
        (Action(kind="click", x=408, y=115), 2.5),         # Enter toolbar - the real commit
    ])


TASK = Task(
    task_id="t04",
    tier="medium",
    # cap = max(3x the oracle's 21 actions, floor). The oracle solves this with
    # perfect foreknowledge; an agent has to look, decide and recover from mistakes,
    # so it gets three times the moves a perfect script needs.
    max_steps=63,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
