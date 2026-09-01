"""Every grader goes through here.

Plain sqlite3 only. No ORM, no model, no LLM judge, no screenshot diffing. A cubicle
score is a fact anyone can re-derive from the committed book.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from decimal import Decimal

from cubicle.types import Verdict


def write_temp_book(data: bytes) -> str:
    """Drop raw book bytes on disk and return the path."""
    fd, path = tempfile.mkstemp(suffix=".gnucash")
    os.close(fd)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def open_book(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def money(num: int, denom: int) -> str:
    """Exact decimal string. Never returns a float."""
    return str((Decimal(num) / Decimal(denom)).quantize(Decimal("0.01")))


def account_by_name(con: sqlite3.Connection, name: str):
    """GnuCash allows duplicate names under different parents; graders that care about
    the parent check it explicitly. Returns None if absent."""
    return con.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()


def accounts_by_name(con: sqlite3.Connection, name: str):
    return con.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchall()


def parent_name(con: sqlite3.Connection, account_row) -> str | None:
    if account_row is None or account_row["parent_guid"] is None:
        return None
    row = con.execute(
        "SELECT name FROM accounts WHERE guid = ?", (account_row["parent_guid"],)
    ).fetchone()
    return row["name"] if row else None


def txn_by_description(con: sqlite3.Connection, desc: str):
    return con.execute("SELECT * FROM transactions WHERE description = ?", (desc,)).fetchone()


def txns_by_description(con: sqlite3.Connection, desc: str):
    return con.execute("SELECT * FROM transactions WHERE description = ?", (desc,)).fetchall()


def splits_for(con: sqlite3.Connection, tx_guid: str):
    return con.execute("SELECT * FROM splits WHERE tx_guid = ?", (tx_guid,)).fetchall()


def split_on_account(con: sqlite3.Connection, tx_guid: str, account_name: str):
    return con.execute(
        "SELECT s.* FROM splits s JOIN accounts a ON a.guid = s.account_guid "
        "WHERE s.tx_guid = ? AND a.name = ?",
        (tx_guid, account_name),
    ).fetchone()


def check_integrity(con: sqlite3.Connection) -> Verdict:
    """Applied to EVERY task. Splits must sum to zero for every transaction.

    An agent that corrupts the book fails even if it satisfied the task's own condition.
    """
    rows = con.execute(
        "SELECT tx_guid, SUM(CAST(value_num AS REAL) / value_denom) AS total "
        "FROM splits GROUP BY tx_guid"
    ).fetchall()
    for r in rows:
        if abs(r["total"]) > 1e-9:
            return Verdict(
                False, f"transaction {r['tx_guid']} does not balance (sum={r['total']})"
            )
    return Verdict(True)
