"""ENG-1 B-04 · ¿Qué noche cobra el triple swap tu bróker? Solo lectura de ``fills``.

Empareja, por símbolo y cuenta, cada deal de apertura con el siguiente de cierre
del lado contrario (mismo volumen) y lista las posiciones que durmieron
exactamente UNA noche (corte 17:00 NY), con la noche y el swap cobrado. Si la
noche jueves→viernes cobra ~3 veces lo de una noche normal, el código actual
(`propfund/costs.py`) acierta; si es la de viernes→lunes, hay que corregirlo.

No escribe en ninguna base de datos (abre lab.db en modo solo lectura).

    .venv\\Scripts\\python.exe docs\\engineering\\tools\\b04_swap_nights.py ^
        --db E:\\trading-lab\\data\\lab.db --out docs\\engineering\\WORKER_REPORTS\\B04-swap.md
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

NY = "America/New_York"


def _nights(open_ts: pd.Timestamp, close_ts: pd.Timestamp) -> list[str]:
    """Cortes de las 17:00 NY cruzados, etiquetados con la noche que empieza."""

    a, b = open_ts.tz_convert(NY), close_ts.tz_convert(NY)
    out = []
    day = a.normalize()
    while day <= b:
        cut = day + pd.Timedelta(hours=17)
        # Solo hay rollover de lunes a viernes; el del viernes cubre el fin de semana.
        if cut.day_of_week < 5 and a < cut <= b:
            nxt = "Mon" if cut.day_of_week == 4 else (cut + pd.Timedelta(days=1)).day_name()[:3]
            out.append(f"{cut.day_name()[:3]}->{nxt}")
        day += pd.Timedelta(days=1)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    path = Path(args.db)
    lines = ["# B04-swap · Swap cobrado por noche en deals reales (solo lectura)", ""]
    if not path.exists():
        Path(args.out).write_text("\n".join(lines + [f"**Sin datos:** no existe {path}", ""]), encoding="utf-8")
        return 1
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        frame = pd.read_sql_query(
            "SELECT id, COALESCE(ts_utc, ts) AS ts, account, symbol, side, volume, qty, price, swap"
            " FROM fills WHERE deal_id IS NOT NULL AND symbol IS NOT NULL ORDER BY account, symbol, id",
            con,
        )
    finally:
        con.close()
    if frame.empty:
        Path(args.out).write_text("\n".join(lines + ["**Sin datos:** no hay deals MT5 en `fills`.", ""]), encoding="utf-8")
        return 0
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    rows = []
    for (account, symbol), group in frame.groupby(["account", "symbol"], dropna=False):
        open_stack: list = []
        for deal in group.itertuples():
            if open_stack and open_stack[-1].side != deal.side:
                entry = open_stack.pop()
                nights = _nights(entry.ts, deal.ts)
                rows.append(
                    {
                        "account": account,
                        "symbol": symbol,
                        "side_open": entry.side,
                        "open": entry.ts.tz_convert(NY).strftime("%Y-%m-%d %a %H:%M"),
                        "close": deal.ts.tz_convert(NY).strftime("%Y-%m-%d %a %H:%M"),
                        "nights": nights,
                        "volume": float(entry.volume or entry.qty or 0.0),
                        "swap": float(deal.swap or 0.0),
                    }
                )
            else:
                open_stack.append(deal)
    one = [r for r in rows if len(r["nights"]) == 1]
    lines += [
        f"Posiciones emparejadas: {len(rows)}; de una sola noche: {len(one)}.",
        "",
        "| Cuenta | Símbolo | Lado | Apertura (NY) | Cierre (NY) | Noche | Volumen | Swap | Swap/volumen |",
        "|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for r in sorted(one, key=lambda x: (x["symbol"], x["nights"][0])):
        per = r["swap"] / r["volume"] if r["volume"] else float("nan")
        lines.append(
            f"| {r['account']} | {r['symbol']} | {r['side_open']} | {r['open']} | {r['close']} | "
            f"{r['nights'][0]} | {r['volume']:g} | {r['swap']:.2f} | {per:.2f} |"
        )
    lines += [
        "",
        "Cómo leerlo: para un mismo símbolo y lado, compara el swap por volumen de la noche",
        "`Thu->Fri` y la de `Fri->Mon` con el de una noche normal (`Mon->Tue`, `Tue->Wed`).",
        "La que sea ~3 veces mayor es la del triple swap. Si no hay ninguna de esas noches: Sin datos.",
        "",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Escrito {out}: {len(one)} posiciones de una noche")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
