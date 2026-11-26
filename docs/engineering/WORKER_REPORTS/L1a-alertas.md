# L1a · Alertas de test: qué se envió de verdad (solo lectura)

Fecha de ejecución: 2026-11-26
Commit: c914cd6
Base de datos: `E:\trading-lab\data\lab.db`, abierta con `file:...?mode=ro` (solo lectura). No se ha escrito, borrado ni modificado nada. No se ha hecho commit.

Filtro aplicado en el paso 1:

```
message like '%gate-test%' or message like '%intra-x%' or message like '%BTCUSD%' or message like '%presupuesto test%'
```

## Paso 1

Comando:

```
E:\trading-lab\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('file:E:/trading-lab/data/lab.db?mode=ro',uri=True);q=\"select ts,event,severity,channel,ok,substr(message,1,80) from alerts where message like '%gate-test%' or message like '%intra-x%' or message like '%BTCUSD%' or message like '%presupuesto test%' order by ts\";rows=c.execute(q).fetchall();print(len(rows));[print(r) for r in rows[:200]]"
```

Salida:

```
1340
('2026-11-09T01:53:52.486+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, USDJPY,')
('2026-11-09T02:00:22.814+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, USDJPY,')
('2026-11-09T02:15:02.288+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, USDJPY,')
('2026-11-09T02:21:18.201+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T02:39:09.352+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T02:59:05.986+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T02:59:06.479+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T02:59:06.831+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T03:12:15.264+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T03:12:15.762+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T03:12:16.128+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T03:23:49.168+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T03:23:49.665+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T03:23:50.041+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T03:32:41.455+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T03:32:41.951+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T03:32:42.345+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T14:18:52.238+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T14:18:52.766+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T14:18:53.106+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T14:27:58.751+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T14:28:00.082+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T14:28:00.969+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T14:40:34.771+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T14:40:35.337+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T14:40:35.677+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T14:59:34.806+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T14:59:35.373+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T14:59:36.096+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T15:42:05.725+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T15:42:06.321+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T15:42:06.835+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T16:19:19.464+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T16:19:20.041+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T16:19:22.592+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T16:48:26.032+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T16:48:26.590+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T16:48:27.094+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T17:24:36.094+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T17:24:36.645+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T17:24:37.006+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T18:34:02.630+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T18:34:03.148+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T18:34:03.532+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T19:15:31.372+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T19:15:31.915+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T19:15:32.301+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T19:53:24.815+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T19:53:25.499+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T19:53:25.855+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T20:06:13.134+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T20:06:13.605+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T20:06:14.192+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T20:21:01.588+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T20:21:02.132+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T20:21:02.569+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T20:34:08.967+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T20:34:09.479+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T20:34:09.875+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T20:43:23.377+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T20:43:23.920+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T20:43:24.286+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T20:59:09.510+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T20:59:10.086+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T20:59:10.437+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T21:27:36.139+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T21:27:36.698+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T21:27:37.092+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T21:49:40.654+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T21:49:41.381+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T21:49:41.813+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T22:11:59.303+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T22:12:00.002+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T22:12:00.441+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T22:51:02.887+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T22:51:03.385+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T22:51:03.755+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-09T23:59:04.304+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-09T23:59:04.786+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-09T23:59:05.263+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T00:16:22.397+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T00:16:22.906+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T00:16:23.267+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T02:31:36.482+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T02:31:36.976+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T02:31:37.363+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T16:09:25.224+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T16:09:25.697+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T16:09:26.144+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T16:24:47.004+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T16:24:47.522+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T16:24:47.922+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T17:19:49.870+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T17:19:50.402+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T17:19:50.870+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T17:30:44.075+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T17:30:44.605+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T17:30:44.976+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T17:46:15.775+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T17:46:16.349+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T17:46:16.721+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T18:13:52.641+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T18:13:53.214+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T18:13:53.665+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T19:53:44.082+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T19:53:44.658+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T19:53:45.020+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T20:15:10.337+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T20:15:10.874+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T20:15:11.247+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T20:26:49.784+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T20:26:50.317+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T20:26:50.723+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T20:44:29.077+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T20:44:29.623+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T20:44:30.045+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-10T23:12:41.146+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-10T23:12:41.670+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-10T23:12:42.080+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T00:06:14.943+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T00:06:15.468+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T00:06:15.848+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T00:15:58.269+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T00:15:58.781+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T00:15:59.178+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T00:25:03.146+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T00:25:03.667+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T00:25:04.077+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T02:04:13.468+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T02:04:14.097+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T02:04:14.454+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T02:23:24.473+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T02:23:25.030+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T02:23:25.399+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T03:03:20.573+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T03:03:21.120+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T03:03:21.473+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T03:14:48.268+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: sin datos: nunca se registró una descarga de este símbolo')
('2026-11-11T03:15:28.382+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T03:32:40.437+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T03:35:08.539+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T03:35:09.063+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T03:35:09.434+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T03:38:19.381+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T03:38:19.944+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T03:40:16.414+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T03:40:16.988+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T03:40:17.394+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T13:32:06.722+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T13:32:07.384+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T13:32:07.871+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T13:32:12.975+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T13:32:13.643+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T13:37:57.293+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T13:37:57.818+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T13:37:58.162+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T13:46:23.133+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T13:46:23.737+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T13:48:48.861+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T13:48:49.363+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T13:48:49.754+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T14:34:18.254+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T14:34:18.827+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T14:36:23.986+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T14:36:24.519+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T14:36:24.914+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T14:41:49.712+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T14:41:50.245+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T14:43:44.717+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T14:43:45.216+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T14:43:45.610+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T15:20:35.887+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T15:20:36.474+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T15:23:00.423+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T15:23:01.000+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T15:23:01.370+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T16:11:33.510+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T16:11:34.150+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T16:14:00.770+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T16:14:01.301+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T16:14:01.740+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T17:24:29.775+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T17:24:31.134+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T17:26:31.851+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T17:26:32.432+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T17:26:32.803+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T17:34:46.640+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T17:34:47.187+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T17:34:47.757+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T17:35:39.469+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T17:35:40.118+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T18:36:07.297+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T18:36:07.876+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T18:38:08.626+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T18:38:09.147+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
('2026-11-11T18:38:09.483+00:00', 'news_blackout', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: CPI')
('2026-11-11T19:18:05.240+00:00', 'freshness_block', 'warning', 'ntfy', 1, 'gate-test/SPY: datos viejos: 7200 min sin refrescar (falla a 2880 min)')
('2026-11-11T19:18:05.773+00:00', 'clock_block', 'warning', 'ntfy', 1, 'gate-test/SPY: reloj desviado 30.0 s')
('2026-11-11T19:20:17.009+00:00', 'universe_block', 'warning', 'ntfy', 1, 'intra-x/BTCUSD: símbolo BTCUSD no permitido en intraday_fx: solo EURUSD, US100.C')
('2026-11-11T19:20:17.589+00:00', 'risk_budget_block', 'warning', 'ntfy', 1, 'intra-xau/XAUUSD: presupuesto test')
```

