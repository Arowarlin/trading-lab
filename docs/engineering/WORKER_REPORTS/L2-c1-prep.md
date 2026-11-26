# L2-c1-prep — descarga de festivos JP y conteo de velas USDJPY

Fecha de ejecución: 2026-11-26
Ámbito: preparación del bloque C1 (fix Tokio / gotobi). **No se ejecutó `c1_tokyo_fix_gotobi.py`.**

## 1. Descarga del CSV oficial (Oficina del Gabinete)

Comando:

```
Invoke-WebRequest -Uri "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv" -OutFile data\calendar\jp_holidays_cao.csv
```

Resultado: **OK** (sin error).

- Ruta: `E:\tl-eng-l1\data\calendar\jp_holidays_cao.csv`
- Tamaño: **21 538 bytes**
- Codificación: Shift-JIS (CP932), como publica la CAO. Cabecera verificada por puntos de código: `国民の祝日・休日月日,国民の祝日・休日名称`.

### Recuento de líneas y rango de fechas

- **Líneas del CSV: 1068** (1 cabecera + 1067 filas de datos; 1068 saltos LF, fichero terminado en LF)
- **Primera fecha: 1955-01-01** (`1955/1/1,元日`)
- **Última fecha: 2027-11-23** (`2027/11/23,勤労感謝の日`)

## 2. Salida literal del comando de conteo

Comando ejecutado (tal cual, sin modificar):

```
E:\trading-lab\.venv\Scripts\python.exe -c "import pandas as pd;f=pd.read_parquet(r'E:\trading-lab\data\cache\dukascopy\USDJPY_M1.parquet',columns=['ask_open']);i=pd.DatetimeIndex(pd.to_datetime(f.index));i=i.tz_localize('UTC') if i.tz is None else i.tz_convert('UTC');m=(i<'2023-01-01')&(i.hour==0)&(i.minute.isin([0,54]));s=f.loc[m,'ask_open'];print('primera',i.min(),'velas_00:00_y_00:54',int(m.sum()),'con_ask',int(s.notna().sum()));print(s.groupby(i[m].year).count().to_string())"
```

Salida literal (stdout, sin editar):

```
primera 2003-05-04 21:00:00+00:00 velas_00:00_y_00:54 10234 con_ask 0
time
2003    0
2004    0
2005    0
2006    0
2007    0
2008    0
2009    0
2010    0
2011    0
2012    0
2013    0
2014    0
2015    0
2016    0
2017    0
2018    0
2019    0
2020    0
2021    0
2022    0
```

Código de salida: 0. Sin errores ni avisos en stderr.

## 3. Observación literal (sin interpretación)

El conteo de filas seleccionadas (`velas_00:00_y_00:54`) es **10 234**, y `con_ask` es **0**: la columna `ask_open` no tiene valores en ninguna de esas filas. No se ha valorado la causa ni el impacto; queda para el bloque C1.

## 4. Estado

- No se ejecutó `c1_tokyo_fix_gotobi.py`.
- No se editó código.
- No se ejecutó `lab`, `pytest` ni `git push`.
- **No se hizo commit.**
- No se leyeron datos de 2023 en adelante (filtro `i<'2023-01-01'` aplicado en el propio comando).
