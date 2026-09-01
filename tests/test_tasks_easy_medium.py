"""Graders for t02-t07, proven against synthetic mutations."""

from __future__ import annotations

from cubicle.tasks import TASKS
from tests.helpers import add_account, add_txn, fresh, guid_of, path_of, reconcile

# --------------------------------------------------------------------- t02

T02 = TASKS["t02"]


def test_t02_fails_on_untouched_book():
    v = T02.grade(path_of(fresh()))
    assert not v.passed and "Printer paper" in v.reason


def test_t02_passes_when_recorded_correctly():
    con = fresh()
    add_txn(con, "Printer paper", "2026-03-14",
            [("Office Supplies", 4250), ("Checking", -4250)])
    assert T02.grade(path_of(con)).passed


def test_t02_rejects_the_wrong_amount():
    con = fresh()
    add_txn(con, "Printer paper", "2026-03-14",
            [("Office Supplies", 4200), ("Checking", -4200)])
    v = T02.grade(path_of(con))
    assert not v.passed and "4200/100" in v.reason


def test_t02_rejects_the_wrong_date():
    con = fresh()
    add_txn(con, "Printer paper", "2026-03-15",
            [("Office Supplies", 4250), ("Checking", -4250)])
    v = T02.grade(path_of(con))
    assert not v.passed and "post_date" in v.reason


def test_t02_rejects_the_wrong_expense_account():
    con = fresh()
    add_txn(con, "Printer paper", "2026-03-14", [("Technology", 4250), ("Checking", -4250)])
    v = T02.grade(path_of(con))
    assert not v.passed and "Office Supplies" in v.reason


def test_t02_rejects_entering_it_twice():
    con = fresh()
    for _ in range(2):
        add_txn(con, "Printer paper", "2026-03-14",
                [("Office Supplies", 4250), ("Checking", -4250)])
    v = T02.grade(path_of(con))
    assert not v.passed and "2 transactions" in v.reason


# --------------------------------------------------------------------- t03

T03 = TASKS["t03"]


def test_t03_fails_on_untouched_book():
    v = T03.grade(path_of(fresh()))
    assert not v.passed and "Misc" in v.reason


def test_t03_passes_on_a_real_rename():
    con = fresh()
    con.execute("UPDATE accounts SET name='Miscellaneous' WHERE name='Misc'")
    con.commit()
    assert T03.grade(path_of(con)).passed


def test_t03_rejects_delete_and_recreate():
    """The recreated account has no 'Postage' transaction attached."""
    con = fresh()
    con.execute("DELETE FROM splits WHERE account_guid = ?", (guid_of(con, "Misc"),))
    con.execute("DELETE FROM accounts WHERE name='Misc'")
    con.commit()
    add_account(con, "Miscellaneous", "Expenses")
    v = T03.grade(path_of(con))
    assert not v.passed and "recreated" in v.reason


def test_t03_rejects_leaving_the_old_account_behind():
    con = fresh()
    add_account(con, "Miscellaneous", "Expenses")
    v = T03.grade(path_of(con))
    assert not v.passed and "still exists" in v.reason


# --------------------------------------------------------------------- t04

T04 = TASKS["t04"]


def test_t04_fails_on_untouched_book():
    assert not T04.grade(path_of(fresh())).passed


def test_t04_passes_on_a_correct_three_way_split():
    con = fresh()
    add_txn(con, "Utilities March", "2026-03-20",
            [("Electric", 8000), ("Water", 4000), ("Checking", -12000)])
    assert T04.grade(path_of(con)).passed


def test_t04_rejects_two_separate_transactions():
    """The common wrong answer: one transaction per expense account."""
    con = fresh()
    add_txn(con, "Utilities March", "2026-03-20", [("Electric", 8000), ("Checking", -8000)])
    add_txn(con, "Utilities March", "2026-03-20", [("Water", 4000), ("Checking", -4000)])
    v = T04.grade(path_of(con))
    assert not v.passed and "2 transactions" in v.reason


def test_t04_rejects_a_wrong_split_amount():
    con = fresh()
    add_txn(con, "Utilities March", "2026-03-20",
            [("Electric", 7000), ("Water", 5000), ("Checking", -12000)])
    v = T04.grade(path_of(con))
    assert not v.passed and "Electric" in v.reason


