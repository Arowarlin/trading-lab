"""EDGE-1 X1: plan de campanas congelado antes de ejecutar.

Lee TL3_REPORTS/edge1_data.json (X0) y escribe:
  - TL3_REPORTS/edge1_plan.json (matriz + hash)
  - TL3_REPORTS/edge1_plan.md   (plan legible)

No registra campanas; eso lo hace scripts/edge1_register.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "TL3_REPORTS" / "edge1_data.json"
PLAN_JSON = ROOT / "TL3_REPORTS" / "edge1_plan.json"
PLAN_MD = ROOT / "TL3_REPORTS" / "edge1_plan.md"

ALLOWED_ASSETS = ["US500", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"]
BLOCKED = {
    "US100": "swap CFD-001 6,24 bps/noche > 5 (coste fuera de magnitud)",
    "US30": "spread Sin datos en CFD-001 y CFD-006",
    "US500": "CFD-001 no permite US500; la regla de dos cuentas (CFD-001 + CFD-006) lo excluye",
}
INSTRUMENTS = {
    "trend_pullback_mtf": set(ALLOWED_ASSETS),
    "vol_squeeze_breakout": set(ALLOWED_ASSETS),
    "london_breakout": {"EURUSD", "GBPUSD", "XAUUSD"},
    "st_reversal_idx": {"US500"},
    "donchian_vol_h4": set(ALLOWED_ASSETS),
    "asia_range_reversion": set(ALLOWED_ASSETS),
    "fix_reversal": {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY"},
    "intraday_momentum_close_v2": {"US500"},
}
NEW_TEMPLATES = [
    "trend_pullback_mtf",
    "vol_squeeze_breakout",
    "london_breakout",
    "st_reversal_idx",
]
TIMEFRAMES = ["M15", "M30", "H1", "H4"]
COST_ACCOUNTS = ["CFD-001", "CFD-006"]
COST_MODE = "worst"
SEGMENTS_FIXED = {
    "is_end": "2019-12-31",
    "oos1": ["2020-01-01", "2022-12-31"],
    "oos2": ["2023-01-01", None],
}


def _hash(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidate_rows(data: dict, seen: set[tuple]) -> list[dict]:
    status = {
        (row["symbol"], row["timeframe"]): row["status"] for row in data["records"]
    }
    starts = {
        (row["symbol"], row["timeframe"]): row.get("is_start_effective")
        for row in data["records"]
    }
    rows = []
    for row in data["matrix"]:
        symbol = row["symbol"]
        timeframe = row["timeframe"]
        template = row["template"]
        if symbol in BLOCKED or symbol not in ALLOWED_ASSETS:
            continue
        if not row["viable"] or row["cost_r"] > 0.10:
            continue
        if status.get((symbol, timeframe)) == "fail":
            continue
        if symbol not in INSTRUMENTS.get(template, set()):
            continue
        if (template, symbol, timeframe) in seen:
            continue
        rows.append(
            {
                **row,
                "is_start": starts.get((symbol, timeframe)) or "2012-01-01",
                "is_end": SEGMENTS_FIXED["is_end"],
                "oos1_start": SEGMENTS_FIXED["oos1"][0],
                "oos1_end": SEGMENTS_FIXED["oos1"][1],
                "oos2_start": SEGMENTS_FIXED["oos2"][0],
                "oos2_end": SEGMENTS_FIXED["oos2"][1],
            }
        )
    rows.sort(key=lambda row: (row["cost_r"], row["template"], row["symbol"], row["timeframe"]))
    return rows


def _select(rows: list[dict]) -> list[dict]:
    selected: list[dict] = []

    def add(row: dict) -> None:
        if row not in selected:
            selected.append(row)

    # Regla congelada X1:
    # 1) una campana por plantilla nueva con alguna combinacion viable;
    # 2) al menos una por activo permitido;
    # 3) al menos tres por temporalidad (para que la consola X7 tenga M15/M30);
    # 4) el resto, por menor cost_r.
    for template in NEW_TEMPLATES:
        candidates = [row for row in rows if row["template"] == template]
        if candidates:
            add(candidates[0])
    for symbol in ALLOWED_ASSETS:
        candidates = [row for row in rows if row["symbol"] == symbol]
        if candidates:
            add(candidates[0])
    for timeframe in TIMEFRAMES:
        for row in [item for item in rows if item["timeframe"] == timeframe]:
            if sum(1 for item in selected if item["timeframe"] == timeframe) >= 3:
                break
            add(row)
    for row in rows:
        if len(selected) >= 28:
            break
        add(row)
    selected = selected[:28]
    selected.sort(key=lambda row: (row["cost_r"], row["template"], row["symbol"], row["timeframe"]))
    return selected


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    import sqlite3

    con = sqlite3.connect(ROOT / "data" / "discovery.db")
    seen = {
        (row[0], row[1], row[2])
        for row in con.execute(
            "select template, instrument, timeframe from disc_campaigns"
        )
    }
    rows = _candidate_rows(data, seen)
    selected = _select(rows)

    campaigns = []
    for index, row in enumerate(selected, start=1):
        slug = (
            f"edge1-{index:02d}-{row['template'].replace('_', '-')[:18]}-"
            f"{row['symbol'].lower()}-{row['timeframe'].lower()}"
        )
        campaigns.append(
            {
                "index": index,
                "campaign_id": slug,
                "template": row["template"],
                "instrument": row["symbol"],
                "timeframe": row["timeframe"],
                "profile": "small",
                "mode": "ga",
                "seed": index,
                "is_start": row["is_start"],
                "is_end": row["is_end"],
                "oos1_start": row["oos1_start"],
                "oos1_end": row["oos1_end"],
                "oos2_start": row["oos2_start"],
                "oos2_end": row["oos2_end"],
                "cost_accounts": COST_ACCOUNTS,
                "cost_mode": COST_MODE,
                "data_source": "dukascopy",
                "cost_r": round(float(row["cost_r"]), 6),
                "worst_account": row["account"],
                "n_total_expected": 440,
            }
        )

    payload = {
        "kind": "edge1-plan",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "segments": {
            "is": "max(2012-01-01, inicio util, usable_from):2019-12-31",
            "oos1": SEGMENTS_FIXED["oos1"],
            "oos2": SEGMENTS_FIXED["oos2"],
        },
        "cost": {
            "accounts": COST_ACCOUNTS,
            "mode": COST_MODE,
            "spread": "p75 + slippage x2 en la puerta X3",
        },
        "blocked": BLOCKED,
        "pass2_rule": {
            "profile": "medium",
            "max_campaigns": 6,
            "condition": "campanas de la pasada 1 con al menos 1 finalista que paso X3 completo",
            "order": "mas finalistas que pasaron; a igualdad, menor cost_r",
            "seed": "1000 + indice de la pasada 1",
        },
        "confirm_rule": {
            "reads": 1,
            "condition": "finalista que pasa las 4 puertas de COLA-EDGE-1 §4",
            "contaminated": "plantillas de apertura NY en indices: a forward, OOS-2 no valido",
        },
        "campaigns": campaigns,
        "n_total_sum": sum(item["n_total_expected"] for item in campaigns),
    }
    payload["plan_hash"] = _hash(
        {
            "segments": payload["segments"],
            "cost": payload["cost"],
            "campaigns": campaigns,
            "pass2_rule": payload["pass2_rule"],
            "confirm_rule": payload["confirm_rule"],
        }
    )
    PLAN_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    from collections import Counter

    by_tf = Counter(item["timeframe"] for item in campaigns)
    by_template = Counter(item["template"] for item in campaigns)
    by_symbol = Counter(item["instrument"] for item in campaigns)
    lines = [
        "# EDGE-1 X1 - plan de campanas congelado",
        "",
        f"**Congelado:** {payload['frozen_at']}",
        f"**Hash del plan:** `{payload['plan_hash']}`",
        f"**Campanas:** {len(campaigns)} · **n_total esperado:** {payload['n_total_sum']:,}",
        "",
        "## 1. Reglas congeladas",
        "",
        "- Fuente unica: `dukascopy`; perfil `small`; modo `ga`; semilla = indice de la matriz.",
        "- Coste: `--cost-account CFD-001 --cost-account CFD-006 --cost-mode worst`.",
        "- IS: `max(2012-01-01, inicio util, usable_from)` por activo/TF (excepcion congelada).",
        "- OOS-1: `2020-01-01:2022-12-31`; OOS-2: `2023-01-01:` (sellado).",
        "- Matriz: combinaciones que la plantilla admite, X0.4 viable (`cost_r <= 0,10`) y sin campana previa con la misma terna.",
        "- Cobertura: 1 por plantilla nueva viable, 1 por activo permitido, >=3 por TF; el resto por menor `cost_r`.",
        "",
        "## 2. Activos bloqueados en X0",
        "",
    ]
    for symbol, reason in BLOCKED.items():
        lines.append(f"- **{symbol}**: {reason}.")
    lines.extend(
        [
            "- **`st_reversal_idx`**: sin combinacion viable (US500 M30 cost_r 0,1088 > 0,10); plantilla creada, sin campana.",
            "",
            "## 3. Matriz",
            "",
            "| # | Campana | Plantilla | Activo | TF | Semilla | IS | OOS-1 | cost_r |",
            "|---:|---|---|---|---|---:|---|---|---:|",
        ]
    )
    for item in campaigns:
        lines.append(
            f"| {item['index']} | `{item['campaign_id']}` | {item['template']} | "
            f"{item['instrument']} | {item['timeframe']} | {item['seed']} | "
            f"{item['is_start']}:{item['is_end']} | "
            f"{item['oos1_start']}:{item['oos1_end']} | {item['cost_r']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"**Suma n_total:** {payload['n_total_sum']:,} (28 x 440).",
            "",
            "## 4. Reparto",
            "",
            f"- Por TF: {dict(sorted(by_tf.items()))}",
            f"- Por activo: {dict(sorted(by_symbol.items()))}",
            f"- Por plantilla: {dict(sorted(by_template.items()))}",
            "",
            "## 5. Pasada 2 (regla fijada ahora)",
            "",
            "Se repiten con perfil `medium` y semilla nueva (`1000 + indice`) las campanas de la pasada 1 "
            "con al menos 1 finalista que paso X3 completo. Maximo 6, por orden de mas finalistas que "
            "pasaron y, a igualdad, menor `cost_r`. Se registran antes de ejecutar y sus finalistas pasan "
            "por X3. Si ninguna cumple, X4 = `sin pasada 2`.",
            "",
            "## 6. Confirmacion OOS-2",
            "",
            "Una sola lectura por finalista que pase las 4 puertas de COLA-EDGE-1 §4. Las plantillas de "
            "apertura NY en indices quedan marcadas `a forward, OOS-2 no valido`; en esta matriz no hay "
            "ninguna campana de esas plantillas.",
            "",
            "## 7. Contaminacion declarada",
            "",
            "US100/US500/US30 ORB (`ny_open_vol_filter`, `session_breakout_htf` y cualquier ORB) tienen el "
            "OOS-2 dentro del diseno del EA `us100-ftmo1`. En esta matriz no se registran esas plantillas.",
            "",
        ]
    )
    PLAN_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Plan: {len(campaigns)} campanas, n_total {payload['n_total_sum']:,}, hash {payload['plan_hash'][:16]}")
    print(f"Por TF: {dict(sorted(by_tf.items()))}")
    print(f"Por activo: {dict(sorted(by_symbol.items()))}")
    print(f"Por plantilla: {dict(sorted(by_template.items()))}")


if __name__ == "__main__":
    main()
