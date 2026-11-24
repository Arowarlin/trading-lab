"""Componentes del carril FTMO: baseline de hashes SHA-256 y control de cambios.

La expansión multiempresa (``tradinglab.propfund``) se construye **alrededor**
de lo que ya funciona. Este módulo guarda un *baseline* del contenido de los
archivos de producción y permite comprobar en cualquier momento qué cambió.

El baseline **no bloquea**: informa. Cualquier cambio debe llevar su prueba de
regresión, su entrada en ``docs/CHANGELOG-produccion.md`` y su tag de rollback
(regla común 4 de ``.orquestador/tl2-audit/TL2_OPENCODE_TASKS.md``).

Grupos del baseline (identificados en la auditoría de la Fase 0, ver
``docs/propfund/01_auditoria.md``):

* ``ea_us100_ftmo1``  – EA externo ``us100-ftmo1`` (MQL5, setfile, plantilla) y
  su registro/espejo Python.
* ``ai_trader``       – carril IA discrecional (código, configuración, scripts).
* ``ftmo_forward``    – las dos estrategias forward fijas del carril FTMO
  (EURUSD ``london_pullback`` y USDJPY ``tokyo_breakout``) más la incubación
  ``us100-trend-d1`` que comparte el mismo archivo de configuración.
* ``ftmo_risk``       – reglas de fondeo, guard, defensa, guardián MT5 y stop
  diario de cuenta que protegen a los tres anteriores.

La comparación ignora CRLF/LF (el repositorio y Windows no coinciden).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import ROOT

# El archivo conserva su nombre histórico para no romper consumidores ni el
# test de aislamiento; el concepto es "baseline".
BASELINE_PATH = Path("config") / "propfund" / "protected_manifest.json"
MANIFEST_PATH = BASELINE_PATH
AUTHORIZATIONS_KEY = "authorizations"

PROTECTED_GROUPS: dict[str, dict] = {
    "ea_us100_ftmo1": {
        "description": "EA externo us100-ftmo1 (US100.cash, magics 93010001/93020001).",
        "paths": [
            "integrations/mt5/us100_ftmo1",
            "config/mt5_eas.yaml",
            "src/tradinglab/ea_registry.py",
            "src/tradinglab/ea_us100.py",
            "src/tradinglab/ea_us100_engine.py",
            "src/tradinglab/ea_forward.py",
            "src/tradinglab/ea_horizon.py",
            "docs/ea_us100_ftmo1.md",
        ],
    },
    "ai_trader": {
        "description": "Carril IA discrecional ai_trader (solo demo, cuenta ftmo_demo).",
        "paths": [
            "config/ai_trader.yaml",
            "src/tradinglab/ai_trader.py",
            "src/tradinglab/ai_session.py",
            "src/tradinglab/ai_setups.py",
            "src/tradinglab/ai_learn.py",
            "src/tradinglab/ai_distill.py",
            "src/tradinglab/ai_replay.py",
            "scripts/ai_trader_distill.ps1",
            "scripts/ai_trader_manage.ps1",
            "scripts/ai_trader_scalp.ps1",
            "scripts/ai_trader_session.ps1",
            "scripts/ai_trader_task_common.ps1",
            "scripts/register_ai_trader_tasks.ps1",
            "docs/ai_trader_opencode.md",
            "docs/ai_trader_skill.md",
            ".opencode/agents/ai-operator.md",
            ".opencode/agents/ai-replay.md",
        ],
    },
    "ftmo_forward": {
        "description": (
            "Las dos estrategias forward fijas del carril FTMO (eurusd-london-pullback-forward, "
            "usdjpy-tokyo-breakout-forward) y la incubación us100-trend-d1."
        ),
        "paths": [
            "config/intraday_forward.yaml",
            "src/tradinglab/forward_intraday.py",
            "src/tradinglab/intraday.py",
            "src/tradinglab/swing.py",
            "src/tradinglab/strategies/swing.py",
            "src/tradinglab/asset_aliases.py",
            "scripts/intraday_forward_execute.ps1",
            "scripts/intraday_forward_signal.ps1",
        ],
    },
    "ftmo_risk": {
        "description": "Reglas de fondeo, guard, defensa, guardián MT5 y stop diario de cuenta.",
        "paths": [
            "src/tradinglab/prop",
            "src/tradinglab/guardian.py",
            "src/tradinglab/account_daily.py",
            "src/tradinglab/symbol_risk.py",
            "src/tradinglab/execution/mt5.py",
            "src/tradinglab/execution/mt5_offsets.py",
            "mql5/TradingLabGuardian.mq5",
            "config/guardian.yaml",
            "config/prop_templates.yaml",
        ],
    },
}

_SKIP_PARTS = {"__pycache__"}


@dataclass(frozen=True)
class IntegrityIssue:
    path: str
    kind: str  # changed | missing | new
    expected: str | None
    actual: str | None


def _normalised(blob: bytes) -> bytes:
    return blob.replace(b"\r\n", b"\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(_normalised(path.read_bytes())).hexdigest()


def _expand(root: Path, rel: str) -> list[Path]:
    target = root / rel
    if target.is_dir():
        return sorted(
            p for p in target.rglob("*")
            if p.is_file() and not (_SKIP_PARTS & set(p.parts)) and p.suffix != ".pyc"
        )
    return [target]


def protected_files(root: Path = ROOT) -> dict[str, list[str]]:
    """Grupo -> rutas relativas (POSIX) de cada archivo protegido."""
    out: dict[str, list[str]] = {}
    for group, spec in PROTECTED_GROUPS.items():
        files: list[str] = []
        for rel in spec["paths"]:
            for path in _expand(root, rel):
                files.append(path.relative_to(root).as_posix())
        out[group] = files
    return out


def compute_manifest(root: Path = ROOT) -> dict:
    groups: dict[str, dict] = {}
    for group, files in protected_files(root).items():
        hashes = {
            rel: (file_sha256(root / rel) if (root / rel).exists() else None)
            for rel in files
        }
        groups[group] = {
            "description": PROTECTED_GROUPS[group]["description"],
            "files": hashes,
        }
    return {"version": 1, "algorithm": "sha256 (CRLF normalizado a LF)", "groups": groups}


def load_manifest(root: Path = ROOT) -> dict | None:
    path = root / MANIFEST_PATH
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _diff(frozen: dict | None, current: dict) -> list[str]:
    """Lista legible de diferencias entre el baseline y el estado actual."""
    changes: list[str] = []
    if frozen is None:
        return changes
    for group, spec in frozen.get("groups", {}).items():
        expected = spec.get("files", {})
        actual = current["groups"].get(group, {}).get("files", {})
        for rel, digest in expected.items():
            now = actual.get(rel)
            if now is None:
                changes.append(f"{group}: {rel} (missing)")
            elif now != digest:
                changes.append(f"{group}: {rel} (changed)")
        for rel in actual:
            if rel not in expected:
                changes.append(f"{group}: {rel} (new)")
    return sorted(changes)


def write_manifest(root: Path = ROOT) -> Path:
    """Escribe el baseline sin tocar las autorizaciones.

    Se conserva por compatibilidad; el camino normal es :func:`write_baseline`,
    que además deja la autorización con fecha y motivo.
    """
    path = root / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = compute_manifest(root)
    frozen = load_manifest(root)
    if frozen and frozen.get(AUTHORIZATIONS_KEY):
        payload[AUTHORIZATIONS_KEY] = frozen[AUTHORIZATIONS_KEY]
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_baseline(reason: str, root: Path = ROOT) -> Path:
    """Reescribe el baseline y registra la autorización con fecha y motivo.

    ``changes`` guarda la diferencia con el baseline anterior, para que el
    registro diga qué se autorizó exactamente.
    """
    if not str(reason or "").strip():
        raise ValueError("el baseline exige un motivo")
    frozen = load_manifest(root)
    current = compute_manifest(root)
    changes = _diff(frozen, current)
    authorizations = list((frozen or {}).get(AUTHORIZATIONS_KEY) or [])
    authorizations.append(
        {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "reason": str(reason).strip(),
            "changes": changes,
        }
    )
    current[AUTHORIZATIONS_KEY] = authorizations
    path = root / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(current, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def verify(root: Path = ROOT) -> dict:
    """Compara el árbol de trabajo contra el baseline.

    Contrato: ``ok`` solo es ``False`` si falta el baseline. Los cambios se
    devuelven en ``changed``/``unchanged`` y en el detalle por grupo, pero no
    bloquean: el control de cambios se apoya en la autorización y la regresión.
    """
    frozen = load_manifest(root)
    if frozen is None:
        return {
            "ok": False,
            "status": "SIN_MANIFIESTO",
            "clean": False,
            "changed": [],
            "unchanged": [],
            "issues": [],
            "groups": {},
        }
    current = compute_manifest(root)
    issues: list[IntegrityIssue] = []
    changed: list[str] = []
    unchanged: list[str] = []
    groups: dict[str, dict] = {}
    for group, spec in frozen.get("groups", {}).items():
        expected = spec.get("files", {})
        actual = current["groups"].get(group, {}).get("files", {})
        group_issues: list[IntegrityIssue] = []
        group_changed: list[str] = []
        group_unchanged: list[str] = []
        for rel, digest in expected.items():
            now = actual.get(rel)
            if now is None and (root / rel).exists() is False:
                group_issues.append(IntegrityIssue(rel, "missing", digest, None))
            elif now != digest:
                group_issues.append(IntegrityIssue(rel, "changed", digest, now))
            else:
                group_unchanged.append(rel)
        for rel, digest in actual.items():
            if rel not in expected:
                group_issues.append(IntegrityIssue(rel, "new", None, digest))
        for issue in group_issues:
            (group_changed if issue.kind in {"changed", "missing", "new"} else group_unchanged).append(
                issue.path
            )
        issues.extend(group_issues)
        changed.extend(group_changed)
        unchanged.extend(group_unchanged)
        groups[group] = {
            "description": spec.get("description", ""),
            "files": len(expected),
            "ok": not group_issues,
            "changed": sorted(group_changed),
            "unchanged": sorted(group_unchanged),
            "issues": [issue.__dict__ for issue in group_issues],
        }
    return {
        "ok": True,
        "status": "SIN CAMBIOS" if not changed else "CAMBIOS",
        "clean": not changed,
        "changed": sorted(set(changed)),
        "unchanged": sorted(set(unchanged)),
        "issues": [issue.__dict__ for issue in issues],
        "groups": groups,
    }


__all__ = [
    "BASELINE_PATH",
    "MANIFEST_PATH",
    "PROTECTED_GROUPS",
    "IntegrityIssue",
    "compute_manifest",
    "file_sha256",
    "load_manifest",
    "protected_files",
    "verify",
    "write_baseline",
    "write_manifest",
]
