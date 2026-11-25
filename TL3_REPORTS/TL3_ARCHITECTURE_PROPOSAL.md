# TL3 · Propuesta de arquitectura de investigación

**Idea central:** no hace falta otro motor. TradingLab ya tiene casi todas las piezas (guard,
snapshots con hash, contador, arnés T01, protocolo v2, SPRT). Falta **un registro de hipótesis** por
encima de las campañas y **tres candados** que hoy son opcionales. Se construye en un espacio aparte
(`src/tradinglab/tl3/`, `data/tl3_research.db`, `TL3_REPORTS/`) y **no modifica** Discovery, el EA,
`ai_trader`, Prop Fund ni `ea_lab`. Todo es **[REC]**.

## 1. Qué se conserva, qué se congela y qué se aparta

| Componente | Decisión | Motivo |
|---|---|---|
| `discovery/` guard, snapshots, campaigns, levels, protocol_v2, power, harness, sprt | **Conservar** y reutilizar desde TL3 por API, sin cambios | Funcionan (`TL3_FORENSIC_AUDIT.md §3`) |
| `fastbt` + `CostBook` v2 | Conservar; TL3 **siempre** llama con `cost_model_version=2` explícito | El default sigue siendo 1 |
| GA / NSGA-II, `optimizer.py`, `perturb.py`, `export_mql5.py` | **Congelar** (no usar en TL3) | Fabrican sobreajuste o no tienen consumidor |
| Carriles `research`, `swing`, `campaign.py` A/B, Optuna en acciones | **Congelar**; fuera del contador de TL3 | Universo distinto |
| EA, `ai_trader`, Prop Fund, `ea_lab`, forward | **Protegidos**, solo lectura | Orden del operador |

## 2. Componentes nuevos (mínimos)

```text
src/tradinglab/tl3/
  registry.py     Registro de hipótesis (append-only) y experimentos
  gates.py        Candados previos al registro (coste/bruto, MDE ≤ δ, holdout libre)
  thresholds.yaml Umbrales estadísticos con hash; fuera del alcance de escritura de agentes
  data_manifest.py Manifiesto de datos: fuente, instrumento real, granularidad, hash
  report.py       Informe estándar: bruto → spread → comisión → slippage → swap → neto
data/tl3_research.db   (nueva; no toca discovery.db ni lab.db)
TL3_REPORTS/          Informes y evidencia
```

### 2.1 Registro de hipótesis (`hypotheses`, solo inserciones)

| Campo | Uso |
|---|---|
| `hypothesis_id` (H-AAAA-NNN) | Identificador único y permanente |
| `parent_id` | Si deriva de otra; **obligatorio** si comparte mecanismo |
| `economic_rationale`, `behavior`, `references` | Fundamento económico escrito antes de mirar |
| `market`, `instrument_class` (`cfd`/`future`), `timeframe` | Separación CFD ↔ futuro por esquema, no por convención |
| `entry`, `exit`, `primary_params`, `plateau_grid` | Regla primaria fija y rejilla de meseta |
| `benchmark` | Placebo, lado aleatorio o regla trivial |
| `primary_metric`, `delta`, `sigma`, `mde`, `rejection_rule` | Criterio prerregistrado |
| `dev_window`, `holdout_window`, `holdout_kind` (`out_of_period`/`out_of_instrument`/`none_param_free`) | Muestras |
| `structural_hash` | Hash de (mecanismo, mercado, TF, reglas normalizadas): detecta reapariciones |
| `status` | `draft` → `approved` → `run` → `rejected`/`candidate`/`validated`, más `burned_holdout` |
| `rejection_reason` | Causa estructurada (`no_power`, `gross_lt_cost`, `holdout_fail`, `instability`…) |

### 2.2 Experimentos (`experiments`)
`experiment_id` (UUID) · `hypothesis_id` · `git_commit` · `config_hash` · `data_manifest_hash` ·
`thresholds_hash` · `cost_model_version` · `seed` · `n_variants` · `started/finished` · métricas ·
ruta del informe. **Reproducir = volver a ejecutar con los mismos cinco hashes y comparar a 1e-9.**

### 2.3 Libro de muestras (`sample_usage`)
Cada lectura de rendimiento registra `(instrumento, TF, ventana, hypothesis_id, kind=dev|holdout)`.
`gates.py` rechaza una hipótesis cuyo holdout se solape con una ventana ya usada como **dev o holdout**
por cualquier hipótesis del mismo mecanismo. Es la versión automática de la contaminación que se
declaró a mano en la campaña 2026-11-B.

## 3. Los tres candados (lo que hoy es opcional)

| Candado | Dónde actúa | Regla |
|---|---|---|
| **Potencia** | Registro | Sin `delta` y `sigma`, no se registra. MDE_holdout (con n de días distintos) > δ → rechazo `no_power` |
| **Coste** | Registro | El bruto esperado (literatura o estudio de evento **sin PnL de la estrategia**) debe ser ≥ 2 × coste estimado; si no, `gross_lt_cost` |
| **Identidad** | Registro | Si el `structural_hash` coincide con una hipótesis rechazada, se bloquea salvo `parent_id` + motivo + **holdout nuevo** |

## 4. Separación de responsabilidades con la IA

| Puede la IA | No puede la IA |
|---|---|
| Proponer hipótesis (borrador) con fundamento y referencias | Aprobar specs o campañas |
| Calcular potencia y coste esperado | Escribir en `thresholds.yaml` (hash verificado en cada ejecución; cambio solo con commit del operador) |
| Redactar informes a partir de resultados | Abrir un holdout, cambiar ventanas o criterios después de ver resultados |
| Buscar relaciones en resultados **ya cerrados** | Lanzar experimentos que sumen pruebas sin aprobación |

Implementación: los umbrales se leen de `thresholds.yaml` y su hash se guarda en cada experimento. Un
experimento con un hash distinto al aprobado en la hipótesis se marca `invalid`.

## 5. Datos (`data_manifest.py`)

- Una fila por archivo: `path`, `source` (mt5/dukascopy/databento), **`instrument_real`**
  (`US100.cash`, `USATECHIDXUSD`, `NQ.c.0`…), `instrument_class`, `granularity` comprobada (paso
  dominante por año), `usable_from`, `has_ask`, `hash`.
- El cargador de TL3 **rechaza** un archivo cuya granularidad dominante no coincida con la pedida en
  la ventana solicitada (evita el fallo de NQ-B) o cuyo `instrument_class` no coincida con la
  hipótesis (evita usar NQ como US100).
- No se modifica ninguna caché existente: el manifiesto las describe; las copias corregidas van a
  `data/tl3/`.

## 6. Informe estándar de cada experimento

1. Hipótesis y criterio prerregistrados (copia literal).
2. Datos: manifiesto y cobertura.
3. Bruto → −spread → −comisión → −slippage → −swap → **neto**, con n, media, IC95 y MDE.
4. Benchmark y diferencia frente a él.
5. Estabilidad: meseta, por año y por régimen de volatilidad prerregistrado.
6. Veredicto según la regla, sin reinterpretar.
7. Pruebas contadas y uso de muestras.

## 7. Coste de construirlo

[INFERENCIA] ~600–900 líneas nuevas más tests, reutilizando Discovery por API. Sin dependencias nuevas.
No se justifica ningún framework adicional (vectorbt, Nautilus, Optuna, RL, más LLMs): la restricción
actual es metodológica y de datos, no de cómputo.
