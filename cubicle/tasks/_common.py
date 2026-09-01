"""Shared grader helpers. Kept tiny and explicit - a grader should read like an
assertion list, not like a framework."""

from __future__ import annotations

import sqlite3

from cubicle.grading import split_on_account, splits_for, txns_by_description
from cubicle.types import Verdict


def exactly_one_txn(con: sqlite3.Connection, desc: str):
    """Returns (row, None) or (None, Verdict) - graders must reject duplicates, because
    'entered it twice' is a real and common agent failure."""
    rows = txns_by_description(con, desc)
    if not rows:
        return None, Verdict(False, f"no transaction described {desc!r}")
    if len(rows) > 1:
        return None, Verdict(False, f"{len(rows)} transactions described {desc!r}, expected 1")
    return rows[0], None


def check_split(con, tx_guid: str, account: str, num: int, denom: int = 100):
    """Money is compared as the exact integer pair GnuCash stores. Never as a float."""
    s = split_on_account(con, tx_guid, account)
    if s is None:
        return Verdict(False, f"no split against {account!r}")
    if (s["value_num"], s["value_denom"]) != (num, denom):
        return Verdict(
            False,
            f"{account} split is {s['value_num']}/{s['value_denom']}, expected {num}/{denom}",
        )
    return None


def check_split_count(con, tx_guid: str, n: int):
    got = len(splits_for(con, tx_guid))
    if got != n:
        return Verdict(False, f"transaction has {got} splits, expected {n}")
    return None


def check_date(txn, iso_day: str):
    """post_date is stored as '2026-03-14 10:59:00'."""
    if not str(txn["post_date"]).startswith(iso_day):
        return Verdict(False, f"post_date is {txn['post_date']!r}, expected {iso_day}")
    return None
