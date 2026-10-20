"""Complete, stable SQL snapshots without changing a live Store's row factory."""
from contextlib import closing
import sqlite3


def dump_store(store):
    # Python 3.12's iterdump consumes the connection's custom row factory.
    # A backup has default tuple rows and includes every table, row and schema
    # object. Keep the live Store locked until that consistent copy is complete.
    with store.lock:
        if store.db.in_transaction:
            raise AssertionError("database snapshot requires committed fixture state")
        with closing(sqlite3.connect(":memory:")) as snapshot:
            store.db.backup(snapshot)
            return tuple(snapshot.iterdump())
