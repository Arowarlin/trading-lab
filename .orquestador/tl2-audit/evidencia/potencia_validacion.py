# Simulación de potencia de la cadena OOS-1 + OOS-2 actual (no usa datos reales).
# Supuesto: R por operación ~ Normal(ventaja, 1). Se ignoran IS, deriva, PBO, WF y régimen
# (que solo pueden bajar más la probabilidad de aprobar).
import numpy as np
rng=np.random.default_rng(1)
def sim(mu,f,sims=20000):
    # R por operación: mezcla tipo stop/objetivo con media mu y sd ~1.1
    n1=rng.poisson(f*1.0,sims); n2=rng.poisson(f*17/12,sims)
    p1=p2=p12=0
    for a,b in zip(n1,n2):
        r1=rng.normal(mu,1.0,a) if a>0 else np.array([])
        ok1 = a>0 and r1.mean()>0 and (r1[r1>0].sum()/max(1e-9,-r1[r1<0].sum()))>1.1
        r2=rng.normal(mu,1.0,b) if b>0 else np.array([])
        if b>=30:
            z=r2.mean()/r2.std(ddof=1)*np.sqrt(b)
            ok2 = r2.mean()>0 and z>=1.645   # random>=95 (más exigente que PSR>=0.9)
        else: ok2=False
        p1+=ok1; p2+=ok2; p12+=ok1 and ok2
    return p1/sims,p2/sims,p12/sims
print("ops/año  ventaja(R)  P(OOS-1)  P(OOS-2)  P(ambas)")
for f in (12,50,250,1000):
  for mu in (0.05,0.10,0.20):
    a,b,c=sim(mu,f,4000)
    print(f"{f:7d}  {mu:9.2f}  {a:8.2f}  {b:8.2f}  {c:8.2f}")
print("nulo (sin ventaja):")
for f in (12,50,250,1000):
    a,b,c=sim(0.0,f,4000); print(f"{f:7d}  {0:9.2f}  {a:8.2f}  {b:8.2f}  {c:8.3f}")
