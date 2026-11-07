# Auditoría de repositorios de referencia · 2026-11-07

Auditoría de solo lectura de tres proyectos solicitados para mejorar la consola.
No se copió código de ningún repositorio en este cambio. La integración es de
**conceptos y UX**, implementada con la biblioteca estándar y las dependencias
que TradingLab ya tenía.

## Resumen de licencias

| Repositorio | Licencia | ¿Se puede reutilizar código? | Decisión |
|---|---|---|---|
| [AutoHedge](https://github.com/The-Swarm-Corporation/AutoHedge) | **MIT** | Sí, conservando aviso de copyright | Tomar diseño de pipeline y separación de agentes |
| [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | **MIT** | Sí, conservando aviso de copyright | Replicar UX de research/terminal, no importar el stack |
| [FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal) | **AGPL-3.0** | Copyleft fuerte | **No copiar código ni assets**; solo ideas de UX |

FinceptTerminal se distribuye como aplicación C++/Qt con Python embebido. Su
licencia AGPL-3.0 obliga a publicar cambios si se distribuye o se ofrece como
servicio. Para evitar contaminar TradingLab, no se ha incorporado ningún
archivo, icono, texto o binario de ese repositorio.

## AutoHedge (MIT)

**Qué aporta**

- Pipeline claro: Director → Quant → Risk Manager → Execution.
- Riesgo antes de ejecución: tamaño, drawdown, exposición y score.
- Salidas estructuradas y logging para auditoría.
- Separación entre tesis, análisis cuantitativo y ejecución.

**Qué se adoptó en TradingLab**

- Panel **Pipeline de decisión** en el Resumen: datos → señal → riesgo →
  ejecución, con estado de cada etapa.
- La idea de que el riesgo es una etapa explícita y previa a la ejecución.
- Estados y logs visibles; ninguna etapa puede saltarse el guard.

**Qué no se adoptó**

- Ejecución autónoma en Solana, wallets o claves privadas.
- Dependencias `swarms`, `solders` o modelos externos.
- Ejecución live sin aprobación humana.

## Vibe-Trading (MIT)

**Qué aporta**

- **Research Lab** con costes, walk-forward, holdout y artefactos versionados.
- **Run Detail**: comparar estrategia, benchmark, drawdown y operaciones.
- **Pixel Office**: equipo de agentes con estados y tareas.
- **Alpha Zoo** y leaderboard de señales.
- Terminal con navegación rápida, command palette y watchlist.

**Qué se adoptó en TradingLab**

- Detalle de research al hacer clic en una fila: PBO, walk-forward, DSR,
  regímenes, drawdown y motivos de bloqueo.
- Watchlist local con sparklines, breadth y detalle por activo.
- Paleta de comandos `Ctrl+K` para navegar y abrir activos.
- Navegación agrupada y barra de estado de terminal.

**Qué no se adoptó**

- Frontend React + FastAPI; la consola sigue siendo HTML/CSS/JS sin build.
- Conectores de bróker, ejecución live o dependencias nuevas.
- Arte, iconos o textos del proyecto.

## FinceptTerminal (AGPL-3.0)

**Qué aporta como referencia de producto**

- Terminal financiera de altísima densidad: mercado, research, cartera, noticias,
  Macroeconomía y editor de nodos.
- Barra de estado, módulos, atajos y jerarquía visual de terminal profesional.
- Separación entre desks/módulos y lectura rápida de métricas.

**Qué se adoptó**

- Únicamente **ideas de UX**: densidad, barra de estado, command palette,
  módulos de Mercado/Decisiones/Repos y jerarquía visual.
- Ninguna línea de código, icono, captura o marca.

**Qué no se adoptó**

- C++20/Qt6, binarios, recursos, temas o dependencias.
- Cualquier módulo que implique ejecución live.

## Cambios aplicados a TradingLab Console

| Módulo | Función | Fuente de inspiración |
|---|---|---|
| Mercado | Watchlist desde `data/cache`, sparklines, breadth y detalle | Vibe-Trading / Fincept |
| Calendario | Próximos eventos macro desde SQLite | Fincept / requisito F11b |
| Decisiones | Retorno forward por rating y muestra insuficiente | Research Lab |
| Research | PBO por activo, walk-forward y gate de regímenes | Vibe-Trading |
| Repos | Auditoría de licencias y decisiones | Este documento |
| Command palette | `Ctrl+K`, búsqueda de vistas y activos | Fincept / Vibe |
| Pipeline | Datos → señal → riesgo → ejecución | AutoHedge |
| Status bar | Modo, Praga, datos, research, git y actualización | Fincept |

## Seguridad y límites

- No se añadieron dependencias: solo se usan `pandas`, `pyarrow` y la stdlib.
- El módulo Mercado **solo lee parquet locales**; no descarga precios.
- El calendario **solo lee `macro_events`**; Finnhub sigue sin conectarse.
- No se activó ningún bot, no se arrancó F13 y no se envió ninguna orden.
- No se leyó ni modificó `.env` ni el Credential Manager.
- No se hizo push; los cambios quedan en commits locales.

## Próximos pasos opcionales (requieren aprobación)

1. Conectar Finnhub para calendario en vivo (requiere `FINNHUB_API_KEY`).
2. Añadir un Run Detail con comparación explícita contra benchmark y curva de
   drawdown, usando los artefactos de backtest ya existentes.
3. Evaluar un “alpha zoo” local con las estrategias deterministas actuales,
   sin incorporar el código de Vibe-Trading.
