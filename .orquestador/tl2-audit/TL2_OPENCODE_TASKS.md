# TL2 · Tareas para OpenCode (DeepSeek V4.1 Flash)

Cada tarea es un bloque independiente: rama propia, tests y commit con tag. **No se ejecuta ninguna tarea sin que Claude escriba su cola** (`.orquestador/COLA-*.md`) con estas especificaciones.

## Reglas comunes (valen para todas)

1. **Solo demo/paper.** Nunca órdenes reales, nunca activar EA, bots ni estrategias.
2. **Sin campañas ni lecturas de OOS** sin la aprobación del operador en la sesión. Los tests usan datos sintéticos.
3. **Nada histórico se reescribe.** Las campañas, evaluaciones y contadores existentes no se modifican. Los cambios de modelo llevan una versión nueva (`cost_model_version`, `protocol_version`) y las campañas antiguas conservan la suya.
4. **Cada cambio en un componente en producción** (EA, forward FTMO, riesgo FTMO, ai_trader, Prop Fund, ea_lab) lleva:
   - (a) un baseline antes del cambio (salida de referencia guardada en `tests/fixtures/baselines/`);
   - (b) un test de regresión que compara antes y después;
   - (c) una entrada en `docs/CHANGELOG-produccion.md`;
   - (d) un tag `tl2-<id>-pre` antes del primer commit, para el rollback.
5. **No bajar umbrales** salvo con la evidencia del arnés T01 (ver T22).
6. **No añadir dependencias** sin justificarlo en el RESULTADO. Solo se pre-aprueba `arch` (para T23).
7. Al terminar: `ruff check`, `pytest -q` una vez, `lab propfund verify`, `count_tests` sin cambios (salvo que la tarea diga lo contrario) y `RESULTADO-<id>.md` con la plantilla de siempre. **Sin push.**

Formato de cada tarea: **Problema · Evidencia · Resultado esperado · Archivos que se tocan · Archivos que no · Diseño · Fórmula · Contratos · Tests unitarios · Tests de integración · Aceptación · Riesgos · Dependencias · Rollback · Documentación.**

---

## FASE 0 · Preparación

### T00 · Protección → control de cambios
- **Problema:** el operador retiró la protección (2026-11-24). El manifiesto y las colas bloqueaban cambios en EA, IA, forward y riesgo.
- **Evidencia:** `propfund/protected.py`, `config/propfund/protected_manifest.json`, `propfund/registry.py:120-140`, `router.py:154`.
- **Resultado esperado:** `lab propfund verify` informa de los archivos cambiados respecto al baseline y **no falla** por ello. Existe `lab propfund baseline --reason "..."` que reescribe el manifiesto y añade una entrada a `authorizations` con fecha y motivo.
- **Se tocan:** `propfund/protected.py`, `propfund/cli.py`, `propfund/registry.py`, `propfund/models.py`, `AGENTS.md`, `docs/CHANGELOG-produccion.md` (nuevo), tests de propfund.
- **No se tocan:** la lógica de trading del EA, de ai_trader y del forward. El router sigue rechazando enviar órdenes a estrategias de motor externo.
- **Diseño:**
  - Renombrar el concepto `protected` a `external_engine` donde signifique "la ejecuta su propio motor" (router, registry), manteniendo el campo YAML antiguo como alias de lectura.
  - El manifiesto pasa a llamarse "baseline".
  - En `AGENTS.md`, sustituir las prohibiciones de archivos protegidos por la regla común 4.
- **Contratos:** `verify() → {"changed": [...], "unchanged": [...], "ok": True}`. `ok` solo es `False` si falta el manifiesto.
- **Tests:** verify con un archivo cambiado devuelve `ok=True` y lo lista; `baseline` añade la autorización; el router sigue rechazando `external_engine`.
- **Aceptación:** suite en verde; `lab propfund verify` muestra 4 grupos con estado "sin cambios"; el diff no toca la lógica de trading.
- **Riesgos:** perder la trazabilidad. Se mitiga porque el registro de cambios es obligatorio.
- **Dependencias:** ninguna. **Rollback:** tag `tl2-t00-pre`.
- **Documentación:** `AGENTS.md`, `docs/propfund/02_arquitectura.md` y el CHANGELOG.

