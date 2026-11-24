import sys, numpy as np, pandas as pd
sys.path.insert(0, "src")  # ejecutar desde la raíz del repo: python -I .orquestador/tl2-audit/evidencia/prueba_spread_fastbt.py
from tradinglab.discovery import fastbt as fb
n=40
idx=pd.date_range("2025-01-06 10:00", periods=n, freq="h", tz="UTC")
P=10000.0
bars=pd.DataFrame({"open":P,"high":P,"low":P,"close":P,"volume":1.0},index=idx)
le=np.zeros(n,bool); se=np.zeros(n,bool)
le[5]=True; se[20]=True
cost=fb.CfdBpsCosts(commission_bps=0.0, slippage_bps=0.0, spread_bps=2.0)
# stop pct 1% => risk = 100 price; time exit 3 bars
ex=fb.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=3)
lim=fb.RunLimits(weekdays=(0,1,2,3,4,5,6))
res=fb.run(fb.Signals(le,se), bars, ex, cost, lim)
for t in res.trades:
    print(t.side, t.reason, "ent_bps",t.entry_cost_bps,"ex_bps",t.exit_cost_bps,"r_cost",round(t.r_cost,6), "=> bps", round(t.r_cost*t.risk_price/t.entry_price*1e4,3))
print("Modelo bid/ask independiente: barras BID planas, spread 2 bps.")
print(" largo: compra al ASK (bid+2bps), vende al BID -> coste 2 bps")
print(" corto: vende al BID, recompra al ASK -> coste 2 bps")
# target exit
ex2=fb.ExitSpec(stop="pct", stop_mult=1.0, target="pct", target_pct=0.5)
bars2=bars.copy(); bars2.iloc[8,bars2.columns.get_loc("high")]=P*1.01
le2=np.zeros(n,bool); le2[5]=True
r2=fb.run(fb.Signals(le2,np.zeros(n,bool)), bars2, ex2, cost, lim)
for t in r2.trades: print("objetivo:",t.side,t.reason,"ent",t.entry_cost_bps,"ex",t.exit_cost_bps)
# short stop: ask toca el stop pero el bid no
bars3=bars.copy(); 
stop_price=P*1.01
bars3.iloc[8,bars3.columns.get_loc("high")]=stop_price*(1-1.0/1e4)  # bid high 1bp bajo el stop; ask = +2bps -> por encima
se3=np.zeros(n,bool); se3[5]=True
r3=fb.run(fb.Signals(np.zeros(n,bool),se3), bars3, fb.ExitSpec(stop="pct", stop_mult=1.0, target=None, time_exit_bars=10), cost, lim)
for t in r3.trades: print("corto, ask sobre el stop en barra 8:", t.reason, "salida barra", t.exit_index)
