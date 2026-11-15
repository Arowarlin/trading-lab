"""Research de tendencia diaria en CFDs de tick grande (Etapa 3m).

Una sola familia nueva, `trend`, con mecanismo:

- señal diaria reutilizando `trend_signal` (EMA rápida/lenta + régimen);
- ejecución en H4 con la señal del día anterior (causal);
- stop ATR sobre cierres H4 (2× o 3× ATR);
- costes FTMO del catálogo (índices 0, oro 0,0007 %/lado), spread medido en las
  velas H4 y slippage 0,5/2 bps;
- `backtest.run` con sesión y días planos explícitos.

Valida con DSR, PBO, walk-forward, holdout y Monte Carlo FTMO 100k, registra
cada variante en `strategy_trials` y escribe el informe en
`reports/research/swing_cfd/`. **No activa nada**: como mucho registra un
candidato en el ciclo de vida.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import run as run_backtest
from .carry import cost_model_from_asset
from .config import ROOT
from .datacheck import check_frame
from .global_dsr import global_srs
from .intraday import cache_file, load_bars
from .intraday_costs import asset_costs
from .prop.rules import PropRules
from .prop.simulator import monte_carlo
from .stats import dsr_local_global, period_sharpe
from .strategies import STRATEGIES
from .strategies.swing import daily_bars, trading_day
from .trials import budget_status, record_trial
from .validation import cscv_pbo
from .walkforward import regime_gate, regime_report, walk_forward

FAMILY = "trend"
BOT_IDS = {"US100.CASH": "us100-trend-d1", "XAUUSD": "xauusd-trend-d1"}
SYMBOLS = ("US100.CASH", "XAUUSD")

# Rejilla acotada a 5 variantes por activo: cada pasada consume un intento del
# presupuesto semanal (config/research_budget.yaml).
GRID: tuple[dict, ...] = (
    {"fast": 20, "slow": 100, "stop_atr": 2.0},
    {"fast": 20, "slow": 200, "stop_atr": 2.0},
    {"fast": 50, "slow": 200, "stop_atr": 2.0},
    {"fast": 20, "slow": 200, "stop_atr": 3.0},
    {"fast": 50, "slow": 200, "stop_atr": 3.0},
)
REGIME = 200
ATR_WINDOW = 14
HYPOTHESIS = (
    "Tendencia diaria en CFDs de tick grande: la dirección de la EMA rápida "
    "sobre la lenta más el filtro de régimen persiste en H4; el stop ATR corta "
    "los giros sin salir en cada retroceso."
)
SESSIONS = {
    "US100.CASH": (("00:00", "23:59"), "UTC"),
    "XAUUSD": (("01:00", "23:59"), "UTC"),
}
# Umbrales de propuesta: los del perfil swing_cfd (no se inventan aquí).
MC_PATHS = 2_000
MC_HORIZON = 120
MC_BLOCK = 5
HOLDOUT_FRACTION = 0.30
PBO_SLICES = 16
PBO_MAX_COMBINATIONS = 2_000
WF_TRAIN_DAYS = 504
WF_TEST_DAYS = 126
MIN_PASS = 0.35
MAX_BREACH = 0.15
MIN_OOS_PASS = 0.25
MIN_TRADES = 20
MAX_PBO = 0.30
MIN_DSR = 0.90
REGIME_YEARS = (2018, 2020, 2022)
REGIME_MIN_OBS = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def spread_bps(frame: pd.DataFrame, *, point: float = 0.01) -> pd.Series:
    """Spread de cada vela en bps del precio.

    MT5 entrega `spread` en puntos enteros; `point` es el tamaño del punto del
    símbolo (0,01 en US100.cash y XAUUSD, verificado con `lab mt5 spec`).
    """
    if "spread" not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype=float)
    spread = pd.to_numeric(frame["spread"], errors="coerce").fillna(0.0)
    close = pd.to_numeric(frame["close"], errors="coerce").replace(0.0, np.nan)
    return (spread * float(point) / close * 10_000.0).fillna(0.0)


def symbol_point(symbol: str, default: float = 0.01) -> float:
    """Tamaño del punto del catálogo; 0,01 si el símbolo no está registrado."""
    try:
        from .instruments import get_instrument

        value = float(get_instrument(symbol).tick_size or 0.0)
        return value if value > 0 else default
    except Exception:
        return default


def daily_returns(returns: pd.Series) -> pd.Series:
    """Retornos por barra agregados a días con barras (sin fines de semana).

    `resample("1D")` rellenaría los días sin datos con 0 y diluiría la muestra;
    se agrupa por el día de cada barra.
    """
    frame = pd.DataFrame(
        {
            "r": returns.fillna(0.0).astype(float),
            "day": trading_day(pd.DatetimeIndex(returns.index)),
        }
    )
    daily = (1.0 + frame["r"]).groupby(frame["day"]).prod() - 1.0
    daily.index = pd.DatetimeIndex(daily.index)
    return daily


def _aligned(series_by_variant: dict[str, pd.Series]) -> np.ndarray | None:
    if len(series_by_variant) < 2:
        return None
    frame = pd.concat(series_by_variant, axis=1, join="inner").dropna()
    if len(frame) < 80:
        return None
    return frame.to_numpy(dtype=float)


def _pbo(matrix: np.ndarray | None) -> dict | None:
    if matrix is None:
        return None
    try:
        result = cscv_pbo(
            matrix,
            n_slices=PBO_SLICES,
            max_combinations=PBO_MAX_COMBINATIONS,
            seed=0,
        )
    except ValueError:
        return None
    payload = result.to_dict()
    payload["verdict"] = result.verdict(MAX_PBO)
    payload["max_pbo"] = MAX_PBO
    return payload


def _wf(matrix: np.ndarray | None) -> dict | None:
    if matrix is None:
        return None
    try:
        result = walk_forward(
            matrix, train_len=WF_TRAIN_DAYS, test_len=WF_TEST_DAYS
        )
    except ValueError:
        return None
    payload = result.to_dict()
    payload["verdict"] = result.verdict()
    payload["scope"] = "global"
    return payload


def _mc(rules: PropRules, returns: pd.Series, *, paths: int, horizon: int, block: int) -> dict:
    payload = monte_carlo(
        rules,
        returns.fillna(0.0),
        n_paths=int(paths),
        horizon=int(horizon),
        block_size=int(block),
    )
    return {
        "pass_rate": float(payload["pass_rate"]),
        "breach_rate": float(payload["breach_rate"]),
        "timeout_rate": float(payload["timeout_rate"]),
        "median_days_to_pass": payload["median_days_to_pass"],
        "pass_ci95": list(payload.get("pass_ci95") or []),
    }


def artifact_name(symbol: str, params: dict) -> str:
    """Nombre estable del artefacto de una variante."""
    safe = "".join(
        char if char.isalnum() or char in "-_." else "_"
        for char in str(symbol).lower()
    )
    return f"{safe}_{params['fast']}_{params['slow']}_{params['stop_atr']:g}.parquet"


def save_variant_artifact(
    out_dir: Path,
    symbol: str,
    params: dict,
    daily_ret: pd.Series,
    daily_equity: pd.Series,
) -> Path:
    """Guarda los retornos diarios de una variante (y su equity diaria).

    Es la entrada de `lab prop exposure-sweep`: el barrido no recalcula el
    backtest, lee esta serie. El run d2316a4be339 no la guardó; se añadió aquí
    y la serie de esa variante se reconstruyó y verificó contra sus métricas.
    """
    target = out_dir / "artifacts" / artifact_name(symbol, params)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "returns": daily_ret.astype(float),
            "equity": daily_equity.reindex(daily_ret.index).astype(float),
        }
    )
    frame.index.name = "date"
    frame.to_parquet(target)
    return target


def _daily_metrics(bt, daily_ret: pd.Series) -> dict:
    """Métricas anualizadas sobre retornos diarios (no sobre barras H4).

    `backtest.run` anualiza con 252 barras; en H4 eso subestima Sharpe y CAGR
    (6 barras por día). Se recalcula sobre la serie diaria, que es la que usan
    el Monte Carlo, el PBO y el walk-forward.
    """
    equity = bt.equity.astype(float)
    by_day = trading_day(pd.DatetimeIndex(equity.index))
    daily_equity = equity.groupby(by_day).last()
    daily_equity.index = pd.DatetimeIndex(daily_equity.index)
    if len(daily_equity) < 2 or len(daily_ret) < 2:
        return {
            "sharpe": 0.0,
            "cagr": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
            "equity": daily_equity,
        }
    total = float(daily_equity.iloc[-1] / daily_equity.iloc[0] - 1.0)
    years = max(
        (daily_equity.index[-1] - daily_equity.index[0]).days / 365.25,
        1.0 / 365.25,
    )
    cagr = float((1.0 + total) ** (1.0 / years) - 1.0) if total > -1.0 else -1.0
    std = float(daily_ret.std(ddof=1))
    sharpe = float(daily_ret.mean() / std * np.sqrt(252.0)) if std > 0 else 0.0
    drawdown = daily_equity / daily_equity.cummax() - 1.0
    return {
        "sharpe": sharpe,
        "cagr": cagr,
        "total_return": total,
        "max_drawdown": float(drawdown.min()),
        "volatility": float(std * np.sqrt(252.0)),
        "equity": daily_equity,
    }


def _failure_reasons(row: dict, *, wf_ok: bool, pbo_ok: bool) -> list[str]:
    reasons: list[str] = []
    if int(row["num_trades"]) < MIN_TRADES:
        reasons.append(f"trades {row['num_trades']} < {MIN_TRADES}")
    if row["sharpe"] <= 0:
        reasons.append(f"Sharpe {row['sharpe']:.2f} <= 0")
    if row["pass_rate"] < MIN_PASS:
        reasons.append(f"P(pasar) {row['pass_rate']:.1%} < {MIN_PASS:.0%}")
    if row["breach_rate"] > MAX_BREACH:
        reasons.append(f"P(breach) {row['breach_rate']:.1%} > {MAX_BREACH:.0%}")
    if row["oos_pass_rate"] is None:
        reasons.append("sin holdout suficiente")
    elif row["oos_pass_rate"] < MIN_OOS_PASS:
        reasons.append(
            f"holdout P(pasar) {row['oos_pass_rate']:.1%} < {MIN_OOS_PASS:.0%}"
        )
    if row["dsr"] is None or row["dsr"] < MIN_DSR:
        reasons.append(f"DSR {(row['dsr'] or 0):.0%} < {MIN_DSR:.0%}")
    if not pbo_ok:
        reasons.append(f"PBO no disponible o > {MAX_PBO:.0%}")
    if not wf_ok:
        reasons.append("walk-forward global no aprobado")
    gate = row.get("regime_gate") or {}
    if not gate.get("passed"):
        reasons.append("regímenes: " + "; ".join(gate.get("reasons") or ["no aprobado"]))
    datacheck = row.get("datacheck") or {}
    if datacheck.get("status") == "falla":
        reasons.append("datacheck: " + "; ".join(datacheck.get("reasons") or ["falla"]))
    return reasons


def data_status(cache_dir: str | Path, symbol: str) -> dict:
    """Qué hay en la caché: H4 (motor) y D1 (informativo)."""
    h4_path = cache_file(cache_dir, symbol, "H4")
    d1_path = cache_file(cache_dir, symbol, "D1")
    status = {
        "h4": {"path": str(h4_path), "exists": h4_path.exists()},
        "d1": {"path": str(d1_path), "exists": d1_path.exists()},
    }
    if not d1_path.exists():
        status["d1"]["status"] = "Sin datos"
        status["d1"]["reason"] = (
            "la caché D1 no está disponible; la serie diaria se construye "
            "desde H4 (offsets semanales verificados)"
        )
    else:
        status["d1"]["status"] = "ok"
    return status


def run_swing(
    db_path: str | Path,
    rules: PropRules,
    cache_dir: str | Path,
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    grid: tuple[dict, ...] = GRID,
    out_dir: str | Path | None = None,
    paths: int = MC_PATHS,
    horizon: int = MC_HORIZON,
    block_size: int = MC_BLOCK,
    record: bool = True,
    run_id: str | None = None,
) -> dict:
    """Barrido de la familia trend diaria; no activa nada."""
    from .learning import count_tests

    run = run_id or uuid.uuid4().hex[:12]
    trials_before = count_tests(db_path) if record else 0
    out = Path(out_dir) if out_dir else ROOT / "reports" / "research" / "swing_cfd"
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    errors: list[dict] = []
    datachecks: dict[str, dict] = {}
    data: dict[str, dict] = {}
    costs_by_symbol: dict[str, dict] = {}
    daily_by_variant: dict[str, pd.Series] = {}
    daily_by_symbol: dict[str, dict[str, pd.Series]] = {}

    for symbol in symbols:
        status = data_status(cache_dir, symbol)
        data[symbol] = status
        if record:
            budget = budget_status(db_path, symbol)
            if budget["exceeded"]:
                errors.append(
                    {
                        "symbol": symbol,
                        "error": (
                            f"presupuesto semanal agotado ({budget['used']}/"
                            f"{budget['limit']} intentos)"
                        ),
                    }
                )
                continue
        try:
            frame = load_bars(cache_dir, symbol, "H4")
        except FileNotFoundError as exc:
            status["h4"]["status"] = "Sin datos"
            status["h4"]["reason"] = str(exc)
            errors.append({"symbol": symbol, "error": str(exc)})
            continue
        if len(frame) < 300:
            errors.append(
                {"symbol": symbol, "error": f"histórico H4 insuficiente ({len(frame)} barras)"}
            )
            continue
        h4_check = check_frame(
            frame,
            symbol,
            timeframe="4h",
            cache_path=status["h4"]["path"],
        )
        status["h4"].update(
            {
                "rows": int(len(frame)),
                "start": str(pd.Timestamp(frame.index[0]).date()),
                "end": str(pd.Timestamp(frame.index[-1]).date()),
            }
        )
        datachecks[f"{symbol}:4h"] = h4_check
        if h4_check["status"] == "falla":
            errors.append(
                {
                    "symbol": symbol,
                    "error": "datacheck H4 falla: " + "; ".join(h4_check["reasons"]),
                }
            )
            continue

        daily = daily_bars(frame)
        daily_check = check_frame(
            daily,
            symbol,
            timeframe="1d",
            cache_path=status["h4"]["path"],
        )
        datachecks[f"{symbol}:1d"] = daily_check
        if daily_check["status"] == "falla":
            errors.append(
                {
                    "symbol": symbol,
                    "error": "datacheck diario falla: "
                    + "; ".join(daily_check["reasons"]),
                }
            )
            continue

        cost = asset_costs(symbol)
        if not cost.verified:
            errors.append(
                {"symbol": symbol, "error": f"comisión sin verificar para {symbol}"}
            )
            continue
        commission = float(cost.commission_bps(frame["close"]).median())
        spread = spread_bps(frame, point=symbol_point(symbol))
        spread_median = float(spread.median())
        spread_p95 = float(spread.quantile(0.95))
        recent = spread.loc[
            spread.index >= spread.index[-1] - pd.Timedelta(days=365 * 3)
        ]
        spread_recent = float(recent.median()) if len(recent) else spread_median
        session, tz = SESSIONS.get(symbol, (("00:00", "23:59"), "UTC"))
        costs_by_symbol[symbol] = {
            "commission_bps_side": round(commission, 4),
            "spread_bps_median": round(spread_median, 4),
            "spread_bps_p95": round(spread_p95, 4),
            "spread_bps_recent_3y": round(spread_recent, 4),
            "slippage_bps_optimistic": float(cost.slippage_optimistic_bps),
            "slippage_bps_conservative": float(cost.slippage_conservative_bps),
            "source": cost.source,
            "swap_long": cost.swap_long,
            "swap_short": cost.swap_short,
            "swap_unit": cost.swap_unit,
            "swap_source": cost.swap_source,
            "swap_provisional": cost.swap_provisional,
            "session": list(session),
            "session_tz": tz,
        }
        cost_bps = commission + spread_recent
        carry = cost_model_from_asset(cost)
        strategy = STRATEGIES["trend_daily_atr"]
        for params in grid:
            variant_id = (
                f"{symbol}|{params['fast']}|{params['slow']}|{params['stop_atr']:g}"
            )
            try:
                signal = strategy(
                    frame,
                    fast=int(params["fast"]),
                    slow=int(params["slow"]),
                    regime=REGIME,
                    stop_atr=float(params["stop_atr"]),
                    atr_window=ATR_WINDOW,
                )
                bt = run_backtest(
                    frame,
                    signal.target,
                    starting_cash=rules.account_size,
                    commission_bps=cost_bps,
                    slippage_bps=float(cost.slippage_conservative_bps),
                    session=session,
                    session_tz=tz,
                    flat_dates=[],
                    carry=carry,
                )
            except Exception as exc:
                errors.append(
                    {
                        "symbol": symbol,
                        "params": params,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }
                )
                continue
            metrics = bt.metrics
            daily_ret = daily_returns(bt.returns)
            if len(daily_ret) < 260:
                errors.append(
                    {
                        "symbol": symbol,
                        "params": params,
                        "error": f"retornos diarios insuficientes ({len(daily_ret)})",
                    }
                )
                continue
            daily_stats = _daily_metrics(bt, daily_ret)
            try:
                artifact = save_variant_artifact(
                    out, symbol, params, daily_ret, daily_stats["equity"]
                )
                artifact_rel = str(artifact.relative_to(out))
            except Exception as exc:
                artifact_rel = None
                errors.append(
                    {
                        "symbol": symbol,
                        "params": params,
                        "error": f"artefacto: {exc}"[:300],
                    }
                )
            split = max(1, int(len(daily_ret) * (1.0 - HOLDOUT_FRACTION)))
            oos = daily_ret.iloc[split:]
            mc = _mc(
                rules, daily_ret, paths=paths, horizon=horizon, block=block_size
            )
            oos_mc = (
                _mc(rules, oos, paths=max(200, paths // 2), horizon=horizon, block=block_size)
                if len(oos) >= 120
                else None
            )
            regime = regime_report(
                daily_ret, years=REGIME_YEARS, min_obs=REGIME_MIN_OBS
            )
            gate = regime_gate(regime, min_return=0.0)
            row = {
                "symbol": symbol,
                "variant_id": variant_id,
                "strategy": "trend_daily_atr",
                "params": {
                    "fast": int(params["fast"]),
                    "slow": int(params["slow"]),
                    "regime": REGIME,
                    "stop_atr": float(params["stop_atr"]),
                    "atr_window": ATR_WINDOW,
                    "timeframe": "H4",
                },
                "sharpe": daily_stats["sharpe"],
                "cagr": daily_stats["cagr"],
                "total_return": daily_stats["total_return"],
                "max_drawdown": daily_stats["max_drawdown"],
                "volatility": daily_stats["volatility"],
                "num_trades": int(metrics.get("num_trades", 0)),
                "win_rate": float(metrics.get("win_rate", 0.0)),
                "pass_rate": mc["pass_rate"],
                "pass_ci95": mc["pass_ci95"],
                "breach_rate": mc["breach_rate"],
                "timeout_rate": mc["timeout_rate"],
                "median_days_to_pass": mc["median_days_to_pass"],
                "oos_pass_rate": oos_mc["pass_rate"] if oos_mc else None,
                "oos_breach_rate": oos_mc["breach_rate"] if oos_mc else None,
                "start": str(daily_ret.index[0].date()),
                "end": str(daily_ret.index[-1].date()),
                "oos_start": str(daily_ret.index[split].date()),
                "oos_end": str(daily_ret.index[-1].date()),
                "sample_days": len(daily_ret),
                "regime_report": regime.to_dict(),
                "regime_gate": gate.to_dict(),
                "datacheck": {
                    "status": daily_check["status"],
                    "reasons": daily_check["reasons"],
                },
                "year_returns": _year_returns(daily_ret),
                "artifact": artifact_rel,
            }
            results.append(row)
            daily_by_variant[f"{symbol}|{params['fast']}|{params['slow']}|{params['stop_atr']:g}"] = daily_ret
            daily_by_symbol.setdefault(symbol, {})[
                f"{params['fast']}|{params['slow']}|{params['stop_atr']:g}"
            ] = daily_ret

    # DSR: cuenta todas las variantes de esta pasada más los intentos previos.
    n_trials = len(results) + max(0, int(trials_before))
    series_list = list(daily_by_variant.values())
    trial_srs = [period_sharpe(series) for series in series_list]
    sr_std = float(np.std(trial_srs, ddof=0)) if len(trial_srs) > 1 else 0.0
    global_info = global_srs(db_path, "daily")
    for row, series in zip(results, series_list):
        pair = dsr_local_global(
            series,
            trial_srs,
            global_info["srs"],
            len(series_list),
            n_trials,
            periods_per_year=252,
            global_sources=global_info["sources"],
            frequency="daily",
        )
        local = pair["local"]
        global_payload = pair["global"]
        row["dsr_local"] = local["dsr"]
        row["dsr_global"] = global_payload["dsr"]
        row["dsr"] = global_payload["dsr"]
        row["dsr_gate"] = (
            "global" if global_payload["dsr"] is not None else "pendiente"
        )
        row["metric_version"] = local["metric_version"]
        row["dsr_local_meta"] = local
        row["dsr_global_meta"] = global_payload
        row["dsr_n_trials"] = n_trials
        row["dsr_trial_sr_std"] = local["trial_sr_std_period"]

    pbo_global = _pbo(_aligned(daily_by_variant))
    pbo_ok = bool(pbo_global and pbo_global["pbo"] <= MAX_PBO)
    pbo_by_symbol = {
        symbol: _pbo(_aligned(series)) for symbol, series in daily_by_symbol.items()
    }
    pbo_symbol_ok = {
        symbol: bool(payload and payload["pbo"] <= MAX_PBO)
        for symbol, payload in pbo_by_symbol.items()
    }
    wf = _wf(_aligned(daily_by_variant))
    wf_ok = bool(wf and wf.get("verdict") == "ok")

    for row in results:
        failures = _failure_reasons(
            row,
            wf_ok=wf_ok,
            pbo_ok=pbo_ok and pbo_symbol_ok.get(row["symbol"], True),
        )
        row["passed"] = not failures
        row["failure_reason"] = "; ".join(failures)

    passed = [row for row in results if row["passed"]]
    best_by_symbol: dict[str, dict] = {}
    for row in results:
        current = best_by_symbol.get(row["symbol"])
        if current is None or row["dsr"] > current["dsr"]:
            best_by_symbol[row["symbol"]] = row

    if record:
        for row in results:
            record_trial(
                db_path,
                family=FAMILY,
                hypothesis=HYPOTHESIS,
                symbol=row["symbol"],
                params=row["params"],
                window_start=row["start"],
                window_end=row["end"],
                result={
                    "sharpe": round(row["sharpe"], 4),
                    "cagr": round(row["cagr"], 4),
                    "max_drawdown": round(row["max_drawdown"], 4),
                    "num_trades": row["num_trades"],
                    "pass_rate": round(row["pass_rate"], 4),
                    "breach_rate": round(row["breach_rate"], 4),
                    "oos_pass_rate": (
                        round(row["oos_pass_rate"], 4)
                        if row["oos_pass_rate"] is not None
                        else None
                    ),
                    "dsr": round(row["dsr"], 4) if row["dsr"] is not None else None,
                    "pbo": (pbo_global or {}).get("pbo"),
                    "walk_forward": (wf or {}).get("verdict"),
                },
                outcome="passed" if row["passed"] else "failed",
                reason=row["failure_reason"][:800],
                source="sweep",
                run_id=run,
                sr_period=row["sharpe"] / np.sqrt(252.0),
                periods_per_year=252.0,
            )

    candidates: list[dict] = []
    if passed:
        from .lifecycle import register_candidate

        for row in passed:
            bot = BOT_IDS.get(row["symbol"])
            if not bot:
                continue
            try:
                candidate = register_candidate(
                    db_path,
                    bot=bot,
                    asset=row["symbol"],
                    evidence={
                        "family": FAMILY,
                        "strategy": row["strategy"],
                        "params": row["params"],
                        "sharpe": row["sharpe"],
                        "dsr": row["dsr"],
                        "pbo": (pbo_global or {}).get("pbo"),
                        "walk_forward": (wf or {}).get("verdict"),
                        "pass_rate": row["pass_rate"],
                        "breach_rate": row["breach_rate"],
                        "source": "lab research-swing",
                        "run_id": run,
                    },
                    note=f"research-swing run {run}; nunca enabled sin incubación",
                )
                candidates.append(candidate)
            except Exception as exc:
                errors.append(
                    {"symbol": row["symbol"], "error": f"lifecycle: {exc}"[:300]}
                )

    report = {
        "generated_at": _now(),
        "run_id": run,
        "family": FAMILY,
        "hypothesis": HYPOTHESIS,
        "symbols": list(symbols),
        "grid": [dict(item) for item in grid],
        "regime": REGIME,
        "atr_window": ATR_WINDOW,
        "timeframe": "H4",
        "rules": rules.describe(),
        "data": data,
        "datachecks": datachecks,
        "costs": costs_by_symbol,
        "costs_status": (
            "costes provisionales"
            if any(item.get("swap_provisional", True) for item in costs_by_symbol.values())
            else "swap incluido"
        ),
        "dsr_n_trials": n_trials,
        "dsr_trial_sr_std": sr_std,
        "pbo": pbo_global,
        "pbo_ok": pbo_ok,
        "pbo_by_symbol": pbo_by_symbol,
        "walk_forward": wf,
        "walk_forward_ok": wf_ok,
        "results": results,
        "errors": errors,
        "passed": len(passed),
        "candidates": candidates,
        "best_by_symbol": {
            symbol: {
                "params": row["params"],
                "sharpe": row["sharpe"],
                "pass_rate": row["pass_rate"],
                "breach_rate": row["breach_rate"],
                "dsr": row["dsr"],
            }
            for symbol, row in best_by_symbol.items()
        },
        "thresholds": {
            "min_pass": MIN_PASS,
            "max_breach": MAX_BREACH,
            "min_oos_pass": MIN_OOS_PASS,
            "min_trades": MIN_TRADES,
            "max_pbo": MAX_PBO,
            "min_dsr": MIN_DSR,
            "wf_train_days": WF_TRAIN_DAYS,
            "wf_test_days": WF_TEST_DAYS,
        },
        "holds_position": False,
        "enabled": False,
    }
    report["files"] = write_report(report, out)
    return report


def _year_returns(daily: pd.Series) -> dict[str, float]:
    if not hasattr(daily.index, "year"):
        return {}
    grouped = (1.0 + daily).groupby(daily.index.year).prod() - 1.0
    return {str(int(year)): float(value) for year, value in grouped.items()}


def _fmt(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "Sin datos"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def render_report(report: dict) -> str:
    lines = [
        "# Tendencia diaria en CFDs de tick grande",
        "",
        f"- Generado: {report['generated_at']}",
        f"- Run: `{report['run_id']}` · familia `{report['family']}`",
        f"- Activos: {', '.join(report['symbols'])} · ejecución H4 · señal D1",
        f"- Reglas: {report['rules']}",
        f"- DSR n_trials: {report['dsr_n_trials']}",
        f"- PBO global: {_fmt((report.get('pbo') or {}).get('pbo'), 3)}",
        f"- Walk-forward global: {(report.get('walk_forward') or {}).get('verdict') or 'Sin datos'}",
        "- Umbrales: "
        f"P(pasar) >= {report['thresholds']['min_pass']:.0%}, "
        f"P(breach) <= {report['thresholds']['max_breach']:.0%}, "
        f"DSR >= {report['thresholds']['min_dsr']:.0%}, "
        f"PBO <= {report['thresholds']['max_pbo']:.0%}, "
        f"trades >= {report['thresholds']['min_trades']}",
        "",
        "## Datos",
        "",
    ]
    for symbol, status in report["data"].items():
        h4 = status.get("h4") or {}
        d1 = status.get("d1") or {}
        lines.append(
            f"- **{symbol}**: H4 "
            f"{'ok' if h4.get('exists') else 'Sin datos'}"
            + (
                f" ({h4.get('rows')} barras, {h4.get('start')} → {h4.get('end')})"
                if h4.get("rows")
                else ""
            )
            + f" · D1 {d1.get('status') or ('ok' if d1.get('exists') else 'Sin datos')}"
            + (f" ({d1.get('reason')})" if d1.get("reason") else "")
        )
    lines += ["", "## Datacheck", ""]
    for key, check in report["datachecks"].items():
        lines.append(
            f"- `{key}`: **{check['status']}** · {check['rows']} barras"
            + (f" · {'; '.join(check['reasons'])}" if check.get("reasons") else "")
        )
    lines += ["", "## Costes", "", "| Activo | Comisión | Spread mediana | Spread p95 | Spread 3 años | Slippage |", "|---|---:|---:|---:|---:|---|"]
    for symbol, cost in report["costs"].items():
        lines.append(
            f"| {symbol} | {_fmt(cost['commission_bps_side'], 3)} bps/lado | "
            f"{_fmt(cost['spread_bps_median'], 3)} bps | "
            f"{_fmt(cost['spread_bps_p95'], 3)} bps | "
            f"{_fmt(cost.get('spread_bps_recent_3y'), 3)} bps | "
            f"{_fmt(cost['slippage_bps_optimistic'], 1)}/"
            f"{_fmt(cost['slippage_bps_conservative'], 1)} bps |"
        )
    lines += [
        "",
        "El coste por lado usa comisión + spread mediano de los últimos 3 años;",
        "el slippage conservador (2 bps) va aparte en `backtest.run`.",
        "",
    ]
    lines += [
        "",
        "## Variantes",
        "",
        "| Activo | Rápida | Lenta | Stop | Sharpe | CAGR | MaxDD | Trades | DSR | PBO | WF | Pasan | P(pasar) | P(breach) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|",
    ]
    for row in sorted(
        report["results"], key=lambda item: (item["symbol"], item["params"]["slow"], item["params"]["fast"], item["params"]["stop_atr"])
    ):
        pbo_symbol = (report.get("pbo_by_symbol") or {}).get(row["symbol"]) or {}
        lines.append(
            f"| {row['symbol']} | {row['params']['fast']} | {row['params']['slow']} | "
            f"{row['params']['stop_atr']:g} | {_fmt(row['sharpe'])} | "
            f"{_fmt(row['cagr'] * 100, 2, '%')} | {_fmt(row['max_drawdown'] * 100, 2, '%')} | "
            f"{row['num_trades']} | {_fmt(row['dsr'], 3)} | "
            f"{_fmt(pbo_symbol.get('pbo'), 3)} | "
            f"{(report.get('walk_forward') or {}).get('verdict') or 'Sin datos'} | "
            f"{'sí' if row['passed'] else 'no'} | {_fmt(row['pass_rate'], 3)} | "
            f"{_fmt(row['breach_rate'], 3)} |"
        )
    if not report["results"]:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | - | - |")
    lines += [
        "",
        f"**Resultado: {report['passed']} de {len(report['results'])} variantes pasan.**",
        "",
    ]
    if report["passed"]:
        lines += [
            "Las que pasan quedan registradas como **candidato** en el ciclo de",
            "vida (nunca `enabled`). La incubación y la promoción son humanas.",
            "",
        ]
    else:
        lines += [
            "Ninguna variante pasa la puerta: **se documenta y se para**. No se",
            "relajan umbrales ni se activa ningún bot.",
            "",
        ]
    if report["errors"]:
        lines += ["## Errores", ""]
        lines += [f"- {item}" for item in report["errors"]]
        lines.append("")
    lines += [
        "> Solo lectura y paper: no envía órdenes y no activa bots.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "swing.json"
    md_path = out_dir / "swing.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_report(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "BOT_IDS",
    "FAMILY",
    "GRID",
    "SYMBOLS",
    "artifact_name",
    "data_status",
    "daily_returns",
    "run_swing",
    "save_variant_artifact",
    "spread_bps",
    "write_report",
]
