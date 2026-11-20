"""Briefing pre-Londres y pre-NY del universo CFD/futuros.

Solo lee datos de MT5 en modo adjunto (``AttachOnlyBroker``), la caché de
``data/`` y ``macro_events``; opcionalmente envía el informe por Telegram.
No envía órdenes, no activa bots y no cambia criterios. Si MT5 no está abierto
o un activo no tiene datos, se escribe **Sin datos**.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import Settings
from .decisions import record_decision
from .intel.calendar import DbCalendarProvider
from .intel.news_scoring import scoring_config
from .propfund.market import ACTIVE_UNIVERSE, CFD_UNIVERSE, briefing_slot
from .time_utils import market_today

WATCHLIST = CFD_UNIVERSE


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


def _rates(ticker: str, settings: Settings):
    """Barras D1 desde MT5 (solo lectura). ``None`` si no hay datos."""
    try:
        from .propfund.market import rates

        frame = rates(ticker, timeframe="D1", count=800, settings=settings)
    except Exception:
        return None
    if frame is None or len(frame) < 25:
        return None
    return frame


def _snapshot(ticker: str, settings: Settings, today: date) -> dict:
    frame = _rates(ticker, settings)
    if frame is None:
        return {
            "ticker": ticker,
            "error": "Sin datos: MT5 no disponible o histórico insuficiente",
        }
    close = frame["close"].astype(float)
    last = float(close.iloc[-1])

    def ret(days: int) -> float | None:
        if len(close) <= days:
            return None
        return float(last / close.iloc[-1 - days] - 1.0)

    def sma(days: int) -> float | None:
        return float(close.iloc[-days:].mean()) if len(close) >= days else None

    sma20, sma50, sma200 = sma(20), sma(50), sma(200)
    trend = "mixed"
    if sma20 and sma50 and sma200:
        if last > sma20 > sma50 > sma200:
            trend = "up"
        elif last < sma20 < sma50 < sma200:
            trend = "down"
    atr = None
    if len(frame) >= 15:
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        prev = close.shift(1)
        tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
        atr = float(tr.iloc[-14:].mean())
    return {
        "ticker": ticker,
        "price": last,
        "return_1d": ret(1),
        "return_5d": ret(5),
        "return_20d": ret(20),
        "trend": trend,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "atr14": atr,
        "as_of": str(frame.index[-1])[:10],
        "error": None,
    }


def _calendar(db_path: str | Path, hours: int) -> dict:
    now = datetime.now(timezone.utc)
    try:
        result = DbCalendarProvider(db_path).fetch(
            now, now + timedelta(hours=max(1, int(hours)))
        )
    except Exception as exc:
        return {"status": "error", "message": str(exc)[:200], "events": []}
    events = []
    for event in result.events:
        events.append(
            {
                "event": event.event,
                "ts_utc": event.ts_utc.isoformat(),
                "importance": event.importance,
                "source": event.source,
            }
        )
    return {
        "status": result.status.value,
        "message": result.message,
        "events": events,
    }


def _fmt_pct(value: float | None) -> str:
    return "Sin datos" if value is None else f"{value * 100:+.2f}%"


def _rating(result: dict | None) -> str:
    return str((result or {}).get("rating") or "Sin datos")


def _confidence(result: dict | None) -> str:
    value = (result or {}).get("confidence")
    return "—" if value is None else f"{float(value):.0%}"


def _slot_label(slot: str) -> str:
    return {
        "pre_london": "pre-Londres",
        "pre_ny": "pre-Nueva York",
    }.get(slot, "fuera de ventana")


def build_report(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    tickers: tuple[str, ...] | list[str] | None = None,
    include_llm: bool = True,
    hours: int = 48,
    client=None,
    agent_runner=None,
    day: date | None = None,
    session: str = "auto",
) -> dict:
    """Construye el briefing; los fallos se muestran como Sin datos."""
    settings = settings or Settings()
    today = day or market_today()
    symbols = [
        str(item).strip().upper() for item in (tickers or ACTIVE_UNIVERSE) if str(item).strip()
    ]
    if not symbols:
        raise ValueError("watchlist vacía")
    slot = session if session in {"pre_london", "pre_ny"} else briefing_slot()
    model = scoring_config(settings)["model"]
    if agent_runner is None:
        from .agents.lite import run_lite_agent

        def agent_runner(ticker, when, cfg, **kwargs):
            return run_lite_agent(ticker, when, cfg, **kwargs)

    rows = []
    errors = []
    for ticker in symbols:
        snapshot = _snapshot(ticker, settings, today)
        result = None
        if include_llm and snapshot.get("error") is None:
            try:
                result = agent_runner(
                    ticker,
                    today.isoformat(),
                    settings,
                    client=client,
                    model=model,
                )
                try:
                    record_decision(
                        db_path,
                        {**result, "ticker": ticker, "date": today.isoformat()},
                        mode="lite",
                    )
                except Exception:
                    pass
            except Exception as exc:
                snapshot["error"] = str(exc)[:240]
                errors.append(f"{ticker}: {snapshot['error']}")
        rows.append({**snapshot, "result": result})
    calendar = _calendar(db_path, hours)
    lines = [
        f"# TradingLab · Briefing {_slot_label(slot)} · {today.isoformat()}",
        "",
        f"- Modo: **{settings.mode}** · datos: **MT5 solo lectura**",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='minutes')}",
        "- Solo lectura: no envía órdenes ni activa bots.",
        "",
        "## Universo CFD",
        "",
        "| Activo | Precio | 1d | 5d | 20d | ATR14 | Tendencia | Rating | Confianza |",
        "|---|---:|---:|---:|---:|---:|---|---|---:|",
    ]
    for row in rows:
        if row.get("error"):
            lines.append(
                f"| {row['ticker']} | Sin datos | — | — | — | — | — | — | — |"
            )
            continue
        atr_text = "Sin datos" if row.get("atr14") is None else f"{row['atr14']:.4g}"
        lines.append(
            f"| {row['ticker']} | {row['price']:.4g} | {_fmt_pct(row['return_1d'])} | "
            f"{_fmt_pct(row['return_5d'])} | {_fmt_pct(row['return_20d'])} | "
            f"{atr_text} | {row['trend']} | {_rating(row.get('result'))} | "
            f"{_confidence(row.get('result'))} |"
        )
    lines += ["", f"## Próximos eventos macro ({hours} h)", ""]
    if calendar["events"]:
        lines += [
            "| UTC | Evento | Importancia | Fuente |",
            "|---|---|---|---|",
        ]
        for event in calendar["events"]:
            lines.append(
                f"| {event['ts_utc'][:16]} | {event['event']} | "
                f"{event['importance']} | {event['source']} |"
            )
    else:
        lines.append(
            f"Sin datos de eventos ({calendar['status']}): "
            f"{calendar.get('message') or 'sin registros'}"
        )
    lines += [
        "",
        "## Notas",
        "",
        "- El rating es una referencia del LLM local; no es una orden.",
        "- Si falta un dato se muestra **Sin datos**; no se inventan precios.",
        "- Revisar siempre el contexto y el riesgo antes de operar.",
    ]
    if errors:
        lines += ["", "### Avisos", ""] + [f"- {item}" for item in errors]
    return {
        "text": "\n".join(lines).strip() + "\n",
        "rows": rows,
        "calendar": calendar,
        "model": model,
        "errors": errors,
        "tickers": symbols,
        "session": slot,
        "read_only": True,
        "source": "mt5",
    }


def send_report(text: str) -> None:
    from .telegram import send_configured

    send_configured(text)


__all__ = ["WATCHLIST", "build_report", "send_report"]
