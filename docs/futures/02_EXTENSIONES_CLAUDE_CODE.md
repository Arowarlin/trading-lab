# FUT-2 · Extensiones de Claude Code, MCP, skills, subagentes y hooks (Fases 2 y 3)

**Fecha:** 2026-11-27 · **Autor:** Claude Code · **Modo:** solo lectura. **No se ha instalado nada.**

## 0. Fuentes

- Catálogo oficial: `anthropics/claude-plugins-official` (Apache-2.0, 317 plugins en
  `.claude-plugin/marketplace.json`), clonado en superficie el 2026-11-27 y leído fichero a fichero
  (`plugin.json`, `hooks/hooks.json`, `.mcp.json`, cabeceras de agentes y comandos). **Confirmado.**
- Sintaxis de instalación según su README: `/plugin install {plugin-name}@claude-plugins-official`
  o `/plugin > Discover`. **Confirmado.**
- Superpowers (`obra/superpowers`, MIT) y claude-mem (`thedotmack/claude-mem`, Apache-2.0):
  clonados y leídos sus hooks. **Confirmado.**
- Herramientas ya presentes **en esta sesión en la nube**: skills integradas `code-review`,
  `simplify`, `security-review`, `skill-creator`, `init`, `update-config`, `loop`; MCP de GitHub y de
  memoria; Playwright y Chromium preinstalados. **Confirmado aquí.** En el Claude Code local del
  operador (Windows) depende de la versión: **No verificado.**

## 1. Plugins oficiales evaluados

| Plugin | Origen | Qué instala (leído) | Red / shell | Duplica | Valor para TradingLab | Decisión |
|---|---|---|---|---|---|---|
| **superpowers** | obra (comunidad, fijado por SHA `22f0b46`) | 15 skills de proceso + hook `SessionStart` que **inyecta `using-superpowers` en cada sesión**: "If there is even a 1% chance a skill might apply… YOU MUST invoke the skill… before ANY response" | Hook de shell local | Flujo de colas, plantillas y verificación del repo | Alto como **ideas**; en bruto **reescribe el comportamiento** por encima de `AGENTS.md` | **No instalar.** Reimplementar 3 conceptos como skills propias (§3) |
| **feature-dev** | Anthropic | 1 comando + 3 agentes (`code-explorer`, `code-architect`, `code-reviewer`) con herramientas de **solo lectura** + WebFetch/WebSearch, `model: sonnet` | No ejecuta shell | Parcial con la cola FUT | Medio | **Más adelante** (opcional) |
| **code-review** | Anthropic | Comando para PR con `gh pr …` y comentario en línea | `gh` | Skill integrada `/code-review` | Bajo | **No** (duplicado) |
| **code-simplifier** | Anthropic | 1 agente (`model: opus`) | No | Skill integrada `/simplify` | Bajo | **No** (duplicado) |
| **pr-review-toolkit** | Anthropic | 6 agentes (comentarios, tests, errores silenciosos, tipos…) | No | `/code-review` | Bajo (no se trabaja con PR) | **No** |
| **security-guidance** | Anthropic | Hooks en `SessionStart` (crea `~/.claude/security/agent-sdk-venv` y **hace `pip install`** del Agent SDK, hasta 180 s), `UserPromptSubmit`, `PostToolUse` en cada edición y revisión por LLM contra `api.anthropic.com` al parar | **Red + pip + coste de tokens en cada parada** | `/security-review` | Medio | **No por ahora**: hooks pesados; usar `/security-review` bajo demanda |
| **github** | catálogo (MCP remoto `api.githubcopilot.com`) | MCP HTTP con `Authorization: Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}` | Red; **necesita un PAT** | `gh` CLI | Bajo | **No** (usar `gh`; no meter PAT en entorno) |
| **context7** | Upstash (MCP remoto `mcp.context7.com`) | Solo `.mcp.json` HTTP | Red: envía **nombres de librerías y consultas** a un tercero | — | **Alto**: documentación actual de databento, DuckDB, Nautilus, hftbacktest; reduce APIs inventadas (también para OpenCode, que admite MCP) | **Candidato 1** |
| **pyright-lsp** | Anthropic | `lspServers.pyright` → `pyright-langserver --stdio` | Local; exige instalar `pyright` | — | Medio: diagnósticos de tipos en paquetes nuevos | **Candidato 2** |
| **claude-md-management** | Anthropic | 1 skill + 1 comando para mantener `CLAUDE.md` | No | — | Bajo: el repo usa `AGENTS.md` | **No** |
| **playwright** | catálogo | MCP `npx @playwright/mcp@latest` (**versión sin fijar**) | Red + navegador | Playwright ya disponible | Bajo hasta tocar el dashboard | **Más adelante**, con versión fijada |
| **chrome-devtools-mcp** | ChromeDevTools (fijado por SHA `a878bca`); el nombre en el catálogo es `chrome-devtools-mcp`, no `chrome-devtools` | MCP de depuración de Chrome | Navegador | Playwright | Bajo | **No** |
| **skill-creator** | Anthropic | 1 skill con scripts de evaluación | Scripts locales | Skill integrada en esta sesión | Medio (para crear las skills de §3) | Usar la integrada; instalar solo si falta en local |
| **claude-code-setup** | Anthropic | 1 skill que recomienda automatizaciones | No | Este documento | Bajo | **No** |
| **ralph-loop** | Anthropic | Hook `Stop` que **vuelve a lanzar el prompt** en bucle | Shell local | `/loop` | **Negativo**: choca con "no crear una cola infinita" y dispara el coste | **Rechazar** |
| **serena** | catálogo (MCP local) | `uvx --from git+https://github.com/oraios/serena serena start-mcp-server` (**HEAD sin fijar**) | Shell + edición semántica; aplicación **GPL-3.0** (SolidLSP MIT) | Grep/Read/Edit | Medio-alto para navegar `cli.py` (12.392 líneas) por símbolos | **PoC opcional**, solo fijado a un tag y en solo lectura |

