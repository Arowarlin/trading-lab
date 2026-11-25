"""E3 · Siembra de avisos con fichero fuente (idempotente)."""

from __future__ import annotations

import sys

from tradinglab.tl3 import warnings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FECHA = "2026-11-25"

ROWS = [
    {
        "subject": "ea:us100-ftmo1",
        "etapa": "T7",
        "texto": "T7 no confirma; muestra efectiva 2013-2014 y 2018-2021",
        "cifras": {
            "operaciones": 374,
            "expectativa_r": -0.0296,
            "lcb95": -0.1753,
            "muestra_efectiva": ["2013-2014", "2018-2021"],
        },
        "source_path": "TL3_REPORTS/ea_oop_dukascopy.md",
    },
    {
        "subject": "ea:us100-ftmo1",
        "etapa": "T6/corto",
        "texto": "El corto pierde en 2023",
        "cifras": {"operaciones_corto": 28, "expectativa_r": -0.1368},
        "source_path": "TL3_REPORTS/TL3_US100_ADDENDUM.md",
    },
    {
        "subject": "ea:us100-ftmo1",
        "etapa": "forward",
        "texto": "Forward con 3 operaciones cerradas; n necesario para decidir",
        "cifras": {
            "cerradas": 3,
            "n_real_0": 237,
            "n_real_010": 515,
            "checkpoints": [30, 60, 515],
        },
        "source_path": "TL3_REPORTS/ea_forward_monitor_plan.md",
    },
    {
        "subject": "ea:us100-ftmo1",
        "etapa": "contaminacion",
        "texto": "Sus componentes coinciden con NASDAQ_EDGE A-E; ningún tramo histórico es limpio",
        "cifras": {"familias": ["A", "B", "C", "D", "E"], "tramos_historicos_limpios": 0},
        "source_path": ".orquestador/COLA-NQEDGE-FORWARD.md",
    },
    {
        "subject": "ai_trader",
        "etapa": "T5",
        "texto": "T5 no concluyente",
        "cifras": {
            "n": 48,
            "delta_vs_tendencia_r": -0.0225,
            "ic95": [-0.1833, 0.1206],
        },
        "source_path": "TL3_REPORTS/ai_trader_contrafactual.md",
    },
    {
        "subject": "ai_trader",
        "etapa": "T5-bis",
        "texto": "La simulación da más que la ejecución real; el gap está en la salida; los stops móviles no se simulan",
        "cifras": {
            "gap_r": -0.2475,
            "entrada_r": 0.0661,
            "costes_r": -0.0089,
            "salida_resto_r": -0.3047,
        },
        "source_path": "TL3_REPORTS/ai_trader_sim_vs_real.md",
    },
    {
        "subject": "ai_trader",
        "etapa": "TCA",
        "texto": "La TCA registra slippage 0 y los costes de ai_trader lo leen",
        "cifras": {
            "filas": 68,
            "slippage_cero": 66,
            "fill_nulo": 2,
            "latencia_nula": 68,
            "decision_fill_mediana_bps": 0.44,
        },
        "source_path": "TL3_REPORTS/tca_diagnostico.md",
    },
    {
        "subject": "ai_trader",
        "etapa": "potencia",
        "texto": "Próxima evaluación única a n=180",
        "cifras": {
            "n": 180,
            "n_delta_t": 177,
            "fecha_estimada": "2027-01-04",
            "hipotesis": "H-2026-012",
        },
        "source_path": "TL3_REPORTS/ai_trader_power_plan.md",
    },
    {
        "subject": "cuenta:CFD-006",
        "etapa": "produccion",
        "texto": "E-3 pendiente: la protección diaria solo usa la equidad",
        "cifras": {"estado": "pendiente", "base_diaria": "equity"},
        "source_path": "docs/CHANGELOG-produccion.md",
    },
    {
        "subject": "prop.simulator",
        "etapa": "produccion",
        "texto": "Modelo diario: balance = equidad al inicio del día; optimista para estrategias que duermen posiciones",
        "cifras": {"day_start_balance": "day_start", "posiciones_abiertas_entre_dias": 0},
        "source_path": "docs/CHANGELOG-produccion.md",
    },
    {
        "subject": "prop.simulator",
        "etapa": "FundingPips",
        "texto": "Cifras de FundingPips anteriores a 020b41b: rotura diaria sobrestimada",
        "cifras": {
            "p_diario_antes_pct": [18.36, 67.68],
            "p_diario_despues_pct": 0,
            "p_financiada_b2_r05_antes_pct": 15.86,
            "p_financiada_b2_r05_despues_pct": 22.46,
            "commit_correccion": "020b41b",
        },
        "source_path": "TL3_REPORTS/tl2_diario_inventario.md",
    },
    {
        "subject": "nqedge",
        "etapa": "forward",
        "texto": "Los OOS históricos están contaminados por el EA. La fase C histórica se ejecutó y el operador la registró; el forward NQF es independiente y está prerregistrado",
        "cifras": {
            "fase_c_ejecutada": True,
            "ventana_local": "16:43-16:51",
            "informal_trials_fila_7_n": 22,
            "informal_trials_fila_6_n": 7,
            "forward": "NQF-A/B/C",
            "inicio": "2026-11-30",
            "n_objetivo": 200,
            "comision_lado_usd": 0.75,
        },
        "source_path": ".orquestador/COLA-NQEDGE-FORWARD.md; informal_trials",
    },
]


def main() -> None:
    added = 0
    for row in ROWS:
        result = warnings.add_warning(
            row["subject"],
            FECHA,
            row["etapa"],
            row["texto"],
            row["cifras"],
            row["source_path"],
        )
        if result is not None:
            added += 1
    total = len(warnings.all_warnings())
    print(f"{added} avisos nuevos; {len(ROWS)} en la siembra; {total} en total")


if __name__ == "__main__":
    main()
