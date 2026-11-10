"""Exporta la configuración que consume el guardián MQL5.

El EA vive dentro de MetaTrader 5 y debe seguir actuando aunque Python no esté
en marcha. Este módulo no ejecuta nada: solo valida las fuentes (cuenta,
límites efectivos y magics) y escribe un JSON pequeño en ``MQL5/Files``.

Regla dura: si falta un límite o un magic, aborta. Nunca rellena valores a
ojo.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .accounts import load_accounts, rules_for_account
from .config import CONFIG_DIR, ROOT
from .forward_intraday import load_forward_bots

GUARDIAN_VERSION = 1
GUARDIAN_FILENAME = "tradinglab_guardian.json"
GUARDIAN_GLOBAL_BLOCK = "TradingLabGuardianBlocked"


class GuardianError(RuntimeError):
    """La configuración del guardián no se puede construir o leer."""


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise GuardianError(f"falta {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise GuardianError(f"no se pudo leer {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise GuardianError(f"{path} no contiene un objeto YAML")
    return raw


def _raw_account(account_id: str, accounts_path: Path | None) -> dict:
    path = Path(accounts_path) if accounts_path else CONFIG_DIR / "accounts.yaml"
    raw = _read_yaml(path)
    accounts = raw.get("accounts") or {}
    if not isinstance(accounts, dict):
        raise GuardianError(f"{path}: 'accounts' no es un objeto")
    entry = accounts.get(account_id)
    if not isinstance(entry, dict):
        disponibles = ", ".join(sorted(str(key) for key in accounts)) or "ninguna"
        raise GuardianError(
            f"cuenta {account_id!r} no existe en {path}; disponibles: {disponibles}"
        )
    return entry


def terminal_data_path(lab_path: Path | None = None) -> Path | None:
    """Ruta de datos del terminal desde ``lab.yaml -> mt5.data_path``."""
    path = Path(lab_path) if lab_path else CONFIG_DIR / "lab.yaml"
    raw = _read_yaml(path)
    mt5 = raw.get("mt5") or {}
    if not isinstance(mt5, dict):
        raise GuardianError(f"{path}: 'mt5' no es un objeto")
    value = mt5.get("data_path")
    if value is None or not str(value).strip():
        return None
    return Path(str(value)).expanduser()


def resolve_target(
    *,
    lab_path: Path | None = None,
    target_path: Path | None = None,
    fallback_dir: Path | None = None,
) -> tuple[Path, bool, str | None]:
    """Devuelve (ruta, es_fallback, aviso)."""
    if target_path is not None:
        return Path(target_path), False, None
    data_path = terminal_data_path(lab_path)
    if data_path is None:
        base = Path(fallback_dir) if fallback_dir else ROOT / "data"
        target = base / "guardian.json"
        warning = (
            "falta mt5.data_path en config/lab.yaml; escribo en "
            f"{target}. Copia el JSON a MQL5/Files o configura esa clave."
        )
        return target, True, warning
    return data_path / "MQL5" / "Files" / GUARDIAN_FILENAME, False, None


def build_config(
    account_id: str = "ftmo_demo",
    *,
    accounts_path: Path | None = None,
    forward_path: Path | None = None,
) -> dict:
    """Construye y valida el JSON; no escribe nada."""
    raw_account = _raw_account(account_id, accounts_path)
    accounts = load_accounts(accounts_path)
    account = accounts.get(account_id)
    if account is None:
        raise GuardianError(f"cuenta {account_id!r} no cargable desde accounts.yaml")
    if account.account_size <= 0:
        raise GuardianError(f"{account_id}: account_size debe ser > 0")

    if account.type == "fondeo":
        if not account.firm or not account.phase:
            raise GuardianError(
                f"{account_id}: cuenta de fondeo sin firm/phase; no se inventan límites"
            )
        try:
            rules = rules_for_account(account)
        except Exception as exc:
            raise GuardianError(
                f"{account_id}: no se pudieron cargar las reglas de {account.firm}/{account.phase}: {exc}"
            ) from exc
        daily = rules.effective_daily_limit_usd / rules.account_size
        max_dd = rules.effective_max_loss_usd / rules.account_size
        limits_source = f"prop.yaml:{account.firm}/{account.phase}:effective"
    else:
        limits = raw_account.get("limits")
        if not isinstance(limits, dict):
            raise GuardianError(
                f"{account_id}: falta 'limits' en accounts.yaml; no se inventan límites"
            )
        missing = [
            key
            for key in ("daily_loss_pct", "max_drawdown_pct")
            if limits.get(key) is None
        ]
        if missing:
            raise GuardianError(
                f"{account_id}: faltan límites en accounts.yaml: {', '.join(missing)}"
            )
        daily = float(limits["daily_loss_pct"])
        max_dd = float(limits["max_drawdown_pct"])
        rules = rules_for_account(account)
        limits_source = "accounts.yaml:limits"

    if not 0.0 < daily < 1.0:
        raise GuardianError(f"{account_id}: daily_loss_pct inválido ({daily!r})")
    if not 0.0 < max_dd < 1.0:
        raise GuardianError(f"{account_id}: max_drawdown_pct inválido ({max_dd!r})")
    reset_tz = str(rules.reset_tz or "").strip()
    if not reset_tz:
        raise GuardianError(f"{account_id}: reset_tz vacío")
    reset_time = str(rules.reset_time or "").strip()
    if not reset_time:
        raise GuardianError(f"{account_id}: reset_time vacío")
    try:
        offset = datetime.now(ZoneInfo(reset_tz)).utcoffset()
    except ZoneInfoNotFoundError as exc:
        raise GuardianError(f"{account_id}: zona horaria desconocida {reset_tz!r}") from exc
    if offset is None:
        raise GuardianError(f"{account_id}: no se pudo calcular el offset de {reset_tz}")
    offset_minutes = int(offset.total_seconds() // 60)

    try:
        bots = load_forward_bots(forward_path)
    except Exception as exc:
        raise GuardianError(f"no se pudieron cargar los magics forward: {exc}") from exc
    magics = sorted({int(bot.magic) for bot in bots})
    if not magics:
        raise GuardianError("intraday_forward.yaml no tiene magics que proteger")

    return {
        "version": GUARDIAN_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "account": account_id,
        "account_size": float(account.account_size),
        "daily_loss_pct": float(daily),
        "max_drawdown_pct": float(max_dd),
        "reset_tz": reset_tz,
        "reset_time": reset_time,
        "reset_utc_offset_minutes": offset_minutes,
        "magics": magics,
        "bots": [bot.id for bot in bots],
        "limits_source": limits_source,
    }


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def export_config(
    account_id: str = "ftmo_demo",
    *,
    accounts_path: Path | None = None,
    forward_path: Path | None = None,
    lab_path: Path | None = None,
    target_path: Path | None = None,
    fallback_dir: Path | None = None,
) -> dict:
    """Valida y escribe el JSON del guardián. Devuelve ruta y aviso."""
    payload = build_config(
        account_id, accounts_path=accounts_path, forward_path=forward_path
    )
    target, fallback, warning = resolve_target(
        lab_path=lab_path, target_path=target_path, fallback_dir=fallback_dir
    )
    try:
        _write_atomic(target, payload)
    except OSError as exc:
        raise GuardianError(f"no se pudo escribir {target}: {exc}") from exc
    return {
        "path": str(target),
        "fallback": fallback,
        "warning": warning,
        "config": payload,
    }


def read_exported(
    *,
    lab_path: Path | None = None,
    target_path: Path | None = None,
    fallback_dir: Path | None = None,
) -> dict:
    """Lee el último JSON exportado; ``exists=False`` si aún no hay."""
    target, fallback, warning = resolve_target(
        lab_path=lab_path, target_path=target_path, fallback_dir=fallback_dir
    )
    result: dict[str, Any] = {
        "path": str(target),
        "fallback": fallback,
        "warning": warning,
        "exists": target.exists(),
        "age_s": None,
        "config": None,
    }
    if not target.exists():
        return result
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GuardianError(f"JSON inválido en {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GuardianError(f"{target} no contiene un objeto JSON")
    result["config"] = payload
    generated = payload.get("generated_at")
    if generated:
        try:
            stamp = datetime.fromisoformat(str(generated))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            result["age_s"] = max(
                0.0, (datetime.now(timezone.utc) - stamp).total_seconds()
            )
        except ValueError:
            result["age_s"] = None
    return result


__all__ = [
    "GUARDIAN_FILENAME",
    "GUARDIAN_GLOBAL_BLOCK",
    "GUARDIAN_VERSION",
    "GuardianError",
    "build_config",
    "export_config",
    "read_exported",
    "resolve_target",
    "terminal_data_path",
]
