"""ENG-F5: ``TRADINGLAB_DB`` redirige la base de datos solo si está definida.

Regresión del comportamiento anterior: sin la variable, ``DEFAULT_DB``,
``telegram.STATE_PATH`` y ``task_health.STATE_FILE`` son exactamente las rutas
de siempre bajo ``ROOT/data``. Se comprueba en subprocesos para que el entorno
de la suite (que sí define la variable) no influya.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

_PROBE = (
    "import json;"
    "from tradinglab import config, telegram, task_health;"
    "print(json.dumps({'root': str(config.ROOT), 'db': str(config.DEFAULT_DB),"
    " 'tg': str(telegram.STATE_PATH), 'th': str(task_health.STATE_FILE)}))"
)


def _probe(env_db: str | None) -> dict:
    env = {key: value for key, value in os.environ.items() if key != "TRADINGLAB_DB"}
    if env_db is not None:
        env["TRADINGLAB_DB"] = env_db
    out = subprocess.run(
        [sys.executable, "-c", _PROBE], env=env, capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_sin_variable_las_rutas_son_las_de_siempre():
    paths = _probe(None)
    root = paths["root"]
    assert paths["db"] == os.path.join(root, "data", "lab.db")
    assert paths["tg"] == os.path.join(root, "data", "telegram_state.json")
    assert paths["th"] == os.path.join(root, "data", "task_missed_seen.json")


def test_con_variable_la_db_y_el_estado_la_siguen(tmp_path):
    target = tmp_path / "otra" / "lab.db"
    paths = _probe(str(target))
    assert paths["db"] == str(target)
    assert paths["tg"] == str(target.parent / "telegram_state.json")
    assert paths["th"] == str(target.parent / "task_missed_seen.json")


def test_la_suite_no_usa_la_db_real():
    from tradinglab import config

    assert os.environ.get("TRADINGLAB_DB")
    assert config.DEFAULT_DB != config.ROOT / "data" / "lab.db"
