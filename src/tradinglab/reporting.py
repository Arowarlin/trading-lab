from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ROOT, Settings
from .db import connect


def _fmt(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _sparkline(series: pd.Series, width: int = 900, height: int = 260) -> str:
    if series is None or len(series) < 2:
        return (
            f'<svg viewBox="0 0 {width} {height}" class="chart">'
            f'<text x="20" y="{height // 2}" fill="#8b949e">Sin historial de equity suficiente</text></svg>'
        )

    values = series.astype(float).tolist()
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 24
    n = len(values)

    points = []
    for i, v in enumerate(values):
        x = pad + (width - 2 * pad) * i / (n - 1)
        y = height - pad - (height - 2 * pad) * (v - lo) / span
        points.append(f"{x:.1f},{y:.1f}")

    positive = values[-1] >= values[0]
    color = "#3fb950" if positive else "#f85149"
    area = f"{pad},{height - pad} " + " ".join(points) + f" {width - pad},{height - pad}"

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" preserveAspectRatio="none">'
        f'<polygon points="{area}" fill="{color}" opacity="0.10"/>'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'</svg>'
    )


def _positions_table(positions: list[dict]) -> str:
    if not positions:
        return '<p class="muted">Sin posiciones abiertas.</p>'
    rows = "".join(
        f"<tr><td>{html.escape(p['ticker'])}</td><td>{p['qty']:g}</td>"
        f"<td>{_fmt(p['avg_price'])}</td><td>{_fmt(p['value'])}</td>"
        f"<td class='{'pos' if p['unrealized'] >= 0 else 'neg'}'>{_fmt(p['unrealized'])}</td></tr>"
        for p in positions
    )
    return (
        "<table><thead><tr><th>Ticker</th><th>Qty</th><th>Precio medio</th>"
        "<th>Valor</th><th>PnL</th></tr></thead><tbody>" + rows + "</tbody></table>"
    )


def _orders_table(orders: list[dict]) -> str:
    if not orders:
        return '<p class="muted">Sin órdenes todavía.</p>'
    rows = "".join(
        f"<tr><td>{html.escape(o['ts'][:19])}</td><td>{html.escape(o['ticker'])}</td>"
        f"<td>{html.escape(o['side'])}</td><td>{o['qty']:g}</td>"
        f"<td>{html.escape(o['status'])}</td><td>{html.escape(o['bot'] or '')}</td></tr>"
        for o in orders
    )
    return (
        "<table><thead><tr><th>Fecha</th><th>Ticker</th><th>Lado</th><th>Qty</th>"
        "<th>Estado</th><th>Bot</th></tr></thead><tbody>" + rows + "</tbody></table>"
    )


def build_dashboard(settings: Settings, broker, db_path: Path, out_path: Path | None = None) -> Path:
    snap = broker.snapshot({})
    equity = broker.equity_series()
    start_equity = float(equity.iloc[0]) if len(equity) else settings.starting_cash
    total_return = (snap["equity"] / start_equity - 1) if start_equity else 0.0

    with connect(db_path) as con:
        orders = [dict(r) for r in con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()]
        llm = con.execute(
            "SELECT COUNT(*) AS n, COALESCE(AVG(latency_ms), 0) AS avg_ms, "
            "COALESCE(SUM(ok), 0) AS ok FROM llm_calls"
        ).fetchone()

    out_path = out_path or ROOT / "reports" / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TradingLab · dashboard</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; padding: 32px; background: #0d1117; color: #e6edf3;
         font: 15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .muted {{ color: #8b949e; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 24px 0; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px 18px; }}
  .card .label {{ color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
  .card .value {{ font-size: 26px; font-weight: 600; margin-top: 6px; }}
  .chart {{ width: 100%; height: 260px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #161b22; border: 1px solid #30363d; border-radius: 10px; overflow: hidden; }}
  th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid #21262d; }}
  th {{ color: #8b949e; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
  tr:last-child td {{ border-bottom: none; }}
  .pos {{ color: #3fb950; }} .neg {{ color: #f85149; }}
  h2 {{ font-size: 16px; margin: 32px 0 12px; }}
</style></head><body>
<h1>TradingLab</h1>
<p class="muted">modo {settings.mode} · broker {settings.execution.broker} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</p>

<div class="grid">
  <div class="card"><div class="label">Equity</div><div class="value">{_fmt(snap['equity'])}</div></div>
  <div class="card"><div class="label">Cash</div><div class="value">{_fmt(snap['cash'])}</div></div>
  <div class="card"><div class="label">Posiciones</div><div class="value">{_fmt(snap['positions_value'])}</div></div>
  <div class="card"><div class="label">Retorno</div>
    <div class="value {'pos' if total_return >= 0 else 'neg'}">{total_return * 100:,.2f}%</div></div>
  <div class="card"><div class="label">Llamadas LLM</div><div class="value">{llm['n']}</div>
    <div class="muted">latencia media {llm['avg_ms'] / 1000:,.1f} s · ok {llm['ok']}/{llm['n']}</div></div>
</div>

<h2>Curva de equity</h2>
{_sparkline(equity)}

<h2>Posiciones</h2>
{_positions_table(snap['positions'])}

<h2>Últimas órdenes</h2>
{_orders_table(orders)}
</body></html>"""

    out_path.write_text(doc, encoding="utf-8")
    return out_path
