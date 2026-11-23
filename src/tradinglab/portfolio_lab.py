"""Laboratorio de cartera: correlación, solape y reto de fondeo sin optimizar pesos.

Solo LEE series: operaciones forward en R con riesgo inicial declarado, copias de
discovery (IS/OOS-1) y métricas sintéticas. Los backtests congelados de equity o
retornos del subyacente **se rechazan**: no declaran riesgo inicial por operación
y convertirlos a R sería silenciosamente falso. Los pesos son reglas fijas (igual,
inversa a volatilidad y tope por idea), nunca optimizadas sobre los datos que se
evalúan. El Monte Carlo se delega a ``prop.simulator``, protegido: se llama, no se
modifica. Este módulo no envía órdenes ni activa bots.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .config import ROOT
from .discovery.databank import decode_returns
from .prop.rules import PropRules, from_yaml
from .prop.simulator import monte_carlo, multiverse_by_trade
from .propfund.registry import load_registry
from .propfund.snapshots import _rules_from_account

__all__ = [
    "StrategySeries",
    "Trade",
    "account_context",
    "active_matrix",
    "align",
    "allocate",
    "analyze",
    "challenge_report",
    "correlation_matrix",
    "exposure_by_symbol",
    "load_ai_trades",
    "load_discovery",
    "load_forward",
    "load_series",
    "loss_coincidence",
    "overlap_by_pair",
    "parse_strategies",
    "render_markdown",
    "synthetic_preset",
]

# Únicos tramos de discovery que esta herramienta puede leer.
ALLOWED_SEGMENTS = ("fitness_is", "oos1")
METHODS = ("equal", "inverse_vol", "capped")
DEFAULT_PATHS = 2_000
DEFAULT_SEED = 42
DEFAULT_BLOCK = 5
HORIZON_DAYS = 60
SYNTHETIC_CORRELATIONS = {"syn-0": 0.0, "syn-50": 0.5, "syn-90": 0.9}
# Se conservan los alias por compatibilidad de CLI, pero ahora fallan con un
# mensaje explícito en vez de convertir equity/retornos del índice en R.
REJECTED_FORWARD_ARTIFACTS = {
    "ftmo-eurusd": ("oracles", "signals_eurusd-london-pullback.parquet", "EURUSD"),
    "ftmo-usdjpy": ("oracles", "signals_usdjpy-tokyo-breakout.parquet", "USDJPY"),
    "us100-trend-d1": ("swing_cfd", "us100-trend-d1.parquet", "US100.cash"),
}


@dataclass(frozen=True)
class Trade:
    """Operación con marca de tiempo. ``r`` es PnL / riesgo inicial declarado."""

    strategy: str
    symbol: str
    entry: datetime | None = None
    exit: datetime | None = None
    r: float | None = None


@dataclass(frozen=True)
class StrategySeries:
    """Serie diaria de R con sus operaciones cuando la fuente las conserva.

    ``dates`` son días con retorno R (pueden incluir días sin operación rellenos
    a 0 en ``align``). ``trade_dates`` son días con al menos una operación: solo
    esos cuentan como pérdidas. ``trade_r`` permite pasar PnL por operación al
    simulador; si está vacío, las probabilidades de ruptura son "Sin datos".
    """

    name: str
    source: str
    symbol: str = "Sin datos"
    trades: tuple[Trade, ...] = ()
    daily_r: tuple[float, ...] = ()
    dates: tuple[date, ...] | None = None
    trade_r: tuple[float, ...] = ()
    trade_dates: tuple[date, ...] = ()
    granularity: str = "Sin datos"
    risk_source: str = "Sin datos"

    def r_values(self) -> np.ndarray:
        return np.asarray(self.daily_r, dtype=float)


def parse_strategies(raw: str | Sequence[str]) -> tuple[str, ...]:
    """CSV de identificadores, recortado y sin duplicados."""
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in out:
            out.append(value)
    return tuple(out)


def _business_dates(days: int, start: date = date(2024, 1, 1)) -> tuple[date, ...]:
    out: list[date] = []
    cursor = start
    while len(out) < days:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor += timedelta(days=1)
    return tuple(out)


def synthetic_preset(
    correlation: float,
    *,
    days: int = 252,
    seed: int = DEFAULT_SEED,
    name: str = "syn",
) -> list[StrategySeries]:
    """Tres series equicorrelacionadas, una operación por día y fechas sintéticas."""
    if not -1.0 <= correlation <= 1.0:
        raise ValueError("la correlación sintética debe estar entre -1 y 1")
    rng = np.random.default_rng(seed)
    common = rng.normal(size=days)
    columns = [
        np.sqrt(correlation) * common + np.sqrt(1.0 - correlation) * rng.normal(size=days)
        for _ in range(3)
    ]
    dates = _business_dates(days)
    out = []
    for leg, column in enumerate(columns):
        std = float(np.std(column, ddof=1)) or 1.0
        values = (column - float(np.mean(column))) / std * 0.8 + 0.15
        label = f"{name}-{chr(65 + leg)}"
        trades = tuple(
            Trade(
                strategy=label,
                symbol="SYN",
                entry=datetime.combine(day, time(hour=9), tzinfo=timezone.utc),
                exit=datetime.combine(day, time(hour=10), tzinfo=timezone.utc),
                r=float(value),
            )
            for day, value in zip(dates, values)
        )
        out.append(
            StrategySeries(
                name=label,
                source="synthetic",
                symbol="SYN",
                trades=trades,
                daily_r=tuple(float(v) for v in values),
                dates=dates,
                trade_r=tuple(float(v) for v in values),
                trade_dates=dates,
                granularity="operacion_R",
                risk_source="sintetico:1R declarado por operación",
            )
        )
    return out


def _read_only(db_path: str | Path) -> sqlite3.Connection:
    target = Path(db_path)
    if not target.is_file():
        raise ValueError(f"Sin datos: no existe {target}")
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _as_date(value: object) -> date:
    stamp = pd.Timestamp(str(value))
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC")
    return stamp.date()


def load_ai_trades(
    symbol: str,
    setup: str,
    *,
    db_path: str | Path | None = None,
) -> StrategySeries:
    """Operaciones forward cerradas: R = pnl / riesgo inicial en USD, por cierre."""
    target = Path(db_path) if db_path else Path(ROOT) / "data" / "lab.db"
    con = _read_only(target)
    try:
        rows = con.execute(
            "SELECT ts, symbol, setup, exit_ts, risk_usd, pnl, r_multiple, status, source "
            "FROM ai_trades WHERE symbol = ? AND setup = ? AND status = 'closed' "
            "AND exit_ts IS NOT NULL AND risk_usd > 0 AND pnl IS NOT NULL "
            "ORDER BY exit_ts",
            (symbol, setup),
        ).fetchall()
    finally:
        con.close()
    if len(rows) < 2:
        raise ValueError(
            f"Sin datos: {symbol}:{setup} tiene menos de 2 operaciones cerradas "
            "con riesgo inicial declarado"
        )
    values: list[float] = []
    dates: list[date] = []
    trades: list[Trade] = []
    for row in rows:
        risk = float(row["risk_usd"])
        pnl = float(row["pnl"])
        r = pnl / risk
        declared = row["r_multiple"]
        if declared is not None and abs(r - float(declared)) > 0.01:
            raise ValueError(
                f"Sin datos: riesgo inicial inconsistente en {symbol}:{setup} "
                f"({r:.4f} vs {float(declared):.4f})"
            )
        close = _as_date(row["exit_ts"])
        values.append(r)
        dates.append(close)
        trades.append(
            Trade(
                strategy=f"{symbol}:{setup}",
                symbol=symbol,
                entry=pd.Timestamp(str(row["ts"])).to_pydatetime(),
                exit=pd.Timestamp(str(row["exit_ts"])).to_pydatetime(),
                r=r,
            )
        )
    daily: dict[date, float] = {}
    for day, value in zip(dates, values):
        daily[day] = daily.get(day, 0.0) + value
    active = tuple(sorted(daily))
    return StrategySeries(
        name=f"fwd:{symbol}:{setup}",
        source=f"ai-forward:riesgo_usd declarado;N={len(values)}",
        symbol=symbol,
        trades=tuple(trades),
        daily_r=tuple(daily[day] for day in active),
        dates=active,
        trade_r=tuple(values),
        trade_dates=tuple(dates),
        granularity="operacion_R",
        risk_source="ai_trades:pnl / risk_usd por operación; fecha de cierre",
    )


def load_forward(name: str, *, root: str | Path = ROOT) -> StrategySeries:
    """Rechaza explícitamente los backtests congelados que no traen riesgo por operación."""
    if name not in REJECTED_FORWARD_ARTIFACTS:
        raise ValueError(f"estrategia forward desconocida: {name}")
    folder, filename, _symbol = REJECTED_FORWARD_ARTIFACTS[name]
    base = Path(root)
    candidates = (
        base / "reports" / "research" / folder / filename,
        base / "data" / "copies" / folder / filename,
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise ValueError(f"Sin datos: no existe el backtest congelado de {name}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - depende del artifact
        raise ValueError(f"Sin datos: no se pudo leer {path.name}: {exc}") from exc
    columns = set(frame.columns)
    if "returns" in columns:
        detail = "contiene 'returns' diarios del subyacente/equity"
    elif "equity" in columns:
        detail = "contiene 'equity' diario derivado del backtest"
    else:
        detail = "no declara columnas de PnL y riesgo inicial"
    raise ValueError(
        f"Sin datos: {name} ({path.name}) {detail}; no hay riesgo inicial por operación. "
        "Convertirlo a R sería una conversión silenciosa inválida. "
        "Usa un token fwd:SIMBOLO:SETUP de ai_trades o un id de discovery."
    )


def load_discovery(
    strategy_id: int,
    *,
    db_path: str | Path | None = None,
) -> StrategySeries:
    """Lee IS/OOS-1 de una estrategia de discovery con conexión ``mode=ro``.

    El blob es R neto por operación (riesgo inicial = stop declarado en el
    backtest) agregado por fecha de cierre. El databank no conserva las filas
    individuales, por lo que las probabilidades de ruptura por operación se
    reporterán como "Sin datos".
    """
    target = Path(db_path) if db_path else Path(ROOT) / "data" / "discovery.db"
    con = _read_only(target)
    try:
        row = con.execute(
            "SELECT id, instrument, level, status, verdict FROM disc_strategies WHERE id = ?",
            (int(strategy_id),),
        ).fetchone()
        if row is None:
            raise ValueError(f"estrategia de discovery desconocida: {strategy_id}")
        rows = con.execute(
            "SELECT segment, metrics_json, returns_blob FROM disc_evaluations "
            "WHERE strategy_id = ? AND segment IN (?, ?) ORDER BY id",
            (int(strategy_id), *ALLOWED_SEGMENTS),
        ).fetchall()
    finally:
        con.close()
    values: list[float] = []
    dates: list[date] = []
    for item in rows:
        returns = decode_returns(item["returns_blob"])
        metrics = json.loads(item["metrics_json"] or "{}")
        stamps = metrics.get("return_dates") or []
        if len(stamps) != len(returns):
            continue
        values.extend(float(v) for v in returns)
        dates.extend(_as_date(stamp) for stamp in stamps)
    if len(values) < 2:
        raise ValueError(f"Sin datos: la estrategia {strategy_id} no tiene series IS/OOS-1 legibles")
    return StrategySeries(
        name=f"disc-{strategy_id}",
        source=f"discovery:nivel={row['level']};estado={row['status']};veredicto={row['verdict']}",
        symbol=str(row["instrument"] or "Sin datos"),
        daily_r=tuple(values),
        dates=tuple(dates),
        granularity="dia_R_agregado_por_cierre",
        risk_source="discovery:R neto por operación con stop declarado; sin filas por operación",
    )


def load_series(
    tokens: Sequence[str],
    *,
    root: str | Path = ROOT,
    db_path: str | Path | None = None,
) -> list[StrategySeries]:
    """Resuelve tokens sintéticos, forward reales o ids numéricos de discovery."""
    out: list[StrategySeries] = []
    for token in parse_strategies(tokens):
        if token in SYNTHETIC_CORRELATIONS:
            out.extend(synthetic_preset(SYNTHETIC_CORRELATIONS[token], name=token))
        elif token.startswith("fwd:"):
            parts = token.split(":")
            if len(parts) != 3 or not parts[1] or not parts[2]:
                raise ValueError("token forward inválido; usa fwd:SIMBOLO:SETUP")
            out.append(load_ai_trades(parts[1], parts[2], db_path=db_path))
        elif token in REJECTED_FORWARD_ARTIFACTS:
            # Se llama solo para producir el mensaje "Sin datos" con el detalle del artifact.
            load_forward(token, root=root)
        elif token.lstrip("-").isdigit():
            out.append(load_discovery(int(token), db_path=db_path))
        else:
            raise ValueError(f"estrategia desconocida: {token}")
    if len(out) < 2:
        raise ValueError("hacen falta al menos 2 series para analizar una cartera")
    return out


def align(series: Sequence[StrategySeries]) -> tuple[tuple[date, ...] | None, np.ndarray]:
    """Alinea por fecha cuando hay fechas; si no, por índice rellenando con cero.

    Un día sin operación es retorno 0 R: no se inventa ninguna operación ausente
    y ese día NO se cuenta como pérdida (ver ``active_matrix``).
    """
    arrays = [item.r_values() for item in series]
    if any(item.size == 0 for item in arrays):
        raise ValueError("Sin datos: alguna serie no tiene retornos diarios en R")
    if all(item.dates for item in series):
        if any(len(item.dates or ()) != array.size for item, array in zip(series, arrays)):
            raise ValueError("fechas y retornos no coinciden en alguna serie")
        dates = tuple(sorted(set().union(*(set(item.dates or ()) for item in series))))
        matrix = np.zeros((len(dates), len(series)), dtype=float)
        for column, (item, array) in enumerate(zip(series, arrays)):
            lookup = {day: position for position, day in enumerate(item.dates or ())}
            for position, day in enumerate(item.dates or ()):
                matrix[lookup[day], column] = array[position]
        return dates, matrix
    length = min(item.size for item in arrays)
    return None, np.column_stack([item[:length] for item in arrays])


def active_matrix(
    series: Sequence[StrategySeries],
    dates: tuple[date, ...] | None,
) -> np.ndarray:
    """Booleano de días con al menos una operación por serie."""
    if dates is None:
        return np.ones((min(len(item.daily_r) for item in series), len(series)), dtype=bool)
    lookup = {day: position for position, day in enumerate(dates)}
    active = np.zeros((len(dates), len(series)), dtype=bool)
    for column, item in enumerate(series):
        trade_days = item.trade_dates or item.dates or ()
        for day in trade_days:
            if day in lookup:
                active[lookup[day], column] = True
    return active


def correlation_matrix(matrix: np.ndarray, active: np.ndarray | None = None) -> np.ndarray:
    """Correlación de R usando solo días en que ambas series operaron."""
    result = np.full((matrix.shape[1], matrix.shape[1]), np.nan)
    for i in range(matrix.shape[1]):
        result[i, i] = 1.0
        for j in range(i + 1, matrix.shape[1]):
            keep = active[:, i] & active[:, j] if active is not None else np.ones(matrix.shape[0], dtype=bool)
            left, right = matrix[keep, i], matrix[keep, j]
            if left.size < 2 or np.std(left) == 0 or np.std(right) == 0:
                continue
            result[i, j] = result[j, i] = float(np.corrcoef(left, right)[0, 1])
    return result


def loss_coincidence(
    matrix: np.ndarray,
    active: np.ndarray | None = None,
) -> dict[tuple[int, int], dict[str, float | None]]:
    """Pérdidas simultáneas sobre días con operación en AMBAS series.

    Los días sin operación se rellenan a 0 R en ``matrix`` pero se excluyen aquí:
    contarlos como pérdidas inflaría el ratio de coincidencia.
    """
    negative = matrix < 0
    if active is not None:
        negative = negative & active
    out: dict[tuple[int, int], dict[str, float | None]] = {}
    for i in range(matrix.shape[1]):
        for j in range(i + 1, matrix.shape[1]):
            both_active = active[:, i] & active[:, j] if active is not None else np.ones(matrix.shape[0], dtype=bool)
            common = int(both_active.sum())
            days = max(1, common)
            neg_i = negative[:, i] & both_active
            neg_j = negative[:, j] & both_active
            both = int(np.count_nonzero(neg_i & neg_j))
            expected = float(int(neg_i.sum()) * int(neg_j.sum()) / days)
            out[(i, j)] = {
                "dias_ambas_operan": common,
                "dias_ambos_negativos": both,
                "esperado_independiente": round(expected, 2),
                "ratio": round(both / expected, 2) if expected > 0 else None,
            }
    return out


def overlap_by_pair(series: Sequence[StrategySeries]) -> dict[tuple[int, int], dict[str, object]]:
    """Solape temporal de posiciones entre series con marcas de timestamp."""
    out: dict[tuple[int, int], dict[str, object]] = {}
    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            left = [item for item in series[i].trades if item.entry and item.exit]
            right = [item for item in series[j].trades if item.entry and item.exit]
            if not left or not right:
                out[(i, j)] = {"estado": "Sin datos"}
                continue
            count = 0
            hours = 0.0
            for a in left:
                for b in right:
                    assert a.entry is not None and a.exit is not None
                    assert b.entry is not None and b.exit is not None
                    start = max(a.entry, b.entry)
                    end = min(a.exit, b.exit)
                    if start < end:
                        count += 1
                        hours += (end - start).total_seconds() / 3600.0
            out[(i, j)] = {
                "operaciones_solapadas": count,
                "horas_solapadas": round(hours, 2),
                "pct_de_la_serie_i": round(100.0 * count / len(left), 1),
            }
    return out


def _max_concurrent(intervals: list[Trade]) -> int:
    events: list[tuple[datetime, int]] = []
    for item in intervals:
        if item.entry and item.exit:
            events.append((item.entry, 1))
            events.append((item.exit, -1))
    current = peak = 0
    for _, delta in sorted(events, key=lambda pair: (pair[0], pair[1])):
        current += delta
        peak = max(peak, current)
    return peak


def exposure_by_symbol(series: Sequence[StrategySeries]) -> dict[str, object]:
    """Exposición por símbolo en número de posiciones concurrentes (no nocional)."""
    per_strategy: dict[str, object] = {}
    portfolio: dict[str, list[Trade]] = {}
    for item in series:
        if not item.trades:
            per_strategy[item.name] = {"estado": "Sin datos", "simbolo": item.symbol}
            continue
        by_symbol: dict[str, dict[str, object]] = {}
        for trade in item.trades:
            portfolio.setdefault(trade.symbol, []).append(trade)
            group = by_symbol.setdefault(trade.symbol, [])
            assert isinstance(group, list)
            group.append(trade)
        per_strategy[item.name] = {
            symbol: {"operaciones": len(group), "max_concurrentes": _max_concurrent(group)}
            for symbol, group in by_symbol.items()
        }
    return {
        "por_estrategia": per_strategy,
        "cartera": {
            symbol: {"operaciones": len(group), "max_concurrentes": _max_concurrent(group)}
            for symbol, group in portfolio.items()
        },
        "notional_usd": "Sin datos: los backtests no declaran tamaño ni precio",
    }


def allocate(
    names: Sequence[str],
    matrix: np.ndarray,
    method: str,
    *,
    cap_pct: float | None = None,
    risk_pct: float = 1.0,
) -> dict[str, float]:
    """Reparto fijo del presupuesto de riesgo. Nunca ajusta pesos a los retornos.

    ``cap_pct`` es riesgo por idea como fracción de la cuenta (regla de la firma);
    se convierte a peso del presupuesto dividiéndolo entre ``risk_pct``.
    """
    count = len(names)
    if count < 2 or matrix.shape[1] != count:
        raise ValueError("los nombres y las columnas de la matriz no coinciden")
    if method == "equal":
        weights = np.full(count, 1.0 / count)
    elif method in {"inverse_vol", "capped"}:
        volatility = matrix.std(axis=0, ddof=1) if matrix.shape[0] > 1 else np.ones(count)
        volatility = np.where(np.isfinite(volatility) & (volatility > 0), volatility, np.inf)
        inverse = np.reciprocal(volatility)
        total = float(inverse.sum())
        base = inverse / total if np.isfinite(total) and total > 0 else np.full(count, 1.0 / count)
        if method == "inverse_vol":
            weights = base
        else:
            if cap_pct is None or not 0 < cap_pct <= 1 or risk_pct <= 0:
                raise ValueError("Sin datos: la firma no declara un tope por idea aplicable")
            weight_cap = min(1.0, cap_pct / risk_pct)
            if weight_cap * count < 1.0 - 1e-9:
                raise ValueError("el tope por idea es inviable con este número de estrategias")
            weights = base.copy()
            for _ in range(count + 2):
                over = weights > weight_cap + 1e-12
                if not over.any():
                    break
                excess = float((weights[over] - weight_cap).sum())
                weights[over] = weight_cap
                free = ~over
                if not free.any():
                    break
                share = base[free] / base[free].sum()
                weights[free] += excess * share
            weights = np.clip(weights, 0.0, weight_cap + 1e-9)
    else:
        raise ValueError(f"método de reparto desconocido: {method}")
    weights = weights / weights.sum()
    return {str(name): float(weight) for name, weight in zip(names, weights)}


def account_context(account: str, *, registry=None) -> dict[str, object]:
    """Reglas del reto y presupuesto de riesgo de una cuenta CFD declarada."""
    reg = registry or load_registry()
    item = reg.accounts.get(account)
    if item is None:
        raise ValueError(f"cuenta desconocida: {account}")
    size = float(item.nominal_size)
    risk_pct = float(item.risk.per_trade_risk_pct)
    if risk_pct <= 0 or size <= 0:
        raise ValueError("Sin datos: riesgo por operación o tamaño de cuenta no declarado")
    if str(item.legacy_account or ""):
        rules: PropRules = from_yaml(str(item.firm), "challenge", size)
    else:
        # Sin offset de servidor: el bridge usa UTC y lo marca como no verificado.
        rules = _rules_from_account(item, {})
    cap_pct: float | None = None
    firm = reg.firm_of(account)
    for program in firm.programs:
        for rule in list(program.rules) + list(firm.firm_constraints):
            if rule.key == "max_risk_per_trade_pct" and rule.value is not None:
                value = float(rule.value)
                cap_pct = value if cap_pct is None else min(cap_pct, value)
    return {
        "account": account,
        "firm": str(item.firm),
        "program": str(item.program),
        "rules": rules,
        "size": size,
        "risk_pct": risk_pct,
        "risk_usd_per_r": size * risk_pct,
        "cap_pct": cap_pct,
        "cap_note": (
            "menor max_risk_per_trade_pct declarado por la firma; fase funded/needs_verification"
            if cap_pct is not None
            else "Sin datos: la firma no declara tope por idea"
        ),
    }


def _trade_pnls(
    series: Sequence[StrategySeries],
    vector: np.ndarray,
    risk_usd_per_r: float,
) -> tuple[list[float], list[int], str]:
    """PnL por operación y tamaños de día para ``multiverse_by_trade``."""
    if any(item.granularity != "operacion_R" or not item.trade_r for item in series):
        return [], [], "Sin datos: la fuente no conserva PnL por operación con riesgo inicial"
    buckets: dict[date, list[float]] = {}
    for item, weight in zip(series, vector):
        if weight == 0:
            continue
        for day, value in zip(item.trade_dates, item.trade_r):
            buckets.setdefault(day, []).append(float(value) * float(weight) * risk_usd_per_r)
    ordered = sorted(buckets)
    pnls = [value for day in ordered for value in buckets[day]]
    sizes = [len(buckets[day]) for day in ordered]
    return pnls, sizes, "operacion_R:pnl por operación agrupado por fecha de cierre"


def _challenge_metrics(sim: dict, universe: dict | None, basis: str) -> dict[str, object]:
    if universe is None:
        breach: dict[str, object] = {
            "p_romper_diario": None,
            "p_romper_maximo": None,
            "p_romper_cualquiera": None,
        }
    else:
        breach = {
            "p_romper_diario": float(universe["prob_breach_daily"]),
            "p_romper_maximo": float(universe["prob_breach_max"]),
            "p_romper_cualquiera": float(universe["prob_breach_any"]),
        }
    return {
        "p_pasar_fase1": float(sim["pass_rate"]),
        **breach,
        "dias_medianos_objetivo": sim["median_days_to_pass"],
        "p_timeout": float(sim["timeout_rate"]),
        "sample_days": int(sim["sample_days"]),
        "trade_basis": basis,
        "sample_warning": None if universe is None else universe.get("sample_warning"),
    }


def challenge_report(
    series: Sequence[StrategySeries],
    weights: dict[str, dict[str, float]],
    context: dict[str, object],
    *,
    matrix: np.ndarray | None = None,
    paths: int = DEFAULT_PATHS,
    seed: int = DEFAULT_SEED,
    block_size: int = DEFAULT_BLOCK,
) -> dict[str, object]:
    """Pasa cada serie y cada cartera por los dos simuladores protegidos."""
    rules = context["rules"]
    risk = float(context["risk_pct"])
    risk_usd = float(context["risk_usd_per_r"])
    aligned = matrix if matrix is not None else align(series)[1]
    if aligned.shape[0] < 2:
        raise ValueError("Sin datos: hacen falta al menos dos días para el Monte Carlo")
    names = [item.name for item in series]
    candidates: list[tuple[str, np.ndarray]] = [
        (f"solo:{name}", vector) for name, vector in zip(names, np.eye(len(names)))
    ]
    for method, mapping in weights.items():
        candidates.append((f"cartera:{method}", np.array([mapping[name] for name in names])))
    results: dict[str, object] = {}
    for label, vector in candidates:
        daily_return = (aligned @ vector) * risk
        sim = monte_carlo(
            rules,
            daily_return,
            n_paths=paths,
            horizon=HORIZON_DAYS,
            seed=seed,
            block_size=block_size,
        )
        pnls, sizes, basis = _trade_pnls(series, vector, risk_usd)
        universe = None
        if len(pnls) >= 2:
            universe = multiverse_by_trade(
                rules,
                pnls,
                n_paths=paths,
                seed=seed,
                day_sizes=sizes,
            )
            basis = f"{basis};N={len(pnls)}"
        results[label] = _challenge_metrics(sim, universe, basis)
    return {
        "account": context["account"],
        "firm": context["firm"],
        "horizon_days": HORIZON_DAYS,
        "paths": paths,
        "seed": seed,
        "block_size": block_size,
        "rules": rules.describe(),
        "risk_usd_per_r": risk_usd,
        "results": results,
    }


def _verdict(challenge: dict[str, object], methods: Sequence[str]) -> dict[str, str]:
    results = challenge["results"]
    assert isinstance(results, dict)
    singles = [value for key, value in results.items() if str(key).startswith("solo:")]
    if not singles:
        return {}
    best_pass = max(float(item["p_pasar_fase1"]) for item in singles)
    known_breach = [
        float(item["p_romper_cualquiera"])
        for item in singles
        if item["p_romper_cualquiera"] is not None
    ]
    worst_breach = min(known_breach) if known_breach else None
    out = {}
    for method in methods:
        key = f"cartera:{method}"
        if key not in results:
            continue
        row = results[key]
        pass_gain = float(row["p_pasar_fase1"]) - best_pass
        breach_text = (
            "P(romper) Sin datos (la fuente no conserva operaciones individuales)"
            if worst_breach is None or row["p_romper_cualquiera"] is None
            else (
                "P(romper) "
                + ("empeora" if float(row["p_romper_cualquiera"]) > worst_breach else "no empeora")
                + f" vs la mejor individual ({float(row['p_romper_cualquiera']) - worst_breach:+.1%})"
            )
        )
        out[method] = (
            f"P(pasar) {'mejora' if pass_gain > 0 else 'no mejora'} vs la mejor individual "
            f"({pass_gain:+.1%}); {breach_text}"
        )
    return out


def analyze(
    strategies: str | Sequence[str],
    account: str,
    *,
    root: str | Path = ROOT,
    db_path: str | Path | None = None,
    paths: int = DEFAULT_PATHS,
    seed: int = DEFAULT_SEED,
    block_size: int = DEFAULT_BLOCK,
) -> dict[str, object]:
    """Informe completo: series, correlaciones, solape, exposición, pesos y reto."""
    series = load_series(strategies, root=root, db_path=db_path)
    context = account_context(account)
    risk_pct = float(context["risk_pct"])
    dates, matrix = align(series)
    active = active_matrix(series, dates)
    names = [item.name for item in series]
    weights: dict[str, dict[str, float]] = {"equal": allocate(names, matrix, "equal")}
    weights["inverse_vol"] = allocate(names, matrix, "inverse_vol")
    cap = context["cap_pct"]
    try:
        weights["capped"] = allocate(
            names,
            matrix,
            "capped",
            cap_pct=float(cap) if cap else None,
            risk_pct=risk_pct,
        )
    except ValueError as exc:
        weights["capped"] = {"estado": str(exc)}
    corr = correlation_matrix(matrix, active)
    challenge = challenge_report(
        series,
        {key: value for key, value in weights.items() if "estado" not in value},
        context,
        matrix=matrix,
        paths=paths,
        seed=seed,
        block_size=block_size,
    )
    return {
        "account": account,
        "firm": context["firm"],
        "program": context["program"],
        "rules": context["rules"].describe(),
        "risk_usd_per_r": context["risk_usd_per_r"],
        "cap_pct": cap,
        "cap_note": context["cap_note"],
        "members": [
            {
                "name": item.name,
                "source": item.source,
                "symbol": item.symbol,
                "days": len(item.daily_r),
                "trades": len(item.trades) if item.trades else "Sin datos",
                "granularity": item.granularity,
                "risk_source": item.risk_source,
            }
            for item in series
        ],
        "alignment": {
            "mode": "fechas" if dates else "indice",
            "days": int(matrix.shape[0]),
            "active_days": int(active.any(axis=1).sum()),
            "active_cells": int(active.sum()),
        },
        "correlation": {
            "labels": names,
            "matrix": [[None if np.isnan(value) else round(float(value), 4) for value in row] for row in corr],
        },
        "simultaneous_losses": {
            f"{names[i]}|{names[j]}": value for (i, j), value in loss_coincidence(matrix, active).items()
        },
        "overlap": {
            f"{names[i]}|{names[j]}": value for (i, j), value in overlap_by_pair(series).items()
        },
        "exposure": exposure_by_symbol(series),
        "weights": weights,
        "challenge": challenge,
        "verdict": _verdict(challenge, tuple(weights)),
    }


def _pct(value: object) -> str:
    return "Sin datos" if value is None else f"{float(value):.1%}"


def render_markdown(payload: dict[str, object]) -> str:
    """Resumen legible, con el mismo vocabulario que el informe de-resultado."""
    lines = [
        "# Portfolio Lab",
        "",
        f"Cuenta: {payload['account']} · firma: {payload['firm']} · {payload['program']}",
        f"Riesgo por 1R: {payload['risk_usd_per_r']} USD · tope por idea: {payload['cap_pct']}",
        f"Alineación: {payload['alignment']['mode']} · {payload['alignment']['days']} días",
        "",
        "## Miembros",
        "",
        "| Estrategia | Origen | Símbolo | Días | Granularidad |",
        "|---|---|---|---:|---|",
    ]
    for item in payload["members"]:
        assert isinstance(item, dict)
        lines.append(
            f"| {item['name']} | {item['source']} | {item['symbol']} | {item['days']} | "
            f"{item['granularity']} |"
        )
    lines += [
        "",
        "## Monte Carlo (fase 1, 60 días)",
        "",
        "| Candidato | P(pasar) | P(romper diario) | P(romper máximo) | Días medianos |",
        "|---|---:|---:|---:|---:|",
    ]
    challenge = payload["challenge"]
    assert isinstance(challenge, dict)
    results = challenge["results"]
    assert isinstance(results, dict)
    for label, row in results.items():
        lines.append(
            f"| {label} | {_pct(row['p_pasar_fase1'])} | {_pct(row['p_romper_diario'])} | "
            f"{_pct(row['p_romper_maximo'])} | {row['dias_medianos_objetivo']} |"
        )
    lines += ["", "## Veredicto", ""]
    for method, text in payload["verdict"].items():
        lines.append(f"- {method}: {text}")
    lines += ["", f"Aviso: {payload['cap_note']}. Sin órdenes, sin campañas, sin OOS de discovery."]
    return "\n".join(lines)
