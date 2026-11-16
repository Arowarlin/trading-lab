from __future__ import annotations

import threading
import time

from tradinglab.db import BUSY_TIMEOUT_MS, connect, init_db


def test_connect_fija_busy_timeout(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        value = con.execute("PRAGMA busy_timeout").fetchone()[0]
    assert int(value) == BUSY_TIMEOUT_MS == 5000


def test_dos_escritores_simultaneos_sin_database_is_locked(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute("CREATE TABLE IF NOT EXISTS busy_test (id INTEGER PRIMARY KEY, value TEXT)")

    barrier = threading.Barrier(2)
    errors: list[str] = []

    def writer(value: str) -> None:
        try:
            with connect(db) as con:
                barrier.wait(timeout=5)
                con.execute("BEGIN IMMEDIATE")
                con.execute("INSERT INTO busy_test(value) VALUES (?)", (value,))
                time.sleep(0.2)
        except Exception as exc:  # pragma: no cover - el assert da el detalle
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [
        threading.Thread(target=writer, args=("uno",)),
        threading.Thread(target=writer, args=("dos",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any("database is locked" in error.lower() for error in errors), errors
    assert not errors, errors
    with connect(db) as con:
        count = con.execute("SELECT COUNT(*) FROM busy_test").fetchone()[0]
    assert count == 2
