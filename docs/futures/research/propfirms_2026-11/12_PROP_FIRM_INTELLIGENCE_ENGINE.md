# Propuesta técnica · Prop Firm Intelligence Engine (PFIE)

**Estado:** diseño, **sin código** (el encargo pide no modificar todavía el proyecto). Amplía el motor EV
ya especificado (`docs/futures/04_SPEC_PROP_EV.md`, FUT-A) con registro, vigilancia de cambios,
compatibilidad de estrategias y ranking. Independiente de cualquier firma: una firma es un fichero de
datos, no código.

## 1. Módulos

```text
src/tradinglab/prop_economics/            (paquete ya previsto en ADR-F03)
  registry/        firmas, programas y planes; reglas versionadas con fuente y caducidad
  sources/         instantáneas de páginas oficiales (hash) y detector de cambios
  compat/          compatibilidad estrategia ↔ firma (automatización, horarios, noticias, contratos)
  sim/             motor EV de FUT-A (DayPath, cuenta, payouts, Monte Carlo, escenarios)
  scoring/         ranking ponderado con evidencia; un dato no verificado no puntúa
  ledger/          libro REAL (tarifas pagadas, payouts recibidos) separado de lo simulado
  alerts/          avisos: regla caducada, cambio detectado, estrategia incompatible
config/prop_economics/
  firms_futures.yaml                       catálogo y categoría de bots (ya existe, FUT-R2)
  programs/<firma>_<programa>_<tamaño>.yaml reglas por programa (esquema de 04 §8)
  sources.yaml                             URLs oficiales vigiladas por firma
data/prop_economics/                        (fuera de git)
  snapshots/<firma>/<fecha>/<sha256>.html   páginas tal como se leyeron
  ledger.db                                 libro real
```

## 2. Modelo de datos

| Entidad | Campos clave |
|---|---|
| `Firm` | id, nombre, web, categoría de bots (`allowed`/`conditional`/`prohibited`/`unverified`), países restringidos, métodos de cobro, plataformas |
| `Program` | firma, nombre, tamaño, fases, versión de reglas, `consulted_at`, `expires_after_days` |
| `Rule` | clave, valor, unidad, fase, estado (`verified`/`parcial`/`no verificado`/`discrepancia`), fuente, cita |
| `Source` | URL, fecha, hash del contenido, código HTTP, legible o bloqueada |
| `StrategyProfile` | instrumento, contratos, stop/target en ticks, operaciones/día, duración media, horario, noticias, ¿automática?, plataforma |
| `CompatibilityVerdict` | firma × programa × estrategia → `compatible` / `con_condiciones` / `incompatible` / `sin_datos`, con las reglas que lo deciden |
| `EvResult` | escenario, horizonte, EV, error MC, probabilidades, capital requerido, P(ruina) — etiqueta **SIMULADO** |
| `LedgerEvent` | solicitado / aprobado / procesado / recibido, importe, fecha, evidencia — etiqueta **REALIZADO** |

## 3. Flujos

1. **Alta o revisión de una firma:** skill `prop-firm-rules-verification` → YAML del programa → test de
   esquema → commit. Una regla sin fuente oficial no entra como `verified`.
2. **Vigilancia de cambios** (tarea programada **solo con aprobación del operador**, ADR de `AGENTS.md`):
   descargar las URLs de `sources.yaml` con el cliente por defecto (sin suplantar navegadores), normalizar
   el texto, comparar el hash con la última instantánea; si cambia → alerta con el diff de texto y la
   regla afectada pasa a `needs_review`. Una web que responde 403 se marca `bloqueada`, nunca se fuerza.
3. **Compatibilidad:** para cada estrategia y programa, comprobar automatización (categoría y
   condiciones: propiedad del bot, plataforma, API, VPS, Live), frecuencia (límites de operaciones/día,
   microscalping por duración), horario de cierre, noticias, contratos y escalado. Resultado con la lista
   de reglas que lo justifican.
4. **EV y ranking:** motor FUT-A con los 5 escenarios; el ranking usa la ponderación del encargo (reglas
   15 %, payouts 20 %, automatización 20 %, drawdown 15 %, costes 10 %, plataforma 10 %, elegibilidad
   10 %). Cada nota cita su evidencia; un criterio sin verificar queda **sin nota** y la firma no se
   ordena en ese ranking.
5. **Libro real:** solo el operador registra tarifas y cobros; el panel muestra REALIZADO y SIMULADO por
   separado.

## 4. Reglas de diseño

- **Sin código por firma.** Toda diferencia entre firmas es un dato (plantillas de payout, modos de
  drawdown, consistencia) del esquema de `04 §3-5`.
- **Silencio ≠ permiso.** Una política de bots no verificada cuenta como no permitida a efectos de
  compatibilidad.
- **Caducidad.** Reglas con más de 30 días sin revisar → el motor no las usa sin `--assume`.
- **Trazabilidad.** Cada número de un informe enlaza a su regla, su fuente y su instantánea.
- **Nada transaccional.** El PFIE no compra, no crea cuentas, no acepta términos, no envía datos
  personales ni órdenes.

## 5. Tareas para OpenCode (DeepSeek V4.1 Flash), tras FUT-A

| ID | Tarea | Depende |
|---|---|---|
| FUT-P1 | `registry/`: cargar `firms_futures.yaml` + programas; validación y caducidad | FUT-A1 |
| FUT-P2 | `sources/`: instantánea con hash y diff de texto (sin red en los tests: fixtures HTML) | P1 |
| FUT-P3 | `compat/`: `StrategyProfile` y veredicto con reglas citadas; tests con perfiles sintéticos | P1 |
| FUT-P4 | `scoring/`: ponderación con "sin nota" para lo no verificado | P1, FUT-A7 |
| FUT-P5 | `alerts/` + CLI `lab propecon watch` (sin tarea programada hasta aprobación) | P2 |
| FUT-P6 | Vista del dashboard: catálogo por categoría de bots, REALIZADO vs SIMULADO | P4, FUT-A8 |
