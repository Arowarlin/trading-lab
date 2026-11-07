"""Modelos pequeños walk-forward, registry SQLite y campeón/retador.

Modelo base: ridge determinista en numpy (sin dependencias nuevas). El
reentrenamiento usa ventanas móviles y solo evalúa el tramo posterior a cada
entrenamiento. El registry no activa bots: la promoción es manual.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROOT
from .db import connect, init_db, utcnow

FEATURES = ("ret1", "ret5", "ret20", "vol20", "sma20", "sma50", "range20")
DEFAULT_TRAIN_DAYS = 504
DEFAULT_TEST_DAYS = 126
DEFAULT_STEP = 126
DEFAULT_ALPHA = 1.0


class ModelError(ValueError):
    pass


@dataclass(frozen=True)
class RidgeModel:
    features: tuple[str, ...]
    mean: list[float]
    std: list[float]
    beta: list[float]
    alpha: float


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    if "close" not in frame.columns:
        raise ModelError("faltan columnas OHLC: close")
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    ret1 = close.pct_change()
    out = pd.DataFrame(index=frame.index)
    out["ret1"] = ret1
    out["ret5"] = close.pct_change(5)
    out["ret20"] = close.pct_change(20)
    out["vol20"] = ret1.rolling(20).std()
    out["sma20"] = close / close.rolling(20).mean() - 1.0
    out["sma50"] = close / close.rolling(50).mean() - 1.0
    high = pd.to_numeric(frame["high"], errors="coerce") if "high" in frame else close
    low = pd.to_numeric(frame["low"], errors="coerce") if "low" in frame else close
    out["range20"] = (high - low).rolling(20).mean() / close
    out["target"] = ret1.shift(-1)
    return out.replace([np.inf, -np.inf], np.nan).dropna()


def _fit_ridge(train: pd.DataFrame, alpha: float = DEFAULT_ALPHA) -> RidgeModel:
    x = train[list(FEATURES)].to_numpy(dtype=float)
    y = train["target"].to_numpy(dtype=float)
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std == 0] = 1.0
    z = (x - mean) / std
    design = np.column_stack([np.ones(len(z)), z])
    penalty = np.eye(design.shape[1]) * float(alpha)
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return RidgeModel(
        features=FEATURES,
        mean=[float(v) for v in mean],
        std=[float(v) for v in std],
        beta=[float(v) for v in beta],
        alpha=float(alpha),
    )


def _predict(model: RidgeModel, frame: pd.DataFrame) -> np.ndarray:
    x = frame[list(model.features)].to_numpy(dtype=float)
    z = (x - np.asarray(model.mean)) / np.asarray(model.std)
    design = np.column_stack([np.ones(len(z)), z])
    return design @ np.asarray(model.beta)


def _metrics(returns: np.ndarray, exposure: np.ndarray) -> dict:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return {
            "days": 0,
            "total_return": None,
            "sharpe": None,
            "max_drawdown": None,
            "hit_rate": None,
            "trades": 0,
            "exposure": None,
        }
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0
    std = float(r.std(ddof=1)) if r.size > 1 else 0.0
    exp = np.asarray(exposure, dtype=int)
    trades = int(np.sum((exp[1:] == 1) & (exp[:-1] == 0))) if exp.size > 1 else int(exp[0])
    return {
        "days": int(r.size),
        "total_return": float(equity[-1] - 1.0),
        "sharpe": float(r.mean() / std * np.sqrt(252)) if std > 0 else 0.0,
        "max_drawdown": float(drawdown.min()),
        "hit_rate": float(np.mean(r[exp[: len(r)] == 1] > 0)) if np.any(exp == 1) else None,
        "trades": trades,
        "exposure": float(np.mean(exp[: len(r)])) if r.size else 0.0,
    }


def train_walk_forward(
    frame: pd.DataFrame,
    *,
    symbol: str,
    db_path: str | Path | None = None,
    train_days: int = DEFAULT_TRAIN_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    step: int = DEFAULT_STEP,
    alpha: float = DEFAULT_ALPHA,
    created_by: str = "cli",
) -> dict:
    """Entrena en ventanas móviles; registra un challenger si hay db_path."""
    if train_days < 80 or test_days < 20 or step < 1:
        raise ModelError("ventanas demasiado pequeñas (train>=80, test>=20)")
    data = _features(frame)
    if len(data) < train_days + test_days:
        raise ModelError(
            f"histórico insuficiente: {len(data)} filas para {train_days}+{test_days}"
        )
    folds = []
    stitched = []
    stitched_exposure = []
    for start in range(train_days, len(data) - test_days + 1, step):
        train = data.iloc[start - train_days : start]
        test = data.iloc[start : start + test_days]
        model = _fit_ridge(train, alpha)
        prediction = _predict(model, test)
        exposure = (prediction > 0).astype(int)
        returns = exposure * test["target"].to_numpy(dtype=float)
        folds.append(
            {
                "train_start": str(train.index[0].date()),
                "train_end": str(train.index[-1].date()),
                "test_start": str(test.index[0].date()),
                "test_end": str(test.index[-1].date()),
                "metrics": _metrics(returns, exposure),
            }
        )
        stitched.extend(returns.tolist())
        stitched_exposure.extend(exposure.tolist())
    if not folds:
        raise ModelError("sin folds walk-forward")
    overall = _metrics(
        np.asarray(stitched),
        np.asarray(stitched_exposure),
    )
    final = _fit_ridge(data, alpha)
    payload = {
        "symbol": symbol.upper(),
        "features": list(FEATURES),
        "alpha": float(alpha),
        "mean": final.mean,
        "std": final.std,
        "beta": final.beta,
        "train_start": str(data.index[0].date()),
        "train_end": str(data.index[-1].date()),
        "folds": len(folds),
        "metrics": overall,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    result = {
        "ok": True,
        "symbol": symbol.upper(),
        "folds": folds,
        "metrics": overall,
        "model": {
            "hash": digest,
            "features": list(FEATURES),
            "alpha": float(alpha),
            "coefficients": final.beta,
            "mean": final.mean,
            "std": final.std,
            "train_start": payload["train_start"],
            "train_end": payload["train_end"],
        },
        "registry_id": None,
    }
    if db_path is not None:
        result["registry_id"] = _register_model(db_path, result, created_by)
    return result


def _register_model(db_path: str | Path, result: dict, created_by: str) -> int:
    init_db(db_path)
    symbol = result["symbol"]
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM model_registry WHERE symbol=?",
            (symbol,),
        ).fetchone()
        version = int(row["v"]) + 1
        cursor = con.execute(
            "INSERT INTO model_registry"
            "(ts, name, version, kind, symbol, features, train_start, train_end, "
            "test_start, test_end, metrics, coefficients, hash, status, created_by) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                f"ridge-{symbol.lower()}",
                version,
                "ridge",
                symbol,
                json.dumps(result["model"]["features"]),
                result["model"]["train_start"],
                result["model"]["train_end"],
                result["folds"][0]["test_start"],
                result["folds"][-1]["test_end"],
                json.dumps(result["metrics"], ensure_ascii=False),
                json.dumps(
                    {
                        "alpha": result["model"]["alpha"],
                        "coefficients": result["model"]["coefficients"],
                        "mean": result["model"]["mean"],
                        "std": result["model"]["std"],
                    }
                ),
                result["model"]["hash"],
                "challenger",
                created_by,
            ),
        )
        model_id = int(cursor.lastrowid)
    _history(db_path, model_id, symbol, "register", created_by, {"version": version})
    return model_id


def _history(
    db_path: str | Path,
    model_id: int | None,
    symbol: str,
    action: str,
    actor: str,
    details: dict,
) -> None:
    with connect(db_path) as con:
        con.execute(
            "INSERT INTO model_registry_history"
            "(ts, model_id, symbol, action, actor, details) VALUES(?,?,?,?,?,?)",
            (utcnow(), model_id, symbol, action, actor, json.dumps(details)),
        )


def _row(row) -> dict:
    item = dict(row)
    for key in ("metrics", "coefficients", "features"):
        try:
            item[key] = json.loads(item[key])
        except (TypeError, ValueError):
            pass
    return item


def list_models(
    db_path: str | Path, symbol: str | None = None
) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        if symbol:
            rows = con.execute(
                "SELECT * FROM model_registry WHERE symbol=? ORDER BY id DESC",
                (symbol.upper(),),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM model_registry ORDER BY id DESC"
            ).fetchall()
    return [_row(row) for row in rows]


def get_model(db_path: str | Path, model_id: int) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM model_registry WHERE id=?", (int(model_id),)
        ).fetchone()
    if row is None:
        raise ModelError(f"modelo no encontrado: {model_id}")
    return _row(row)


def promote_model(
    db_path: str | Path,
    model_id: int,
    *,
    confirm: bool,
    by: str = "humano",
) -> dict:
    if not confirm:
        raise ModelError("promover un modelo exige confirmación explícita")
    init_db(db_path)
    model = get_model(db_path, model_id)
    previous = None
    with connect(db_path) as con:
        row = con.execute(
            "SELECT id FROM model_registry WHERE symbol=? AND status='champion' "
            "ORDER BY id DESC LIMIT 1",
            (model["symbol"],),
        ).fetchone()
        if row:
            previous = int(row["id"])
            con.execute(
                "UPDATE model_registry SET status='retired' WHERE id=?", (previous,)
            )
        con.execute(
            "UPDATE model_registry SET status='champion' WHERE id=?", (model_id,)
        )
    _history(
        db_path,
        model_id,
        model["symbol"],
        "promote",
        by,
        {"previous_id": previous},
    )
    return {
        "model": get_model(db_path, model_id),
        "previous_id": previous,
        "bot_enabled": False,
    }


def rollback_model(
    db_path: str | Path,
    symbol: str,
    *,
    confirm: bool,
    by: str = "humano",
) -> dict:
    if not confirm:
        raise ModelError("rollback exige confirmación explícita")
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM model_registry_history WHERE symbol=? AND action='promote' "
            "ORDER BY id DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
    if row is None:
        raise ModelError(f"sin historial de promoción para {symbol}")
    details = json.loads(row["details"] or "{}")
    previous = details.get("previous_id")
    if not previous:
        raise ModelError(f"{symbol} no tiene campeón anterior")
    previous_model = get_model(db_path, int(previous))
    with connect(db_path) as con:
        con.execute(
            "UPDATE model_registry SET status='retired' WHERE symbol=? AND status='champion'",
            (symbol.upper(),),
        )
        con.execute(
            "UPDATE model_registry SET status='champion' WHERE id=?",
            (int(previous),),
        )
    _history(
        db_path,
        int(previous),
        symbol.upper(),
        "rollback",
        by,
        {"restored_id": int(previous)},
    )
    return {"model": previous_model, "restored_id": int(previous), "bot_enabled": False}


def compare_models(db_path: str | Path, symbol: str) -> dict:
    rows = list_models(db_path, symbol)
    champion = next((row for row in rows if row["status"] == "champion"), None)
    challenger = next((row for row in rows if row["status"] == "challenger"), None)
    return {
        "symbol": symbol.upper(),
        "champion": champion,
        "challenger": challenger,
        "note": "Solo comparación informativa; no activa ni promueve nada.",
    }


def qlib_status() -> dict:
    venv = ROOT / ".venv-qlib"
    return {
        "available": venv.exists(),
        "path": str(venv),
        "note": (
            "Qlib debe vivir en .venv-qlib; no se añaden dependencias a .venv."
            if not venv.exists()
            else "Venv separado detectado; evaluación Qlib pendiente de datos."
        ),
    }


def registry_payload(db_path: str | Path) -> dict:
    return {
        "models": list_models(db_path),
        "qlib": qlib_status(),
        "note": "Challenger por defecto; promoción/rollback manual y sin activar bots.",
    }


__all__ = [
    "DEFAULT_ALPHA",
    "DEFAULT_STEP",
    "DEFAULT_TEST_DAYS",
    "DEFAULT_TRAIN_DAYS",
    "FEATURES",
    "ModelError",
    "RidgeModel",
    "compare_models",
    "get_model",
    "list_models",
    "promote_model",
    "qlib_status",
    "registry_payload",
    "rollback_model",
    "train_walk_forward",
]
