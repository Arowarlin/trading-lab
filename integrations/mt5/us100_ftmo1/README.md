# Copia versionada · EA US100_FTMO1

Copia de los archivos que viven en el terminal FTMO:

```text
<data_path>/MQL5/Experts/TradingLab/US100_FTMO1/
```

Incluye el parche de riesgo dinámico v3 (`InpDynRisk`, escalera
1,0/0,6/0,35/0,25 %) aplicado el 2026-11-14. El `.ex5` compilado en el terminal
terminó con **0 errores y 0 warnings** con MetaEditor 64.

- Magic: `93010001`
- Símbolo: `US100.cash`
- Setfile: `US100_FTMO_v3_challenge.set`
- Registro del laboratorio: `config/mt5_eas.yaml`
- Validación: `lab ea validate us100-ftmo1`
- Informe: `reports/ea/us100-ftmo1_v3.md`
- Documento: `docs/ea_us100_ftmo1.md`

Para recompilar en el terminal:

```powershell
& "C:\Program Files\FTMO Global Markets MT5 Terminal\MetaEditor64.exe" `
  /compile:"<data_path>\MQL5\Experts\TradingLab\US100_FTMO1\US100_EA.mq5" `
  /log:"<data_path>\MQL5\Experts\TradingLab\US100_FTMO1\compile.log"
```

El laboratorio no adjunta el EA a ningún gráfico ni envía órdenes por él.
