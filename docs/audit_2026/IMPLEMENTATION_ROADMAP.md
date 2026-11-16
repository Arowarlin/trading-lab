# IMPLEMENTATION_ROADMAP

| Semana | Trabajo | Criterio de aceptación | Quién |
|---|---|---|---|
| 1 (16-22 nov) | T01, T03, T04, T05 | El test del DSR da 0,9004; el guardián incluye 93010001 y 93020001; propuesta de desactivación lista | opencode |
| 1 | Pasar el guardián a CLOSE **después** de T03; desactivar los forwards de FX; abrir el FTMO Free Trial para el EA | Guardián 5/5; EA en su propia cuenta | Operador |
| 2 | T02, T06, T07 | dsr_v2.md publicado; tests de swap y spread en verde | opencode |
| 2 | Leer dsr_v2.md y decidir si algún candidato del cementerio merece revisión | Decisión escrita en campanas.md | Operador |
| 3 | T08, T09, T10, T11 | Informe de robustez del EA | opencode |
| 4 | T12, T13, T14 | Riesgo por clúster aplicado | opencode |
| 5+ | Pre-registro de S2 (momentum diversificado) y S3 (cambio de mes) | Pre-registro con hash **antes** de ejecutar | Operador aprueba y opencode ejecuta |
| Continuo | Forward del EA: 60 días o 40 operaciones | Criterios congelados | Automático |

**Hito de decisión, fin de enero de 2027:** con el forward del EA completo y F13 cerrado, se decide si se compra un challenge, usando el barrido de horizonte y el forward.
