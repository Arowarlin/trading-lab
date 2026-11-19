# 03 · Matriz de empresas (consulta 2026-11-19)

Fuente de verdad: `config/propfund/firms.yaml` (con URL y fecha por política).
"Verificada" = leída en el help center o la web oficial de la firma. Todo lo
demás cuenta como **no verificado** y el router lo trata como `ALERT_ONLY`.

## CFD

| Firma | Automatización | Estado | Condiciones clave | Fuente |
|---|---|---|---|---|
| **FTMO** (protegida) | con condiciones | verificada | EAs sin aprobación previa; hiperactividad > 2.000 peticiones/día prohibida; estilo replicable en real | ftmo.com FAQ · Forbidden Trading Practices |
| The5ers | con condiciones | por verificar | EAs permitidos según comparativas; oficial prohíbe HFT, arbitraje de latencia/rollover y abuso de pendientes | the5ers.com/faqs/prohibited-trading-practices |
| FundedNext | con condiciones | verificada | solo MT4/MT5; EAs de terceros solo < 50K USD y con tarifa; estrategia única; sin Telegram/WhatsApp | help.fundednext.com/…/8020763 |
| FundingPips | con condiciones | verificada | EA de terceros solo como gestor de riesgo; automatización completa solo con EA propio y prueba de propiedad | intercom.help/fundingpips/…/8536000 |
| FXIFY | con condiciones | por verificar | comparativas indican aprobación previa; FXIFY Futures (otro producto) prohíbe EAs | fuente secundaria |

## Futures

| Firma | Automatización | Estado | Condiciones clave | Fuente |
|---|---|---|---|---|
| Topstep | con condiciones | verificada | bots solo vía API TopstepX/ProjectX; Combine y Express Funded, **no** Live Funded; sin HFT ni VPS/VPN | help.topstep.com/…/11187768 |
| Apex Trader Funding | **prohibida** | por verificar | la lista oficial de actividades prohibidas veta automatización; fuentes discrepan sobre evaluación → no se asume | apextraderfunding.com/help-center |
| MyFundedFutures | con condiciones | verificada | automatización con configuración propia; sin HFT; sin explotar fills simulados; CME en live | intercom.help/myfundedfutures/…/8444599 |
| Tradeify | con condiciones | verificada | bot propio demostrable, **exclusivo de Tradeify**, sin HFT, sin hedging entre cuentas | help.tradeify.co/…/10468318 |
| Take Profit Trader | **prohibida** | por verificar | "No Trading Bots or Algos" en Test, PRO y PRO+; PRO exige ejecución manual | fuente secundaria |

## Reglas numéricas

Solo FTMO tiene valores (objetivo 10 %/5 %, diario 5 %, máximo 10 % estático,
reset Europe/Prague; fuente secundaria del 2026-11-05 ya usada por
`config/prop.yaml`). Para el resto, cada programa lleva `needs_verification`
hasta leer el contrato vigente. La consola muestra **Sin datos**.

## Versionado

`rules_version` por firma. Al editar una regla: subir la versión y ejecutar
`lab propfund affected --firm <id> [--program <id>]` para ver las cuentas
afectadas.