### T01 · Arnés de autoevaluación del pipeline
- **Problema:** no se conoce la tasa de falsos positivos ni la de falsos negativos del pipeline (P0-3).
- **Evidencia:** no existe ningún test que inyecte una ventaja conocida y compruebe si se recupera.
- **Resultado esperado:** `lab discovery harness --protocol current|v2 --freq 12,50,250,1000 --edge 0,0.05,0.1,0.2 --sims N --seed S` produce una tabla P(aprobar) con IC binomial. **No toca el contador ni la base de datos.**
- **Se tocan:** `discovery/harness.py` (nuevo), `cli.py` (un comando), `tests/test_discovery_harness.py`.
- **No se tocan:** el databank y el guard. El arnés usa una base temporal en memoria.
- **Diseño:** dos generadores:
  - (a) **sintético:** paseo aleatorio BID con spread conocido y señales de entrada que añaden `+δ·riesgo` al movimiento de la siguiente salida (ventaja exacta);
  - (b) **sobre snapshot real:** señales aleatorias (nulo) o señales "oráculo-ruido" que eligen la dirección correcta con probabilidad `p` calibrada a δ.
  
  Cada simulación recorre el protocolo completo (factibilidad, IS, deriva, OOS, confirmación) con una base temporal.
- **Fórmula:** IC de Wilson al 95 % para cada probabilidad.
- **Tests:** con δ = 0 y 1.000 simulaciones, P(aprobar) del protocolo actual < 0,05; con δ = 0,5 R y 1.000 operaciones por año, P(aprobar) > 0,9; reproducible con la misma semilla.
- **Aceptación:** tabla del protocolo actual en `reports/discovery/harness-current.md`, coherente en orden de magnitud con `evidencia/potencia_validacion.salida.txt`.
- **Riesgos:** tardar mucho. Usar `workers` y un número de simulaciones configurable.
- **Dependencias:** ninguna. **Rollback:** borrar el comando nuevo (aditivo).
- **Documentación:** `docs/tradinglab2/15_HARNESS.md`.

### T02 · Copia automática de `discovery.db`
- **Problema:** el registro de pruebas y el sello de OOS-2 no tienen respaldo automático.
- **Resultado esperado:** tras `register`, `approve`, `run`, `confirm` y `record-informal`, se crea `data/backups/discovery_<UTC>.db` con `sqlite3.backup`, y se conservan las 30 últimas copias más una por mes.
- **Se tocan:** `discovery/databank.py` o `campaigns.py` (un hook) y tests.
- **Aceptación:** test con una base temporal: la copia existe y `PRAGMA integrity_check` devuelve `ok`.
- **Rollback:** desactivar el hook con `discovery.backup: false` en `engine.yaml`.

---

## FASE 1 · Integridad de costes

### T10 · Modelo de ejecución BID/ASK único
- **Problema:** doble spread en salidas que no son por objetivo; stop de corto disparado con el BID (P0-1).
- **Evidencia:** `fastbt.py:222-235`, `:317-333`, `:381-404`, `:735-975` (`_core`), `:991-1190` (`_calendar_core`); `costs.py:399-407`; demostración en `evidencia/prueba_spread_fastbt.py`.
- **Resultado esperado:** coste de spread exactamente uno por operación; stop de corto disparado cuando el ASK toca el stop; desglose de coste por operación (`spread_r`, `slip_r`, `comm_r`, `swap_r`).
- **Se tocan:** `discovery/fastbt.py`, `discovery/costs.py`, `discovery/drift.py` (usa el mismo panel), tests de fastbt y de costes.
- **No se tocan:** `ea_us100_engine.py` (es la referencia).
- **Diseño:**
  - `CostPanel` pasa a llevar `spread_bps`, `slip_bps` y `comm_bps` por separado.
  - En `_core` y `_calendar_core`:
    - largo: entrada `comm + slip + spread`; salida `comm + slip`, o solo `comm` si es por objetivo;
    - corto: entrada `comm + slip`; salida `comm + slip + spread`, o `comm` + el spread ya incluido en el precio si es por objetivo;
    - el disparo del stop de un corto usa `high + spread`.
  - Añadir `cost_model_version = 2` en el config de las campañas nuevas.
  - Las funciones aceptan `cost_model_version` y la v1 se conserva para reproducir campañas antiguas.
