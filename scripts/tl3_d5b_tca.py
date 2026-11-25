"""D5b · Diagnóstico de la TCA (solo lectura, no suma)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(".")
DB = ROOT / "data" / "lab.db"
ROWS = ROOT / "TL3_REPORTS" / "ai_trader_t5_rows.json"
REPORT = ROOT / "TL3_REPORTS" / "tca_diagnostico.md"
POINT = {"US100.cash": 0.01, "XAUUSD": 0.01, "GBPUSD": 1e-5, "USDJPY": 0.001}
T5_ENTRY_R = 0.0661


def _connect():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tca_counts(con) -> list[dict]:
    return [
        dict(row)
        for row in con.execute(
            "SELECT bot, symbol, COUNT(*) AS rows,"
            " SUM(slippage_bps = 0) AS zero,"
            " SUM(fill_px IS NULL) AS null_fill,"
            " SUM(bid IS NULL OR ask IS NULL OR requested_price IS NULL) AS legacy"
            " FROM tca GROUP BY bot, symbol ORDER BY bot, symbol"
        )
    ]


def _join_trades(con, rows: list[dict], window_s: int) -> pd.DataFrame:
    trades = {
        int(row["id"]): dict(row)
        for row in con.execute(
            "SELECT id, ts, symbol, side, style, entry, magic FROM ai_trades"
        )
    }
    fills = pd.DataFrame(
        [
            dict(row)
            for row in con.execute(
                "SELECT id, ts_utc, bot, symbol, side, price, magic FROM fills"
                " WHERE bot LIKE 'ai:%'"
            )
        ]
    )
    fills["ts"] = pd.to_datetime(fills.ts_utc, utc=True)
    tca = pd.DataFrame(
        [
            dict(row)
            for row in con.execute(
                "SELECT id, ts_utc, bot, symbol, side, fill_px FROM tca"
                " WHERE bot LIKE 'ai:%'"
            )
        ]
    )
    tca["ts"] = pd.to_datetime(tca.ts_utc, utc=True)

    matched = []
    for row in rows:
        trade = trades.get(int(row["id"]))
        if trade is None:
            continue
        ts = pd.Timestamp(trade["ts"])
        base = (
            (fills.bot == f"ai:{trade['style']}")
            & (fills.symbol.str.upper() == trade["symbol"].upper())
            & (fills.side.str.lower() == trade["side"].lower())
            & (fills.magic == trade["magic"])
            & ((fills.ts - ts).abs() <= pd.Timedelta(seconds=window_s))
        )
        candidates = fills[base]
        if len(candidates) != 1:
            continue
        fill = float(candidates.iloc[0].price)
        decision = float(trade["entry"])
        sign = 1 if trade["side"] == "buy" else -1
        point = POINT[trade["symbol"]]
        same_tca = tca[
            (tca.bot == f"ai:{trade['style']}")
            & (tca.symbol.str.upper() == trade["symbol"].upper())
            & (tca.side.str.lower() == trade["side"].lower())
            & ((tca.ts - ts).abs() <= pd.Timedelta(seconds=window_s))
        ]
        tca_fill = (
            float(same_tca.iloc[0].fill_px)
            if len(same_tca) == 1 and pd.notna(same_tca.iloc[0].fill_px)
            else None
        )
        matched.append(
            {
                "id": int(row["id"]),
                "symbol": trade["symbol"],
                "side": trade["side"],
                "decision": decision,
                "fill": fill,
                "bps": sign * (fill - decision) / decision * 1e4,
                "points": sign * (fill - decision) / point,
                "fill_r": sign
                * (fill - decision)
                / abs(float(row["real_entry"]) - float(row["real_sl"])),
                "tca_fill": tca_fill,
                "tca_diff_points": None
                if tca_fill is None
                else abs(tca_fill - fill) / point,
                "tca_diff_bps": None
                if tca_fill is None
                else abs(tca_fill - fill) / fill * 1e4,
            }
        )
    return pd.DataFrame(matched)


def _stats(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"n": 0}
    return {
        "n": len(frame),
        "median_bps": float(frame["bps"].median()),
        "p95_bps": float(frame["bps"].quantile(0.95)),
        "median_points": float(frame["points"].median()),
        "p95_points": float(frame["points"].quantile(0.95)),
        "mean_r": float(frame["fill_r"].mean()),
        "median_r": float(frame["fill_r"].median()),
    }


def main() -> None:
    con = _connect()
    counts = _tca_counts(con)
    total = dict(
        con.execute(
            "SELECT COUNT(*) AS rows, SUM(slippage_bps = 0) AS zero,"
            " SUM(fill_px IS NULL) AS null_fill,"
            " SUM(latency_ms IS NULL) AS null_latency,"
            " SUM(bid IS NULL OR ask IS NULL OR requested_price IS NULL) AS legacy"
            " FROM tca"
        ).fetchone()
    )
    decisions = dict(
        con.execute(
            "SELECT COUNT(*) AS n, SUM(entry IS NOT NULL) AS with_entry"
            " FROM ai_decisions WHERE decision='take'"
        ).fetchone()
    )
    orders = dict(
        con.execute(
            "SELECT COUNT(*) AS n, SUM(limit_price IS NOT NULL) AS with_price"
            " FROM orders WHERE order_type='market'"
        ).fetchone()
    )
    signals = dict(
        con.execute(
            "SELECT COUNT(*) AS n, SUM(run_id IS NOT NULL) AS with_run"
            " FROM signals"
        ).fetchone()
    )
    fills_ai = dict(
        con.execute(
            "SELECT COUNT(*) AS n, SUM(order_id IS NULL) AS null_order"
            " FROM fills WHERE bot LIKE 'ai:%'"
        ).fetchone()
    )
    tca_fill_ids = dict(
        con.execute(
            "SELECT COUNT(*) AS n, SUM(fill_id IS NULL) AS null_fill_id FROM tca"
        ).fetchone()
    )
    con.close()

    rows = json.loads(ROWS.read_text(encoding="utf-8"))
    rows = [row for row in rows if int(row["id"]) not in {52, 54}]
    strict = _join_trades(_connect(), rows, 5)
    extended = _join_trades(_connect(), rows, 20)
    strict_stats = _stats(strict)
    extended_stats = _stats(extended)
    unmatched = sorted({int(row["id"]) for row in rows} - set(extended["id"]))
    diff = extended["tca_diff_points"].dropna()
    diff_bps = extended["tca_diff_bps"].dropna()
    diff_nonzero = int((diff_bps > 0).sum())

    lines = [
        "# TL3-D · D5b Diagnóstico de la TCA",
        "",
        "Solo lectura: no se modifica `execution/mt5.py`, `execution/paper.py`, "
        "`lab.db` ni la tabla `tca`. Nada de este bloque suma al contador.",
        "",
        "## 1. Causa",
        "",
        "**Confirmada.** `execution/mt5.py:772-783` registra:",
        "",
        "- `signal_px=price` y `order_px=price`, donde `price` es el precio de la "
        "petición en el momento del envío, no el precio de la decisión.",
        "- `fill_px = result.price or price`: si MT5 devuelve 0, cae al precio "
        "pedido.",
        "- `slippage_bps=tca_slip(price, fill_px, side)` y no se pasa "
        "`latency_ms`.",
        "",
        "`execution/paper.py:140-155` hace lo mismo con `signal_px=price`, "
        "`order_px=price`, `fill_px=fill_px` y, además, "
        "`slippage_bps=self.slippage_bps` (el supuesto del modelo, no una medida). "
        "`tca.record_fill` guarda `ts_utc` como hora de registro, no de fill.",
        "",
        "Consecuencia: la TCA solo mide el desvío entre el envío y la ejecución en "
        "el mismo tick; nunca entre la decisión y la ejecución. Si `result.price` "
        "es 0 o igual a `price`, el resultado es 0 por construcción.",
        "",
        "## 2. Conteos",
        "",
        f"- Filas: **{total['rows']}**; `slippage_bps=0`: **{total['zero']}**; "
        f"`fill_px` nulo: **{total['null_fill']}**; `latency_ms` nulo: "
        f"**{total['null_latency']}**; sin `bid`/`ask`/`requested_price`: "
        f"**{total['legacy']}**.",
        "",
        "| Bot | Símbolo | Filas | Slippage 0 | `fill_px` nulo | Sin bid/ask/requested |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in counts:
        lines.append(
            f"| {row['bot']} | {row['symbol']} | {row['rows']} | "
            f"{row['zero']} | {row['null_fill']} | {row['legacy']} |"
        )
    lines += [
        "",
        "Las 2 filas de `qqq-trend-f13` no tienen `fill_px`; las otras 66 filas "
        "tienen slippage 0. Todas las filas tienen `latency_ms` nulo.",
        "",
        "## 3. Slippage decisión → ejecución",
        "",
        "No hay un precio de decisión unible sin suposiciones en las tablas que "
        "mira D5b:",
        "",
        f"- `ai_decisions`: {decisions['n']} decisiones `take`, "
        f"{decisions['with_entry']} con `entry`; no hay `proposal_id`/`order_id` y "
        "las 48 recientes lo tienen nulo.",
        f"- `orders`: {orders['n']} órdenes market, "
        f"{orders['with_price']} con `limit_price`.",
        f"- `signals`: {signals['n']} filas, {signals['with_run']} con `run_id`; "
        "no hay `order_id`.",
        f"- `fills` de IA: {fills_ai['n']} filas, {fills_ai['null_order']} con "
        f"`order_id` nulo; `tca.fill_id` nulo en {tca_fill_ids['null_fill_id']} de "
        f"{tca_fill_ids['n']}.",
        "",
        "Sí existe un enlace exacto para las operaciones de IA: "
        "`ai_trades.entry` (precio de la propuesta/decisión) y `fills.price` "
        "(fill real), unidos por bot, símbolo, lado, magic y una ventana temporal "
        "única. Se exige **una sola** fila candidata; si hay 0 o >1, es "
        "**Sin datos**.",
        "",
        "| Ventana | n | Mediana bps | p95 bps | Mediana puntos | p95 puntos | "
        "Media R | Mediana R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| ≤5 s | {strict_stats['n']} | {strict_stats['median_bps']:.3f} | "
        f"{strict_stats['p95_bps']:.3f} | {strict_stats['median_points']:.1f} | "
        f"{strict_stats['p95_points']:.1f} | {strict_stats['mean_r']:+.4f} | "
        f"{strict_stats['median_r']:+.4f} |",
        f"| ≤20 s | {extended_stats['n']} | {extended_stats['median_bps']:.3f} | "
        f"{extended_stats['p95_bps']:.3f} | {extended_stats['median_points']:.1f} | "
        f"{extended_stats['p95_points']:.1f} | {extended_stats['mean_r']:+.4f} | "
        f"{extended_stats['median_r']:+.4f} |",
        "",
        f"Sin datos con la ventana de 20 s: "
        f"{', '.join('#' + str(i) for i in unmatched) or 'ninguna'}.",
        "",
        "Por símbolo (ventana de 20 s):",
        "",
        "| Símbolo | n | Mediana bps | p95 bps |",
        "|---|---:|---:|---:|",
    ]
    for symbol, group in extended.groupby("symbol"):
        lines.append(
            f"| {symbol} | {len(group)} | {group['bps'].median():.3f} | "
            f"{group['bps'].quantile(0.95):.3f} |"
        )
    lines += [
        "",
        f"El `fill_px` de la TCA **no es el fill real** en "
        f"{diff_nonzero} de {len(diff_bps)} operaciones comparables: mediana de "
        f"|diferencia| {diff_bps.median():.3f} bps, máximo {diff_bps.max():.3f} bps. "
        "Ejemplo: #15, TCA 26899.43 frente a fill real 26907.23 "
        f"({diff.max():.0f} puntos de US100, "
        f"{diff_bps.max():.3f} bps).",
        "",
        "Para los bots que no son de IA no hay precio de decisión: "
        "`tca.signal_px` es el precio de envío y `orders.limit_price` es nulo, así "
        "que su decisión → ejecución es **Sin datos**; el envío → fill de la TCA "
        "es ~0 por construcción.",
        "",
        "### Comparación con T5-bis",
        "",
        f"T5-bis atribuye **+{T5_ENTRY_R:.4f} R** a la entrada, medido como "
        "`sim_entry − ai_trades.entry` (la decisión), no como `sim_entry − fill`. "
        f"El fill real fue **{extended_stats['mean_r']:+.4f} R** peor que la "
        "decisión (media, ventana de 20 s); por tanto, la entrada simulada frente "
        f"al fill real es ~**{T5_ENTRY_R - extended_stats['mean_r']:+.4f} R**. La "
        "mayor parte del componente de entrada es la regla de entrada de la "
        "simulación, no la ejecución. No se rehace T5 y las cifras agregadas de "
        "C1/T5 no cambian.",
        "",
        "## 4. Lectores de `tca.slippage_bps`",
        "",
        "| Lector | Qué hace | Efecto con el valor actual |",
        "|---|---|---|",
        "| `ai_trader.py:3209` (`_slippage_avg`) | `AVG(slippage_bps)` por bot y "
        "símbolo; llena `slippage_avg` del marcador de celdas. | Muestra 0 bps; "
        "no es un coste ni un gate (solo se imprime en `cli.py:9759`). |",
        "| `ai_distill.py:1260` (`_forward_validation`) | `AVG(slippage_bps)` por "
        "bot; exige n≥10 y `avg ≤ max_slippage_bps` (3.0) y ≤ el supuesto. | "
        "Pasa siempre con 0; la validación forward no puede detectar slippage. |",
        "| `tca.py:211-215` (`build_tca`) | p50/p95/EWMA y estado `ok`/`vigilar`/"
        "`deriva`. | p50≈0 → `ok`; con <5 fills, `sin datos`. |",
        "| `tca.py:250-280` (`_alert_transitions`) | Envía `tca_drift` solo al pasar "
        "a `deriva`. | Nunca se dispara con 0. |",
        "| `tca.py:296-312` (`attach_to_drift`) | Añade `tca_status` y EWMA a las "
        "filas de deriva. | Informativo; no cambia el estado de deriva. |",
        "| `web.py:2044-2062` (`/api/tca`) | Panel TCA. | Muestra `ok`. |",
        "| `cli.py:8654-8679` (`lab tca`) | Tabla de slippage/latencia. | Muestra "
        "0 bps y latencia Sin datos. |",
        "| `discovery/slippage_measured.py:286-291` | Fuente `tca`: usa "
        "`order_px`/`fill_px` para celdas y propuesta de costes "
        "(`costs.measured.yaml`). | También mide ~0; la propuesta subestima el "
        "coste. No se ejecutó en este bloque. |",
        "",
        "## 5. Propuesta de corrección (no aplicada)",
        "",
        "1. **`signal_px`**: pasar el precio de la decisión/propuesta (el que "
        "genera la señal o el plan), no el precio de la petición. Si no existe, "
        "pasar `None` y dejar `slippage_bps` nulo; nunca 0.",
        "2. **`fill_px`**: usar el precio del deal ejecutado. Si MT5 devuelve 0, "
        "dejar `None`; no caer a `price`.",
        "3. **`latency_ms`**: capturar la hora de la decisión y la del fill y "
        "pasar la diferencia en ms. Como mínimo, medir envío → fill y etiquetarlo "
        "como tal; no llamarlo decisión → ejecución.",
        "4. **Paper**: registrar el coste esperado en `expected_cost_bps` y la "
        "medida real en `slippage_bps`; no etiquetar `self.slippage_bps` como "
        "slippage medido.",
        "5. **Filas antiguas**: no borrar ni reescribir. Añadir una marca "
        "`measurement`/`tca_version` (o una vista `tca_measured`) que excluya las "
        "filas sin `latency_ms` o sin `bid`/`ask`/`requested_price`, y hacer que "
        "los consumidores lean la vista. Las filas viejas quedan para auditoría.",
        "6. **Producción**: `execution/mt5.py` es la ejecución del forward y de "
        "`ai_trader`. Aplicar esto exige otra cola con aprobación del operador: "
        "línea base (`lab propfund baseline --reason`), test de regresión, "
        "`docs/CHANGELOG-produccion.md` y tag `tl2-<id>-pre`.",
        "",
        "## Límites",
        "",
        "- No se modificó `execution/mt5.py`, `execution/paper.py`, `tca.py`, "
        "`lab.db` ni la tabla `tca`.",
        "- No se enviaron órdenes ni se abrió MT5.",
        "- No se ejecutó `discovery/slippage_measured` ni se escribió "
        "`costs.measured.yaml`.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
