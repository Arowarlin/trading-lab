# TL3-F · Saneamiento F1

**Fecha:** 2026-11-26 00:59 UTC
**Lock:** `proyecto-tl3-f` (`opencode-tl3-f`).
**Alcance:** solo lectura de datos y documentación. No toca producción, no
registra campañas, no calcula PnL y no suma a `count_tests`.

## 1. Auditoría de `scripts/tl3_warnings.py`

El script es un CLI fino sobre `tradinglab.tl3.warnings`:

| Comando | Qué hace | Efectos |
|---|---|---|
| `list [--db]` | JSON con todos los avisos | Solo lectura |
| `render <subject> [--db]` | Markdown de un subject | Solo lectura |

Comprobaciones:

- `python scripts/tl3_warnings.py list` devuelve **12 avisos** (ids 1-12),
  todos con `subject`, `fecha`, `etapa`, `cifras`, `source_path` y
  `created_at`.
- `python scripts/tl3_warnings.py render "ea:us100-ftmo1"` devuelve los 4
  avisos del EA en Markdown, con su fuente.
- `pytest tests/test_tl3_warnings.py -q` → **3 passed**.
- El script fuerza UTF-8 en stdout, no escribe en la base y no toca
  `count_tests`.
- No está expuesto como subcomando de `lab`; es un script de operador. No es
  un defecto para este bloque, pero conviene recordarlo: la vía canónica para
  los avisos es `scripts/tl3_warnings.py`.

**Veredicto:** Conforma. Sin defectos que bloqueen.

## 2. Huecos D3 de US100 (2012, 2016, 2017)

La regla D3/T7 exige, por sesión NYSE:

- ≥357 velas M1 en 09:30-15:44 de la sesión **y** de la anterior;
- ≥744 velas M1 entre 18:00 del día anterior y 09:29.

La tabla completa está en `TL3_REPORTS/data_coverage.md`. Extracto US100:

| Año | Sesiones NYSE | Días sin velas | ≥95 % sesión | Mediana nocturna (min) | ≥80 % nocturno | Válidas T7 | Hueco máx (min) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2011 | 73 | 68 | 3 | 0 | 0.0 % | 0 | 0.0 |
| 2012 | 250 | 12 | 229 | 0 | 0.0 % | **0** | 0.1 |
| 2013 | 252 | 63 | 121 | 681 | 49.6 % | 72 | 0.1 |
| 2014 | 252 | 1 | 195 | 885 | 86.1 % | 174 | 0.1 |
| 2015 | 252 | 0 | 245 | 450 | 15.1 % | 37 | 0.0 |
| 2016 | 252 | 0 | 251 | 450 | 0.0 % | **0** | 0.0 |
| 2017 | 251 | 0 | 249 | 442 | 0.0 % | **0** | 0.0 |
| 2018 | 251 | 0 | 248 | 927 | 72.1 % | 175 | 0.0 |
| 2019 | 252 | 0 | 249 | 930 | 100.0 % | 246 | 0.0 |
| 2020 | 253 | 0 | 251 | 930 | 98.4 % | 245 | 0.0 |
| 2021 | 252 | 0 | 251 | 930 | 100.0 % | 250 | 0.0 |
| 2022 | 251 | 0 | 250 | 930 | 100.0 % | 249 | 0.0 |
| 2023 | 250 | 0 | 248 | 930 | 100.0 % | 246 | 0.0 |
| 2024 | 252 | 0 | 248 | 925 | 99.6 % | 243 | 0.0 |
| 2025 | 250 | 0 | 247 | 929 | 99.6 % | 244 | 0.0 |
| 2026 | 224 | 0 | 224 | 930 | 100.0 % | 224 | 0.0 |

Lectura de los tres huecos:

- **2012:** 12 días sin velas y solo 229/250 sesiones con ≥95 % de cobertura
  intradía; la mediana nocturna es 0 y ninguna sesión cumple la regla. No es
  un hueco rellenable: faltan velas de noche.
- **2016:** la sesión está casi completa (251/252), pero la mediana nocturna
  es 450 min y **0 %** de sesiones alcanza los 744 min exigidos.
- **2017:** igual que 2016: 249/251 de sesión, mediana nocturna 442 min y 0 %
  de sesiones válidas.

**Ventana continua adoptada:** `2019-01-02` → `2026-11-25`. Se excluyen
2011-2018: 2012/2016/2017 no tienen ninguna sesión válida y 2018 solo llega
al 72,1 % de noches. 2019-2026 tiene ≥98,4 % de noches en todos los años. Para
H-2026-013 (intradía, sin swap) esto es suficiente: el filtro D1 usa cierres
de sesiones completas y la posición se cierra antes de la noche.

## 3. `tl2-edge-map.patch` y `config/` vs `configs/`

- `tl2-edge-map.patch` estaba versionado en la raíz. Es un parche antiguo, no
  aplicado; su contenido no se usa en el motor. Se archiva con
  `git mv tl2-edge-map.patch legacy/tl2-edge-map.patch`. El Edge Map canónico
  sigue siendo `reports/discovery/edge_map.md`; el parche queda como historia.
- **`config/`** es la raíz de configuración canónica que leen el motor y el
  CLI: `config/discovery/engine.yaml`, `config/discovery/templates/`,
  `config/propfund/`, `config/campaigns/`, `config/proposals/` y
  `config/vector/`. Los specs de investigación viven en `.orquestador/specs/`.
- **`configs/`** solo contiene `edge1_h1_ny_impulse.yaml`, el prerregistro de
  la hipótesis EDGE1. Ningún módulo lo lee: la única referencia es la línea
  descriptiva de `scripts/edge1_h1_ny_impulse.py`. No es una segunda raíz de
  configuración y no debe crecer con YAML de runtime.
- Decisión: no se mueve en F1. Se deja como documento de prerregistro y se
  anota que, si se quiere una carpeta canónica, el destino futuro es
  `config/prereg/` o `.orquestador/specs/`, nunca `configs/`.

## 4. Consecuencia para F2 (H-2026-013)

- Instrumento: US100, H1, Dukascopy BID.
- IS: `2019-01-02` → `2023-12-31` (cobertura continua).
- OOS: `2024-01-01` → `2026-11-25` (no se lee en F2).
- Regla: largo intradía con filtro `Close_D1 > SMA50_D1`; entrada en la vela
  H1 siguiente a la señal de las 09:00 NY; stop 2,0×ATR(14) H1; target 2R;
  salida por tiempo a las 15:55 NY; `nights = 0` (sin swap).
- Puertas: `cost_r <= 0.10` (mediana de viabilidad) y muestra mínima H1 de 40
  operaciones. F2 solo ejecuta `preflight` y `feasibility`, sin PnL.

## 5. Comandos y artefactos

```powershell
python scripts/orq_lock.py acquire --resource proyecto-tl3-f --owner opencode-tl3-f --cola "tl3-f"
python scripts/tl3_warnings.py list
python scripts/tl3_warnings.py render "ea:us100-ftmo1"
pytest tests/test_tl3_warnings.py -q
git mv tl2-edge-map.patch legacy/tl2-edge-map.patch
```

- `count_tests` al empezar F1: **5446** (no 1926; la pasada EDGE1 sigue
  sumando discovery). F1 no lo modifica.
