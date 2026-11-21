from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / "src" / "tradinglab" / "discovery"
MANIFEST = ROOT / "config" / "propfund" / "protected_manifest.json"

FORBIDDEN_CALLS = {"submit_market", "close_position", "modify_position"}
ALLOWED_EXECUTION_MODULES = {
    "execution.mt5_offsets",
    "tradinglab.execution.mt5_offsets",
}


def _discovery_sources() -> list[Path]:
    return sorted(DISCOVERY.rglob("*.py"))


def test_importar_discovery_no_importa_execution() -> None:
    code = (
        "import sys; import tradinglab.discovery; "
        "print('tradinglab.execution' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"


def test_discovery_no_importa_ni_llama_funciones_de_ordenes() -> None:
    for path in _discovery_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("tradinglab.execution"), path
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module not in ALLOWED_EXECUTION_MODULES:
                    assert not module.startswith("tradinglab.execution"), path
                    assert not module.startswith("execution"), path
            elif isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None)
                assert name not in FORBIDDEN_CALLS, f"{path}: {name}"


def test_discovery_no_escribe_rutas_protegidas() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    protected = sorted(
        {rel for group in manifest.get("groups", {}).values() for rel in group.get("files", {})}
    )
    assert protected
    for path in _discovery_sources():
        text = path.read_text(encoding="utf-8")
        for rel in protected:
            assert rel not in text, f"{path} menciona {rel}"


def test_discovery_no_abre_archivos_para_escritura() -> None:
    for path in _discovery_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                modes = [kw.value.value for kw in node.keywords if kw.arg == "mode"]
                if node.args and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    modes.append(node.args[1].value)
                assert all(m not in {"w", "a", "x", "wb", "ab"} for m in modes), path