## 2. Proyectos de la comunidad

| Proyecto | Licencia | Último push | ★ | Hallazgo | Decisión |
|---|---|---|---:|---|---|
| affaan-m/everything-claude-code | — | — | — | **No existe con ese dueño** (422). Hay un `WorldFlowAI/everything-claude-code` (6.930 ★) **sin licencia** | **Rechazar** |
| obra/superpowers | MIT | 2026-11-26 | 328.262 | Ver §1 | Reimplementar conceptos |
| oraios/serena | GPL-3.0 (app) / MIT (SolidLSP) | 2026-11-27 | 31.758 | Ver §1 | PoC opcional |
| upstash/context7 | MIT | 2026-11-27 | 65.556 | Ver §1 | Candidato 1 |
| thedotmack/claude-mem | Apache-2.0 | 2026-11-27 | 120.200 | Hooks en **todos** los eventos (`PreToolUse` de Read/Bash/Grep, `PostToolUse: *`, prompts, `Stop`, `SessionEnd`) que guardan la actividad en SQLite/Chroma con un servicio worker | **Rechazar**: capturaría salidas con datos de trading y posibles secretos; duplica la memoria de Claude Code |
| modelcontextprotocol/servers | MIT → Apache-2.0 (en transición) | 2026-11-27 | 92.302 | Servidores de referencia (filesystem, git, fetch…) | **Referencia**; duplican herramientas integradas |
| omgits0mar / ianwieds / ethanstoner awesome-claude-code | CC0 / CC0 / MIT | — | 5 / 2 / 0 | Catálogos | Referencia |

## 3. Configuración mínima recomendada

1. **Context7** (MCP remoto). Beneficio medible: que Claude y OpenCode citen la API real de Databento,
   DuckDB y Nautilus. Riesgo: las consultas salen a Upstash. Regla: nunca pegar código ni datos del
   laboratorio en una consulta.
2. **pyright-lsp**, con `pyright` fijado y configurado solo para `src/tradinglab/futures/` y
   `src/tradinglab/prop_economics/`.

