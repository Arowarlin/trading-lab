"""Arnés de autoevaluación del pipeline (T01).

Dos modos, ambos en memoria y sin tocar ``discovery.db`` ni el contador:

* ``gates``: genera flujos de R por operación para IS, OOS-1 y OOS-2 y aplica
  las reglas de :mod:`tradinglab.discovery.decisions`. Las puertas que no se
  pueden simular con flujos de R (PBO, WF, régimen, perturbaciones, coste
  x1,5 y challenge) se marcan como aprobadas: cota superior optimista.
* ``bars``: barras BID sintéticas con un spread conocido y una señal con
  ventaja ``δ`` conocida, pasadas por ``fastbt`` v2 + ``CostBook``. Debe
  recuperar ``δ − coste`` dentro del intervalo de confianza.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.stats import t as t_dist

from ..config import ROOT
from . import decisions
from .config import load_engine_config

REPORT_PATH = ROOT / "reports" / "discovery" / "harness-current.md"
DEFAULT_FREQUENCIES = (12.0, 50.0, 250.0, 1000.0)
DEFAULT_EDGES = (0.0, 0.05, 0.10, 0.20)
DEFAULT_SEED = 7
DEFAULT_SIMS = 2000
Z95 = 1.959963984540054


@dataclass(frozen=True)
class GateRow:
    frequency: float
    edge: float
    distribution: str
    simulations: int
    approved: int
    level3: int
    p_approve: float
    ci_low: float
    ci_high: float
    p_level3: float


@dataclass(frozen=True)
class BarsRow:
    edge: float
    trades: int
    recovered_mean_r: float
    expected_r: float
    ci_low: float
    ci_high: float
    cost_r: float
    passed: bool


def wilson_interval(
    successes: int, total: int, *, z: float = Z95
) -> tuple[float, float]:
    """Intervalo de Wilson al 95 % para una proporción."""

    if total <= 0:
        return 0.0, 1.0
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def segment_years(
    config=None, *, today: date | None = None
) -> dict[str, float]:
    """Duración en años de los tramos por defecto de ``engine.yaml``."""

    config = config or load_engine_config()
    segments = config.data_quality.default_segments
    end = today or datetime.now(timezone.utc).date()

    def years(start: str, finish: str | None) -> float:
        first = pd.Timestamp(start).date()
        last = end if finish is None else pd.Timestamp(finish).date()
        return max(0.0, (last - first).days / 365.25)

    return {
        "is": years(segments["is"][0], segments["is"][1]),
        "oos1": years(segments["oos1"][0], segments["oos1"][1]),
        "oos2": years(segments["oos2"][0], segments["oos2"][1]),
    }


def _draw(
    rng: np.random.Generator,
    shape: tuple[int, int],
    edge: float,
    distribution: str,
) -> np.ndarray:
    if distribution == "t":
        # t con 4 grados de libertad, escalada a desviación 1.
        return edge + rng.standard_t(4, size=shape) / math.sqrt(2.0)
    return rng.normal(edge, 1.0, size=shape)


def _profit_factor(values: np.ndarray) -> np.ndarray:
    positive = np.where(values > 0.0, values, 0.0).sum(axis=1)
    negative = -np.where(values < 0.0, values, 0.0).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(negative > 0.0, positive / negative, np.inf)
    return ratio


def _simulate_v2(
    rng: np.random.Generator,
    *,
    frequency: float,
    edge: float,
    sims: int,
    n_development: int,
    n_holdout: int,
    distribution: str,
) -> GateRow:
    """Protocolo v2: LCB en desarrollo y holdout único con consistencia."""

    development = _draw(
        rng, (sims, max(1, n_development)), float(edge), distribution
    )
    mean_dev = development.mean(axis=1)
    sd_dev = development.std(axis=1, ddof=1)
    n_dev = max(1, n_development)
    critical = float(t_dist.ppf(0.95, max(1, n_dev - 1)))
    with np.errstate(divide="ignore", invalid="ignore"):
        lcb_dev = mean_dev - critical * sd_dev / math.sqrt(n_dev)
    drift = 100.0 * norm.cdf(mean_dev * math.sqrt(n_dev))
    level3 = (lcb_dev > 0.0) & (drift >= decisions.DEFAULT_DRIFT_PERCENTILE)
    if n_holdout > 0:
        holdout = _draw(
            rng, (sims, int(n_holdout)), float(edge), distribution
        )
        mean_h = holdout.mean(axis=1)
        sd_h = holdout.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t_h = np.where(
                sd_h > 0.0, mean_h / sd_h * math.sqrt(n_holdout), 0.0
            )
            consistency = mean_h >= lcb_dev - 2.0 * sd_h / math.sqrt(n_holdout)
        level4 = level3 & (t_h >= 1.6448536269514722) & consistency
    else:
        level4 = np.zeros(sims, dtype=bool)
    approved = int(level4.sum())
    level3_count = int(level3.sum())
    low, high = wilson_interval(approved, sims)
    return GateRow(
        frequency=float(frequency),
        edge=float(edge),
        distribution=distribution,
        simulations=sims,
        approved=approved,
        level3=level3_count,
        p_approve=approved / sims,
        ci_low=low,
        ci_high=high,
        p_level3=level3_count / sims,
    )


def simulate_gates(
    *,
    frequency: float,
    edge: float,
    simulations: int,
    seed: int,
    years: dict[str, float],
    folds: int = 4,
    distribution: str = "normal",
    protocol: str = "v1",
) -> GateRow:
    """Una celda frecuencia × ventaja × distribución."""

    rng = np.random.default_rng(int(seed))
    sims = max(1, int(simulations))
    n_is = max(1, int(round(float(frequency) * years["is"])))
    n_oos1 = max(1, int(round(float(frequency) * years["oos1"])))
    n_oos2 = max(0, int(round(float(frequency) * years["oos2"])))

    if str(protocol).lower() == "v2":
        return _simulate_v2(
            rng,
            frequency=frequency,
            edge=edge,
            sims=sims,
            n_development=n_is + n_oos1,
            n_holdout=n_oos2,
            distribution=distribution,
        )

    is_values = _draw(rng, (sims, n_is), float(edge), distribution)
    is_mean = is_values.mean(axis=1)
    fold_size = max(1, n_is // max(1, int(folds)))
    positive = np.zeros(sims, dtype=int)
    for _index in range(max(1, int(folds))):
        fold = _draw(rng, (sims, fold_size), float(edge), distribution)
        positive += (fold.mean(axis=1) > 0.0).astype(int)

    # Control de deriva: percentil del resultado frente a entradas nulas.
    drift_percentile = 100.0 * norm.cdf(is_mean * math.sqrt(n_is))
    rank1 = (
        (drift_percentile >= decisions.DEFAULT_DRIFT_PERCENTILE)
        & (is_mean > 0.0)
        & (positive >= max(1, int(folds) - 1))
    )

    oos1_values = _draw(rng, (sims, n_oos1), float(edge), distribution)
    oos1_mean = oos1_values.mean(axis=1)
    oos1_pf = _profit_factor(oos1_values)
    oos1_ok = (oos1_mean > 0.0) & (oos1_pf > decisions.MIN_PROFIT_FACTOR)

    # level3: finalista + coste x1,5 y perturbaciones (no simuladas → pasan).
    level3 = rank1 & oos1_ok

    if n_oos2 > 0:
        oos2_values = _draw(rng, (sims, n_oos2), float(edge), distribution)
        oos2_mean = oos2_values.mean(axis=1)
        oos2_sd = oos2_values.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            z_value = np.where(
                oos2_sd > 0.0,
                oos2_mean / oos2_sd * math.sqrt(n_oos2),
                0.0,
            )
        enough = n_oos2 >= 30
        # random OOS-2 ≥ 95 ≈ z ≥ 1,645; el resto de puertas de nivel 4 pasan.
        level4 = (
            level3
            & enough
            & (oos2_mean > 0.0)
            & (z_value >= 1.6448536269514722)
        )
    else:
        level4 = np.zeros(sims, dtype=bool)

    approved = int(level4.sum())
    level3_count = int(level3.sum())
    low, high = wilson_interval(approved, sims)
    return GateRow(
        frequency=float(frequency),
        edge=float(edge),
        distribution=distribution,
        simulations=sims,
        approved=approved,
        level3=level3_count,
        p_approve=approved / sims,
        ci_low=low,
        ci_high=high,
        p_level3=level3_count / sims,
    )


def simulate_bars(
    *,
    edge: float,
    trades: int,
    seed: int,
    spread_bps: float = 2.0,
    risk_pct: float = 3.0,
    sigma_pct: float = 1.0,
    price: float = 10_000.0,
) -> BarsRow:
    """Señal sintética con ventaja conocida a través de fastbt v2 + CostBook."""

    from . import fastbt
    from .costs import CostBook

    count = max(1, int(trades))
    rng = np.random.default_rng(int(seed))
    n = count * 3 + 3
    index = pd.date_range("2024-01-01 00:00", periods=n, freq="h", tz="UTC")
    open_ = np.full(n, price, dtype=float)
    high = np.full(n, price, dtype=float)
    low = np.full(n, price, dtype=float)
    close = np.full(n, price, dtype=float)
    long_sig = np.zeros(n, dtype=bool)
    risky = price * float(risk_pct) / 100.0
    sigma = price * float(sigma_pct) / 100.0
    for position in range(count):
        signal = 3 * position + 1
        entry = signal + 1
        exit_ = entry + 1
        long_sig[signal] = True
        move = float(edge) * risky + rng.normal(0.0, sigma)
        move = max(move, -0.99 * risky)  # el stop no se toca en la muestra
        open_[entry] = price
        high[entry] = price
        low[entry] = price
        close[entry] = price
        open_[exit_] = price
        close[exit_] = price + move
        high[exit_] = max(price, close[exit_])
        low[exit_] = min(price, close[exit_])
    bars = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )
    signals = fastbt.Signals(long_sig, np.zeros(n, dtype=bool))

    cost_model = fastbt.CfdBpsCosts(
        commission_bps=0.0,
        slippage_bps=0.0,
        spread_bps=float(spread_bps),
    )
    panel = cost_model.panel(bars)
    account = type(
        "SyntheticAccount",
        (),
        {
            "account": "SYNTH",
            "instrument": "US100",
            "panel": lambda self, _bars: panel,
            "swap": None,
        },
    )()
    book = CostBook(
        [account], mode="target", session_tz="UTC", cost_model_version=2
    )
    limits = fastbt.RunLimits(
        session_tz="UTC",
        session_start="00:00",
        session_end="23:00",
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        close_at_end=False,
        cost_model_version=2,
    )
    result = fastbt.run(
        signals,
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=risk_pct, target=None, time_exit_bars=1),
        book,
        limits,
        cost_model_version=2,
    )
    applied = book.apply(result.trades, session_tz="UTC")
    values = np.array(
        [trade.r_net for trade in applied.trades if trade.r_net is not None],
        dtype=float,
    )
    cost_r = spread_bps / 10_000.0 * price / risky
    expected = float(edge) - cost_r
    if len(values) > 1:
        standard_error = values.std(ddof=1) / math.sqrt(len(values))
        low_ci = values.mean() - Z95 * standard_error
        high_ci = values.mean() + Z95 * standard_error
    else:
        low_ci = high_ci = float(values.mean()) if len(values) else 0.0
    passed = bool(
        low_ci <= expected <= high_ci
        or abs(float(values.mean()) - expected) <= 1e-9
    )
    return BarsRow(
        edge=float(edge),
        trades=int(len(values)),
        recovered_mean_r=float(values.mean()) if len(values) else 0.0,
        expected_r=expected,
        ci_low=float(low_ci),
        ci_high=float(high_ci),
        cost_r=float(cost_r),
        passed=passed,
    )


def _parse_values(values: Iterable[float] | str) -> tuple[float, ...]:
    if isinstance(values, str):
        raw = [item.strip() for item in values.split(",") if item.strip()]
        return tuple(float(item) for item in raw)
    return tuple(float(item) for item in values)


def render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Arnés de autoevaluación · resultado actual",
        "",
        "Generado por `lab discovery harness`. Datos sintéticos; no toca el",
        "databank ni el contador de pruebas.",
        "",
        f"- Semilla: `{payload['seed']}` · simulaciones: `{payload['simulations']}`",
        f"- Protocolo: `{payload.get('protocol', 'v1')}`",
        f"- Tramos (años): `{payload['years']}`",
        "",
    ]
    if payload["mode"] == "gates":
        lines += [
            "## Puertas simuladas",
            "",
            "Se simulan deriva, IS > 0, pliegues, OOS-1 (expectativa y PF) y",
            "OOS-2 (n ≥ 30, media > 0, z ≥ 1,645). PBO, WF, régimen,",
            "perturbaciones, coste x1,5 y challenge se tratan como aprobados",
            "(cota superior optimista).",
            "",
            "| Ops/año | Ventaja R | Distribución | P(aprobar) | IC95 % | P(nivel 3) |",
            "|---:|---:|---|---:|---:|---:|",
        ]
        for row in payload["rows"]:
            lines.append(
                f"| {row.frequency:g} | {row.edge:g} | {row.distribution} | "
                f"{row.p_approve:.3f} | "
                f"[{row.ci_low:.3f}, {row.ci_high:.3f}] | {row.p_level3:.3f} |"
            )
    else:
        lines += [
            "## Recuperación de la ventaja en barras sintéticas",
            "",
            "La diferencia entre `δ` y la media recuperada con la misma semilla",
            "es ruido de muestreo, no un sesgo: con 5 semillas la media oscila",
            "alrededor de `δ − coste`. Se demuestra en el RESULTADO de C3.",
            "",
            "| Ventaja R | Operaciones | Media recuperada | Esperado (δ − coste) | IC95 % | Coste R | Pasa |",
            "|---:|---:|---:|---:|---|---:|---|",
        ]
        for row in payload["rows"]:
            lines.append(
                f"| {row.edge:g} | {row.trades} | {row.recovered_mean_r:.4f} | "
                f"{row.expected_r:.4f} | [{row.ci_low:.4f}, {row.ci_high:.4f}] | "
                f"{row.cost_r:.5f} | {'sí' if row.passed else 'no'} |"
            )
    lines.append("")
    return "\n".join(lines)


def run(
    *,
    mode: str = "gates",
    frequencies: Iterable[float] | str = DEFAULT_FREQUENCIES,
    edges: Iterable[float] | str = DEFAULT_EDGES,
    simulations: int = DEFAULT_SIMS,
    seed: int = DEFAULT_SEED,
    output: str | Path | None = None,
    today: date | None = None,
    protocol: str = "v1",
) -> dict[str, Any]:
    """Ejecuta el arnés y escribe el informe Markdown."""

    mode = str(mode).strip().lower()
    if mode not in {"gates", "bars"}:
        raise ValueError("mode debe ser gates o bars")
    protocol = str(protocol).strip().lower()
    if protocol not in {"v1", "v2"}:
        raise ValueError("protocol debe ser v1 o v2")
    frequencies = _parse_values(frequencies)
    edges = _parse_values(edges)
    config = load_engine_config()
    years = segment_years(config, today=today)
    if mode == "gates":
        rows: list[Any] = []
        for frequency in frequencies:
            for edge in edges:
                for distribution in ("normal", "t"):
                    rows.append(
                        simulate_gates(
                            frequency=frequency,
                            edge=edge,
                            simulations=simulations,
                            seed=seed,
                            years=years,
                            distribution=distribution,
                            protocol=protocol,
                        )
                    )
    else:
        rows = [
            simulate_bars(
                edge=edge, trades=simulations, seed=seed + index
            )
            for index, edge in enumerate(edges)
        ]
    payload = {
        "mode": mode,
        "protocol": protocol,
        "seed": int(seed),
        "simulations": int(simulations),
        "years": {key: round(value, 3) for key, value in years.items()},
        "frequencies": frequencies,
        "edges": edges,
        "rows": rows,
    }
    path = Path(output) if output else REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(payload), encoding="utf-8")
    payload["path"] = str(path)
    payload["rows_as_dict"] = [asdict(row) for row in rows]
    return payload


__all__ = [
    "BarsRow",
    "DEFAULT_EDGES",
    "DEFAULT_FREQUENCIES",
    "DEFAULT_SIMS",
    "GateRow",
    "REPORT_PATH",
    "render_report",
    "run",
    "segment_years",
    "simulate_bars",
    "simulate_gates",
    "wilson_interval",
]
