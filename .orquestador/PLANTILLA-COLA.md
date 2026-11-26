# PLANTILLA DE COLA · <proyecto>

**Creada:** <fecha> · **Aprobada por el operador:** <sí/no>.
**Modo:** cadena continua <bloques>, sin pedir confirmación. Un commit pequeño por bloque.
**No suma al contador** ni toca producción salvo que el bloque lo diga expresamente.

## 1. Reglas

- Las de `AGENTS.md` y `COLA-TL3-D.md §1`. Escritura solo con Python o con `git`.
- Commits por ruta: `git add <rutas>` y `git commit -m "..." -- <rutas>`. Nunca `git add -A`,
  `git add .` ni `git commit -a`.
- Locks: `readme-plan` antes de README/PLAN, `changelog-produccion` antes del CHANGELOG de
  producción, `protected-manifest` antes del manifiesto protegido, `tl3-registry` antes del
  registro TL3 y `proyecto-<nombre>` para la cola activa.
- El `pid` de `owner.json` es el del comando `scripts/orq_lock.py`, que termina al instante.
  **Nunca** se usa para declarar un lock huérfano: solo cuenta la antigüedad (> 2 h), y lo decide
  el operador.
- Prohibido: producción (EA, `ai_trader`, forward, `prop/`, riesgo FTMO, `execution/`,
  `config/propfund/`, `schedule.yaml`, `.env`); `record-informal`; órdenes; campañas; `push`;
  borrar ficheros.
- Si falta un dato: **Sin datos**; no se inventa. Fallo técnico: 3 reintentos y, si sigue,
  `bloqueado: <motivo>` y se documenta.

## 2. Arranque

- `git status --untracked-files=no`: solo puede haber el externo conocido
  `reports/discovery/edge_map.md`.
- Los ficheros **sin seguimiento** de otras sesiones no bloquean: los commits son por ruta.
- Si hay otros ficheros versionados modificados, comprobar cada 5 min durante 60 min. Si siguen:
  `bloqueado: otra sesión con cambios sin commit`. No tocarlos ni incluirlos.
- Si hay otro `pytest -q` en marcha, los bloques de análisis siguen; el cierre espera (5 min,
  máximo 60) antes de lanzar su suite.
- Anotar `count_tests` al arrancar y comprobar que no cambia al cerrar.

## 3. Bloques

### V · Verificación (antes de cualquier ejecución que cuente)

- La hace **otra sesión** distinta de la que construyó el código; juzga conformidad con el
  prerregistro, nunca el resultado.
- Datos sintéticos y tramo de desarrollo; salidas sin P&L de la muestra evaluada.
- Comprobaciones: unidades/magnitudes, constantes frente al prerregistro, huella de la muestra,
  horas/calendario, frecuencia de disparo, todas las salidas (incluido SL primero), señales
  perdidas, tamaño/NO TRADE y sanidad del placebo/benchmark.
- Informe con veredicto **Conforma** / **Defectos**. Si hay defectos, no se corrige el código
  congelado: decide el operador.

### <Bloque 1> · <título>

<Objetivo, pasos, tests, rutas y commit.>

## 4. Cierre

- Con `held("pytest-full")`: `ruff check`, `pytest -q`, `lab doctor`, `lab propfund verify`.
- Con `held("readme-plan")`: README §11 y PLAN, una línea por bloque.
- `count_tests` igual que al arrancar; si no, `bloqueado: contador cambiado`.
- Commit `<proyecto>: cierre <ciclo>` y tag `<proyecto>-<ciclo>`.

## 5. Aviso

- Resumen a Telegram con `lab telegram send --file <resumen>`; si no hay Telegram,
  `lab alerts send`.
- Formato **Hecho / 1..N / Aviso / Siguiente**, con locks, verificaciones, avisos sembrados y
  bloqueos.
