"""WF-TF: walk-forward con ventanas por timeframe sobre la matriz de robustez.

Reutiliza ``robustness._frontier_frame`` (matriz diaria ordenada de dias
habiles con ceros, arreglo R2 de ROBUST-1) y ``walkforward.walk_forward``.
No cambia umbrales ni puertas. Solo lee IS (``fitness_is``) y OOS-1 para
cerrar operaciones; nunca abre OOS-2. No escribe en discovery.db ni lab.db:
las lecturas se hacen con conexiones SQLite en modo ``ro``.

Uso:
    python scripts/wf_tf_eval.py --all-edge1-finalists \
        --out TL3_REPORTS/wf_tf_eval_edge1.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from tradinglab.discovery import campaigns, databank, perturb, robustness
from tradinglab.discovery.config import load_engine_config
from tradinglab.walkforward import walk_forward

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "discovery.db"

# Ventanas prerregistradas en TL3_REPORTS/robust1_wf_windows.md (train/test
# en dias habiles). La tabla esta congelada; no se ajusta con resultados.
WINDOWS: dict[str, tuple[int, int]] = {
    "M5": (60, 20),
    "M15": (60, 20),
    "M30": (120, 40),
    "H1": (180, 60),
    "H4": (360, 120),
    "D1": (504, 126),
}
MIN_FOLDS = 3


@contextmanager
def readonly_databank(db_path: str | Path | None = None) -> Iterator[Path]:
    """Fuerza las lecturas de ``databank`` a SQLite en modo solo lectura.

    ``databank._resolve_target`` inicializa el esquema al abrir una conexion
    normal. Aqui ``init_databank`` es un no-op y ``connect`` abre el fichero
    con ``mode=ro``, de modo que ninguna funcion de lectura pueda escribir.
    """

    target = Path(db_path or databank.DEFAULT_DISCOVERY_DB).resolve()
    original_connect = databank.connect
    original_init = databank.init_databank

    @contextmanager
    def _ro_connect(path: str | Path) -> Iterator[sqlite3.Connection]:
        resolved = Path(path).resolve()
        con = sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro", uri=True, timeout=30
        )
        con.execute("PRAGMA busy_timeout=5000")
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def _no_init(path: str | Path | None = None, *, con=None) -> Path:
        return Path(path or target)

    databank.connect = _ro_connect  # type: ignore[assignment]
    databank.init_databank = _no_init  # type: ignore[assignment]
    try:
        yield target
    finally:
        databank.connect = original_connect  # type: ignore[assignment]
        databank.init_databank = original_init  # type: ignore[assignment]


def windows_for(timeframe: str) -> tuple[int, int]:
    """Ventanas prerregistradas del TF; falla si el TF no esta en la tabla."""

    key = str(timeframe or "").strip().upper()
    if key not in WINDOWS:
        raise KeyError(f"TF sin ventana prerregistrada: {timeframe}")
    return WINDOWS[key]


def install_assumed_slippage() -> None:
    """Completa un perfil sin slippage con el asumido de ``engine.yaml``.

    CFD-006 (US500) no publica ``slippage_price``; sus campanas ya usaron el
    slippage asumido del motor (US500 = 0,5). Se parchea solo la carga del
    perfil en este proceso, igual que ``edge2_x3.py``; no se toca el motor ni
    ningun umbral. Si el perfil ya trae slippage, no cambia nada.
    """

    from dataclasses import replace

    from tradinglab.discovery.costs import assumed_slippage_for
    from tradinglab.propfund import costs as profile_module

    original = profile_module.load_profile
    if getattr(original, "_wf_tf_assumed_slippage", False):
        return

    def load_profile(account_id, instrument, **kwargs):
        profile = original(account_id, instrument, **kwargs)
        if getattr(profile, "slippage_price", None) is None:
            value, _source = assumed_slippage_for(instrument)
            profile = replace(profile, slippage_price=float(value))
        return profile

    load_profile._wf_tf_assumed_slippage = True  # type: ignore[attr-defined]
    profile_module.load_profile = load_profile
    # ENG-1 B-03: perturb ya no importa load_profile; el coste de validación se
    # construye en discovery.costs (validation_cost y build_account_cost).
    from tradinglab.discovery import costs as discovery_costs

    discovery_costs.load_profile = load_profile


def _sin_datos(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "status": "Sin datos",
        "verdict": "Sin datos",
        "ok": False,
        "reason": reason,
        "efficiency": None,
        "stitched_sharpe": None,
        "n_folds": 0,
        **extra,
    }


def evaluate_matrix(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    train_len: int | None = None,
    test_len: int | None = None,
    min_oos_sharpe: float | None = None,
    min_efficiency: float | None = None,
    trade_times_by_strategy: dict[int, list[Any]] | None = None,
    strategy_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Aplica el WF a una matriz ya construida, con las ventanas del TF."""

    config = load_engine_config().robustness
    min_sharpe = (
        float(config.wf_min_oos_sharpe)
        if min_oos_sharpe is None
        else float(min_oos_sharpe)
    )
    min_eff = (
        float(config.wf_min_efficiency)
        if min_efficiency is None
        else float(min_efficiency)
    )
    try:
        default_train, default_test = windows_for(timeframe)
    except KeyError as exc:
        return _sin_datos(str(exc), timeframe=str(timeframe))
    train = int(train_len if train_len is not None else default_train)
    test = int(test_len if test_len is not None else default_test)
    base = {
        "timeframe": str(timeframe or "").strip().upper(),
        "train_len": train,
        "test_len": test,
        "n_variants": int(frame.shape[1]),
        "rows": int(frame.shape[0]),
        "first_date": frame.index[0].date().isoformat() if len(frame) else None,
        "last_date": frame.index[-1].date().isoformat() if len(frame) else None,
        "thresholds": {
            "min_oos_sharpe": min_sharpe,
            "min_efficiency": min_eff,
            "min_folds": MIN_FOLDS,
        },
    }
    try:
        wf = walk_forward(
            frame.to_numpy(dtype=float), train_len=train, test_len=test
        )
    except ValueError as exc:
        return _sin_datos(str(exc), **base)

    verdict = wf.verdict(
        min_stitched_sharpe=min_sharpe,
        min_efficiency=min_eff,
    )
    ok = bool(
        wf.n_folds >= MIN_FOLDS
        and verdict == "ok"
        and wf.stitched_sharpe > min_sharpe
        and wf.efficiency >= min_eff
    )
    result = {
        **base,
        **wf.to_dict(),
        "verdict": verdict if wf.n_folds >= MIN_FOLDS else "Sin datos",
        "ok": ok,
        "status": "ok" if wf.n_folds >= MIN_FOLDS else "Sin datos",
        "fold_details": list(wf.fold_details),
    }
    if wf.n_folds < MIN_FOLDS:
        result["reason"] = f"folds insuficientes ({wf.n_folds} < {MIN_FOLDS})"
    if trade_times_by_strategy is not None and strategy_ids is not None:
        result.update(
            robustness._wf_trade_frequency(  # noqa: SLF001 - misma funcion que R3
                frame,
                list(wf.fold_details),
                trade_times_by_strategy,
                strategy_ids,
            )
        )
    return result


