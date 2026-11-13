from __future__ import annotations

from pathlib import Path

import yaml


def _config() -> dict:
    path = Path(__file__).resolve().parents[1] / "config" / "vector" / "vector.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_fuentes_y_codificacion_mt5():
    config = _config()
    sources = config["sources"]
    assert config["data_dir"].endswith("data/vector")
    assert "lab_logs" in sources
    assert sources["mt5_terminal"]["encoding"]["charset"] == "utf-16le"
    assert sources["mt5_experts"]["encoding"]["charset"] == "utf-16le"
    assert "tradinglab_guardian.log" in sources["guardian"]["include"][0]
    assert (
        sources["task_scheduler"]["channels"][0]
        == "Microsoft-Windows-TaskScheduler/Operational"
    )
    assert sources["task_scheduler"]["type"] == "windows_event_log"


def test_destinos_locales_sin_red():
    config = _config()
    sinks = config["sinks"]
    assert set(sinks) == {"all", "alerts"}
    assert all(item["type"] == "file" for item in sinks.values())
    assert "all-%Y-%m-%d.jsonl" in sinks["all"]["path"]
    assert sinks["alerts"]["path"].endswith("alerts.jsonl")
    assert "alert" not in {item["type"] for item in sinks.values()}


def test_clasificacion_cubre_patrones():
    config = _config()
    vrl = config["transforms"]["classify"]["source"]
    for text in (
        "traceback",
        "autotrading disabled",
        "guardian_trigger",
        "order_reject_10016",
        "task_result_nonzero",
        "requote",
        "reconnect",
        "mt5_connection",
    ):
        assert text in vrl
    assert config["transforms"]["alerts_only"]["condition"]
    assert ".severity" in config["transforms"]["alerts_only"]["condition"]


def test_tests_nativos_de_vector():
    config = _config()
    tests = config["tests"]
    names = {item["name"] for item in tests}
    assert "critical traceback" in names
    assert "critical order rejection" in names
    assert "critical task result nonzero" in names
    assert "warn requote" in names
    assert "normal line does not alert" in names
    normal = next(item for item in tests if item["name"] == "normal line does not alert")
    assert normal["no_outputs_from"] == ["alerts_only"]
    for item in tests:
        for entry in item["inputs"]:
            assert entry["insert_at"] == "classify"


def test_script_de_test_y_copia_del_config():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "vector_test.ps1").read_text(encoding="utf-8")
    assert "vector test" in script
    assert "config\\vector\\vector.yaml" in script
    install = (root / "scripts" / "vector_install.ps1").read_text(encoding="utf-8")
    assert "0.61.0" in install
    assert "3ac167f226204e141d164c6218ae54a2df77dda1b3322bef4b565d4066c4cfad" in install
