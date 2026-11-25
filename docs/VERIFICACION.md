# Verificación de conformidad antes de una prueba

Adaptado del proceso de **ath-quant-desk** (MIT, GiacomoGhi): se adapta la idea,
no se copia código.

## Principio

- Verifica **otra sesión** distinta de la que construyó el código.
- Juzga la **conformidad con el prerregistro**, nunca el resultado.
- Se hace **antes** de la ejecución que cuenta, con datos sintéticos y con el
  tramo de desarrollo.
- Sus salidas no contienen P&L de la muestra evaluada.
- Un defecto no se corrige en esta sesión: si el código está congelado, corregirlo
  crea una variante nueva con fecha de inicio nueva y decide el operador.

## Lista de comprobación

1. **Unidades y magnitudes.** Cada componente de coste se convierte a bps o R y
   se compara con el rango esperado que declara el prerregistro. Fuera de rango
   por un factor de 3 o más = defecto.
2. **Constantes frente al prerregistro.** Tabla línea a línea: valor del
   prerregistro frente a la constante del código (umbrales, ventanas, horas, δ,
   semillas).
3. **Muestra.** Huella SHA-256 de los ids o fechas. Si la prueba reutiliza una
   muestra, se reproducen sus cifras de referencia publicadas.
4. **Horas y calendario.** Entradas y salidas a la hora declarada en NY; semanas
   de cambio de horario; festivos y cierres tempranos.
5. **Frecuencia de disparo.** Fuera de la mitad o del doble de lo esperado =
   vuelve al diseño.
6. **Salidas.** Cada regla de salida se ve disparar al menos una vez, incluida la
   de SL primero.
7. **Señales perdidas.** Muestra de momentos con la condición cumplida y sin
   operación: cada uno tiene explicación.
8. **Tamaño de posición y NO TRADE.**
9. **Sanidad del placebo o del benchmark** cuando forma parte de la puerta de
   potencia: dispersión frente a la esperada.

## Veredicto

El informe usa **Conforma** o **Defectos**. Los defectos se anotan en
`RESULTADO-TL3.md` y no se corrigen en esta sesión.

## Registro

- Tabla `verifications` de `data/tl3/tl3_research.db`: `hypothesis_id`,
  `code_hash`, `verifier`, `verdict`, `report`, `created_at`. Solo filas nuevas.
- `registry.require_verified(hypothesis_id, code_hash)` lanza un error si no hay
  un `Conforma` para ese hash. Las pruebas futuras deben llamarla antes de
  ejecutar; no se aplica a las ya ejecutadas.
