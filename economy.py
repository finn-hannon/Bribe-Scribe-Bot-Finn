import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any


DB_PATH = "bribe_scribe.db"
STARTING_BALANCE = 1000
DAILY_AMOUNT = 150
DAILY_COOLDOWN_HOURS = 24

def connect() -> sqlite3.Connection:
    # Opens (or creates) the database file and returns a connection object
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    # Creates tables if they do not exist yet
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_daily_claim_at TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Migration: add column if this DB was created before we added it
        try:
            conn.execute("ALTER TABLE users ADD COLUMN last_daily_claim_at TEXT")
        except sqlite3.OperationalError:
            # Column already exists
            pass
    

def ensure_user(user_id: int) -> None:
    init_db()
    # Makes sure a user exists in the database.
    # If not, insert them with the starting balance.
    now = datetime.now(timezone.utc).isoformat()

    with connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            conn.execute(
            "INSERT INTO users (user_id, balance, created_at) VALUES (?, ?, ?)",
            (user_id, STARTING_BALANCE, now),
        )            

            conn.execute(
            "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, STARTING_BALANCE, "starting_balance", now),
        )

def get_balance(user_id: int) -> int:
    ensure_user(user_id)
    init_db()

    with connect() as conn:
        row = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        return int(row["balance"])

def top_balances(limit: int = 10):
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return rows

def get_recent_transactions(user_id: int, limit: int = 10):
    init_db()
    ensure_user(user_id)

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT tx_id, amount, reason, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY tx_id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return rows

def claim_daily(user_id: int):
    """
    Grants a daily dividend if the user has not claimed within the cooldown window.
    Returns a tuple:
      (ok: bool, message: str, new_balance: int, seconds_remaining: int)
    """
    init_db()
    ensure_user(user_id)

    now = datetime.now(timezone.utc)

    with connect() as conn:
        row = conn.execute(
            "SELECT balance, last_daily_claim_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        balance = int(row["balance"])
        last = row["last_daily_claim_at"]

        if last:
            last_dt = datetime.fromisoformat(last)
            next_allowed = last_dt + timedelta(hours=DAILY_COOLDOWN_HOURS)
            if now < next_allowed:
                remaining = int((next_allowed - now).total_seconds())
                return False, "Dividends already claimed.", balance, remaining

        # Grant dividends
        new_balance = balance + DAILY_AMOUNT
        conn.execute(
            "UPDATE users SET balance = ?, last_daily_claim_at = ? WHERE user_id = ?",
            (new_balance, now.isoformat(), user_id),
        )

        # Record the transaction
        conn.execute(
            "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, DAILY_AMOUNT, "daily_dividends", now.isoformat()),
        )

        conn.commit()

        return True, "Dividends paid.", new_balance, 0

def transfer(from_user_id: int, to_user_id: int, amount: int):
    """
    Move Warp Stones from one user to another.

    Returns: (ok: bool, message: str)
    """
    init_db()
    ensure_user(from_user_id)
    ensure_user(to_user_id)

    if amount <= 0:
        return False, "Amount must be a positive number."

    if from_user_id == to_user_id:
        return False, "You cannot pay yourself."

    now = datetime.now(timezone.utc).isoformat()

    with connect() as conn:
        # Start a transaction that locks the DB for writes.
        # This prevents two transfers happening at the same time from corrupting balances.
        conn.execute("BEGIN IMMEDIATE")

        from_row = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (from_user_id,),
        ).fetchone()

        to_row = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (to_user_id,),
        ).fetchone()

        from_balance = int(from_row["balance"])
        to_balance = int(to_row["balance"])

        if from_balance < amount:
            conn.execute("ROLLBACK")
            return False, "Insufficient Warp Stones."

        new_from = from_balance - amount
        new_to = to_balance + amount

        # Update both balances
        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (new_from, from_user_id),
        )
        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (new_to, to_user_id),
        )

        # Log both sides in transactions
        conn.execute(
            "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (from_user_id, -amount, f"transfer_to:{to_user_id}", now),
        )
        conn.execute(
            "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (to_user_id, amount, f"transfer_from:{from_user_id}", now),
        )

        conn.commit()

    return True, "Transfer complete."

def grant(user_id: int, amount: int, reason: str = "admin_grant"):
    """
    Adds (or subtracts) Warp Stones from a user's balance and logs it.
    Returns: (ok: bool, message: str, new_balance: int)
    """
    init_db()
    ensure_user(user_id)

    if amount == 0:
        return False, "Amount must not be zero.", get_balance(user_id)

    now = datetime.now(timezone.utc).isoformat()

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        balance = int(row["balance"])
        new_balance = balance + amount

        if new_balance < 0:
            conn.execute("ROLLBACK")
            return False, "That would put the balance below zero.", balance

        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (new_balance, user_id),
        )

        conn.execute(
            "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, amount, reason, now),
        )

        conn.commit()

    return True, "Granted.", new_balance


def set_balance(user_id: int, new_balance: int, reason: str = "admin_set_balance"):
    """
    Sets a user's balance to an exact value and logs the delta as a transaction.
    Returns: (ok: bool, message: str, final_balance: int, delta: int)
    """
    init_db()
    ensure_user(user_id)

    if new_balance < 0:
        return False, "Balance cannot be negative.", get_balance(user_id), 0

    now = datetime.now(timezone.utc).isoformat()

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        old_balance = int(row["balance"])
        delta = new_balance - old_balance

        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (new_balance, user_id),
        )

        # Log the difference so your ledger still reconciles
        conn.execute(
            "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, delta, reason, now),
        )

        conn.commit()

    return True, "Balance set.", new_balance, delta

def backfill_starting_transactions() -> int:
    """
    For any user that has no transactions, create a starting_balance transaction
    equal to their current balance.
    Returns the number of users backfilled.
    """
    init_db()

    with connect() as conn:
        users = conn.execute(
            """
            SELECT u.user_id, u.balance, u.created_at
            FROM users u
            LEFT JOIN transactions t ON t.user_id = u.user_id
            WHERE t.user_id IS NULL
            """
        ).fetchall()

        count = 0
        for row in users:
            conn.execute(
                "INSERT INTO transactions (user_id, amount, reason, created_at) VALUES (?, ?, ?, ?)",
            (
            int(row["user_id"]),
            int(row["balance"]),
            "starting_balance_backfill",
            str(row["created_at"]),
            ),
        )
            count += 1

        conn.commit()
        return count