Todo lo demás: no, o más adelante con un motivo. Superpowers **no** se instala; sus tres ideas útiles
(`verification-before-completion`, `systematic-debugging`, `writing-plans`) ya están en el método del
repo o pasan a las skills propias.

### 3.0 Estado (2026-11-27, aprobado por el operador)

Instalados con **alcance de proyecto** desde esta sesión, con la CLI oficial (Claude Code 2.1.332):

```text
claude plugin marketplace add anthropics/claude-plugins-official --scope project
claude plugin install context7@claude-plugins-official --scope project
claude plugin install pyright-lsp@claude-plugins-official --scope project
```

Quedan declarados en `.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`), así que
Claude Code los ofrece al abrir el repo en cualquier equipo. Evidencia: `docs/futures/evidencia/
plugins-antes.txt` y `plugins-despues.txt` (inventario: Context7 = 1 MCP, pyright-lsp = 1 LSP; coste de
contexto siempre activo ~0 tokens en ambos).

- **Context7 en la nube:** el entorno `trading-lab` permite ya `mcp.context7.com` (cambio aprobado);
  `curl` llega (HTTP 405 a un GET, lo esperado), pero `claude mcp list` sigue dando `ERR_PROXY_TUNNEL`
  en esta sesión. **No verificado** hasta una sesión nueva. En Windows no hay proxy.
- **pyright-lsp** necesita `pyright-langserver` en el PATH. En la nube ya viene (1.1.414). En Windows:
  `uv tool install pyright` (una vez).
- **Hooks** (`§7`) activos: `.claude/hooks/run.sh` + `tl_guard.py`, 61 tests en
  `tests/test_claude_hooks.py`. Se lanzan con `bash`: en Windows hace falta **Git for Windows** (Git Bash).
  Si no hay bash o Python, el hook falla y la acción sigue (no bloquea): es una red de seguridad, no un
  sandbox. **No verificado en Windows**; primera prueba del operador: pedir a Claude `git add -A` y ver que
  se deniega, y revisar `/hooks`.

### 3.1 Instalación y vuelta atrás (para el equipo del operador, **requiere aprobación**)

```powershell
# 0) Guardar la configuración actual
Copy-Item $HOME\.claude\settings.json $HOME\.claude\settings.json.pre-fut2 -ErrorAction SilentlyContinue
claude plugin list > E:\trading-lab\docs\futures\evidencia\plugins-antes.txt
```

En Claude Code:

```text
/plugin marketplace add anthropics/claude-plugins-official
/plugin install context7@claude-plugins-official
/plugin install pyright-lsp@claude-plugins-official
```

Prueba de funcionamiento: pedir "usa context7 para la firma de `databento.Historical.timeseries.get_range`"
y abrir un `.py` de `src/tradinglab/` para ver diagnósticos de pyright.
Vuelta atrás: `/plugin uninstall context7@claude-plugins-official` (ídem pyright-lsp) y restaurar
`settings.json.pre-fut2`. **No verificado:** que `claude plugin list` exista con ese nombre en la versión
local; si no, copiar la salida de `/plugin`.

## 4. Arquitectura MCP

| Servidor | Tipo | Acceso | Estado |
|---|---|---|---|
| Herramientas integradas (Read/Edit/Bash/Grep) | local | repo | ya |
| `gh` CLI (no MCP) | local | GitHub con la sesión del operador | ya |
| Context7 | HTTP remoto | solo documentación pública | candidato 1 |
| **`tradinglab-state` (propio, nuevo)** | stdio local | **solo lectura**: `count_tests`, campañas y su estado, hipótesis TL3, manifiesto de datasets, reglas de firma vigentes y su caducidad. SQLite abierto con `mode=ro` | BACKLOG (FUT-T2) |

Motivo del servidor propio: hoy cada agente consulta el estado con SQL improvisado
(`OPENCODE_PROMPTS.md` L1a). Un servidor de solo lectura da la **misma respuesta a Claude y a OpenCode**
y no puede escribir en ninguna base.

