import sqlite3

import pytest

from cubicle.fixtures.build_seed import VARIANTS, seed_bytes
from cubicle.grading import open_book, write_temp_book


@pytest.fixture(scope="module")
def base():
    return open_book(write_temp_book(seed_bytes("base")))


def _names(con) -> set[str]:
    return {r["name"] for r in con.execute("SELECT name FROM accounts")}


def test_every_variant_builds():
    for v in VARIANTS:
        data = seed_bytes(v)
        assert data[:15] == b"SQLite format 3", f"{v} is not a SQLite file"


def test_base_has_the_expected_chart_of_accounts(base):
    for expected in (
        "Checking",
        "Savings",
        "Office Supplies",
        "Utilities",
        "Electric",
        "Water",
        "Technology",
        "Misc",
        "Consulting",
    ):
        assert expected in _names(base), f"missing account {expected}"


def test_account_hierarchy_is_correct(base):
    row = base.execute(
        "SELECT p.name AS parent FROM accounts a JOIN accounts p ON p.guid = a.parent_guid "
        "WHERE a.name = 'Electric'"
    ).fetchone()
    assert row["parent"] == "Utilities"


def test_base_has_twelve_transactions_six_in_march(base):
    total = base.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
    march = base.execute(
        "SELECT COUNT(*) c FROM transactions WHERE post_date LIKE '2026-03%'"
    ).fetchone()["c"]
    assert total == 12
    assert march == 6


def test_base_is_entirely_unreconciled(base):
    states = {r["reconcile_state"] for r in base.execute("SELECT reconcile_state FROM splits")}
    assert states == {"n"}


def test_every_transaction_balances(base):
    rows = base.execute(
        "SELECT tx_guid, SUM(CAST(value_num AS REAL) / value_denom) AS total "
        "FROM splits GROUP BY tx_guid"
    ).fetchall()
    assert rows
    assert all(abs(r["total"]) < 1e-9 for r in rows)


def test_values_are_exact_integer_pairs(base):
    row = base.execute(
        "SELECT s.value_num, s.value_denom FROM transactions t "
        "JOIN splits s ON s.tx_guid = t.guid "
        "WHERE t.description = 'Electric bill' AND s.value_num > 0"
    ).fetchone()
    assert (row["value_num"], row["value_denom"]) == (8840, 100)


def test_t05_adds_invoice_1041_at_250():
    con = open_book(write_temp_book(seed_bytes("t05")))
    row = con.execute(
        "SELECT s.value_num, s.value_denom FROM transactions t "
        "JOIN splits s ON s.tx_guid = t.guid "
        "WHERE t.description = 'Invoice 1041' AND s.value_num > 0"
    ).fetchone()
    assert (row["value_num"], row["value_denom"]) == (25000, 100)


def test_t07_pre_creates_software_subscriptions():
    con = open_book(write_temp_book(seed_bytes("t07")))
    count = con.execute(
        "SELECT COUNT(*) c FROM accounts WHERE name = 'Software Subscriptions'"
    ).fetchone()["c"]
    assert count == 1


def test_t01_does_not_pre_create_software_subscriptions():
    """t01 asks the agent to create it, so it must not already exist."""
    con = open_book(write_temp_book(seed_bytes("base")))
    assert "Software Subscriptions" not in _names(con)


def test_t10_has_both_named_adjustments():
    con = open_book(write_temp_book(seed_bytes("t10")))
    descs = {r["description"] for r in con.execute("SELECT description FROM transactions")}
    assert {"Adjustment A", "Adjustment B"} <= descs


def test_t09_keeps_bank_fee_absent():
    """The agent must add it; if the seed already had it the task would be trivial."""
    con = open_book(write_temp_book(seed_bytes("t09")))
    descs = {r["description"] for r in con.execute("SELECT description FROM transactions")}
    assert "Bank fee" not in descs


def test_seeds_are_deterministic_across_calls():
    assert seed_bytes("base") == seed_bytes("base")


def test_unknown_variant_raises():
    with pytest.raises(ValueError, match="unknown variant"):
        seed_bytes("t99")
