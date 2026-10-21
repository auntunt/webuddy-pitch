"""sqlite3 compatibility for tests that must run on the deployment target (Python 3.8–3.10).

``sqlite3.SQLITE_*`` result codes and ``OperationalError.sqlite_errorcode`` only appeared in
CPython 3.11. The platform's own code does not need them; only the concurrency tests assert
*why* a writer was rejected (busy vs. denied). Keep that assertion on older interpreters by
mapping the same stable SQLite C result codes and falling back to the exception text, which
is what the C library reports anyway ("database is locked" / "not authorized").
"""
import sqlite3

# Stable sqlite3.h result/authorizer codes (identical in every SQLite version).
SQLITE_OK = 0
SQLITE_DENY = 1
SQLITE_BUSY = 5
SQLITE_AUTH = 23
SQLITE_ALTER_TABLE = 26

# Python 3.11+ exposes the real constants; use them when present so a drift is caught.
SQLITE_OK = getattr(sqlite3, "SQLITE_OK", SQLITE_OK)
SQLITE_DENY = getattr(sqlite3, "SQLITE_DENY", SQLITE_DENY)
SQLITE_BUSY = getattr(sqlite3, "SQLITE_BUSY", SQLITE_BUSY)
SQLITE_AUTH = getattr(sqlite3, "SQLITE_AUTH", SQLITE_AUTH)
SQLITE_ALTER_TABLE = getattr(sqlite3, "SQLITE_ALTER_TABLE", SQLITE_ALTER_TABLE)


def error_code(exc):
    """The SQLite result code behind an exception, or None where CPython does not expose it (<3.11)."""
    return getattr(exc, "sqlite_errorcode", None)


def is_busy(exc):
    """True when the writer was rejected because another connection holds the lock."""
    code = error_code(exc)
    if code is not None:
        return code == SQLITE_BUSY
    return "locked" in str(exc).lower()


def is_auth_denied(exc):
    """True when a SQLite authorizer vetoed the statement (CPython <3.11 reports only the text)."""
    code = error_code(exc)
    if code is not None:
        return code == SQLITE_AUTH
    return "not authorized" in str(exc).lower() or "authoriz" in str(exc).lower()