## Paso 2

Comando:

```
E:\trading-lab\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('file:E:/trading-lab/data/lab.db?mode=ro',uri=True);print(c.execute('select * from learning_holdout').fetchall());print(c.execute('select symbol,timeframe,last_bar_utc,fetched_at_utc,source from data_freshness order by id desc limit 15').fetchall())"
```

Salida:

```
[(1, '2025-01-01', '2026-11-07', '650388e480bba869', '2026-11-07T23:13:04.055+00:00')]
[('GBPUSD', 'H1', '2026-11-26T19:00:00+00:00', '2026-11-26T19:00:06+00:00', 'mt5:1515349730'), ('GBPUSD', 'H1', '2026-11-26T18:00:00+00:00', '2026-11-26T18:45:05+00:00', 'mt5:1515349730'), ('GBPUSD', 'H1', '2026-11-26T18:00:00+00:00', '2026-11-26T18:30:06+00:00', 'mt5:1515349730'), ('GBPUSD', 'H1', '2026-11-26T18:00:00+00:00', '2026-11-26T18:15:05+00:00', 'mt5:1515349730'), ('GBPUSD', 'H1', '2026-11-26T18:00:00+00:00', '2026-11-26T18:00:06+00:00', 'mt5:1515349730'), ('EURUSD', 'tick', '2026-11-06T00:00:00+00:00', '2026-11-26T17:46:12+00:00', 'ticks'), ('GBPUSD', 'H1', '2026-11-26T17:00:00+00:00', '2026-11-26T17:45:06+00:00', 'mt5:1515349730'), ('EURUSD', 'M15', '2025-03-14T20:45:00+00:00', '2026-11-26T17:45:05+00:00', 'mt5'), ('EURUSD', 'M15', '2025-01-03T23:45:00+00:00', '2026-11-26T17:43:09+00:00', 'mt5'), ('GBPUSD', 'H1', '2026-11-26T17:00:00+00:00', '2026-11-26T17:30:06+00:00', 'mt5:1515349730'), ('EURUSD', 'tick', '2026-11-06T00:00:00+00:00', '2026-11-26T17:25:57+00:00', 'ticks'), ('EURUSD', 'M15', '2025-03-14T20:45:00+00:00', '2026-11-26T17:24:56+00:00', 'mt5'), ('EURUSD', 'M15', '2025-01-03T23:45:00+00:00', '2026-11-26T17:22:58+00:00', 'mt5'), ('GBPUSD', 'H1', '2026-11-26T17:00:00+00:00', '2026-11-26T17:15:06+00:00', 'mt5:1515349730'), ('XAUUSD', 'M5', '2026-11-26T17:00:00+00:00', '2026-11-26T17:00:09+00:00', 'mt5:1515349730')]
```

