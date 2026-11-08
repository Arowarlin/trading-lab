# Biblioteca de conocimiento

Revisado: 2026-11-08

Fichas originales. No se copia texto de terceros; enlaces y licencias
se revisan antes de adoptar una dependencia.

| Herramienta | Categoría | Licencia | Versión | Estado |
|---|---|---|---|---|
| [Deflated Sharpe Ratio (DSR)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) | Metodología de validación | n/a (metodología) | n/a (metodología) | adoptada |
| [Probability of Backtest Overfitting (PBO/CSCV)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253) | Metodología de validación | n/a (metodología) | n/a (metodología) | adoptada |
| [Walk-forward](docs/README.md) | Metodología de validación | n/a (metodología) | n/a (metodología) | adoptada |
| [Monte Carlo de reglas](docs/README.md) | Metodología de validación | n/a (metodología) | n/a (metodología) | adoptada |
| [FRED (Federal Reserve Economic Data)](https://fred.stlouisfed.org/docs/api/fred/) | Datos macro | Datos según términos de FRED/St. Louis Fed | API v1 | adoptada |
| [SEC EDGAR API](https://www.sec.gov/edgar/sec-api-documentation) | Datos fundamentales | Datos públicos; términos SEC | EDGAR API v1 | adoptada |
| [yfinance](https://github.com/ranaroussi/yfinance) | Datos de mercado | Apache-2.0 | 1.8.0 | adoptada |
| [LM Studio](https://lmstudio.ai/docs) | LLM local | Propietaria; términos de LM Studio | Local; ver la app instalada | adoptada |
| [Optuna](https://optuna.org) | Optimización | MIT | 5.0.0 | adoptada |
| [QuantStats](https://github.com/ranaroussi/quantstats) | Reporting | Apache-2.0 | 0.0.86 | adoptada |
| [Microsoft Qlib](https://github.com/microsoft/qlib) | Plataforma de modelos | MIT | 0.9.7 | descartada |
| [hmmlearn](https://github.com/hmmlearn/hmmlearn) | Régimen | BSD-3-Clause | 0.3.3 | descartada |
| [VectorBT](https://github.com/polakowo/vectorbt) | Backtesting | Apache-2.0 | 1.2.0 | descartada |
| [Backtrader](https://www.backtrader.com) | Backtesting | GPL-3.0 | 1.9.78.123 | descartada |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean) | Motor de trading | Apache-2.0 | Sin datos (no instalado) | descartada |

## Fichas

### Deflated Sharpe Ratio (DSR)

- **ID**: `dsr`
- **Categoría**: Metodología de validación
- **Problema**: Corrige el Sharpe por número de pruebas, asimetría y curtosis para reducir el sesgo de selección.
- **Enlace oficial**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- **Licencia**: n/a (metodología)
- **Versión**: n/a (metodología)
- **Dependencias**: numpy; implementación propia
- **Datos/costes**: Sin coste; usa los retornos ya calculados
- **Ventajas**: Penaliza la búsqueda masiva; obliga a declarar n_trials.
- **Riesgos**: No demuestra edge por sí solo; depende de la calidad de la muestra.
- **Pruebas en TradingLab**: tests/test_research.py::test_deflated_sharpe_penaliza_mas_variantes
- **Estado**: adoptada
- **Motivo**: Se usa como filtro de propuesta y en el contador de trials.

### Probability of Backtest Overfitting (PBO/CSCV)

- **ID**: `pbo`
- **Categoría**: Metodología de validación
- **Problema**: Estima la probabilidad de que la mejor variante in-sample quede por debajo de la mediana out-of-sample.
- **Enlace oficial**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- **Licencia**: n/a (metodología)
- **Versión**: n/a (metodología)
- **Dependencias**: numpy; implementación propia de CSCV
- **Datos/costes**: Sin coste; matriz de retornos de variantes
- **Ventajas**: Mide sobreajuste de forma explícita y reproducible.
- **Riesgos**: Necesita suficientes variantes y bloques; no sustituye OOS ni walk-forward.
- **Pruebas en TradingLab**: tests/test_research.py; tests/test_validation.py
- **Estado**: adoptada
- **Motivo**: Gate de propuestas; PBO > umbral no se propone.

### Walk-forward

- **ID**: `walk-forward`
- **Categoría**: Metodología de validación
- **Problema**: Evalúa la estabilidad de una estrategia entrenando en el pasado y probando en el tramo siguiente.
- **Enlace oficial**: docs/README.md
- **Licencia**: n/a (metodología)
- **Versión**: n/a (metodología)
- **Dependencias**: numpy/pandas; implementación propia
- **Datos/costes**: Sin coste; histórico local
- **Ventajas**: Respeta el orden temporal y detecta degradación.
- **Riesgos**: Puede elegir variantes inestables si el tramo de test es corto.
- **Pruebas en TradingLab**: tests/test_research.py; tests/test_walkforward.py
- **Estado**: adoptada
- **Motivo**: Gate global de propuestas y validación de modelos.

### Monte Carlo de reglas

- **ID**: `monte-carlo`
- **Categoría**: Metodología de validación
- **Problema**: Estima probabilidad de pasar/romper reglas de fondeo con remuestreo de operaciones.
- **Enlace oficial**: docs/README.md
- **Licencia**: n/a (metodología)
- **Versión**: n/a (metodología)
- **Dependencias**: numpy/pandas; implementación propia
- **Datos/costes**: Sin coste; retornos del backtest
- **Ventajas**: Cuantifica riesgo de ruina/breach con intervalos.
- **Riesgos**: Asume que el pasado representa el futuro; no captura regímenes nuevos.
- **Pruebas en TradingLab**: tests/test_research.py; tests/test_prop_sim.py
- **Estado**: adoptada
- **Motivo**: Se usa para pass/breach y escenarios por exposición.

### FRED (Federal Reserve Economic Data)

- **ID**: `fred`
- **Categoría**: Datos macro
- **Problema**: Aporta calendario/indicadores macro para blackout y contexto.
- **Enlace oficial**: https://fred.stlouisfed.org/docs/api/fred/
- **Licencia**: Datos según términos de FRED/St. Louis Fed
- **Versión**: API v1
- **Dependencias**: httpx; API key
- **Datos/costes**: Gratis con API key; límites de uso
- **Ventajas**: Fuente pública, estable y documentada.
- **Riesgos**: Revisión de series y latencia; no es dato intradía.
- **Pruebas en TradingLab**: tests/test_intel_fred.py (si aplica)
- **Estado**: adoptada
- **Motivo**: API key presente; se usa para calendario macro cuando hay datos.

### SEC EDGAR API

- **ID**: `sec-edgar`
- **Categoría**: Datos fundamentales
- **Problema**: Consulta filings y company facts oficiales.
- **Enlace oficial**: https://www.sec.gov/edgar/sec-api-documentation
- **Licencia**: Datos públicos; términos SEC
- **Versión**: EDGAR API v1
- **Dependencias**: httpx; User-Agent con contacto
- **Datos/costes**: Gratis; respetar rate limits
- **Ventajas**: Fuente primaria y oficial.
- **Riesgos**: Formato variable por compañía; no es señal directa.
- **Pruebas en TradingLab**: tests/test_intel_sec.py (si aplica)
- **Estado**: adoptada
- **Motivo**: User-Agent configurado; se usa para due diligence.

### yfinance

- **ID**: `yfinance`
- **Categoría**: Datos de mercado
- **Problema**: Descarga OHLCV diario ajustado para la caché parquet.
- **Enlace oficial**: https://github.com/ranaroussi/yfinance
- **Licencia**: Apache-2.0
- **Versión**: 1.8.0
- **Dependencias**: pandas, numpy, requests; sin API key
- **Datos/costes**: Gratis; datos de Yahoo con limitaciones
- **Ventajas**: Sencillo para equities/ETF y prototipos.
- **Riesgos**: No es fuente oficial; puede cambiar o faltar; FX diario con artefactos OHLC.
- **Pruebas en TradingLab**: tests/test_datacheck.py; tests/test_data_normalize.py
- **Estado**: adoptada
- **Motivo**: Proveedor actual de la caché diaria; el datacheck vigila su calidad.

### LM Studio

- **ID**: `lm-studio`
- **Categoría**: LLM local
- **Problema**: Sirve modelos locales (Qwen) para agentes y lecciones.
- **Enlace oficial**: https://lmstudio.ai/docs
- **Licencia**: Propietaria; términos de LM Studio
- **Versión**: Local; ver la app instalada
- **Dependencias**: LM Studio + modelo Qwen local
- **Datos/costes**: Hardware local; sin coste por token
- **Ventajas**: Privacidad y coste marginal cero.
- **Riesgos**: Latencia/VRAM; no apto para decisiones autónomas.
- **Pruebas en TradingLab**: tests/test_llm.py; `lab doctor` LM Studio OK
- **Estado**: adoptada
- **Motivo**: Redacta propuestas/lecciones; nunca aprueba ni activa.

### Optuna

- **ID**: `optuna`
- **Categoría**: Optimización
- **Problema**: Búsqueda de hiperparámetros con poda y registro de trials.
- **Enlace oficial**: https://optuna.org
- **Licencia**: MIT
- **Versión**: 5.0.0
- **Dependencias**: numpy, sqlalchemy, alembic, colorlog, tqdm; instalado 5.0.0
- **Datos/costes**: Sin coste; CPU local
- **Ventajas**: Trial counter auditable y poda temprana.
- **Riesgos**: Aumenta el número de pruebas; debe sumar a n_trials del DSR.
- **Pruebas en TradingLab**: tests/test_optimize.py; smoke real 3 trials (PBO 80.3%, 0 propuestas)
- **Estado**: adoptada
- **Motivo**: Adoptada en Etapa 7 con walk-forward, holdout sellado y gates DSR/PBO/WF.

### QuantStats

- **ID**: `quantstats`
- **Categoría**: Reporting
- **Problema**: Genera informes HTML de retornos frente a benchmark.
- **Enlace oficial**: https://github.com/ranaroussi/quantstats
- **Licencia**: Apache-2.0
- **Versión**: 0.0.86
- **Dependencias**: pandas, numpy, matplotlib, scipy, seaborn, tabulate; instalado 0.0.86
- **Datos/costes**: Sin coste; datos locales
- **Ventajas**: Informe visual rápido para revisión humana.
- **Riesgos**: Solo lectura; no debe alterar criterios ni propuestas.
- **Pruebas en TradingLab**: tests/test_quantstats_report.py; HTML smoke OK
- **Estado**: adoptada
- **Motivo**: Adoptada en Etapa 7 para HTML por propuesta frente a SPY, solo lectura.

### Microsoft Qlib

- **ID**: `qlib`
- **Categoría**: Plataforma de modelos
- **Problema**: Framework de investigación cuantitativa y modelos.
- **Enlace oficial**: https://github.com/microsoft/qlib
- **Licencia**: MIT
- **Versión**: 0.9.7
- **Dependencias**: Paquete pesado; no instalado
- **Datos/costes**: Requiere datos propios; no incluidos
- **Ventajas**: Workflows y modelos variados.
- **Riesgos**: Complejidad y dependencias; no aporta ventaja clara frente al walk-forward actual.
- **Pruebas en TradingLab**: No instalado; solo `lab models` comprueba .venv-qlib
- **Estado**: descartada
- **Motivo**: No se adopta: coste de integración alto y sin edge demostrado.

### hmmlearn

- **ID**: `hmmlearn`
- **Categoría**: Régimen
- **Problema**: Modelos ocultos de Markov para regímenes.
- **Enlace oficial**: https://github.com/hmmlearn/hmmlearn
- **Licencia**: BSD-3-Clause
- **Versión**: 0.3.3
- **Dependencias**: numpy/scikit-learn; no instalado
- **Datos/costes**: Sin coste; serie local
- **Ventajas**: Etiquetas probabilísticas de régimen.
- **Riesgos**: Inestabilidad con muestras cortas; difícil de explicar.
- **Pruebas en TradingLab**: No instalado; reglas causales en tests/test_regimes.py
- **Estado**: descartada
- **Motivo**: No se adopta: el clasificador por reglas es causal y suficiente.

### VectorBT

- **ID**: `vectorbt`
- **Categoría**: Backtesting
- **Problema**: Backtesting vectorizado de muchas variantes.
- **Enlace oficial**: https://github.com/polakowo/vectorbt
- **Licencia**: Apache-2.0
- **Versión**: 1.2.0
- **Dependencias**: Paquete pesado; no instalado
- **Datos/costes**: Sin coste; datos propios
- **Ventajas**: Rápido para barridos grandes.
- **Riesgos**: Superficie de dependencias; no sustituye el motor validado actual.
- **Pruebas en TradingLab**: No instalado
- **Estado**: descartada
- **Motivo**: No se adopta: el backtester propio ya cubre la necesidad.

### Backtrader

- **ID**: `backtrader`
- **Categoría**: Backtesting
- **Problema**: Framework de backtesting con brokers/indicadores.
- **Enlace oficial**: https://www.backtrader.com
- **Licencia**: GPL-3.0
- **Versión**: 1.9.78.123
- **Dependencias**: No instalado
- **Datos/costes**: Sin coste; datos propios
- **Ventajas**: Ecosistema maduro.
- **Riesgos**: GPL-3.0 y mantenimiento incierto; no se necesita.
- **Pruebas en TradingLab**: No instalado
- **Estado**: descartada
- **Motivo**: No se adopta por licencia GPL y falta de necesidad.

### QuantConnect LEAN

- **ID**: `lean`
- **Categoría**: Motor de trading
- **Problema**: Motor de eventos completo para backtest/paper/live.
- **Enlace oficial**: https://github.com/QuantConnect/Lean
- **Licencia**: Apache-2.0
- **Versión**: Sin datos (no instalado)
- **Dependencias**: C#/.NET, Docker; no instalado
- **Datos/costes**: Datos y infraestructura aparte
- **Ventajas**: Motor maduro y multi-mercado.
- **Riesgos**: Complejidad, .NET y superficie de ejecución; no se necesita para paper actual.
- **Pruebas en TradingLab**: No instalado
- **Estado**: descartada
- **Motivo**: No se adopta: Fase 8 mantiene el backtester propio.
