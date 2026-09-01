"""t01's grader, tested against synthetic mutations.

Graders are proven correct here, offline, before any agent or oracle exists - so a
grader bug can never hide behind an agent failure.
"""

from __future__ import annotations

import uuid

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book, write_temp_book
from cubicle.tasks.t01_create_account import TASK


def book_with_account(
    name: str = "Software Subscriptions",
    parent: str = "Expenses",
    atype: str = "EXPENSE",
) -> str:
    """Insert an account directly, the way a successful agent would leave the book."""
    path = write_temp_book(seed_bytes("base"))
    con = open_book(path)
    row = con.execute(
        "SELECT guid, commodity_guid FROM accounts WHERE name = ?", (parent,)
    ).fetchone()
    con.execute(
        "INSERT INTO accounts (guid, name, account_type, commodity_guid, commodity_scu,"
        " non_std_scu, parent_guid, code, description, hidden, placeholder) "
        "VALUES (?, ?, ?, ?, 100, 0, ?, '', '', 0, 0)",
        (uuid.uuid4().hex, name, atype, row["commodity_guid"], row["guid"]),
    )
    con.commit()
    return path


def test_fails_on_the_untouched_book():
    verdict = TASK.grade(write_temp_book(seed_bytes("base")))
    assert not verdict.passed
    assert "Software Subscriptions" in verdict.reason


def test_passes_when_the_account_is_created_correctly():
    assert TASK.grade(book_with_account()).passed


def test_rejects_the_wrong_parent():
    verdict = TASK.grade(book_with_account(parent="Assets"))
    assert not verdict.passed
    assert "parent" in verdict.reason


def test_rejects_the_wrong_account_type():
    verdict = TASK.grade(book_with_account(atype="ASSET"))
    assert not verdict.passed
    assert "type" in verdict.reason


def test_rejects_a_misspelled_name():
    verdict = TASK.grade(book_with_account(name="Software Subscription"))
    assert not verdict.passed


def test_rejects_creating_it_twice():
    path = book_with_account()
    con = open_book(path)
    row = con.execute("SELECT guid, commodity_guid FROM accounts WHERE name='Expenses'").fetchone()
    con.execute(
        "INSERT INTO accounts (guid, name, account_type, commodity_guid, commodity_scu,"
        " non_std_scu, parent_guid, code, description, hidden, placeholder) "
        "VALUES (?, 'Software Subscriptions', 'EXPENSE', ?, 100, 0, ?, '', '', 0, 0)",
        (uuid.uuid4().hex, row["commodity_guid"], row["guid"]),
    )
    con.commit()
    verdict = TASK.grade(path)
    assert not verdict.passed
    assert "2 accounts" in verdict.reason


def test_task_metadata_is_sane():
    assert TASK.task_id == "t01"
    assert TASK.tier == "easy"
    assert TASK.max_steps == 15
    assert "Software Subscriptions" in TASK.prompt