- **Fórmula:** `§1.2` de `TL2_QUANT_AUDIT.md`.
- **Contratos:** `Trade` añade `spread_r`, `slip_r` y `comm_r` (opcionales; su suma más `swap_r` es igual a `r_cost`).
- **Tests unitarios** (resultados calculados a mano):
  1. precio plano, spread 2 bps → coste 2 bps en largo y en corto, con salida por stop, tiempo, señal y fin;
  2. objetivo de un largo → 1 spread;
  3. ASK sobre el stop de un corto con el BID por debajo → sale en esa barra;
  4. spread variable: se usa el de la barra de cada pata;
  5. la v1 reproduce exactamente los números actuales (paridad).
- **Test de integración:** paridad de convención con `ea_us100_engine` en una serie sintética común (mismo precio de llenado en las 4 rutas).
- **Aceptación:** todos los tests en verde. Informe antes/después de `cost_r` en las specs `q2-fix-*`, `q1-*` y `r9b-*` **usando solo feasibility** (sin rendimiento). El RESULTADO incluye la tabla de diferencias.
- **Riesgos:** romper la paridad con informes antiguos. Se mitiga con la v1 conservada.
- **Dependencias:** T01 (para medir el efecto sobre la tasa de error). **Rollback:** tag `tl2-t10-pre` y `cost_model_version: 1` por defecto.
- **Documentación:** `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md`.

### T11 · Spread histórico por barra
- **Problema:** el p75 medido en 2026 se aplica a 2010–2024 (P1-2, P1-3).
- **Resultado esperado:** para fuentes con `ask_close` (Dukascopy FX y metales), `spread_t = ask_t − bid_t`, escalado al bróker con la razón de medianas por hora local medida en los últimos 90 días comunes. Si no hay ASK: la mediana por hora del bróker. El p75 queda solo para el escenario de estrés.
- **Se tocan:** `discovery/costs.py`, `discovery/fastbt.py` (acepta un array de spread por barra), `data_sources.py` y tests.
- **Fórmula:** `s_t = s_t^D · m_h^bróker / m_h^D`.
- **Tests:** serie sintética con ASK conocido → spread por barra exacto; sin ASK → mediana horaria; el escalado preserva la mediana del bróker.
- **Aceptación:** informe de spread medio por año y símbolo (2010–2026) en `reports/discovery/spread-historico.md`.
- **Dependencias:** T10. **Rollback:** `spread_model: p75_static`.

### T12 · Slippage medido desde fills
- **Problema:** slippage supuesto de 0,5 pip por lado en FX (P1-1).
- **Resultado esperado:** `lab costs slippage-measure` calcula, desde `mt5_fills` y TCA, la mediana y el p75 de |fill − solicitado| por símbolo, cuenta, tipo (mercado, stop, límite) y franja horaria, con su n.
  - Con n ≥ 30, escribe `slippage_price` en `costs.yaml` con `source: measured` y la fecha.
  - Con n < 30, mantiene el supuesto y lo marca.
- **Se tocan:** `tca.py` o `slippage_probe.py`, `propfund/costs.py`, tests y `costs.yaml` (solo con el comando y la aprobación del operador).
- **Tests:** fills sintéticos con slippage conocido → mediana exacta; celda con n < 30 → se conserva el supuesto.
- **Aceptación:** tabla de medidas en el RESULTADO. **Sin datos** si no hay fills suficientes.
- **Dependencias:** T10. **Rollback:** restaurar `costs.yaml` desde git.