## 5. Skills propias de TradingLab (creadas el 2026-11-27 en `.claude/skills/`)

De las 26 propuestas se crean **9**. Se descartan las que duplican skills integradas
(`tradinglab-code-review` → `/code-review`; `tradinglab-security-audit` → `/security-review`;
`tradinglab-documentation`) y las que hoy no tienen datos (`footprint-analysis`,
`market-microstructure-analysis`: se crean cuando exista FUT-B2). Ruta: `.claude/skills/<nombre>/SKILL.md`.

| Skill | Agrupa | Entradas | Procedimiento (resumen) | Validación | Salidas | Falla si | Restricciones |
|---|---|---|---|---|---|---|---|
| `futures-data-audit` | data-audit, instrument-spec, contract-rollover, data-quality | ruta del dataset + manifiesto | identidad (raíz, contrato, `instrument_id`), esquema, zona horaria, sesiones CME y DST, rolls desde `definition`, huecos, duplicados, hash | informe reproducible con hash | `reports/futures/data/<id>.md` | falta manifiesto o hash | nunca descarga; "Sin datos" si falta algo |
| `hypothesis-preregistration` | hypothesis-design, experiment-registration, ny-open, order-flow | idea | mecanismo, datos, regla fija, costes, criterio de rechazo previo, **chequeo de contaminación** (FUT-11), potencia (MDE vs ventaja mínima rentable) | plantilla completa, sin resultados | borrador `H-YYYY-NNN` | MDE > ventaja plausible; datos contaminados sin marcar | **no registra ni ejecuta**: eso es del operador |
| `backtest-leakage-audit` | leakage, same-bar, fills, timezone | código + spec | lista de §3.1 de `00_AUDITORIA_REPO.md` aplicada al cambio | tests sintéticos rojos/verdes | informe con línea de código | — | solo lectura |
| `statistical-validation` | validation, walk-forward, monte-carlo | resultados de una campaña | puertas v3, PBO sobre población, DSR/Bonferroni sobre lecturas del OOS-2 (ENG-S2), bandas | comparación con umbrales congelados | veredicto | piden bajar un umbral | **nunca** cambia umbrales |
| `prop-firm-rules-verification` | rules-verification | firma + programa | solo fuentes oficiales; cada regla con valor, URL, fecha de consulta, vigencia, certeza; marca discrepancias | dos lecturas coinciden o `discrepancia` | YAML de `config/prop_economics/programs/` | fuente secundaria única | no inventar; "Sin datos" |
| `prop-firm-ev-analysis` | expected-value, trailing-dd, payout, lifecycle | estrategia (DayPaths) + programa | correr el motor de `04_SPEC_PROP_EV.md` con 4 escenarios y 4 horizontes | error MC, CRN, reglas no caducadas | informe EV | reglas caducadas; escenario optimista como principal | separar **realizado** de **simulado** |
| `futures-risk-sizing` | risk-sizing | stop en ticks, riesgo USD, firma | contratos enteros, micros, topes por firma y escalado | redondeo hacia abajo; 0 contratos = NO TRADE | tabla de tamaño | tope desconocido | nunca envía órdenes |
| `opencode-task-generation` | task generation | especificación | formato de `05_COLA_Y_ROADMAP.md §4` para **DeepSeek V4.1 Flash**: una sesión, ficheros cerrados, cifras exactas, punto de parada | checklist del formato | prompt pegable | tarea > 1 sesión | prohibiciones de `AGENTS.md` siempre incluidas |
| `tradinglab-regression-testing` | regression-testing | cambio en producción | baseline (`lab propfund baseline`), test antes/después, CHANGELOG, tag `tl2-<id>-pre` | test rojo antes / verde después | entrada de CHANGELOG | falta baseline | solo con aprobación del operador |

## 6. Subagentes (creados el 2026-11-27 en `.claude/agents/`)

