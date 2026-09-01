import pytest

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import (
    account_by_name,
    check_integrity,
    money,
    open_book,
    parent_name,
    split_on_account,
    splits_for,
    txn_by_description,
    txns_by_description,
    write_temp_book,
)


@pytest.fixture
def con():
    """A fresh connection per test - several tests mutate the book."""
    return open_book(write_temp_book(seed_bytes("base")))


def test_money_is_exact_and_never_a_float():
    assert money(4250, 100) == "42.50"
    assert money(-12000, 100) == "-120.00"
    assert money(8840, 100) == "88.40"
    assert isinstance(money(1, 3), str)


def test_account_lookup_returns_row_with_type(con):
    acct = account_by_name(con, "Checking")
    assert acct is not None
    assert acct["account_type"] == "BANK"


def test_missing_account_returns_none(con):
    assert account_by_name(con, "Nonexistent") is None


def test_parent_name_resolves_the_hierarchy(con):
    assert parent_name(con, account_by_name(con, "Electric")) == "Utilities"
    assert parent_name(con, account_by_name(con, "Technology")) == "Expenses"


def test_parent_name_of_none_is_none(con):
    assert parent_name(con, None) is None


def test_txn_lookup_and_splits(con):
    tx = txn_by_description(con, "Electric bill")
    assert tx is not None
    assert len(splits_for(con, tx["guid"])) == 2


def test_txns_by_description_returns_all_duplicates(con):
    assert len(txns_by_description(con, "Electric bill")) == 1
    assert txns_by_description(con, "Nope") == []


def test_split_on_account_picks_the_right_side(con):
    tx = txn_by_description(con, "Electric bill")
    expense = split_on_account(con, tx["guid"], "Electric")
    bank = split_on_account(con, tx["guid"], "Checking")
    assert expense["value_num"] == 8840
    assert bank["value_num"] == -8840


def test_integrity_passes_on_a_clean_book(con):
    assert check_integrity(con).passed


def test_integrity_fails_on_an_unbalanced_book(con):
    tx = txn_by_description(con, "Electric bill")
    split = splits_for(con, tx["guid"])[0]
    con.execute(
        "UPDATE splits SET value_num = value_num + 500 WHERE guid = ?", (split["guid"],)
    )
    verdict = check_integrity(con)
    assert not verdict.passed
    assert "does not balance" in verdict.reason


def test_integrity_reason_names_the_offending_transaction(con):
    tx = txn_by_description(con, "Water bill")
    split = splits_for(con, tx["guid"])[0]
    con.execute("UPDATE splits SET value_num = 1 WHERE guid = ?", (split["guid"],))
    assert tx["guid"] in check_integrity(con).reason


def test_write_temp_book_roundtrips():
    data = seed_bytes("base")
    with open(write_temp_book(data), "rb") as fh:
        assert fh.read() == data
