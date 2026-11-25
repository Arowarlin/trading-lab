# TL3 · Literatura para T8 (pre-FOMC) y H1 (deriva nocturna)

**Fecha:** 2026-11-25 · **Uso:** fundamento y referencias de H-2026-009 (T8) y H-2026-010 (H1).
No cambia ningún prerregistro: T8 se ejecuta tal como está en `COLA-TL3.md §4` (con la enmienda de
swap del 2026-11-25). Nada de esto es resultado nuestro.

Etiquetas: **[LEÍDO]** texto leído en la fuente; **[RESUMEN]** solo resumen o extracto del buscador;
**[INFERENCIA]** razonamiento propio.

## 1. T8 · Deriva previa al FOMC

| Fuente | Muestra | Hallazgo | Estado |
|---|---|---|---|
| Lucca y Moench (2015), *Journal of Finance* 70(1) | S&P 500, sep-1994 → mar-2011 | Exceso de rentabilidad medio de **49 bps** de 14:00 a 14:00 antes del anuncio; ~4 %/año. 1980-1993: ~20 bps; 1960-1979: nada | [LEÍDO] vía Knox y Vissing-Jorgensen §5.2 |
| Lucca y Moench (2018), blog NY Fed | abr-2011 → jun-2018 | En reuniones **con rueda de prensa**: ~40 bps desde la apertura del día anterior hasta mediodía. **Sin rueda de prensa: ninguna evidencia** | [LEÍDO] |
| Boguth, Grégoire y Martineau (2019), *JFQA* | abr-2011 → sep-2017 | La deriva solo aparece en reuniones con rueda de prensa | [RESUMEN] |
| Kurov, Wolfe y Gilbert (2021), *Finance Research Letters* 40 | hasta ~2019 | La deriva **prácticamente desaparece desde 2016**, con y sin rueda de prensa; lo atribuyen a menor incertidumbre | [RESUMEN] (el PDF dio 404) |
| Knox y Vissing-Jorgensen (FEDS 2026-023, versión 25-ago-2025), Fed Board | 1994 → dic-2023 | **~20 bps por reunión en la noche previa desde marzo de 2011**. La prima de riesgo implícita en opciones solo es 1-2 bps mayor en días FOMC (ago-2016 → 2023): la deriva no parece una prima de riesgo estructural | [LEÍDO] |
| QuantSeeker (feb-2025), blog | SPY 1993 → 2024 | Largo del cierre previo al cierre del día del anuncio: persiste; **plano 2016-2019**, se recupera después; incluye 5 bps por lado | [LEÍDO]; no revisado por pares |

Notas: desde 2019 todas las reuniones tienen rueda de prensa, así que la distinción de 2011-2018 deja de
aplicar. La ventana de T8 (15:55 del día previo → 12:25/13:55) incluye la noche previa que miden Knox y
Vissing-Jorgensen.

**[INFERENCIA] Qué esperar de T8.** La literatura posterior a 2011 sitúa el efecto en ~20 bps o menos,
con un tramo plano en 2016-2019. El δ = 30 bps de T8 viene de la muestra 1994-2011. Con σ del
placebo ≈ 1,2 % y ~120 eventos, la potencia para un efecto real de 20 bps es de ~55 %, y de ~5 % si
el efecto es 0. Un "no confirma" será, por tanto, poco informativo sobre si existe un efecto pequeño;
sí descarta un efecto del tamaño original. Un "confirma" sería una replicación independiente
(2011-2026, CFD, neto de costes) que la literatura no tiene más allá de 2023-2024.

## 2. H1 · Deriva nocturna

| Fuente | Muestra | Hallazgo | Estado |
|---|---|---|---|
| Boyarchenko, Larsen y Whelan, NY Fed SR 917 → *Review of Financial Studies* 36(9), 2023 | E-mini S&P 500, 1998-2019 | La mayor rentabilidad se concentra de **2:00 a 3:00 ET** (apertura europea): 3,7 %/año = **1,48 bps/día**. Cierre→apertura 4,6 %/año (desde 2004). La causa propuesta es el inventario de los creadores de mercado tras el desequilibrio del cierre | [LEÍDO] |
| Mismo trabajo, costes | E-mini | Largo de 2:00 a 3:00: Sharpe **1,1 antes de costes y −0,5 tras el bid-ask**. Solo la versión condicionada al desequilibrio del cierre (comprar tras cierre vendedor) sobrevive a costes | [LEÍDO] |
| Boyarchenko, Larsen y Whelan (jul-2026), blog NY Fed "The Disappearing Overnight Drift" | E-mini S&P 500, NQ y YM, 2021-2025 | La ventana de 2:00 a 3:00 **promedia casi cero desde 2021**; lo atribuyen a la compresión de los desequilibrios de cierre | [LEÍDO] |
| Lou, Polk y Skouras (2019), *JFE* | acciones EE. UU. | Patrón noche/día bien documentado; los costes hacen la estrategia "mucho menos atractiva" | [RESUMEN] |

**[INFERENCIA] Qué implica para H1.** Los retornos de futuros ya son netos del tipo libre de riesgo,
mientras que un CFD cobra el tipo completo más un margen (CFD-006: 7,33 %/año ≈ 2,0 bps por noche
natural). Por noche hábil, el bruto en futuros (~1,8 bps antes de 2020, ~0 en la apertura europea
desde 2021) no cubre el margen del bróker más spread y slippage (~1,1 bps). Esto coincide con la
puerta de coste corregida: **H1 = `rejected: cost_gate`**. No conviene reabrirla como variante
condicionada al desequilibrio del cierre: necesita volumen con signo (Databento OHLCV no lo da) y su
motor se debilitó en 2021-2025.

## 3. Fuentes

- Lucca y Moench (2015): https://econpapers.repec.org/RePEc:bla:jfinan:v:70:y:2015:i:1:p:329-371
- Lucca y Moench (2018): https://libertystreeteconomics.newyorkfed.org/2018/11/the-pre-fomc-announcement-drift-more-recent-evidence.html
- Boguth, Grégoire y Martineau (2019): https://econpapers.repec.org/RePEc:cup:jfinqa:v:54:y:2019:i:6:p:2327-2353_2
- Kurov, Wolfe y Gilbert (2021): https://ideas.repec.org/a/eee/finlet/v40y2021ics1544612320315956.html
- Knox y Vissing-Jorgensen (FEDS 2026-023): https://www.federalreserve.gov/econres/feds/files/2026023pap.pdf
- QuantSeeker (2025): https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift
- Boyarchenko, Larsen y Whelan, SR 917: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf
- Boyarchenko, Larsen y Whelan (2021): https://libertystreeteconomics.newyorkfed.org/2021/05/the-overnight-drift-in-us-equity-returns
- Boyarchenko, Larsen y Whelan (2026): https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/
- Lou, Polk y Skouras (2019): https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
