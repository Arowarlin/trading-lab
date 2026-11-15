"""Registro de EAs externos de MT5 que el laboratorio solo observa.

El EA vive y opera dentro de MetaTrader 5. TradingLab no lo lanza, no lo
activa y no envía órdenes por él; solo guarda su identidad, su magic y su
setfile para que el Diario, el TCA y la consola sepan qué posiciones son suyas.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import DEFAULT_DB, ROOT
from .db import connect, init_db

CONFIG_PATH = ROOT / "config" / "mt5_eas.yaml"
EA_PREFIX = "ea:"


class EAError(ValueError):
    pass


@dataclass(frozen=True)
class ExternalEA:
    id: str
    name: str
    platform: str
    account: str
    symbol: str
    magic: int
    managed_magics: tuple[int, ...]
    strategy: str
    timeframe: str
    enabled: bool
    status: str
    setfile: Path
    experts_dir: Path
    notes: str = ""

    @property
    def bot_id(self) -> str:
        return f"{EA_PREFIX}{self.id}"

    def files(self) -> dict:
        return {
            "setfile": self.setfile.exists(),
            "mq5": (self.experts_dir / "US100_EA.mq5").exists(),
            "ex5": (self.experts_dir / "US100_EA.ex5").exists(),
            "experts_dir": self.experts_dir.exists(),
        }


def load_eas(path: str | Path | None = None) -> list[ExternalEA]:
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        return []
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    items = raw.get("eas") or []
    if not isinstance(items, list):
        raise EAError("mt5_eas.yaml: `eas` debe ser una lista")
    out: list[ExternalEA] = []
    ids: set[str] = set()
    magics: set[int] = set()
    from .accounts import load_accounts

    try:
        known_accounts = load_accounts()
    except Exception as exc:
        raise EAError(f"no se pudo leer accounts.yaml: {exc}") from exc
    for item in items:
        if not isinstance(item, dict):
            raise EAError("EA inválido")
        ea_id = str(item.get("id") or "").strip()
        if not ea_id or ea_id in ids:
            raise EAError(f"id de EA vacío o duplicado: {ea_id!r}")
        ids.add(ea_id)
        platform = str(item.get("platform") or "mt5").strip().lower()
        if platform != "mt5":
            raise EAError(f"{ea_id}: solo se admite platform=mt5")
        account = str(item.get("account") or "").strip()
        if not account:
            raise EAError(f"{ea_id}: falta account")
        if account not in known_accounts:
            raise EAError(f"{ea_id}: cuenta desconocida: {account}")
        magic = int(item.get("magic") or 0)
        if magic <= 0 or magic in magics:
            raise EAError(f"{ea_id}: magic inválido o duplicado")
        magics.add(magic)
        managed = tuple(
            int(value)
            for value in (item.get("managed_magics") or [magic])
        )
        setfile = Path(str(item.get("setfile") or ""))
        experts = Path(str(item.get("experts_dir") or ""))
        out.append(
            ExternalEA(
                id=ea_id,
                name=str(item.get("name") or ea_id),
                platform=platform,
                account=account,
                symbol=str(item.get("symbol") or "US100.cash"),
                magic=magic,
                managed_magics=managed,
                strategy=str(item.get("strategy") or "external_mt5"),
                timeframe=str(item.get("timeframe") or "M5").upper(),
                enabled=bool(item.get("enabled", False)),
                status=str(item.get("status") or "demo"),
                setfile=setfile,
                experts_dir=experts,
                notes=str(item.get("notes") or ""),
            )
        )
    return out


def get_ea(ea_id: str, path: str | Path | None = None) -> ExternalEA | None:
    return next((ea for ea in load_eas(path) if ea.id == ea_id), None)


def ea_magic_map(path: str | Path | None = None) -> dict[int, str]:
    return {ea.magic: ea.bot_id for ea in load_eas(path)}


def _last_fills(ea: ExternalEA, db_path: str | Path, limit: int = 5) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT ts, symbol, side, qty, price, deal_id FROM fills "
            "WHERE bot = ? ORDER BY id DESC LIMIT ?",
            (ea.bot_id, int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def status(
    ea: ExternalEA,
    *,
    db_path: str | Path = DEFAULT_DB,
    broker=None,
) -> dict:
    files = ea.files()
    positions = []
    if broker is not None:
        try:
            positions = [
                item
                for item in broker.positions()
                if int(item.get("magic") or 0) == ea.magic
            ]
        except Exception:
            positions = []
    fills = _last_fills(ea, db_path)
    return {
        "id": ea.id,
        "name": ea.name,
        "symbol": ea.symbol,
        "magic": ea.magic,
        "strategy": ea.strategy,
        "timeframe": ea.timeframe,
        "enabled": ea.enabled,
        "status": ea.status,
        "setfile": str(ea.setfile),
        "experts_dir": str(ea.experts_dir),
        "files": files,
        "positions": positions,
        "open_positions": len(positions),
        "last_fills": fills,
        "notes": ea.notes,
    }


def as_bot_row(ea: ExternalEA, *, db_path: str | Path = DEFAULT_DB) -> dict:
    fills = _last_fills(ea, db_path, limit=1)
    actions = []
    if fills:
        fill = fills[0]
        actions.append(
            {
                "ticker": fill["symbol"],
                "status": "filled",
                "delta": fill["qty"],
                "price": fill["price"],
            }
        )
    return {
        "id": ea.id,
        "type": "external_mt5",
        "strategy": ea.strategy,
        "universe": [ea.symbol],
        "timeframe": ea.timeframe,
        "enabled": ea.enabled,
        "archived": False,
        "proposed": False,
        "external": True,
        "exposure": 1.0,
        "magic": ea.magic,
        "description": ea.notes or f"EA externo {ea.name} en {ea.symbol}",
        "last_actions": actions,
        "evaluation": None,
    }


__all__ = [
    "CONFIG_PATH",
    "EAError",
    "EA_PREFIX",
    "ExternalEA",
    "as_bot_row",
    "ea_magic_map",
    "get_ea",
    "load_eas",
    "status",
]
