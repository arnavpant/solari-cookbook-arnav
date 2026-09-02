"""Graders for the hard tier, t08-t10, proven against synthetic mutations.

Same discipline as the easy and medium tiers: every grader is shown to reject the
specific plausible wrong answer, not merely to accept the right one. For the hard tier
the plausible wrong answers are different in kind - they are drift failures. An agent
does not get t08 wrong by misunderstanding it, it gets five of six entries in and loses
the thread. That is exactly what a long-horizon benchmark has to be able to see.
"""

from __future__ import annotations

from cubicle.tasks import TASKS
from cubicle.tasks.t08_six_entries import ENTRIES
from cubicle.tasks.t09_reconcile_statement import BANK_FEE, OFF_STATEMENT, ON_STATEMENT
from cubicle.tasks.t10_month_end_close import CLOSEOUT, MOVED
from tests.helpers import add_account, add_txn, fresh, guid_of, path_of, reconcile

# --------------------------------------------------------------------- t08

T08 = TASKS["t08"]


def _enter_all(con, skip: str | None = None, amounts: dict[str, int] | None = None,
               dates: dict[str, str] | None = None) -> None:
    """Enter the six prompted transactions, optionally dropping or corrupting one."""
    amounts = amounts or {}
    dates = dates or {}
    for day, desc, account, cents in ENTRIES:
        if desc == skip:
            continue
        add_txn(con, desc, dates.get(desc, day),
                [(account, amounts.get(desc, cents)),
                 ("Checking", -amounts.get(desc, cents))])


def test_t08_fails_on_untouched_book():
    v = T08.grade(path_of(fresh()))
    assert not v.passed


def test_t08_passes_when_all_six_entered():
    con = fresh()
    _enter_all(con)
    assert T08.grade(path_of(con)).passed


def test_t08_rejects_five_of_six():
    """The signature long-horizon failure: the agent drifts and stops one short."""
    con = fresh()
    _enter_all(con, skip="Envelopes")
    v = T08.grade(path_of(con))
    assert not v.passed and "Envelopes" in v.reason


def test_t08_rejects_a_duplicated_entry():
    con = fresh()
    _enter_all(con)
    day, desc, account, cents = ENTRIES[0]
    add_txn(con, desc, day, [(account, cents), ("Checking", -cents)])
    v = T08.grade(path_of(con))
    assert not v.passed and desc in v.reason


def test_t08_rejects_a_wrong_amount():
    con = fresh()
    _enter_all(con, amounts={"Monitor arm": 6321})
    v = T08.grade(path_of(con))
    assert not v.passed and "Monitor arm" in v.reason


def test_t08_rejects_a_wrong_date():
    con = fresh()
    _enter_all(con, dates={"Courier run": "2026-05-13"})
    v = T08.grade(path_of(con))
    assert not v.passed and "Courier run" in v.reason


# --------------------------------------------------------------------- t09

T09 = TASKS["t09"]


def _add_bank_fee(con, cents: int = None, day: str = None) -> None:
    day_, desc, account, default = BANK_FEE
    add_txn(con, desc, day or day_,
            [(account, cents or default), ("Checking", -(cents or default))])


def _clear(con, descriptions) -> None:
    for desc in descriptions:
        con.execute(
            "UPDATE splits SET reconcile_state = 'c' WHERE tx_guid IN "
            "(SELECT guid FROM transactions WHERE description = ?)",
            (desc,),
        )
    con.commit()


def test_t09_fails_on_untouched_book():
    v = T09.grade(path_of(fresh("t09")))
    assert not v.passed


def test_t09_fails_when_the_missing_entry_was_never_added():
    """Five of six clear fine; the whole task is noticing the sixth is absent."""
    con = fresh("t09")
    _clear(con, ON_STATEMENT)
    v = T09.grade(path_of(con))
    assert not v.passed and BANK_FEE[1] in v.reason


def test_t09_fails_when_added_but_nothing_cleared():
    con = fresh("t09")
    _add_bank_fee(con)
    v = T09.grade(path_of(con))
    assert not v.passed


def test_t09_passes_when_added_and_all_six_cleared():
    con = fresh("t09")
    _add_bank_fee(con)
    _clear(con, list(ON_STATEMENT) + [BANK_FEE[1]])
    assert T09.grade(path_of(con)).passed


def test_t09_rejects_clearing_a_transaction_not_on_the_statement():
    con = fresh("t09")
    _add_bank_fee(con)
    _clear(con, list(ON_STATEMENT) + [BANK_FEE[1]] + list(OFF_STATEMENT))
    v = T09.grade(path_of(con))
    assert not v.passed and OFF_STATEMENT[0] in v.reason


def test_t09_rejects_the_wrong_amount_on_the_added_entry():
    con = fresh("t09")
    _add_bank_fee(con, cents=1600)
    _clear(con, list(ON_STATEMENT) + [BANK_FEE[1]])
    v = T09.grade(path_of(con))
    assert not v.passed and BANK_FEE[1] in v.reason


# --------------------------------------------------------------------- t10

T10 = TASKS["t10"]


def _move(con, description: str, to_account: str) -> None:
    """Re-point the expense leg of a transaction, the way the split editor would."""
    con.execute(
        "UPDATE splits SET account_guid = ? WHERE value_num > 0 AND tx_guid IN "
        "(SELECT guid FROM transactions WHERE description = ?)",
        (guid_of(con, to_account), description),
    )
    con.commit()


def test_t10_fails_on_untouched_book():
    v = T10.grade(path_of(fresh("t10")))
    assert not v.passed


def test_t10_fails_when_the_account_exists_but_nothing_moved():
    con = fresh("t10")
    add_account(con, CLOSEOUT, "Expenses")
    v = T10.grade(path_of(con))
    assert not v.passed


def test_t10_passes_when_the_account_exists_and_both_moved():
    con = fresh("t10")
    add_account(con, CLOSEOUT, "Expenses")
    for desc in MOVED:
        _move(con, desc, CLOSEOUT)
    assert T10.grade(path_of(con)).passed


def test_t10_rejects_moving_only_one():
    con = fresh("t10")
    add_account(con, CLOSEOUT, "Expenses")
    _move(con, MOVED[0], CLOSEOUT)
    v = T10.grade(path_of(con))
    assert not v.passed and MOVED[1] in v.reason


def test_t10_rejects_the_wrong_parent():
    con = fresh("t10")
    add_account(con, CLOSEOUT, "Misc")
    for desc in MOVED:
        _move(con, desc, CLOSEOUT)
    v = T10.grade(path_of(con))
    assert not v.passed and "parent" in v.reason.lower()


def test_t10_rejects_sweeping_an_unrelated_transaction_in():
    """The fast wrong answer: re-point everything in Misc instead of the two named."""
    con = fresh("t10")
    add_account(con, CLOSEOUT, "Expenses")
    for desc in list(MOVED) + ["Postage"]:
        _move(con, desc, CLOSEOUT)
    v = T10.grade(path_of(con))
    assert not v.passed and "Postage" in v.reason
