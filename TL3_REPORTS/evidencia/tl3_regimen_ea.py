"""TL3 · análisis explicativo del EA us100-ftmo1 (solo lectura).

Lee los R diarios ya publicados (`reports/ea/us100-ftmo1_daily_r.parquet`) y
la caché M5 del EA. No ejecuta el motor, no cambia parámetros y no suma
pruebas. Uso:

    .\.venv\Scripts\python.exe -X utf8 -I TL3_REPORTS\evidencia\tl3_regimen_ea.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    r = pd.read_parquet(ROOT / "reports/ea/us100-ftmo1_daily_r.parquet")
    r["date"] = pd.to_datetime(r["date"])
    r = r.set_index("date")["r"]
    px = pd.read_parquet(ROOT / "data/cache/ea/US100_CASH_M5_NY.parquet")
    gaps = pd.Series(px.index[1:] - px.index[:-1], index=px.index[1:])
    print("Paso dominante por año:")
    for year, g in gaps.groupby(gaps.index.year):
        print(year, g.value_counts().index[0])
    px = px[px.index >= "2021-09-14"]
    rth = px.between_time("09:30", "15:55")
    d = rth.resample("D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    d["rng"] = (d.high - d.low) / d.open * 100
    m = pd.DataFrame({"R": r.resample("ME").sum(), "n": r.resample("ME").count()})
    dm = d.resample("ME").agg({"rng": "mean"})
    dm["trend"] = d.close.resample("ME").last().pct_change() * 100
    x = m.join(dm, how="inner").dropna()
    print("meses", len(x), "corr(R, rango)", round(x.R.corr(x.rng), 3),
          "corr(R, tendencia)", round(x.R.corr(x.trend), 3),
          "corr(R, |tendencia|)", round(x.R.corr(x.trend.abs()), 3))
    x["vol"] = pd.qcut(x.rng, 3, labels=["baja", "media", "alta"])
    print(x.groupby("vol", observed=True).agg(R=("R", "sum"), meses=("R", "size"),
                                              R_mes=("R", "mean")).round(2))
    y = x.groupby(x.index.year).agg(
        R=("R", "sum"), rango=("rng", "mean"),
        tendencia_abs=("trend", lambda s: s.abs().mean()),
        meses_pos=("R", lambda s: (s > 0).mean()),
    )
    print(y.round(2))
    print(r.groupby(r.index.day_of_week).agg(["count", "mean", "sum"]).round(3))
    top = r.sort_values(ascending=False)
    print("cuota del R total en los 20 mejores días:", round(top.head(20).sum() / r.sum(), 3))
    eq = r.cumsum()
    dd = eq - eq.cummax()
    print("DD máx R", round(dd.min(), 2), "fecha", dd.idxmin().date())


if __name__ == "__main__":
    main()