### T13 · Swap histórico
- **Problema:** el swap de 2026 se aplica a 2013 (P1-3).
- **Resultado esperado:** `SwapSpec` admite `mode: historical`: `swap_t = (tipo_ref_t + markup_lado) · nocional · días / 360`, con los tipos diarios desde FRED (ya integrado en `intel/fred.py`) y un markup calibrado para que el valor de hoy coincida con el medido en `swap.yaml`. El crédito sigue en 0 en Discovery.
- **Tests:** con el tipo histórico igual al de hoy se reproduce `swap.yaml`; el triple rollover se mantiene; con tipo 0 solo queda el markup.
- **Aceptación:** tabla de swap medio anual por símbolo y lado.
- **Dependencias:** T10. **Rollback:** `swap.mode: static`.

---

## FASE 2 · Protocolo estadístico v2 (solo campañas nuevas)

### T20 · Puerta de potencia en preflight
- **Problema:** se gastan pruebas en campañas que no pueden aprobar (P0-2).
- **Resultado esperado:** `preflight` añade operaciones esperadas en desarrollo y en holdout (solo conteos, permitido por el guard), el MDE (`§2.2`) y el veredicto `potencia_ok` si `MDE_holdout ≤ δ` (δ declarado en la spec, campo nuevo `plausible_edge_r`). Sin δ: aviso, no bloqueo.
- **Tests:** n = 400 y δ = 0,10 → MDE 0,1245 → sin potencia; n = 700 → con potencia.
- **Aceptación:** el preflight de las specs existentes muestra el MDE. La línea "potencia de la regla" se añade a los informes antiguos.
- **Dependencias:** T01. **Rollback:** campo opcional.

### T21 · Especificación primaria y rejilla de meseta
- **Problema:** se selecciona el mejor punto del frente (P1-4).
- **Resultado esperado:** la spec admite `primary:` (un punto) y `plateau_grid:`. El run evalúa los dos. La decisión usa solo la primaria. La meseta es la fracción de vecinos con expectativa neta > 0, y debe ser ≥ 0,6.
  - `n_total` para DSR y familia = 1 por primaria.
  - La rejilla se registra como `plateau_n` en una columna aparte.
  - El contador global suma `1 + plateau_n` para no ocultar miradas.
- **Tests:** la decisión no cambia al permutar los valores de la rejilla; la meseta se calcula bien en una rejilla 3×3 sintética.
- **Dependencias:** T01. **Rollback:** `protocol_version: 1` por defecto.

### T22 · Holdout único y prueba de consistencia
- **Problema:** OOS-1 sin potencia (P0-2).
- **Resultado esperado:** con `protocol_version: 2`, el tramo sellado es uno solo (`holdout`), de una sola lectura y solo para la primaria. Regla: `t = x̄_h / (s_h/√n_h) ≥ 1,645` y `x̄_h ≥ LCB_dev − 2·s_h/√n_h`.
- **Aceptación (obligatoria):** el arnés T01 muestra:
  - `P_v2(aprobar | nulo) ≤ max(0,05; P_v1)`, y
  - `P_v2(aprobar | δ = 0,10)` > `P_v1` en las frecuencias con potencia.
  
  Si no, la tarea se rechaza.
- **Dependencias:** T01, T20, T21. **Rollback:** `protocol_version: 1`.

### T23 · Control por familia (SPA de Hansen)
- **Resultado esperado:** `lab discovery family-test <familia>` aplica el SPA (paquete `arch`) sobre las series diarias de las primarias de la familia, con bootstrap estacionario de bloque igual a la duración media de las operaciones, y guarda el p-valor de familia.
- **Tests:** 10 series nulas → p > 0,05 en la mayoría de las semillas; una serie con ventaja fuerte → p < 0,05.
- **Dependencias:** T21. Dependencia nueva: `arch` (justificada).

### T24 · Confirmación forward con SPRT
- **Resultado esperado:** `lab forward sprt <estrategia> --delta δ --alpha 0.05 --beta 0.2` lee las operaciones forward en demo (R por operación) y devuelve `Λ_n`, los umbrales y la decisión (continuar, aceptar ventaja o rechazar). Solo lectura.
- **Fórmula:** `Λ_n = (δ/σ²)·ΣR − nδ²/(2σ²)`, con `σ` de desarrollo.
- **Tests:** serie sintética con μ = δ → acepta H1 en un tiempo esperado coherente; μ = 0 → acepta H0.
- **Dependencias:** ninguna.

