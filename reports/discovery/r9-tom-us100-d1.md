# Informe · `r9-tom-us100-d1`

Fecha: 2026-11-24. Campaña `done`, 9 combinaciones, 0 finalistas.
IS 2014-01-01 → 2024-06-30 · D1 · US100 · Dukascopy.

## Veredicto

**Pendiente de anclaje: resultado no válido.** La campaña se ejecutó con el
anclaje D1 antiguo (desplazado un día); queda sustituida por
`r9b-tom-us100-d1`. No se analiza su rendimiento.

> Ejecutadas con el anclaje D1 antiguo (desplazado); resultado no válido;
> sustituidas por `r9b-tom`.

## Qué pasó

La etiqueta D1 es la apertura de la sesión NYSE a las 17:00 de Nueva York del
día anterior. El `month_turn` antiguo mapeaba por la fecha de la etiqueta y no
por la sesión, así que la entrada y la salida se desplazaban un día y los meses
que terminaban en viernes o víspera de festivo se perdían. Corregido en el
commit `35265b8` (anclaje por sesión, con tests de junio 2024 y Acción de
Gracias).

## Estado administrativo

- `r9-tom-us100-d1` conserva `approved_at` y su cuenta en el DSR: **9 pruebas**.
- No se pudo ejecutar `supersede` (campaña `done` con 9 evaluaciones); el
  operador registró `r9b-tom-us100-d1`, que suma **otras 9** al contador.
- No hay doble conteo oculto: son dos campañas aprobadas y el contador las
  muestra separadas.

## Tabla

| Bruto | Coste | Neto | Deriva | Operaciones | Pliegues |
|---|---|---|---|---|---|
| No se analiza | No se analiza | No se analiza | No se analiza | No se analiza | No se analiza |

El resultado de esta campaña no se usa para decidir nada. El informe vigente
es el de `r9b-tom-us100-d1`, ejecutado con el anclaje corregido.

## Decisión

Hipótesis 1 (cambio de mes) **probada** con el anclaje corregido en
`r9b-tom-us100-d1`; esta campaña queda archivada como inválida por anclaje. No
se proponen variantes ni re-optimizaciones.
