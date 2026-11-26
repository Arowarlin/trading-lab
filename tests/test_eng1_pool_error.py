"""ENG-1 F0-06: si el worker no puede arrancar, el error lleva el motivo real.

Antes la cola abortaba con un ``BrokenProcessPool`` sin explicación y el
"Sin datos: ..." del inicializador se perdía.
"""

from __future__ import annotations

import pytest
from test_discovery_jobs import _dataset, _db, _register, _strategies

from tradinglab.discovery import jobs


def test_cola_abortada_incluye_el_motivo_del_arranque(tmp_path, monkeypatch):
    from concurrent.futures.process import BrokenProcessPool

    class _BrokenPool:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, *args, **kwargs):
            raise BrokenProcessPool("A child process terminated abruptly")

    db = _db(tmp_path)
    _register(db, _dataset())
    jobs.enqueue("camp", _strategies(2), db_path=db)
    monkeypatch.setattr(jobs, "ProcessPoolExecutor", _BrokenPool)
    monkeypatch.setattr(
        jobs, "_init_failure_reason", lambda payload: "ValueError: Sin datos: broker_spreads"
    )
    with pytest.raises(jobs.QueueError) as info:
        jobs.run_queue("camp", 2, db_path=db)
    message = str(info.value)
    assert "BrokenProcessPool" in message
    assert "arranque del worker: ValueError: Sin datos: broker_spreads" in message


def test_motivo_de_arranque_restaura_el_estado():
    jobs._WORKER["marca"] = 1
    reason = jobs._init_failure_reason({"bogus": True})
    assert reason
    assert jobs._WORKER.get("marca") == 1
    jobs._WORKER.pop("marca", None)