---

## FASE 3 · Datos para ganar potencia

### T30 · Familias multi-instrumento
- Extiende `basket.py` (N2): una hipótesis con la misma regla en N instrumentos se evalúa con R agregados y operaciones agrupadas. `n_total` = 1 por primaria.
- **Aceptación:** el MDE de la familia se reduce aproximadamente en √N en el preflight.

### T31 · Futuros ajustados por vencimiento
- Serie continua con ajuste hacia atrás por diferencia en el día de cambio de volumen, y otra con ajuste por razón. Test: no hay retornos de más de 5 σ en los días de cambio que no estén en la serie del contrato.
- **Aceptación:** informe de saltos antes y después en los 7 símbolos.

### T32 · Historia completa en las specs D1
- Las plantillas D1 usan `usable_from` del snapshot (2013 en índices de Dukascopy, 2003 en FX) en lugar de 2018, cuando la calidad es `ok` o `warn`.

---

## FASE 4 · Reevaluación (requiere la aprobación del operador)

### T40 · Reevaluar fix de divisas y Q3 con costes v2 y protocolo v2
Campañas nuevas `q2b-*` y `q3b-*`, que suman al contador. Specs idénticas salvo `cost_model_version: 2`, `protocol_version: 2` y la primaria declarada **antes** de ejecutar. Para el fix, la primaria es la de la hipótesis del artículo: salida a 1 hora.

### T41 · EA us100-ftmo1 bajo el protocolo v2
- **Solo lectura del EA** (no se cambia su lógica en esta tarea).
- Se calcula:
  - DSR con las 8 variantes;
  - holdout = operaciones posteriores a la congelación de v3.2;
  - forward frente a backtest por operación (carriles de deriva);
  - SPRT sobre el forward.
- **Aceptación:** informe `reports/ea/us100-ftmo1-v2.md` con veredicto y potencia.
- **Mejoras del EA:** solo después de este informe, como versión nueva (v3.3) con las reglas comunes 4 y 5.

### T42 · ai_trader frente a su gemela aleatoria
Informe con la diferencia de R por operación (IA − gemela), su IC por bootstrap y el coste de operar el carril (tiempo, tokens). Decisión del operador: mantener, congelar o retirar.

---

## FASE 5 · Firmas

### T50 · Reglas verificadas y versionadas
- Sustituir las fuentes secundarias de FTMO por la página oficial (consultada con fecha). Añadir `effective_from` por regla.
- Los simuladores aplican FundingPips con `max(balance, equity)` en el reinicio diario.
- **Tests:** caso sintético en que el equity supera al balance en el reinicio y luego cae.

---

## FASE 6 · Limpieza (después de la Fase 1)

| ID | Tarea | Aceptación |
|---|---|---|
| T60 | Verificar los 18 módulos no importados (grep en CLI, scripts y tareas) y mover a `legacy/` con `git mv` los que no se usen | Suite en verde; `lab doctor` en verde |
| T61 | Dividir `cli.py` en `cli/<grupo>.py` sin cambiar comandos ni opciones | Test que compara `lab --help` de cada grupo antes y después |
| T62 | `backtest.py`, `intraday.py` y `ea_lab` usan el `ExecutionModel` de T10 | Tests de paridad por motor |
| T63 | README de unas 200 líneas: estado real, mapa y enlaces | Revisión de Claude |

---

## Cómo verifica Claude cada tarea

1. Lee el diff completo, no solo el RESULTADO.
2. Ejecuta las pruebas de evidencia (`evidencia/*.py`) y los tests nuevos.
3. Comprueba que nada histórico cambió: hash de las tablas de campañas antes y después; `count_tests` igual salvo lo declarado.
4. Para costes y protocolo: compara con el arnés T01 y con las tablas antes/después.
5. Firma el RESULTADO con "Aprobado", "Aprobado con correcciones" (con una cola de corrección) o "Rechazado" (con rollback al tag `-pre`).
