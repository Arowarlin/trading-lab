# Fixtures F12a · export MQL5

Estos archivos son **sintéticos**, no datos de mercado ni campañas:

- `generated/synthetic_*.mq5`: EA exportado por `tradinglab.discovery.export_mql5`.
- `generated/synthetic_*.manifest.json`: sha256, magic, bloques y perfil de riesgo.
- `generated/synthetic_*.trace.csv`: traza de entradas calculada con `fastbt`
  sobre las barras sintéticas de `export_samples.synthetic_bars(seed=11)`.

Se regeneran con:

```powershell
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\python.exe -m tradinglab.discovery.export_samples --out tests/fixtures/f12_export/generated
```

`tests/test_discovery_export_mql5.py` compara los bytes generados con estos
archivos (golden) y exige que dos exportaciones de la misma estrategia tengan
el mismo sha256. No se ejecuta el Tester ni se envían órdenes.