De los 15 propuestos quedan **7**. Se descartan: *Rust Code Reviewer* (el repo **no tiene ningún `.rs`**,
Confirmado), *Security Auditor* y *Python Code Reviewer* (cubiertos por `/security-review` y
`/code-review`), *Documentation Auditor* y *Performance Engineer* (tareas puntuales de la cola). Se fusionan
NY Open con Futures Quant, y Order Flow con Microstructure. Ruta: `.claude/agents/<nombre>.md`.

| Agente | Responsabilidad | Herramientas | Prohibido |
|---|---|---|---|
| `futures-quant-researcher` | hipótesis NY open/intradía, potencia, contaminación | Read, Grep, Glob, WebSearch, WebFetch | Edit, Write, Bash |
| `microstructure-researcher` | hipótesis de order flow, requisitos de datos | Read, Grep, Glob, WebSearch, WebFetch | Edit, Write, Bash |
| `futures-data-engineer` | revisar canalizaciones y manifiestos | Read, Grep, Glob, Bash (solo lectura, con hook §7) | Edit/Write fuera de `reports/futures/` |
| `statistical-validation-auditor` | revisar resultados contra puertas congeladas | Read, Grep, Glob | Edit, Write, Bash |
| `prop-economics-analyst` | reglas oficiales y lectura de informes EV | Read, Grep, Glob, WebSearch, WebFetch | Edit, Write, Bash |
| `risk-execution-engineer` | revisar riesgo, órdenes, adaptadores (NT8, ProjectX, Tradovate) | Read, Grep, Glob | **cualquier envío de órdenes**; Edit en `execution/` |
| `tradinglab-reviewer` | revisión de entregas de OpenCode con el checklist del repo | Read, Grep, Glob, Bash (ruff/pytest/git diff) | Edit, Write, push |

Los agentes de investigación devuelven su informe a la sesión principal, que es la única que escribe.
**No verificado:** que la versión local de Claude Code acepte patrones de Bash en el `tools:` de un
agente; por eso la restricción de Bash va en el hook de §7.

## 7. Hooks (activos desde el 2026-11-27; `.claude/settings.json` del proyecto)

Todos deterministas, baratos (< 1 s) y reversibles (borrar la entrada del JSON). Ninguno hace commit,
push ni despliegue.

| Evento | Matcher | Qué hace | Coste |
|---|---|---|---|
| `PreToolUse` | `Bash` | **Bloquea** (exit 2 con motivo): `lab campaign run`, `lab research*`, `lab discovery run|approve|confirm|supersede`, `record-informal`, `git push` a `master`, `git add -A`, `git add .`, `git commit -a`, `rm`/`del`/`Remove-Item`, `schtasks`/`Register-ScheduledTask`. Es `AGENTS.md` convertido en control duro | ~10 ms |
| `PreToolUse` | `Edit|Write` | **Bloquea** `.env*`, `config/propfund/protected_manifest.json`, `scripts/register_tasks_tz.ps1`, `config/schedule.yaml`; **avisa** si la ruta es de producción (EA, `ai_trader`, `prop/`, `execution/`, `ea_lab/`) | ~10 ms |
| `PostToolUse` | `Edit|Write` en `*.py` | `ruff check <fichero>` solo del fichero editado | < 1 s |
| `Stop` | — | Si el diff toca rutas de producción y `docs/CHANGELOG-produccion.md` no cambió, imprime un aviso. Nunca lanza la suite (31-35 min) | < 1 s |
| pre-commit (no hook de Claude) | — | trufflehog `--no-verification` sobre lo preparado | segundos |

El registro de experimentos **no se automatiza** con un hook: decidir qué cuenta como prueba es una
decisión estadística (skill `hypothesis-preregistration`).

## 8. Riesgos de esta capa

| Riesgo | Mitigación |
|---|---|
| Una extensión sobrescribe las reglas del repo (Superpowers, claude-mem) | No instalarlas; hooks propios con las reglas de `AGENTS.md` |
| Versiones sin fijar (`@latest`, `git+…` HEAD) | Fijar versión o SHA antes de instalar |
| Secretos en configuración (PAT de GitHub) | No usar el plugin `github`; secretos en keyring |
| Coste de tokens por hooks con LLM | Ningún hook llama a un modelo |
