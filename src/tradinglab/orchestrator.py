from __future__ import annotations

import inspect
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .alerts import send as send_alert
from .config import DEFAULT_DB, ROOT, Settings
from .data import fetch
from .db import connect, utcnow
from .indicators import atr
from .killswitch import allows_order
from .killswitch import ensure as ensure_killswitch
from .risk import check_order, size_position
from .strategies import STRATEGIES

BOTS_FILE = ROOT / "config" / "bots.yaml"
ARCHIVE_FILE = ROOT / "config" / "bots_archive.yaml"


@dataclass
class BotSpec:
    id: str
    type: str
    strategy: str
    universe: list[str]
    timeframe: str = "1d"
    enabled: bool = False
    params: dict = field(default_factory=dict)
    description: str = ""
    exposure: float = 1.0
    archived: bool = False


@dataclass
class BotAction:
    bot: str
    ticker: str
    target: float
    price: float
    held: float
    desired: int
    delta: int
    status: str
    detail: str = ""
    order: dict | None = None


def load_archive_ids(path: Path | None = None) -> set[str]:
    path = path or ARCHIVE_FILE
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(x) for x in raw.get("archived", [])}


def load_bots(path: Path | None = None) -> list[BotSpec]:
    path = path or BOTS_FILE
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    archived = load_archive_ids()
    bots = []
    for item in raw.get("bots", []):
        bots.append(
            BotSpec(
                id=item["id"],
                type=item.get("type", "deterministic"),
                strategy=item["strategy"],
                universe=[t.upper() for t in item.get("universe", [])],
                timeframe=item.get("timeframe", "1d"),
                enabled=bool(item.get("enabled", False)),
                params=item.get("params", {}) or {},
                description=item.get("description", ""),
                exposure=float(item.get("exposure", 1.0)),
                archived=item["id"] in archived,
            )
        )
    return bots


def _filtered_params(func, params: dict) -> dict:
    allowed = set(inspect.signature(func).parameters)
    return {k: v for k, v in params.items() if k in allowed}


def run_bot(
    spec: BotSpec,
    settings: Settings,
    broker,
    *,
    dry_run: bool = False,
    start: str | None = None,
) -> list[BotAction]:
    """Evalúa un bot sobre su universo y ejecuta (o simula) los cambios."""
    if spec.strategy not in STRATEGIES:
        raise ValueError(f"Estrategia desconocida en bot {spec.id}: {spec.strategy}")

    from datetime import date, timedelta

    start = start or (date.today() - timedelta(days=365 * 8)).isoformat()
    today = date.today().isoformat()
    strategy_fn = STRATEGIES[spec.strategy]
    params = _filtered_params(strategy_fn, spec.params)

    actions: list[BotAction] = []
    snap = broker.snapshot({})
    ks, _ = ensure_killswitch(
        DEFAULT_DB,
        broker.equity_series(),
        settings.risk,
        current=snap["equity"],
        tz=settings.timezone,
    )

    for ticker in spec.universe:
        try:
            df = fetch(ticker, start, today, settings.data.cache_dir)
            result = strategy_fn(df, **params)
            price = float(df["close"].iloc[-1])
            atr_value = float(atr(df).iloc[-1])
            target = float(result.target.iloc[-1])
        except Exception as exc:
            actions.append(
                BotAction(spec.id, ticker, 0.0, 0.0, 0.0, 0, 0, "error", str(exc)[:200])
            )
            continue

        snap = broker.snapshot({ticker: price})
        held = next((p["qty"] for p in snap["positions"] if p["ticker"] == ticker), 0.0)

        if not dry_run:
            try:
                with connect(DEFAULT_DB) as con:
                    con.execute(
                        "INSERT INTO signals(ts, ticker, bot, side, strength, price, reason) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (
                            utcnow(),
                            ticker,
                            spec.id,
                            "long" if target > 0 else "flat",
                            target,
                            price,
                            f"target={target:.2f}",
                        ),
                    )
            except Exception:
                pass

        if target > 0:
            max_pct = settings.risk.max_position_pct * max(0.0, min(spec.exposure, 1.0))
            desired = size_position(
                snap["equity"],
                price,
                atr_value,
                settings.risk,
                max_pct=max_pct,
            )
        else:
            desired = 0

        delta = int(desired - held)
        action = BotAction(spec.id, ticker, target, price, held, desired, delta, "sin_cambios")

        if delta == 0:
            actions.append(action)
            continue

        if not allows_order(ks, delta):
            action.status = "bloqueado"
            action.detail = f"kill switch: {ks.reason}"
            actions.append(action)
            send_alert(
                "killswitch_block",
                f"{spec.id}/{ticker}: {ks.reason}",
                severity="warning",
            )
            continue

        if delta > 0:
            check = check_order(
                equity=snap["equity"],
                cash=snap["cash"],
                price=price,
                qty=delta,
                current_positions=len(snap["positions"]),
                gross_exposure=snap["positions_value"],
                cfg=settings.risk,
            )
            if not check.approved or check.qty <= 0:
                action.status = "bloqueado"
                action.detail = check.reason
                actions.append(action)
                send_alert(
                    "guard_block",
                    f"{spec.id}/{ticker}: {check.reason}",
                    severity="warning",
                )
                continue
            if check.qty < delta:
                action.detail = check.reason
            delta = check.qty
            action.delta = delta

        if dry_run:
            action.status = "dry_run"
            actions.append(action)
            continue

        try:
            order = broker.submit_market(
                ticker, delta, price, bot=spec.id, reason=f"target={target:.2f}"
            )
            action.status = "ejecutado"
            action.order = order
        except Exception as exc:
            action.status = "error"
            action.detail = str(exc)[:200]

        actions.append(action)

    return actions


def run_all(
    settings: Settings,
    broker,
    *,
    only: str | None = None,
    dry_run: bool = False,
    include_disabled: bool = False,
) -> list[BotAction]:
    actions: list[BotAction] = []
    for spec in load_bots():
        if only and spec.id != only:
            continue
        if spec.archived:
            continue
        if not spec.enabled and not include_disabled:
            continue
        if spec.type not in ("deterministic", "hybrid"):
            continue
        actions.extend(run_bot(spec, settings, broker, dry_run=dry_run))
    return actions


def write_dry_run_log(
    actions: list[BotAction],
    out_dir: str | Path,
    *,
    broker: str,
    when: datetime | None = None,
) -> str:
    """Persiste un dry-run en JSON para revisar la fase paper sin órdenes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = when or datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "broker": broker,
        "dry_run": True,
        "actions": [asdict(a) for a in actions],
    }
    path = out / f"dryrun_{now.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


__all__ = [
    "BotAction",
    "BotSpec",
    "load_archive_ids",
    "load_bots",
    "run_all",
    "run_bot",
    "write_dry_run_log",
]
