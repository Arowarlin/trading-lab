"""Informe pre-market nativo con Qwen local, sin Trading-R1 ni WSL.

Solo lee datos/caché y macro_events; opcionalmente envía el informe por
Telegram. No envía órdenes, no activa bots y no cambia criterios.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import data as data_mod
from .config import Settings
from .decisions import record_decision
from .intel.calendar import DbCalendarProvider
from .intel.news_scoring import scoring_config
from .time_utils import market_today

WATCHLIST = ("SPY", "QQQ", "NVDA")


def _snapshot(ticker: str, settings: Settings, today: date) -> dict:
    start = (today.replace(year=today.year - 3)).isoformat()
    try:
        frame = data_mod.fetch(
            ticker,
            start,
            today.isoformat(),
            settings.data.cache_dir,
        )
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)[:240]}
    if len(frame) < 25:
        return {"ticker": ticker, "error": f"histórico insuficiente: {len(frame)} barras"}
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


def build_report(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    tickers: tuple[str, ...] | list[str] = WATCHLIST,
    include_llm: bool = True,
    hours: int = 48,
    client=None,
    agent_runner=None,
    day: date | None = None,
) -> dict:
    """Construye el informe; los fallos se muestran como Sin datos."""
    settings = settings or Settings()
    today = day or market_today()
    symbols = [str(item).strip().upper() for item in tickers if str(item).strip()]
    if not symbols:
        raise ValueError("watchlist vacía")
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
        f"# TradingLab · Pre-market {today.isoformat()}",
        "",
        f"- Modo: **{settings.mode}** · broker: **{settings.execution.broker}**",
        f"- Generado: {datetime.now(timezone.utc).isoformat(timespec='minutes')}",
        "- Solo lectura: no envía órdenes ni activa bots.",
        "",
        "## Watchlist",
        "",
        "| Activo | Precio | 1d | 5d | 20d | Tendencia | Rating | Confianza |",
        "|---|---:|---:|---:|---:|---|---|---:|",
    ]
    for row in rows:
        if row.get("error"):
            lines.append(
                f"| {row['ticker']} | Sin datos | — | — | — | — | — | — |"
            )
            continue
        lines.append(
            f"| {row['ticker']} | {row['price']:.2f} | {_fmt_pct(row['return_1d'])} | "
            f"{_fmt_pct(row['return_5d'])} | {_fmt_pct(row['return_20d'])} | "
            f"{row['trend']} | {_rating(row.get('result'))} | "
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
    }


def send_report(text: str) -> None:
    from .telegram import send_configured

    send_configured(text)


__all__ = ["WATCHLIST", "build_report", "send_report"]
