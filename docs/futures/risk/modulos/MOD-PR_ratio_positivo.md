# MOD-PR · Módulo de estructuras de RATIO POSITIVO (objetivo ≥ stop)

**Fecha:** 2026-11-28 · **Autor:** Claude Code · Pareja de `MOD-NR_ratio_negativo.md`; mismo simulador,
misma ventaja neta en USD, mismas reglas (Topstep 50K verificadas el 2026-11-27).
**Estado:** módulo de investigación; implementación en el motor = FUT-M2 (OpenCode, tras FUT-A6).

## 1. Definición

`RR = W/L ≥ 1`: se gana menos veces, pero cada ganancia vale al menos lo que cada pérdida. Rejilla
simulada: RR en {1; 1,5; 2; 3} y riesgo en {250; 500; 1.000; 1.500} USD por operación.

## 2. Matemática

- **Acierto de equilibrio:** `p* = L/(W + L)`; con RR 1,5 y 500 USD de riesgo, `p* = 0,42`.
- **La ventaja está en el pago**, no en el acierto (tendencia, rupturas con continuación).
- **Validación:** la desviación por operación es mayor (≈ 1,24 R con RR 1,5). Para que la cota inferior
  de +0,08 R supere 0 hacen falta ≈ 654 operaciones (`01 §2.2`).
- **Rachas:** con p ≈ 0,45, una racha de 8 pérdidas tiene ≈ 0,8 % de probabilidad en 8 operaciones
  dadas, pero en un año de unas 250 operaciones es casi segura. El tamaño tiene que aguantarla dentro
  del MLL: `8 × riesgo ≤ MLL` → **riesgo ≤ 250 USD si se quiere sobrevivir a 8 pérdidas seguidas en 50K**.

## 3. Interacción con las reglas

| Regla | Efecto en ratio positivo |
|---|---|
| Día ganador mínimo | fácil de alcanzar: con 250 USD de riesgo y RR 1,5 un día ganador vale ≈ 350 USD |
| Consistencia (Topstep 55 % en Combine; Lucid Flex 40 % en evaluación; MFF/TradeDay según plan) | ganancias grandes en un día suben el objetivo: con riesgo ≥ 1.100 USD y RR 1,5, un día > 1.650 USD activa la regla en Topstep |
| Tope por retiro | ganar mucho en una cuenta no sirve: el excedente sobre el tope queda en la cuenta y expuesto al MLL |
| Microscalping | rara vez aplica: objetivos amplios duran minutos |

## 4. Resultados (Topstep 50K, 4.000 caminos, presupuesto 1.500 USD; ventajas **hipotéticas**)

**Con ventaja neta de +40 USD por operación:**

| Riesgo | RR | EV 12 m | Mediana 12 m | P(neto > 0) | Ruina 24 m | Cuentas 24 m |
|---:|---:|---:|---:|---:|---:|---:|
| 250 | 1,5 | 1.304 | 530 | 0,62 | **1,0 %** | 9,7 |
| 250 | 3,0 | 2.611 | 1.499 | 0,72 | 3,5 % | 15,2 |
| **500** | **1,5** | **3.058** | **1.962** | **0,76** | 9,1 % | 29,9 |
| 500 | 2,0 | 3.850 | 2.589 | 0,75 | 15,6 % | 33,3 |
| 500 | 3,0 | 4.245 | 2.680 | 0,68 | 28,6 % | 32,1 |
| 1.000 | 1,5 | 4.876 | 1.748 | 0,58 | 43,6 % | 49,2 |
| 1.000 | 3,0 | 1.751 | −1.476 | 0,32 | 70,1 % | 34,7 |

**Con ventaja neta 0:** el mejor de este módulo es riesgo 500 y RR 2 (EV de 1.533 y mediana de 444 a
12 m, ruina del 33,5 % a 24 m). Con RR alto y riesgo alto la mediana es la pérdida de todo el
presupuesto (−1.476).

## 5. Cuándo tiene ventaja este módulo

1. **Riesgo bajo o moderado (≤ 25 % del MLL):** domina a todos los ratios negativos (que con riesgo
   bajo ni siquiera cobran).
2. **Tolerancia de ruina baja:** 250-500 USD con RR 1,5-3 dan ruina ≤ 10 % con mediana positiva.
3. **Estrategias cuya ventaja está en el pago:** rupturas de la apertura de NY, continuación de
   tendencia (Research B).

**Pierde frente al ratio negativo:** con riesgo ≥ 50 % del MLL, RR alto produce muchas cuentas rotas y
la mediana se hunde.

## 6. Frontera combinada (ambos módulos, +40 USD netos, 12 meses)

| Tolerancia de ruina del presupuesto (24 m) | Mejor estructura | EV 12 m | Mediana 12 m |
|---|---|---:|---:|
| ≤ 1 % | NR-colchón (día mínimo) | 1.813 | 1.471 |
| ≤ 5 % | PR · 250 USD · RR 3 | 2.611 | 1.499 |
| ≤ 10 % | **PR · 500 USD · RR 1,5** | **3.058** | **1.962** |
| ≤ 20 % | PR · 500 USD · RR 2 | 3.850 | 2.589 |
| ≤ 30 % | **NR · 1.500 USD · RR 0,75** | **5.010** | **3.874** |

**Conclusión:**
- **Ningún ratio es mejor en abstracto.** La tolerancia de ruina del operador elige la fila; la ventaja
  validada de cada estructura elige si se opera.
- Con la filosofía "agresivo cuando los datos lo justifiquen", el extremo de la frontera es un ratio
  negativo con riesgo grande. Exige una ventaja validada en esa estructura, el escalado real del XFA y
  aceptar perder el presupuesto en ~28 de cada 100 proyectos.

## 7. Criterios de aceptación del módulo

| ID | Criterio |
|---|---|
| PR-A1 | Ventaja en R con n ≥ 654 y cota inferior al 95 % > 0 (o la de su escalón de la escalera) |
| PR-A2 | Racha máxima de pérdidas del pool (P95, stationary bootstrap) × riesgo < 80 % del MLL |
| PR-A3 | EV y mediana a 12 m > 0 en el motor FUT-A con la cota inferior, ruina ≤ tolerancia |
| PR-A4 | Ningún día ganador típico activa la consistencia de la firma (mejor día < c·objetivo) |

## 8. Tareas para OpenCode (DeepSeek V4.1 Flash), tras FUT-A6

| ID | Tarea | Aceptación |
|---|---|---|
| FUT-M1 | Política `NegativeRatioPolicy` (objetivo ≥ día mínimo + margen; stop ≤ colchón − margen; bloqueo por microscalping) | Reproduce `MOD-NR §4` (±2 SE) con el pool sintético |
| FUT-M2 | Política `PositiveRatioPolicy` (riesgo fijo/escalera; control de consistencia) | Reproduce `MOD-PR §4` (±2 SE) |
| FUT-M3 | Frontera EV–ruina–mediana combinada y selección por tolerancia | Reproduce la tabla de §6 |
