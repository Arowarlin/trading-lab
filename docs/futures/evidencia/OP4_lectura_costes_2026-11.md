# OP-4 · Lectura de Claude de la tabla de costes de FUT-B1 (2026-11-28)

**Fuente:** `databento_costes_2026-11.json`, metadatos de Databento del 2026-11-28 (precio por uso, sin
créditos ni suscripciones). Esto es una lectura para decidir; la decisión es del operador.

## 1. Qué encontró la revisión

- **El total de 14.065,31 USD no es lo que hace falta.** FUT-B1 cotizó un plan amplio: las 6 raíces, todos
  los esquemas y muestras de L2/L3. Las dos familias que se pueden registrar piden mucho menos.
- **Los `trades` se pagarían dos veces.** Cada registro de `tbbo` es un trade (precio, tamaño, lado agresor)
  con el mejor bid/ask justo antes. En la tabla, `trades` y `tbbo` tienen exactamente el mismo número de
  registros en NQ (722.673.729), MNQ, ES y MES. Con `tbbo` sobra `trades`.
- **El OOS-2 no hace falta todavía.** Está sellado (OP-8) y solo se lee si una hipótesis llega a candidata.
  Se puede comprar entonces, y así el sello también es físico.

## 2. Paquetes

| Paquete | Qué | Para | USD (exacto de B1) |
|---|---|---|---:|
| **1 · Research B** | `ohlcv-1m` de ES y GC, 2010-06-06 → 2026-11-27, y `definition` de ES y GC | FUT-RB-1 entero (RB_spec §2) | **41,89** |
| **2 · Research A con OOS-2** | `tbbo` de NQ (señal) y MNQ (fills), 2019-01-01 → 2026-11-27, y `definition` | FUT-RA-1 y su lectura única del OOS-2 | **≤ 4.133,45** |
| 2a · Research A solo IS | lo mismo, 2019-05-06 → 2024-01-01 | FUT-RA-1 sin OOS-2 | **Sin datos** (ver §3) |

**No hace falta ahora** (9.889,97 USD del total):

| Partida | USD | Por qué no |
|---|---:|---|
| `trades` de las 6 raíces, 2019-2026 | 4.680,24 | NQ y MNQ ya van dentro de `tbbo`; ES, MES, GC y MGC no están en ninguna familia de order flow registrable |
| `tbbo` de ES y MES | 2.954,57 | réplicas RA-1-ES, solo si RA-1 pasa (RA_spec §7) |
| Muestras `mbp-1`, `mbp-10` y `mbo` | 1.915,30 | familias RA-2 y RA-3, más tarde |
| NQ 2017-2018 (`trades` + `tbbo`) | 300,45 | opción de ampliar la muestra; se decide antes de comprar |
| `ohlcv-1m` de NQ, MNQ, MES y MGC | 39,40 | Research B no los usa: los micros entran solo por costes (RB_spec §2) |

## 3. Pendiente para cerrar OP-4

- **Cifra exacta del paquete 2a** (solo IS) y del `status` para las sesiones (D-3 de RB_spec): el script
  tiene ahora `--plan minimo`, que cotiza solo eso y separa IS y OOS-2. Son 12 filas, solo metadatos y
  gratis. Prompt S2b en `OPENCODE_PROMPTS.md`.
- **Lectura de Claude, no recomendación de compra:**
  - el paquete 1 desbloquea Research B entero por unos 42 USD y no depende de nada más;
  - el paquete 2 es el grueso, y conviene ver antes la cifra de 2a.
