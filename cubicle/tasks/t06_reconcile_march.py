"""t06 - reconcile only March.

The whole point is the discrimination. The seed deliberately holds six March
transactions and six outside March, so an agent that just marks the entire register
reconciled - the fast wrong answer - fails.
"""

from __future__ import annotations

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import account_by_name, open_book
from cubicle.types import Task, Verdict

PROMPT = (
    "In GnuCash, open the Assets:Checking account register.\n"
    "Mark every transaction dated in March 2026 as reconciled.\n"
    "Do NOT mark transactions from any other month.\n"
    "When exactly the March transactions are reconciled, respond with the done action."
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

    missed = [r["description"] for r in march if r["reconcile_state"] != "y"]
    if missed:
        return Verdict(False, f"March transactions not reconciled: {', '.join(sorted(missed))}")

    overreached = [r["description"] for r in other if r["reconcile_state"] == "y"]
    if overreached:
        return Verdict(
            False,
            "reconciled transactions outside March: " + ", ".join(sorted(overreached)),
        )

    return Verdict(True)


def oracle(cd) -> None:
    raise NotImplementedError("record the coordinates from a live desktop first")


TASK = Task(
    task_id="t06",
    tier="medium",
    max_steps=30,
    prompt=PROMPT,
    seed=lambda: seed_bytes("base"),
    grade=grade,
    oracle=oracle,
)
