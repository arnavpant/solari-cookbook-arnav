"""Generates every seed book programmatically.

Seeds are built rather than hand-crafted so they are reproducible, diffable, and so a
reviewer can see exactly what state an agent started from.

Each task owns its own seed. Tasks never depend on another task having run.
"""

from __future__ import annotations

import datetime as dt
import functools
import os
import tempfile
import warnings
from decimal import Decimal

# piecash emits a wall of SQLAlchemy relationship-overlap warnings on import and on
# every create_book(). They are noise from its own model definitions, not our problem.
warnings.filterwarnings("ignore", module=r"piecash\..*")
warnings.filterwarnings("ignore", message=r".*will copy column.*")
warnings.filterwarnings("ignore", message=r".*overlaps.*")

import piecash  # noqa: E402
from piecash import Account, Split, Transaction  # noqa: E402

VARIANTS = ("base", "t05", "t07", "t09", "t10")

TOP_LEVEL = (("Assets", "ASSET"), ("Expenses", "EXPENSE"), ("Income", "INCOME"))

# (name, gnucash type, parent path). Order matters: parents before children.
BASE_ACCOUNTS = (
    ("Checking", "BANK", "Assets"),
    ("Savings", "BANK", "Assets"),
    ("Office Supplies", "EXPENSE", "Expenses"),
    ("Utilities", "EXPENSE", "Expenses"),
    ("Electric", "EXPENSE", "Expenses:Utilities"),
    ("Water", "EXPENSE", "Expenses:Utilities"),
    ("Technology", "EXPENSE", "Expenses"),
    ("Misc", "EXPENSE", "Expenses"),
    ("Consulting", "INCOME", "Income"),
)

# Twelve entries, all paid from Assets:Checking. Exactly six fall in March 2026 - those
# are t06's targets. The six outside March exist so a grader can catch an agent that
# reconciled the whole register indiscriminately.
BASE_TXNS = (
    ("2026-02-03", "Feb rent share", "Expenses:Office Supplies", "120.00"),
    ("2026-02-11", "Coffee supplies", "Expenses:Office Supplies", "18.75"),
    ("2026-02-24", "Domain renewal", "Expenses:Technology", "22.00"),
    ("2026-03-02", "March paper order", "Expenses:Office Supplies", "64.00"),
    ("2026-03-06", "Electric bill", "Expenses:Utilities:Electric", "88.40"),
    ("2026-03-11", "Water bill", "Expenses:Utilities:Water", "31.20"),
    ("2026-03-17", "Laptop stand", "Expenses:Technology", "51.25"),
    ("2026-03-23", "Stationery", "Expenses:Office Supplies", "12.99"),
    ("2026-03-29", "Cloud hosting", "Expenses:Technology", "40.00"),
    ("2026-04-04", "April paper order", "Expenses:Office Supplies", "58.00"),
    ("2026-04-09", "Postage", "Expenses:Misc", "9.10"),
    ("2026-04-18", "Printer toner", "Expenses:Office Supplies", "76.30"),
)

CHECKING = "Assets:Checking"


def _find(book, full_name: str) -> Account:
    node = book.root_account
    for part in full_name.split(":"):
        node = next(a for a in node.children if a.name == part)
    return node


def _add_txn(book, usd, when: str, desc: str, expense_path: str, amount: str) -> None:
    """One two-split expense paid from Checking. Splits sum to zero by construction."""
    amt = Decimal(amount)
    Transaction(
        currency=usd,
        description=desc,
        post_date=dt.date.fromisoformat(when),
        splits=[
            Split(account=_find(book, expense_path), value=amt),
            Split(account=_find(book, CHECKING), value=-amt),
        ],
    )


def build_book(path: str, variant: str = "base") -> None:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")
    if os.path.exists(path):
        os.remove(path)

    book = piecash.create_book(path, currency="USD")
    usd = book.commodities.get(mnemonic="USD")

    for name, atype in TOP_LEVEL:
        Account(name=name, type=atype, commodity=usd, parent=book.root_account)
    book.save()

    for name, atype, parent in BASE_ACCOUNTS:
        Account(name=name, type=atype, commodity=usd, parent=_find(book, parent))
    book.save()

    for when, desc, path_, amount in BASE_TXNS:
        _add_txn(book, usd, when, desc, path_, amount)
    book.save()

    if variant == "t05":
        # t05 asks the agent to correct this from 250.00 to 520.00.
        _add_txn(book, usd, "2026-03-19", "Invoice 1041", "Expenses:Technology", "250.00")
    elif variant == "t07":
        # t07 only re-parents it, so it must already exist (t07 must not depend on t01).
        Account(
            name="Software Subscriptions",
            type="EXPENSE",
            commodity=usd,
            parent=_find(book, "Expenses"),
        )
    elif variant == "t09":
        # Identical to base on purpose. The statement in t09's prompt lists six lines;
        # five match these transactions and 'Bank fee' is deliberately absent, so the
        # agent has to notice and add it.
        pass
    elif variant == "t10":
        _add_txn(book, usd, "2026-03-25", "Adjustment A", "Expenses:Misc", "15.00")
        _add_txn(book, usd, "2026-03-26", "Adjustment B", "Expenses:Misc", "25.00")

    book.save()
    book.close()


@functools.lru_cache(maxsize=None)
def seed_bytes(variant: str = "base") -> bytes:
    """The seed book as raw bytes, ready to fs.write() onto a desktop."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANTS}")
    fd, path = tempfile.mkstemp(suffix=".gnucash")
    os.close(fd)
    try:
        build_book(path, variant)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "base.gnucash"
    variant = sys.argv[2] if len(sys.argv) > 2 else "base"
    build_book(out, variant)
    print(f"wrote {out} ({os.path.getsize(out)} bytes, variant={variant})")