## Cuántas se enviaron de verdad

`channel != 'none' and ok = 1` significa que el aviso salió por un canal real (aquí `ntfy`) y el envío se registró como correcto.

| Ámbito | Filas | `channel != 'none'` y `ok = 1` | Porcentaje |
|---|---:|---:|---:|
| Filas del filtro (paso 1) | 1340 | **1210** | 90,3 % |
| Tabla `alerts` completa | 1428 | 1281 | 89,7 % |

Desglose de las 1340 filas del filtro, por canal y resultado:

```
[('ntfy', 1, 1210), ('ntfy', 0, 130)]
```

- Las 1340 tienen `channel = 'ntfy'`: **ninguna** quedó con `channel = 'none'`, así que no hay avisos «silenciosos» en este conjunto.
- 130 filas con `ok = 0`: intentos de envío por ntfy que fallaron (no llegaron).

## Fechas de la primera y la última

Del conjunto filtrado (paso 1):

- **Primera:** `2026-11-09T01:53:52.486+00:00` (universe_block · intra-x/BTCUSD)
- **Última:** `2026-11-26T17:44:53.523+00:00` (news_blackout · intra-xau/XAUUSD: CPI)
- Rango: 17 días y 15 h 51 min.

De la tabla `alerts` completa, como referencia:

- Primera: `2026-11-07T04:03:17.192+00:00`
- Última: `2026-11-26T17:44:53.523+00:00`

## Notas

- El comando del paso 1, copiado tal cual en PowerShell, no arranca: los `\"` provocan `ParserError: Falta un argumento en la lista de parámetros`. Se ejecutó el mismo código Python (misma URI `mode=ro`, misma consulta, mismo `rows[:200]`) desde un fichero temporal; esa es la salida de arriba. No se modificó ninguna fila ni el resultado.
- El comando del paso 1 encuentra 1340 filas pero solo imprime las 200 primeras (`rows[:200]`). Las 1140 restantes no aparecen en la salida literal; el conteo y los agregados de arriba sí las incluyen.
- Los eventos del filtro: `universe_block` 283 (259 ok), `risk_budget_block` 278 (254 ok), `news_blackout` 278 (254 ok), `clock_block` 241 (212 ok), `freshness_block` 240 (213 ok), y 20 filas sueltas de `unknown_magic:...` y `missing_sl:...BTCUSD...` (18 ok). Todas las filas con `ok = 0` son de los cinco eventos de bloqueo.
- Los avisos `gate-test/SPY`, `intra-x/BTCUSD`, `intra-xau/XAUUSD: presupuesto test` y `...: CPI` se repiten aproximadamente cada 15 minutos de forma continua entre el 9 y el 26 de noviembre, también hoy. Es el patrón de un job programado que ejecuta el test de compuertas, no un incidente aislado.
- La consola de PowerShell mostraba `s?mbolo` por la página de códigos (cp850). El texto guardado en la base de datos es `símbolo`; la salida de arriba se capturó en UTF-8 desde la misma consulta, sin cambiar datos.
- Sin datos para lo que no está en las tablas consultadas: no se ha inspeccionado ninguna otra tabla, ni el contenido de los envíos, ni los logs de ntfy. No se ha borrado ninguna fila y no se ha hecho commit.
