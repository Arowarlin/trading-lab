"""EDGE-2 Y1: plan congelado de campanas de indices.

Lee TL3_REPORTS/edge2_data.json (Y0) y escribe edge2_plan.json/.md.
No registra campanas; eso lo hace scripts/edge2_register.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "TL3_REPORTS" / "edge2_data.json"
PLAN_JSON = ROOT / "TL3_REPORTS" / "edge2_plan.json"
PLAN_MD = ROOT / "TL3_REPORTS" / "edge2_plan.md"

TEMPLATES = [
    "trend_pullback_mtf",
    "vol_squeeze_breakout",
    "donchian_vol_h4",
    "st_reversal_idx",
]
ALLOWED_ASSETS = ["US100", "US500", "US30"]
BLOCKED = {
    "US30": "spread Sin datos en broker_spreads y costs.measured.yaml",
}
INSTRUMENTS = {
    "trend_pullback_mtf": set(ALLOWED_ASSETS),
    "vol_squeeze_breakout": set(ALLOWED_ASSETS),
    "donchian_vol_h4": set(ALLOWED_ASSETS),
    "st_reversal_idx": set(ALLOWED_ASSETS),
}
TIMEFRAMES = ["M15", "M30", "H1", "H4"]
COST_ACCOUNTS = ["CFD-001", "CFD-006"]
COST_MODE = "worst"
MAX_CAMPAIGNS = 20


def _hash(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    status = {(r["symbol"], r["timeframe"]): r["status"] for r in data["records"]}
    rows = []
    for row in data["matrix"]:
        symbol = row["symbol"]
        tf = row["timeframe"]
        template = row["template"]
        if template not in TEMPLATES or symbol in BLOCKED:
            continue
        if symbol not in INSTRUMENTS.get(template, set()):
            continue
        if status.get((symbol, tf)) == "fail" or not row["viable"]:
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r["cost_r"], r["template"], r["symbol"], r["timeframe"]))
    # Cobertura minima antes del corte: 1 por plantilla viable y 1 por TF.
    selected = []

    def add(row):
        if row not in selected:
            selected.append(row)

    for template in TEMPLATES:
        candidates = [r for r in rows if r["template"] == template]
        if candidates:
            add(candidates[0])
    for tf in TIMEFRAMES:
        candidates = [r for r in rows if r["timeframe"] == tf]
        if candidates:
            add(candidates[0])
    for row in rows:
        if len(selected) >= MAX_CAMPAIGNS:
            break
        add(row)
    selected = selected[:MAX_CAMPAIGNS]
    selected.sort(key=lambda r: (r["cost_r"], r["template"], r["symbol"], r["timeframe"]))

    campaigns = []
    for index, row in enumerate(selected, start=1):
        tf = row["timeframe"]
        if tf in {"M15", "M30"}:
            is_start = "2015-01-02"
            is_end = "2019-12-31"
            oos1 = ["2020-01-01", "2022-12-31"]
        else:
            is_start = "2019-01-02"
            is_end = "2020-12-31"
            oos1 = ["2021-01-01", "2022-12-31"]
        campaigns.append(
            {
                "index": index,
                "campaign_id": f"edge2-{index:02d}-{row['template'].replace('_', '-')[:18]}-{row['symbol'].lower()}-{tf.lower()}",
                "template": row["template"],
                "instrument": row["symbol"],
                "timeframe": tf,
                "profile": "small",
                "mode": "ga",
                "seed": index,
                "is_start": is_start,
                "is_end": is_end,
                "oos1_start": oos1[0],
                "oos1_end": oos1[1],
                "oos2_start": "2023-01-01",
                "oos2_end": None,
                "cost_accounts": ["CFD-006"] if row["symbol"] == "US500" else COST_ACCOUNTS,
                "cost_mode": "worst",
                "data_source": "dukascopy",
                "cost_r": round(float(row["cost_r"]), 6),
                "worst_account": row["account"],
                "n_total_expected": 440,
            }
        )
    payload = {
        "kind": "edge2-plan",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "templates": TEMPLATES,
        "excluded": {
            "intraday_momentum_close_v2": "Y1.1: flat_at 15:55 nunca cae en vela M15/M30/H1; no se toca fastbt.py",
            "ny_open_vol_filter": "sesion de apertura NY: solo forward",
            "session_breakout_htf": "sesion de apertura NY: solo forward",
        },
        "segments": {
            "M15/M30": "2015-01-02:2019-12-31 (usable_from; Y1 decia 2014)",
            "H1/H4": "2019-01-02:2020-12-31 (2018 tiene huecos nocturnos reales)",
            "oos1": "2020-01-01:2022-12-31 (M15/M30) / 2021-01-01:2022-12-31 (H1/H4)",
            "oos2": "2023-01-01:",
        },
        "cost": {"accounts": COST_ACCOUNTS, "mode": COST_MODE},
        "blocked": BLOCKED,
        "pass2_rule": {
            "profile": "medium",
            "max_campaigns": 4,
            "condition": "campanas con al menos 1 finalista que paso Y3 completo",
            "order": "mas finalistas; a igualdad, menor cost_r",
            "seed": "1000 + indice",
        },
        "campaigns": campaigns,
        "n_total_sum": sum(c["n_total_expected"] for c in campaigns),
    }
    payload["plan_hash"] = _hash(
        {k: payload[k] for k in ("segments", "cost", "campaigns", "pass2_rule", "excluded")}
    )
    PLAN_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter

    by_tf = Counter(c["timeframe"] for c in campaigns)
    by_template = Counter(c["template"] for c in campaigns)
    by_symbol = Counter(c["instrument"] for c in campaigns)
    lines = [
        "# EDGE-2 Y1 - plan de campanas congelado",
        "",
        f"**Congelado:** {payload['frozen_at']}",
        f"**Hash:** `{payload['plan_hash']}`",
        f"**Campanas:** {len(campaigns)} · **n_total:** {payload['n_total_sum']:,}",
        "",
        "## Reglas congeladas",
        "",
        "- Fuente `dukascopy`; perfil `small`; modo `ga`; semilla = indice.",
        "- Coste `CFD-001` + `CFD-006`, `--cost-mode worst`; US500 solo `CFD-006` porque CFD-001 no lo permite.",
        "- M15/M30: IS 2015-01-02:2019-12-31 (Y1 decia 2014; `usable_from` manda).",
        "- H1/H4: IS 2019-01-02:2020-12-31 (2018 tiene huecos nocturnos reales; no es error del control).",
        "- OOS-1: 2020-01-01:2022-12-31 (M15/M30) / 2021-01-01:2022-12-31 (H1/H4). OOS-2: 2023-01-01:.",
        "- `intraday_momentum_close_v2` excluida por Y1.1; no se toca `fastbt.py`.",
        "- US30 fuera: spread Sin datos. US100 con swap 6,24 bps/noche pasa la cota enmendada 0,8-7,3.",
        "- Maximo 20 campanas; cobertura 1 por plantilla y 1 por TF, resto por menor `cost_r`.",
        "",
        "## Matriz",
        "",
        "| # | Campana | Plantilla | Activo | TF | Semilla | IS | OOS-1 | cost_r |",
        "|---:|---|---|---|---|---:|---|---|---:|",
    ]
    for c in campaigns:
        lines.append(
            f"| {c['index']} | `{c['campaign_id']}` | {c['template']} | {c['instrument']} | "
            f"{c['timeframe']} | {c['seed']} | {c['is_start']}:{c['is_end']} | "
            f"{c['oos1_start']}:{c['oos1_end']} | {c['cost_r']:.4f} |"
        )
    lines += [
        "",
        f"**Suma n_total:** {payload['n_total_sum']:,} ({len(campaigns)} x 440).",
        "",
        f"- Por TF: {dict(sorted(by_tf.items()))}",
        f"- Por activo: {dict(sorted(by_symbol.items()))}",
        f"- Por plantilla: {dict(sorted(by_template.items()))}",
        "",
        "## Pasada 2",
        "",
        "Maximo 4 campanas con al menos 1 finalista que pase Y3 completo; perfil `medium`, semilla `1000 + indice`.",
        "",
    ]
    PLAN_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Plan: {len(campaigns)} campanas, n_total {payload['n_total_sum']:,}, hash {payload['plan_hash'][:16]}")
    print(f"Por TF: {dict(sorted(by_tf.items()))} · activo: {dict(sorted(by_symbol.items()))} · plantilla: {dict(sorted(by_template.items()))}")


if __name__ == "__main__":
    main()
