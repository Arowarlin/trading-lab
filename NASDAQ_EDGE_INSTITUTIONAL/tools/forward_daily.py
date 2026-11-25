"""F5 · registro diario del forward NQEDGE (sin resultados).

Lee el dia cerrado (M1 de US100.cash, MT5 attach-only con login verificado),
aplica las variantes congeladas y anade filas al ledger append-only.

**No calcula ni imprime P&L, R, PF, win rate ni medias.** Guarda precios,
contratos y motivo de salida; el R se calcula solo en F7. La comision MNQ es
obligatoria: sin ella, `bloqueado: falta comision MNQ del operador`.

Uso:
  python tools/forward_daily.py --commission-side-usd 1.25
  python tools/forward_daily.py --date 2026-12-01 --commission-side-usd 1.25
  python tools/forward_daily.py --source csv --csv dia.csv --commission-side-usd 1.25
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import math
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
LEDGER = PROJ / "04_FORWARD/ledger.csv"
MODELS = PROJ / "tools/forward_models.py"
SYMBOL = "US100.cash"
NY = "America/New_York"
FIELDS = [
    "date", "variant", "entry_min", "side", "entry", "stop", "target",
    "contracts", "exit_min", "exit_price", "exit_reason",
    "commission_side_usd", "slip_ticks", "source", "models_sha256", "daily_sha256",
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fm = _load("forward_models", MODELS)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Costs:
    commission_side_usd: float
    slip_ticks: float = 1.0


@dataclass
class DayResult:
    rows: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {
        "signals": 0, "news": 0, "target_lt": 0, "bad_stop": 0, "no_trade": 0,
    })


def session_from_frame(frame: pd.DataFrame, day: str) -> dict | None:
    """Convierte M1 UTC/NY de un dia en la sesion que comen los modelos."""
    df = frame.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    local = df.tz_convert(NY)
    target = pd.Timestamp(day).date()
    rth = local[(local.index.date == target)]
    rth = rth[(rth.index.hour * 60 + rth.index.minute >= 570)
              & (rth.index.hour * 60 + rth.index.minute < 960)]
    if len(rth) < 380:
        return None
    mins = (rth.index.hour * 60 + rth.index.minute).to_numpy()
    if mins[-1] < 955:
        return None
    prev_day = last_complete_session(target)
    prev = local[
        (local.index >= pd.Timestamp(prev_day, tz=NY) + pd.Timedelta(hours=18))
        & (local.index < pd.Timestamp(target, tz=NY) + pd.Timedelta(hours=9, minutes=30))
    ]
    overnight_ok = len(prev) > 60
    return {
        "day": str(target),
        "excluded": False,
        "t": mins,
        "o": rth["open"].to_numpy(dtype=float),
        "h": rth["high"].to_numpy(dtype=float),
        "l": rth["low"].to_numpy(dtype=float),
        "c": rth["close"].to_numpy(dtype=float),
        "v": rth["volume"].to_numpy(dtype=float) if "volume" in rth else np.ones(len(rth)),
        "onh": float(prev["high"].max()) if overnight_ok else math.nan,
        "onl": float(prev["low"].min()) if overnight_ok else math.nan,
        "pdh": math.nan,
        "pdl": math.nan,
        "pre_excluded": True,
    }


def build_day(sessions: list[dict], costs: Costs, variants=None) -> DayResult:
    fomc, tier1 = fm.load_news(PROJ)
    prepared = fm.prepare_sessions(sessions)
    today = prepared[-1]
    result = DayResult()
    for variant in variants or fm.VARIANTS:
        kept = []
        for s in fm.signals_for(today, variant):
            result.counts["signals"] += 1
            reason = fm.news_reason(today["day"], s.entry_min, fomc, tier1)
            if reason is not None:
                result.counts["news"] += 1
                continue
            j = int(np.searchsorted(today["t"], s.entry_min))
            if j >= len(today["t"]):
                continue
            entry = float(today["o"][j])
            stop_pt = abs(entry - s.stop)
            if stop_pt < 2 * fm.TICK:
                result.counts["bad_stop"] += 1
                continue
            if s.target is not None and (s.target - entry) * s.side < stop_pt:
                result.counts["target_lt"] += 1
                continue
            contracts = fm.contracts_for_risk(stop_pt, costs.commission_side_usd,
                                              slip_ticks=costs.slip_ticks)
            if contracts < 1:
                result.counts["no_trade"] += 1
                continue
            kept.append((s, contracts))
        for s, contracts in kept[:3]:
            news_exit = fm.news_exit_minute(today["day"], tier1)
            ex = fm.execute_signal(
                today, s, contracts=contracts, slip_ticks=costs.slip_ticks,
                news_exit=news_exit,
            )
            if ex is None:
                result.counts["target_lt"] += 1
                continue
            result.rows.append({
                "date": today["day"],
                "variant": variant,
                "entry_min": ex.entry_min,
                "side": s.side,
                "entry": round(ex.entry, 4),
                "stop": round(ex.stop, 4),
                "target": round(ex.target, 4),
                "contracts": contracts,
                "exit_min": ex.exit_min,
                "exit_price": round(ex.exit_price, 4),
                "exit_reason": ex.reason,
                "commission_side_usd": costs.commission_side_usd,
                "slip_ticks": costs.slip_ticks,
                "source": "",
                "models_sha256": "",
                "daily_sha256": "",
            })
    return result


def append_ledger(rows: list[dict], source: str, daily_hash: str) -> int:
    LEDGER.parent.mkdir(exist_ok=True)
    existing = set()
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                existing.add((row["date"], row["variant"], row["entry_min"]))
    new = 0
    with LEDGER.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if not LEDGER.exists() or LEDGER.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            key = (row["date"], row["variant"], str(row["entry_min"]))
            if key in existing:
                continue
            row = dict(row, source=source, models_sha256=sha256(MODELS),
                       daily_sha256=daily_hash)
            writer.writerow(row)
            existing.add(key)
            new += 1
    return new


def ledger_stats(path: Path | None = None) -> dict[str, dict]:
    path = path or LEDGER
    out: dict[str, dict] = {
        v: {"n": 0, "first": None, "last": None} for v in fm.VARIANTS
    }
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            item = out.setdefault(row["variant"], {"n": 0, "first": None, "last": None})
            item["n"] += 1
            d = row["date"]
            item["first"] = d if item["first"] is None or d < item["first"] else item["first"]
            item["last"] = d if item["last"] is None or d > item["last"] else item["last"]
    return out


def estimate(n: int, first: str | None, last: str | None) -> str | None:
    remaining = max(0, 200 - n)
    if remaining == 0:
        return "alcanzado"
    if n <= 0 or first is None or last is None:
        return None
    span = max(1, (date.fromisoformat(last) - date.fromisoformat(first)).days + 1)
    per_day = n / span
    days = int(math.ceil(remaining / per_day))
    return str((date.fromisoformat(last) + timedelta(days=days)).isoformat())


def last_complete_session(day: date | None = None) -> date:
    from tradinglab.discovery import calendars as cal

    d = (day or pd.Timestamp.now(tz=NY).date()) - timedelta(days=1)
    for _ in range(14):
        if d.weekday() < 5 and not cal.is_holiday(cal.NYSE, d) \
                and cal.early_close_hhmm(cal.NYSE, d) is None:
            return d
        d -= timedelta(days=1)
    raise SystemExit("Sin datos: no encuentro una sesion NYSE completa reciente")


def read_mt5(day: date, *, account_id: str = "CFD-001") -> tuple[pd.DataFrame, str]:
    from tradinglab.accounts import load_accounts
    from tradinglab.propfund.snapshots import default_broker_factory

    account = load_accounts().get(account_id)
    if account is None:
        raise SystemExit(f"Sin datos: cuenta {account_id} no encontrada")
    broker = default_broker_factory(account)
    health = broker.connect() or {}
    if not health.get("identity_ok"):
        raise SystemExit("Sin datos: login MT5 no verificado antes de leer")
    frame = broker.rates(SYMBOL, "M1", count=12000)
    after = broker.health() or {}
    if not after.get("identity_ok"):
        raise SystemExit("Sin datos: login MT5 no verificado despues de leer")
    return frame, f"mt5:{SYMBOL}"


def read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df.set_index("time")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Registro diario NQEDGE (sin resultados)")
    ap.add_argument("--date", help="dia NY a registrar (YYYY-MM-DD); por defecto el ultimo cerrado")
    ap.add_argument("--commission-side-usd", type=float, default=None,
                    help="comision MNQ por contrato y lado (input del operador)")
    ap.add_argument("--slip-ticks", type=float, default=1.0)
    ap.add_argument("--source", choices=("mt5", "csv"), default="mt5")
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--account", default="CFD-001")
    ap.add_argument("--dry-run", action="store_true", help="no escribe el ledger")
    args = ap.parse_args(argv)

    if args.commission_side_usd is None:
        print("Sin datos: comision MNQ por contrato y lado", file=sys.stderr)
        print("bloqueado: falta comision MNQ del operador", file=sys.stderr)
        return 2

    day = date.fromisoformat(args.date) if args.date else last_complete_session()
    if args.source == "mt5":
        frame, source = read_mt5(day, account_id=args.account)
    else:
        if args.csv is None:
            print("Sin datos: --source csv exige --csv", file=sys.stderr)
            return 2
        frame, source = read_csv(args.csv), f"csv:{args.csv.name}"

    today = session_from_frame(frame, str(day))
    if today is None:
        print(f"Sin datos: sesion {day} incompleta o sin 380 barras RTH", file=sys.stderr)
        return 2
    prev_day = last_complete_session(day)
    prev = session_from_frame(frame, str(prev_day))
    sessions = [s for s in (prev, today) if s is not None]
    result = build_day(sessions, Costs(args.commission_side_usd, args.slip_ticks))
    new = 0 if args.dry_run else append_ledger(result.rows, source, sha256(Path(__file__)))
    stats = ledger_stats()
    print(f"dia {day}: {len(result.rows)} filas ({new} nuevas)")
    print(f"senales {result.counts['signals']}; noticias {result.counts['news']}; "
          f"<1R {result.counts['target_lt']}; stop invalido {result.counts['bad_stop']}; "
          f"NO TRADE {result.counts['no_trade']}")
    for v in fm.VARIANTS:
        item = stats.get(v, {"n": 0, "first": None, "last": None})
        print(f"{v}: n={item['n']}; estimado {estimate(item['n'], item['first'], item['last'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
