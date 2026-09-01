"""t03 - rename an account.

The interesting part is proving it was RENAMED and not deleted-and-recreated. Rather
than compare guids (piecash generates fresh ones each build), we check that the account
kept the transaction that was already posted against it. A recreated account would be
empty.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import accounts_by_name, open_book, parent_name
from cubicle.tasks._common import play
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, rename the existing expense account 'Misc' to 'Miscellaneous'.\n"
    "Do not create a new account - rename the one that is already there.\n"
    "When it is renamed, respond with the done action."
)


def grade(book_path: str) -> Verdict:
    con = open_book(book_path)

    if accounts_by_name(con, "Misc"):
        return Verdict(False, "an account named 'Misc' still exists")

    matches = accounts_by_name(con, "Miscellaneous")
    if not matches:
        return Verdict(False, "no account named 'Miscellaneous' exists")
    if len(matches) > 1:
        return Verdict(False, f"{len(matches)} accounts named 'Miscellaneous' exist")

    acct = matches[0]
    if acct["account_type"] != "EXPENSE":
        return Verdict(False, f"wrong account type {acct['account_type']!r}, expected 'EXPENSE'")

    parent = parent_name(con, acct)
    if parent != "Expenses":
        return Verdict(False, f"wrong parent {parent!r}, expected 'Expenses'")

    # The seeded 'Postage' expense was posted against Misc. If the agent deleted the
    # account and made a new one, that split would not be here.
    kept = con.execute(
        "SELECT COUNT(*) c FROM splits s JOIN transactions t ON t.guid = s.tx_guid "
        "WHERE s.account_guid = ? AND t.description = 'Postage'",
        (acct["guid"],),
    ).fetchone()["c"]
    if kept != 1:
        return Verdict(
            False,
            "'Miscellaneous' has no 'Postage' transaction - the account was recreated, "
            "not renamed",
        )

    return Verdict(True)


def oracle(cd) -> None:
    """Recorded 2026-09-01 at 1280x720. Expand Expenses, select Misc, Edit, retype."""
    from cubicle.types import Action

    play(cd, [
        (Action(kind="click", x=13, y=241), 1.5),    # expand the Expenses tree
        (Action(kind="click", x=75, y=264), 1.0),    # select 'Misc'
        (Action(kind="click", x=295, y=115), 2.5),   # Edit in the toolbar
        (Action(kind="click", x=463, y=154), 0.8),   # the Account name field
        (Action(kind="key", text="ctrl+a"), 0.5),
        (Action(kind="type", text="Miscellaneous"), 1.0),
        (Action(kind="click", x=559, y=692), 2.5),   # OK
    ])


TASK = Task(
    task_id="t03",
    tier="easy",
    # cap = max(3x the oracle's 7 actions, floor). The oracle solves this with
    # perfect foreknowledge; an agent has to look, decide and recover from mistakes,
    # so it gets three times the moves a perfect script needs.
    max_steps=21,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
