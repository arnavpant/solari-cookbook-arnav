"""t10 - month-end close: create an account, then move two named transactions into it.

Two operations that are each individually easy - t01 creates an account, and re-pointing
a split is the same edit t05 makes - chained so that the second depends on the first
having been done correctly. If the account is created under the wrong parent, the moves
land somewhere real and the screen looks entirely plausible.

The trap is scope. Both target transactions currently sit in Expenses:Misc alongside a
third that must not move. Re-pointing everything in Misc is faster, looks right, and is
wrong; the grader names the transaction that was swept in.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import account_by_name, open_book, parent_name, splits_for
from cubicle.tasks._common import exactly_one_txn
from cubicle.types import Task, Verdict

CLOSEOUT = "Q1 Closeout"
PARENT = "Expenses"
MOVED = ("Adjustment A", "Adjustment B")

PROMPT = (
    f"In GnuCash, create a new Expense account named '{CLOSEOUT}' directly under\n"
    f"'{PARENT}'.\n"
    f"Then move the two transactions described '{MOVED[0]}' and '{MOVED[1]}' into it,\n"
    f"by changing the expense account on each one from Expenses:Misc to\n"
    f"Expenses:{CLOSEOUT}.\n"
    "Leave every other transaction exactly where it is.\n"
    "When both have been moved, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    account = account_by_name(con, CLOSEOUT)
    if account is None:
        return Verdict(False, f"no account named {CLOSEOUT!r} exists")
    if account["account_type"] != "EXPENSE":
        return Verdict(
            False, f"{CLOSEOUT} is {account['account_type']}, expected EXPENSE"
        )
    got_parent = parent_name(con, account)
    if got_parent != PARENT:
        return Verdict(False, f"{CLOSEOUT} parent is {got_parent!r}, expected {PARENT!r}")

    for desc in MOVED:
        txn, bad = exactly_one_txn(con, desc)
        if bad:
            return bad
        on_closeout = [
            s for s in splits_for(con, txn["guid"]) if s["account_guid"] == account["guid"]
        ]
        if len(on_closeout) != 1:
            return Verdict(
                False,
                f"{desc}: {len(on_closeout)} splits against {CLOSEOUT!r}, expected 1",
            )

    # Nothing else may have been re-pointed. This is the "swept all of Misc into it"
    # answer, which satisfies both conditions above and is still wrong.
    strays = con.execute(
        "SELECT DISTINCT t.description FROM splits s JOIN transactions t ON t.guid = s.tx_guid "
        "WHERE s.account_guid = ?",
        (account["guid"],),
    ).fetchall()
    extra = sorted({r["description"] for r in strays} - set(MOVED))
    if extra:
        return Verdict(
            False, f"moved into {CLOSEOUT} but not asked for: " + ", ".join(extra)
        )

    return Verdict(True)


def oracle(cd) -> None:
    raise NotImplementedError(
        "t10's oracle is not recorded yet. Every coordinate in this suite was read off a "
        "real screenshot at 1280x720 - none are guessed - so recording it needs a live "
        "desktop. See scripts/setup_desktop.py."
    )


TASK = Task(
    task_id="t10",
    tier="hard",
    # See t08: the 3x-oracle floor cannot be computed until the oracle is recorded.
    max_steps=60,
    prompt=PROMPT,
    seed=lambda: seed_bytes("t10"),
    grade=grade,
    oracle=oracle,
)
