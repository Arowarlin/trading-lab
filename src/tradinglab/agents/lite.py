from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..config import DEFAULT_DB, ROOT, Settings
from ..data import fetch
from ..indicators import atr, rsi, sma
from ..llm import LLMClient
from ..time_utils import market_today
from .bridge import RATING_TO_TARGET, AgentError

# Contexto compacto: una sola llamada al LLM con datos objetivos. En un 27B
# local (~1-2 tok/s) un run multi-agente con herramientas tarda horas; esto
# tarda minutos y mantiene la decisión diaria.
SCHEMA: dict = {
    "type": "object",
    "properties": {
        "rating": {
            "type": "string",
            "enum": ["Buy", "Overweight", "Hold", "Underweight", "Sell"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "thesis": {"type": "string", "maxLength": 600},
        "risks": {"type": "string", "maxLength": 400},
        "horizon_days": {"type": "integer", "minimum": 1, "maximum": 120},
    },
    "required": ["rating", "confidence", "thesis", "risks", "horizon_days"],
    "additionalProperties": False,
}

SYSTEM = (
    "Eres un analista cuantitativo disciplinado. Recibes SOLO datos técnicos "
    "objetivos de un activo y debes emitir una decisión de swing (2-8 semanas). "
    "No inventes noticias, fundamentales ni precios que no estén en los datos. "
    "Si la señal es ambigua o el riesgo/beneficio no está claro, elige Hold. "
    'Responde únicamente con el JSON del esquema: rating, confidence (0-1), '
    "thesis (máx. 600 caracteres), risks (máx. 400) y horizon_days."
)


def _pct(value: float, base: float) -> float | None:
    if base == 0 or not math.isfinite(base) or not math.isfinite(value):
        return None
    return round((value / base - 1.0) * 100.0, 2)


def build_context(df: pd.DataFrame, ticker: str, day: str) -> dict:
    """Resumen numérico compacto; sin texto libre que el modelo pueda inflar."""
    if len(df) < 220:
        raise AgentError(f"histórico insuficiente para {ticker}: {len(df)} barras")

    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    ma20 = float(sma(close, 20).iloc[-1])
    ma50 = float(sma(close, 50).iloc[-1])
    ma200 = float(sma(close, 200).iloc[-1])
    atr14 = float(atr(df).iloc[-1])
    rsi_raw = rsi(close).iloc[-1]
    if pd.isna(rsi_raw):
        # RSI es NA cuando no hubo pérdidas en la ventana (serie monótona).
        rsi14 = 100.0 if close.diff().iloc[-14:].clip(lower=0).sum() > 0 else None
    else:
        rsi14 = float(rsi_raw)

    window = close.iloc[-252:] if len(close) >= 252 else close
    high_52w = float(window.max())
    low_52w = float(window.min())
    rets = close.pct_change()
    vol20 = float(rets.iloc[-20:].std() * math.sqrt(252) * 100.0)
    vol_ratio = float(df["volume"].iloc[-1] / df["volume"].iloc[-20:].mean())

    def ret(days: int) -> float | None:
        if len(close) <= days:
            return None
        return round(float(close.iloc[-1] / close.iloc[-1 - days] - 1.0) * 100.0, 2)

    if price > ma50 > ma200:
        trend = "up"
    elif price < ma50 < ma200:
        trend = "down"
    else:
        trend = "mixed"

    return {
        "ticker": ticker.upper(),
        "date": day,
        "price": round(price, 4),
        "returns_pct": {
            "1d": ret(1),
            "5d": ret(5),
            "20d": ret(20),
            "60d": ret(60),
            "120d": ret(120),
        },
        "sma": {"20": round(ma20, 4), "50": round(ma50, 4), "200": round(ma200, 4)},
        "price_vs_sma_pct": {
            "20": _pct(price, ma20),
            "50": _pct(price, ma50),
            "200": _pct(price, ma200),
        },
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "atr14": round(atr14, 4) if math.isfinite(atr14) else None,
        "atr_pct": round(atr14 / price * 100.0, 2) if price else None,
        "high_52w": round(high_52w, 4),
        "low_52w": round(low_52w, 4),
        "distance_from_high_pct": _pct(price, high_52w),
        "distance_from_low_pct": _pct(price, low_52w),
        "realized_vol_20d_pct": round(vol20, 2) if math.isfinite(vol20) else None,
        "volume_ratio_20d": round(vol_ratio, 2) if math.isfinite(vol_ratio) else None,
        "trend": trend,
    }


def _validate(decision: dict) -> dict:
    rating = str(decision.get("rating", "Hold")).strip()
    if rating not in RATING_TO_TARGET:
        rating = "Hold"
    try:
        confidence = min(max(float(decision.get("confidence", 0.0)), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        horizon = int(decision.get("horizon_days", 20))
    except (TypeError, ValueError):
        horizon = 20
    return {
        "rating": rating,
        "confidence": round(confidence, 3),
        "thesis": str(decision.get("thesis", ""))[:600],
        "risks": str(decision.get("risks", ""))[:400],
        "horizon_days": max(1, min(horizon, 120)),
    }


def run_lite_agent(
    ticker: str,
    analysis_date: str | None,
    settings: Settings,
    *,
    client: LLMClient | None = None,
    start: str = "",
    out_dir: str | Path | None = None,
    model: str | None = None,
) -> dict:
    """Una llamada al LLM con contexto técnico compacto. Devuelve la decisión."""
    day = analysis_date or market_today().isoformat()
    ticker = ticker.upper()
    start = start or (market_today().replace(year=market_today().year - 3)).isoformat()

    df = fetch(ticker, start, market_today().isoformat(), settings.data.cache_dir)
    context = build_context(df, ticker, day)

    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": (
                "Datos de mercado (JSON):\n"
                + json.dumps(context, ensure_ascii=False)
                + "\n\nEmite la decisión para un horizonte de swing."
            ),
        },
    ]

    llm_cfg = (
        settings.llm.model_copy(update={"model": model})
        if model
        else settings.llm
    )
    client = client or LLMClient(llm_cfg, DEFAULT_DB)
    started = time.perf_counter()
    raw = client.chat_json(messages, purpose=f"agent-lite:{ticker}", schema=SCHEMA)
    elapsed = round(time.perf_counter() - started, 1)
    decision = _validate(raw)

    payload = {
        "ok": True,
        "mode": "lite",
        "ticker": ticker,
        "date": day,
        "rating": decision["rating"],
        "confidence": decision["confidence"],
        "decision": decision["thesis"],
        "risks": decision["risks"],
        "horizon_days": decision["horizon_days"],
        "model": llm_cfg.model,
        "elapsed_s": elapsed,
        "context": context,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    out = Path(out_dir) if out_dir else ROOT / "data" / "agent_runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"lite_{ticker}_{day}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload


__all__ = ["SCHEMA", "SYSTEM", "build_context", "run_lite_agent"]