def evaluate_campaign(
    campaign_id: str,
    timeframe: str,
    *,
    db_path: str | Path | None = None,
    with_frequency: bool = True,
    train_len: int | None = None,
    test_len: int | None = None,
) -> dict[str, Any]:
    """Evalua una campana con la matriz y las ventanas de su TF."""

    with readonly_databank(db_path):
        frame, strategy_ids = robustness._frontier_frame(  # noqa: SLF001
            campaign_id, db_path
        )
        if frame is None:
            return {
                **_sin_datos("menos de 2 estrategias en el frontier"),
                "campaign_id": campaign_id,
                "timeframe": str(timeframe or "").strip().upper(),
            }
        trade_times = None
        if with_frequency:
            _combined, _campaign, setup, cost = perturb.load_campaign_inputs(
                campaign_id, db_path=db_path
            )
            is_frame = campaigns.load_segment(
                campaign_id, "is", db_path=db_path
            )
            trade_times = robustness.variant_trade_times(
                campaign_id,
                frame=is_frame,
                setup=setup,
                cost=cost,
                db_path=db_path,
            )
        result = evaluate_matrix(
            frame,
            timeframe,
            train_len=train_len,
            test_len=test_len,
            trade_times_by_strategy=trade_times,
            strategy_ids=strategy_ids,
        )
        result["campaign_id"] = campaign_id
        return result