# --------------------------------------------------------------------- t05

T05 = TASKS["t05"]


def _fix_invoice(con, amount: int) -> None:
    tx = con.execute(
        "SELECT guid FROM transactions WHERE description='Invoice 1041'"
    ).fetchone()["guid"]
    con.execute("UPDATE splits SET value_num=?, quantity_num=? "
                "WHERE tx_guid=? AND value_num > 0", (amount, amount, tx))
    con.execute("UPDATE splits SET value_num=?, quantity_num=? "
                "WHERE tx_guid=? AND value_num < 0", (-amount, -amount, tx))
    con.commit()


def test_t05_fails_on_the_uncorrected_book():
    v = T05.grade(path_of(fresh("t05")))
    assert not v.passed and "25000/100" in v.reason


def test_t05_passes_when_corrected_in_place():
    con = fresh("t05")
    _fix_invoice(con, 52000)
    assert T05.grade(path_of(con)).passed


def test_t05_rejects_adding_a_second_transaction():
    """The seductive wrong answer: leave the $250 and add a $520."""
    con = fresh("t05")
    add_txn(con, "Invoice 1041", "2026-03-19",
            [("Technology", 52000), ("Checking", -52000)])
    v = T05.grade(path_of(con))
    assert not v.passed and "2 transactions" in v.reason


def test_t05_rejects_a_wrong_corrected_amount():
    con = fresh("t05")
    _fix_invoice(con, 51000)
    v = T05.grade(path_of(con))
    assert not v.passed and "51000/100" in v.reason


# --------------------------------------------------------------------- t06

T06 = TASKS["t06"]


def test_t06_fails_on_untouched_book():
    v = T06.grade(path_of(fresh()))
    assert not v.passed and "not reconciled" in v.reason


def test_t06_passes_when_only_march_is_reconciled():
    con = fresh()
    reconcile(con, "Checking", "2026-03")
    assert T06.grade(path_of(con)).passed


def test_t06_rejects_reconciling_everything():
    """The fast wrong answer, and the reason the seed has non-March transactions."""
    con = fresh()
    con.execute("UPDATE splits SET reconcile_state='y' WHERE account_guid = ?",
                (guid_of(con, "Checking"),))
    con.commit()
    v = T06.grade(path_of(con))
    assert not v.passed and "outside March" in v.reason


def test_t06_rejects_a_partial_reconcile():
    con = fresh()
    reconcile(con, "Checking", "2026-03")
    tx = con.execute(
        "SELECT guid FROM transactions WHERE description='Water bill'"
    ).fetchone()["guid"]
    con.execute("UPDATE splits SET reconcile_state='n' WHERE tx_guid=?", (tx,))
    con.commit()
    v = T06.grade(path_of(con))
    assert not v.passed and "Water bill" in v.reason


# --------------------------------------------------------------------- t07

T07 = TASKS["t07"]


def test_t07_fails_on_untouched_book():
    v = T07.grade(path_of(fresh("t07")))
    assert not v.passed and "Expenses" in v.reason


def test_t07_passes_when_reparented():
    con = fresh("t07")
    con.execute("UPDATE accounts SET parent_guid=? WHERE name='Software Subscriptions'",
                (guid_of(con, "Technology"),))
    con.commit()
    assert T07.grade(path_of(con)).passed


def test_t07_rejects_moving_technology_instead():
    """Moving the parent under the child also makes the path look plausible."""
    con = fresh("t07")
    con.execute("UPDATE accounts SET parent_guid=? WHERE name='Technology'",
                (guid_of(con, "Software Subscriptions"),))
    con.commit()
    v = T07.grade(path_of(con))
    assert not v.passed


def test_t07_rejects_delete_and_recreate_under_technology():
    con = fresh("t07")
    con.execute("DELETE FROM accounts WHERE name='Software Subscriptions'")
    con.commit()
    add_account(con, "Software Subscriptions", "Technology")
    add_account(con, "Software Subscriptions", "Expenses")
    v = T07.grade(path_of(con))
    assert not v.passed and "2 accounts" in v.reason
