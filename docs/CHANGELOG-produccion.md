# Cambios en producción

Registro obligatorio de los cambios en componentes de producción: EA
`us100-ftmo1`, carril forward FTMO, riesgo FTMO, `ai_trader`, Prop Fund y
`ea_lab`. Cada entrada indica la autorización del operador, qué cambió y cómo se
comprueba. El baseline de hashes vive en
`config/propfund/protected_manifest.json` y se consulta con
`lab propfund verify`; se reescribe con `lab propfund baseline --reason "..."`.

## 2026-11-24 · Retirada de la protección de componentes

- **Autorización del operador (literal):** "EL PASO YA NO ESTA PROTEGIDO
  QUITALE LA PROTECCION".
- **Qué cambia:** el manifiesto deja de bloquear. `lab propfund verify` informa
  de los archivos cambiados y sale con código 0; `lab propfund baseline
  --reason "..."` reescribe el baseline y añade una entrada a `authorizations`
  con fecha, motivo y lista de cambios. El concepto `protected` de una
  estrategia pasa a `external_engine` (la ejecuta su propio motor); el YAML
  antiguo con `protected: true` sigue cargando como alias de lectura.
- **Qué no cambia:** el router sigue rechazando enviar órdenes a estrategias de
  motor externo. Solo demo/paper; ninguna orden real.
- **Rollback:** tag `tl2-t00-pre`.
