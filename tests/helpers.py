"""Mutate a seed book the way a successful (or unsuccessful) agent would leave it.

Graders are proven against these offline, so grader correctness never depends on having
a working agent - and an agent failure can never be mistaken for a grader bug.
"""

from __future__ import annotations

import sqlite3
import uuid

from cubicle.fixtures.build_seed import seed_bytes
from cubicle.grading import open_book, write_temp_book


def fresh(variant: str = "base") -> sqlite3.Connection:
    # sqlite3.Connection does not accept arbitrary attributes, so the path is recovered
    # from the connection itself via path_of() rather than stashed on it.
    return open_book(write_temp_book(seed_bytes(variant)))


def path_of(con: sqlite3.Connection) -> str:
    return con.execute("PRAGMA database_list").fetchone()[2]


def guid_of(con, name: str) -> str:
    return con.execute("SELECT guid FROM accounts WHERE name = ?", (name,)).fetchone()["guid"]


def currency_guid(con) -> str:
    return con.execute("SELECT guid FROM commodities WHERE mnemonic = 'USD'").fetchone()["guid"]


def add_txn(con, description: str, day: str, legs: list[tuple[str, int]]) -> str:
    """legs: [(account name, value_num)] in cents. Must sum to zero."""
    tx = uuid.uuid4().hex
    con.execute(
        "INSERT INTO transactions (guid, currency_guid, num, post_date, enter_date, description)"
        " VALUES (?, ?, '', ?, ?, ?)",
        (tx, currency_guid(con), f"{day} 10:59:00", f"{day} 10:59:00", description),
    )
    for account, num in legs:
        con.execute(
            "INSERT INTO splits (guid, tx_guid, account_guid, memo, action, reconcile_state,"
            " reconcile_date, value_num, value_denom, quantity_num, quantity_denom, lot_guid)"
            " VALUES (?, ?, ?, '', '', 'n', NULL, ?, 100, ?, 100, NULL)",
            (uuid.uuid4().hex, tx, guid_of(con, account), num, num),
        )
    con.commit()
    return tx


def add_account(con, name: str, parent: str, atype: str = "EXPENSE") -> str:
    row = con.execute(
        "SELECT guid, commodity_guid FROM accounts WHERE name = ?", (parent,)
    ).fetchone()
    guid = uuid.uuid4().hex
    con.execute(
        "INSERT INTO accounts (guid, name, account_type, commodity_guid, commodity_scu,"
        " non_std_scu, parent_guid, code, description, hidden, placeholder)"
        " VALUES (?, ?, ?, ?, 100, 0, ?, '', '', 0, 0)",
        (guid, name, atype, row["commodity_guid"], row["guid"]),
    )
    con.commit()
    return guid


def reconcile(con, account: str, date_prefix: str, state: str = "c") -> None:
    con.execute(
        f"UPDATE splits SET reconcile_state = '{state}' WHERE account_guid = ? AND tx_guid IN "
        "(SELECT guid FROM transactions WHERE post_date LIKE ?)",
        (guid_of(con, account), f"{date_prefix}%"),
    )
    con.commit()
