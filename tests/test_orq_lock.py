"""E1 · Locks de coordinación entre sesiones."""

from __future__ import annotations

import json
import multiprocessing
import time
from datetime import datetime, timedelta, timezone

import pytest

from tradinglab import orq_lock


def _worker(locks_dir: str, barrier, queue, hold_s: float) -> None:
    barrier.wait(timeout=10)
    try:
        orq_lock.acquire("shared", "worker", locks_dir=locks_dir)
    except orq_lock.LockBusy:
        queue.put("busy")
        return
    queue.put("acquired")
    time.sleep(hold_s)
    orq_lock.release("shared", "worker", locks_dir=locks_dir)


def test_dos_procesos_solo_uno_gana(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=_worker,
            args=(str(tmp_path), barrier, queue, 1.0),
        )
        for _ in range(2)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(15)
        assert proc.exitcode == 0
    results = [queue.get(timeout=2) for _ in procs]
    assert sorted(results) == ["acquired", "busy"]


def test_release_mueve_y_no_borra(tmp_path):
    orq_lock.acquire("r", "a", locks_dir=tmp_path)
    assert (tmp_path / "r.lock").is_dir()
    released = orq_lock.release("r", "a", locks_dir=tmp_path)
    assert not (tmp_path / "r.lock").exists()
    assert (tmp_path / "released").is_dir()
    assert released["released"].endswith(".lock")
    assert any((tmp_path / "released").glob("r.*.lock"))


def test_otro_dueno_no_puede_liberar(tmp_path):
    orq_lock.acquire("r", "a", locks_dir=tmp_path)
    with pytest.raises(orq_lock.LockNotOwner):
        orq_lock.release("r", "b", locks_dir=tmp_path)
    assert (tmp_path / "r.lock").is_dir()


def test_lock_viejo_se_informa_y_no_se_roba(tmp_path):
    path = tmp_path / "viejo.lock"
    path.mkdir()
    started = datetime.now(timezone.utc) - timedelta(hours=3)
    (path / "owner.json").write_text(
        json.dumps(
            {
                "owner": "sesion-a",
                "cola": "COLA-A",
                "pid": 1,
                "host": "test",
                "started_at": started.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    locks = orq_lock.status(locks_dir=tmp_path)
    assert len(locks) == 1
    assert locks[0]["old"] is True
    assert locks[0]["owner"] == "sesion-a"
    with pytest.raises(orq_lock.LockBusy):
        orq_lock.acquire("viejo", "sesion-b", locks_dir=tmp_path)
    assert path.is_dir()


def test_held_libera_con_excepcion(tmp_path):
    with pytest.raises(RuntimeError, match="boom"):
        with orq_lock.held("r", "a", locks_dir=tmp_path):
            raise RuntimeError("boom")
    assert orq_lock.status(locks_dir=tmp_path) == []
    assert any((tmp_path / "released").glob("r.*.lock"))


def test_release_sin_lock(tmp_path):
    with pytest.raises(orq_lock.LockMissing):
        orq_lock.release("r", "a", locks_dir=tmp_path)