def _finalists(prefix: str, db_path: str | Path) -> list[dict[str, Any]]:
    target = Path(db_path).resolve()
    con = sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "select id, campaign_id, timeframe, instrument from disc_strategies "
            "where campaign_id like ? and status = 'finalist' "
            "order by campaign_id, id",
            (f"{prefix}-%",),
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def _strategy_rows(
    strategy_ids: list[int], db_path: str | Path
) -> list[dict[str, Any]]:
    if not strategy_ids:
        return []
    target = Path(db_path).resolve()
    con = sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    marks = ",".join("?" for _ in strategy_ids)
    try:
        rows = con.execute(
            f"select id, campaign_id, timeframe, instrument from disc_strategies "
            f"where id in ({marks}) order by campaign_id, id",
            [int(item) for item in strategy_ids],
        ).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def _group_by_campaign(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        campaign_id = str(row["campaign_id"])
        item = grouped.setdefault(
            campaign_id,
            {
                "campaign_id": campaign_id,
                "timeframe": str(row["timeframe"]),
                "finalist_ids": [],
            },
        )
        item["finalist_ids"].append(int(row["id"]))
    return grouped


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="WF-TF por timeframe")
    parser.add_argument(
        "--all-edge1-finalists",
        action="store_true",
        help="atajo de --finalists-prefix edge1",
    )
    parser.add_argument(
        "--finalists-prefix",
        default=None,
        help="prefijo de campana para los finalistas (edge1, edge2, ...)",
    )
    parser.add_argument(
        "--strategy",
        type=int,
        action="append",
        default=[],
        help="id de estrategia finalista (repetible)",
    )
    parser.add_argument(
        "--campaign",
        action="append",
        default=[],
        help="id de campana (repetible)",
    )
    parser.add_argument(
        "--timeframe",
        default=None,
        help="TF para --campaign (si no, el de la campana)",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="ruta de discovery.db (solo lectura)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="JSON de salida",
    )
    parser.add_argument(
        "--no-frequency",
        action="store_true",
        help="omite la mediana de operaciones por ventana (mas rapido)",
    )
    parser.add_argument("--train-len", type=int, default=None)
    parser.add_argument("--test-len", type=int, default=None)
    args = parser.parse_args()
    install_assumed_slippage()

    db_path = Path(args.db)
    rows: list[dict[str, Any]] = []
    prefix = "edge1" if args.all_edge1_finalists else args.finalists_prefix
    if prefix:
        rows.extend(_finalists(prefix, db_path))
    rows.extend(_strategy_rows(args.strategy, db_path))
    seen: set[int] = set()
    unique_rows = []
    for row in rows:
        if int(row["id"]) in seen:
            continue
        seen.add(int(row["id"]))
        unique_rows.append(row)

    grouped = _group_by_campaign(unique_rows)
    for campaign_id in args.campaign:
        if campaign_id in grouped:
            continue
        with readonly_databank(db_path):
            campaign = databank.get_campaign(campaign_id, db_path=db_path)
        if campaign is None:
            raise SystemExit(f"campana no registrada: {campaign_id}")
        timeframe = args.timeframe or str(campaign["timeframe"])
        grouped[campaign_id] = {
            "campaign_id": campaign_id,
            "timeframe": timeframe,
            "finalist_ids": [],
        }

    results: list[dict[str, Any]] = []
    for campaign_id, item in grouped.items():
        print(
            f"[WF-TF] {campaign_id} {item['timeframe']} "
            f"finalistas={len(item['finalist_ids'])}",
            flush=True,
        )
        result = evaluate_campaign(
            campaign_id,
            item["timeframe"],
            db_path=db_path,
            with_frequency=not args.no_frequency,
            train_len=args.train_len,
            test_len=args.test_len,
        )
        result["finalist_ids"] = item["finalist_ids"]
        results.append(result)
        print(
            f"[WF-TF] {campaign_id} folds={result.get('n_folds')} "
            f"eff={result.get('efficiency')} "
            f"stitched={result.get('stitched_sharpe')} "
            f"verdict={result.get('verdict')} ok={result.get('ok')}",
            flush=True,
        )

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "windows": {key: list(value) for key, value in WINDOWS.items()},
        "min_folds": MIN_FOLDS,
        "results": results,
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        print(f"Escrito {out}: {len(results)} campanas", flush=True)
    else:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
        )


if __name__ == "__main__":
    main()
