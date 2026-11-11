from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tradinglab.datacheck import check_frame, check_symbol, find_cache


def _frame(rows: int = 300, start: str = "2020-01-01") -> pd.DataFrame:
    index = pd.bdate_range(start, periods=rows)
    close = 100.0 + np.arange(rows) * 0.1
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000.0,
        },
        index=index,
    )


def _write(tmp_path: Path, frame: pd.DataFrame, *, meta: dict | None = None) -> Path:
    path = tmp_path / "SPY__2020-01-01__2021-01-01.parquet"
    frame.to_parquet(path)
    if meta is not None:
        path.with_suffix(".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )
    return path


def test_frame_limpio_es_aviso_por_ajuste_no_declarado() -> None:
    result = check_frame(_frame(), "SPY")
    assert result["status"] == "aviso"
    assert result["checks"]["ohlc"]["status"] == "ok"
    assert result["checks"]["duplicados"]["status"] == "ok"
    assert result["checks"]["orden"]["status"] == "ok"
    assert result["checks"]["calendario"]["status"] == "ok"
    assert result["checks"]["ajuste"]["status"] == "aviso"
    assert any("ajuste" in reason for reason in result["reasons"])


def test_metadatos_declaran_ajuste_y_tz(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        _frame(),
        meta={"adjusted": True, "adjustment": "auto_adjust=True", "timezone": "date-only"},
    )
    result = check_frame(_frame(), "SPY", cache_path=path)
    assert result["status"] == "ok"
    assert result["checks"]["ajuste"]["status"] == "ok"
    assert result["checks"]["zona_horaria"]["status"] == "ok"


def test_duplicados_y_orden_son_falla() -> None:
    frame = _frame()
    duplicated = pd.concat([frame, frame.iloc[[10]]])
    result = check_frame(duplicated, "SPY")
    assert result["status"] == "falla"
    assert result["checks"]["duplicados"]["status"] == "falla"

    reversed_frame = frame.iloc[::-1]
    result = check_frame(reversed_frame, "SPY")
    assert result["status"] == "falla"
    assert result["checks"]["orden"]["status"] == "falla"


def test_ohlc_inconsistente_es_falla() -> None:
    frame = _frame()
    frame.loc[frame.index[5], "high"] = frame["low"].iloc[5] - 1.0
    result = check_frame(frame, "SPY")
    assert result["status"] == "falla"
    assert result["checks"]["ohlc"]["status"] == "falla"
    assert "OHLC inconsistente" in result["checks"]["ohlc"]["reason"]


def test_ruido_de_coma_flotante_en_ohlc_no_es_falla() -> None:
    """Yahoo ajustado deja close == high + 3e-15; eso no es un dato roto."""
    frame = _frame()
    frame.loc[frame.index[5], "close"] = frame["high"].iloc[5] + 3.55e-15
    result = check_frame(frame, "SPY")
    assert result["checks"]["ohlc"]["status"] == "ok"
    # un céntimo de verdad sí falla
    frame.loc[frame.index[6], "close"] = frame["high"].iloc[6] + 0.01
    result = check_frame(frame, "SPY")
    assert result["checks"]["ohlc"]["status"] == "falla"


def test_huecos_de_calendario_aviso_y_falla() -> None:
    frame = _frame(rows=300)
    small_gap = frame.drop(frame.index[100:110])
    result = check_frame(small_gap, "SPY")
    assert result["checks"]["calendario"]["status"] in {"aviso", "ok"}

    big_gap = frame.drop(frame.index[50:150])
    result = check_frame(big_gap, "SPY")
    assert result["status"] == "falla"
    assert result["checks"]["calendario"]["status"] == "falla"


def test_salto_extremo_aviso() -> None:
    frame = _frame(rows=300)
    jump = frame.index[150]
    new_close = float(frame["close"].iloc[149]) * 1.5
    frame.loc[jump, "open"] = new_close
    frame.loc[jump, "high"] = new_close * 1.01
    frame.loc[jump, "low"] = new_close * 0.99
    frame.loc[jump, "close"] = new_close
    result = check_frame(frame, "SPY")
    assert result["checks"]["ohlc"]["status"] == "ok"
    assert result["checks"]["saltos"]["status"] == "aviso"
    assert result["status"] == "aviso"


def test_bid_ask_presente_y_forex_sin_spread() -> None:
    frame = _frame()
    with_spread = frame.copy()
    with_spread["bid"] = with_spread["close"] - 0.01
    with_spread["ask"] = with_spread["close"] + 0.01
    assert check_frame(with_spread, "SPY")["checks"]["bid_ask"]["status"] == "ok"

    assert check_frame(frame, "SPY")["checks"]["bid_ask"]["status"] == "ok"
    forex = check_frame(frame, "EURUSD")
    assert forex["checks"]["bid_ask"]["status"] == "aviso"


def test_find_cache_elige_la_mas_larga(tmp_path: Path) -> None:
    short = tmp_path / "SPY__2023-01-01__2026-11-07.parquet"
    long = tmp_path / "SPY__2015-01-01__2026-11-07.parquet"
    one_day = tmp_path / "SPY__2026-11-07__2026-11-07.parquet"
    for path in (short, long, one_day):
        _frame(rows=10).to_parquet(path)
    assert find_cache(tmp_path, "SPY") == long


def test_check_symbol_sin_cache_es_sin_datos(tmp_path: Path) -> None:
    result = check_symbol("NOPE", cache_dir=tmp_path)
    assert result["status"] == "falla"
    assert result["rows"] == 0
    assert "Sin datos" in result["reasons"][0]


def test_check_symbol_lee_parquet(tmp_path: Path) -> None:
    path = _write(tmp_path, _frame())
    result = check_symbol("SPY", cache_dir=tmp_path)
    assert result["cache_path"] == str(path)
    assert result["rows"] == 300
    assert result["status"] in {"ok", "aviso"}
