//+------------------------------------------------------------------+
//|                                                    US100_EA.mq5  |
//|  Expert Advisor US100 (Nasdaq 100) · Apertura de Nueva York      |
//|  Cuenta FTMO 100K con presupuesto de riesgo compartido (XAUUSD). |
//|                                                                  |
//|  Arquitectura: M5 ejecución · M15 estructura/FVG · H1 dirección  |
//|  (opcional) · D1 régimen. Señales solo con velas cerradas.       |
//|                                                                  |
//|  Configuración por defecto = variante validada con datos FTMO    |
//|  US100.cash M5 2021-09 → 2026-11 (ver documentación).            |
//+------------------------------------------------------------------+
#property copyright "US100 FTMO Project"
#property version   "1.00"
#property description "NY Open · Liquidity Confluence / ORB · Riesgo compartido FTMO"

#include <Trade/Trade.mqh>
#include "Shared_Logger.mqh"
#include "Shared_FTMO_Risk.mqh"
#include "US100_MarketAnalysis.mqh"
#include "US100_Strategy.mqh"
#include "US100_RiskManager.mqh"
#include "US100_EntryManager.mqh"
#include "US100_ExitManager.mqh"

//──────────────────────────────── INPUTS ────────────────────────────
input group "1 · Símbolo y hora"
input string            InpSymbol        = "";              // Símbolo (vacío = el del gráfico)
input ENUM_SERVER_CLOCK InpClock         = CLOCK_NY_PLUS_7; // Reloj del servidor
input int               InpManualGMT     = 2;               // Desfase GMT de invierno (solo modo manual)

input group "2 · Estrategia"
input ENUM_STRAT_MODE   InpMode          = STRAT_CONFLUENCE; // Modo de estrategia
input bool              InpAggressive    = true;            // Confluencia: modo agresivo (validado)
input int               InpMinScore      = 55;              // Confluencia: puntuación mínima
input bool              InpAllowLong     = true;            // Permitir LONG
input bool              InpAllowShort    = true;            // Permitir SHORT
input int               InpORMinutes     = 15;              // Opening Range (minutos desde 9:30 NY)
input int               InpTradeStart    = 945;             // Inicio de entradas NY (HHMM)
input int               InpTradeEnd      = 1130;            // Fin de entradas NY (HHMM)
input int               InpFlatAt        = 1545;            // Cierre forzoso NY (HHMM)

input group "3 · Pesos del score (se normalizan a 100)"
input double InpWSweep  = 25; // Liquidity sweep
input double InpWFvg    = 20; // FVG
input double InpWVwap   = 20; // VWAP
input double InpWStruct = 15; // Estructura M5
input double InpWRvol   = 10; // Volumen relativo (tick volume)
input double InpWOr     = 10; // Opening Range

input group "4 · Filtros de mercado"
input bool   InpUseRegime     = true;   // Régimen diario (cierre RTH vs SMA)
input int    InpRegimeLen     = 20;     // Régimen: días de la media
input bool   InpUseGap        = true;   // Filtro de gap de apertura
input double InpGapMin        = 0.7;    // Gap mínimo (× mediana de 20 días)
input bool   InpUseH1         = false;  // Bloquear contra tendencia H1 fuerte (no mejoró en el test)
input int    InpH1Ema         = 50;     // H1: EMA
input bool   InpUseM15        = false;  // Bloquear contra estructura M15 (no mejoró en el test)
input bool   InpUseVolRegime  = false;  // Régimen de volatilidad (ATR / mediana)
input double InpVolLo         = 0.6;    // Volatilidad mínima
input double InpVolHi         = 2.0;    // Volatilidad máxima
input double InpAbnormalVol   = 3.0;    // Bloqueo por volatilidad anormal (0 = off)
input int    InpMaxSpreadPts  = 300;    // Spread máximo (points)
input bool   InpNewsFilter    = true;   // Noticias USD de alto impacto (solo real/demo)
input int    InpNewsBefore    = 15;     // Minutos antes
input int    InpNewsAfter     = 15;     // Minutos después

input group "5 · Módulos de análisis"
input bool   InpUsePD = true;  input bool InpUseON = true; input bool InpUsePM = true; input bool InpUseOR = true;
input int    InpSweepCool    = 10;   // Sweep: enfriamiento por nivel (velas)
input int    InpSweepWindow  = 12;   // Sweep: vigencia (velas)
input double InpFvgMinAtr    = 0.15; // FVG: tamaño mínimo (× ATR)
input double InpFvgProxAtr   = 1.0;  // FVG: proximidad (× ATR)
input int    InpFvgExt       = 40;   // FVG: vigencia (velas)
input ENUM_TIMEFRAMES InpFvgHtf = PERIOD_M15; // FVG de temporalidad superior
input double InpVwapExtSd    = 2.0;  // VWAP: sobre-extensión (σ)
input double InpRvolThr      = 1.5;  // RVOL de confirmación
input double InpRvolLow      = 0.7;  // RVOL insuficiente (veto)
input int    InpPivL         = 5;    // Pivote M5 izquierda
input int    InpPivR         = 5;    // Pivote M5 derecha
input int    InpM15Piv       = 3;    // Pivote M15

input group "6 · ORB (solo modo ORB_RETEST)"
input ENUM_CONFIRM InpConfirm   = CONFIRM_EITHER; // Confirmación
input double InpRetestTolAtr    = 0.25; // Tolerancia del retest (× ATR)
input int    InpConfirmBars     = 12;   // Velas máximas para confirmar
input double InpFailAtr         = 0.5;  // Falsa ruptura: vuelta al rango (× ATR)

input group "7 · Stop Loss / Take Profit"
input ENUM_SL_TYPE InpSlType    = SLT_ATR; // Tipo de stop
input double InpSlAtr           = 1.5;  // SL: múltiplo de ATR
input double InpSlBufAtr        = 0.1;  // SL estructural: colchón (× ATR)
input double InpSlMinAtr        = 0.5;  // SL mínimo (× ATR)
input double InpSlMaxAtr        = 3.0;  // SL estructural máximo (× ATR)
input double InpMinSlPts        = 2.0;  // SL mínimo absoluto (precio)
input double InpRR              = 3.0;  // TP = RR × riesgo (1:2 dio menos expectativa)
input bool   InpUseRoom         = false; // Exigir recorrido hasta PDH/ONH
input double InpRoomR           = 1.0;  // Recorrido mínimo (× riesgo)
input bool   InpBE              = false; // Break even condicionado (no mejoró en el test)
input double InpBER             = 1.0;  // BE: cierre de vela a ≥ N R
input double InpBEOffPts        = 0.5;  // BE: puntos a favor
input bool   InpTrail           = false; // Trailing stop ATR
input double InpTrailAtr        = 2.0;  // Trailing: distancia (× ATR)
input bool   InpCloseOnNews     = false; // Cerrar posición antes de noticias

input group "8 · Riesgo del EA"
input double InpRiskPct         = 0.35; // Riesgo por operación (% capital inicial)
input bool   InpUseExceptional  = false; // Usar riesgo excepcional (solo tras validación)
input double InpExceptionalPct  = 0.50; // Riesgo excepcional (%)
input int    InpMaxTrades       = 3;    // Máximo de operaciones diarias
input int    InpMaxConsecLoss   = 2;    // Pérdidas consecutivas que detienen la sesión
input bool   InpDynRisk        = true; // Riesgo din?mico por drawdown (v3)
input double InpDynBase        = 1.00; // Riesgo base si DD < D1 (%)
input double InpDynDD1         = 2.0;  // Umbral DD 1 (%)
input double InpDynR1          = 0.60; // Riesgo con DD >= D1 (%)
input double InpDynDD2         = 4.0;  // Umbral DD 2 (%)
input double InpDynR2          = 0.35; // Riesgo con DD >= D2 (%)
input double InpDynDD3         = 6.0;  // Umbral DD 3 (%)
input double InpDynR3          = 0.25; // Riesgo con DD >= D3 (%)
input int    InpDeviationPts    = 30;   // Desviación máxima (points)
input int    InpCooldown        = 5;    // Velas M5 mínimas entre señales

input group "9 · Riesgo compartido FTMO (igual en ambos EAs)"
input double InpInitialCapital  = 100000; // Capital inicial FTMO
input double InpMaxAggRiskPct   = 0.70;  // Riesgo agregado máximo de ambos EAs (%)
input double InpDailyLossPct    = 1.25;  // Pérdida diaria interna (%)
input double InpMaxDDPct        = 5.0;   // Drawdown total interno (%)
input double InpFtmoDailyPct    = 5.0;   // Límite oficial FTMO diario (%) · 1-Step: 3
input double InpFtmoMaxPct      = 10.0;  // Límite oficial FTMO máximo (%)
input bool   InpRequireSL       = true;  // Bloquear si hay posiciones sin SL en la cuenta
input string InpManagedMagics   = "93010001,93020001"; // Magics de los EAs gestionados
input bool   InpKillAll         = true;  // Kill switch cierra los EAs gestionados
input bool   InpResetKill       = false; // Reiniciar el kill switch al cargar

input group "10 · Varios"
input long   InpMagic           = 93010001; // Número mágico de este EA
input int    InpWarmupBars      = 8000;   // Velas M5 de calentamiento (≥ 25 días para régimen y gap)
input ENUM_FTMO_LOG InpLogLevel = FTLOG_INFO; // Nivel de registro
input bool   InpLogFile         = true;   // Guardar registro en archivo
input bool   InpDashboard       = true;   // Panel en el gráfico

//──────────────────────────────── OBJETOS ───────────────────────────
CLogger          g_log;
CSharedFTMORisk  g_shared;
CMarketAnalysis  g_ma;
CStrategy        g_strat;
CRiskManager     g_risk;
CEntryManager    g_entry;
CExitManager     g_exit;
string           g_sym;
datetime         g_lastBar = 0;
bool             g_warm = false;
SSignal          g_lastSig;
string           g_lastMsg = "";
long             g_lastSigBar = -1000000;

int HM(const int hhmm) { return (hhmm / 100) * 60 + hhmm % 100; }

datetime NyDayStartServer()
  {
   datetime now = TimeTradeServer();
   datetime ny = CTimeUtil::ServerToNY(now);
   MqlDateTime d; TimeToStruct(ny, d);
   return now - (d.hour * 3600 + d.min * 60 + d.sec);
  }

//──────────────────────────────── INIT ──────────────────────────────
int OnInit()
  {
   g_sym = InpSymbol == "" ? _Symbol : InpSymbol;
   g_log.Init("US100", InpLogLevel, InpLogFile);
   CTimeUtil::Configure(InpClock, InpManualGMT);

   if(InpRiskPct <= 0 || InpRiskPct > 1.0 || InpExceptionalPct > 1.0)
     { g_log.Error("Riesgo por operación fuera de rango (0-1 %)."); return INIT_PARAMETERS_INCORRECT; }
   if(InpUseExceptional) g_log.Warn("Riesgo excepcional ACTIVADO: úsalo solo tras validar el EA en demo.");
   if(InpClock == CLOCK_AUTO_GMT && MQLInfoInteger(MQL_TESTER))
      g_log.Warn("El modo de reloj automático no es fiable en el Strategy Tester: usa NY+7 o manual.");

   SSharedRiskConfig sc;
   sc.initialCapital = InpInitialCapital; sc.maxAggRiskPct = InpMaxAggRiskPct; sc.dailyLossPct = InpDailyLossPct;
   sc.maxDrawdownPct = InpMaxDDPct; sc.ftmoDailyPct = InpFtmoDailyPct; sc.ftmoMaxPct = InpFtmoMaxPct;
   sc.reservationTTLsec = 30; sc.requireSL = InpRequireSL; sc.managedMagics = InpManagedMagics;
   if(!g_shared.Init(sc, GetPointer(g_log))) return INIT_FAILED;
   if(InpResetKill) g_shared.ResetKill();

   SMarketConfig mc;
   mc.symbol = g_sym; mc.orMinutes = InpORMinutes; mc.tradeStartHHMM = InpTradeStart; mc.tradeEndHHMM = InpTradeEnd;
   mc.flatHHMM = InpFlatAt; mc.atrLen = 14; mc.rvolLen = 20; mc.rvolThr = InpRvolThr; mc.rvolLow = InpRvolLow;
   mc.sweepCool = InpSweepCool; mc.sweepWindow = InpSweepWindow; mc.fbWindow = 6;
   mc.usePD = InpUsePD; mc.useON = InpUseON; mc.usePM = InpUsePM; mc.useOR = InpUseOR;
   mc.fvgMinAtr = InpFvgMinAtr; mc.fvgProxAtr = InpFvgProxAtr; mc.fvgExt = InpFvgExt; mc.fvgMax = 20; mc.fvgHtf = InpFvgHtf;
   mc.pivL = InpPivL; mc.pivR = InpPivR; mc.m15Piv = InpM15Piv; mc.h1EmaLen = InpH1Ema; mc.h1SlopeBars = 5;
   mc.regLen = InpRegimeLen; mc.gapLen = 20; mc.volLen = 20;
   g_ma.Init(mc, GetPointer(g_log));

   SStrategyConfig st;
   st.mode = InpMode; st.aggressive = InpAggressive; st.minScore = InpMinScore;
   st.wSweep = InpWSweep; st.wFvg = InpWFvg; st.wVwap = InpWVwap; st.wStruct = InpWStruct; st.wRvol = InpWRvol; st.wOr = InpWOr;
   st.allowLong = InpAllowLong; st.allowShort = InpAllowShort;
   st.useRegime = InpUseRegime; st.useGap = InpUseGap; st.gapMin = InpGapMin; st.useH1 = InpUseH1; st.useM15 = InpUseM15;
   st.useVolRegime = InpUseVolRegime; st.volLo = InpVolLo; st.volHi = InpVolHi; st.abnormalVol = InpAbnormalVol;
   st.vwapExtSd = InpVwapExtSd;
   st.confirm = InpConfirm; st.retestTolAtr = InpRetestTolAtr; st.confirmBars = InpConfirmBars; st.failAtr = InpFailAtr;
   st.slType = InpSlType; st.slAtr = InpSlAtr; st.slBufAtr = InpSlBufAtr; st.slMinAtr = InpSlMinAtr; st.slMaxAtr = InpSlMaxAtr;
   g_strat.Init(st, GetPointer(g_log));

   SRiskConfig rc;
   rc.symbol = g_sym; rc.magic = InpMagic; rc.initialCapital = InpInitialCapital; rc.riskPct = InpRiskPct;
   rc.useExceptional = InpUseExceptional; rc.exceptionalPct = InpExceptionalPct;
   rc.maxTradesDay = InpMaxTrades; rc.maxConsecLosses = InpMaxConsecLoss; rc.maxSpreadPoints = InpMaxSpreadPts;
   rc.dynRisk = InpDynRisk; rc.dynBase = InpDynBase; rc.dynDD1 = InpDynDD1; rc.dynR1 = InpDynR1;
   rc.dynDD2 = InpDynDD2; rc.dynR2 = InpDynR2; rc.dynDD3 = InpDynDD3; rc.dynR3 = InpDynR3;
   if(!g_risk.Init(rc, GetPointer(g_log))) return INIT_FAILED;

   SEntryConfig ec;
   ec.symbol = g_sym; ec.magic = InpMagic; ec.rr = InpRR; ec.minSlPoints = InpMinSlPts; ec.maxSlPoints = 0;
   ec.deviationPoints = InpDeviationPts; ec.newsFilter = InpNewsFilter; ec.newsBefore = InpNewsBefore; ec.newsAfter = InpNewsAfter;
   ec.useRoom = InpUseRoom; ec.roomR = InpRoomR;
   g_entry.Init(ec, GetPointer(g_log), GetPointer(g_risk), GetPointer(g_shared), GetPointer(g_ma));

   SExitConfig xc;
   xc.symbol = g_sym; xc.magic = InpMagic; xc.be = InpBE; xc.beR = InpBER; xc.beOffsetPts = InpBEOffPts;
   xc.trail = InpTrail; xc.trailAtr = InpTrailAtr; xc.closeOnNews = InpCloseOnNews; xc.killClosesAllManaged = InpKillAll;
   g_exit.Init(xc, GetPointer(g_log), GetPointer(g_shared), GetPointer(g_ma), InpDeviationPts);

   if(StringFind(InpManagedMagics, IntegerToString(InpMagic)) < 0)
      g_log.Warn("El magic de este EA no está en la lista de EAs gestionados.");
   g_log.Info(StringFormat("Iniciado en %s · modo %s · riesgo %.2f%% · tope agregado %.2f%% · diario %.2f%% · DD %.2f%%",
                           g_sym, InpMode == STRAT_CONFLUENCE ? "CONFLUENCE" : "ORB_RETEST", g_risk.RiskPct(),
                           InpMaxAggRiskPct, InpDailyLossPct, InpMaxDDPct));
   g_warm = false; g_lastBar = 0;
   EventSetTimer(5);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   g_shared.Release(InpMagic);
   Comment("");
  }

//──────────────────────────────── LÓGICA ────────────────────────────
void Warmup()
  {
   int avail = Bars(g_sym, PERIOD_M5);
   int need = InpPivL + InpPivR + 10;
   if(avail < need + 100) return;
   int start = MathMin(InpWarmupBars, avail - need);
   SSignal sig; SMarket s;
   for(int sh = start; sh >= 2; sh--)
     {
      g_ma.ProcessBar(sh);
      g_ma.Get(s);
      g_strat.OnBar(s, sig);
     }
   g_lastBar = iTime(g_sym, PERIOD_M5, 1);
   g_warm = true;
   g_log.Info(StringFormat("Calentamiento completado con %d velas M5.", start - 1));
  }

void OnNewBar()
  {
   g_ma.ProcessBar(1);
   SMarket s; g_ma.Get(s);
   g_exit.OnBar(s);
   SSignal sig;
   if(g_strat.OnBar(s, sig) && s.bar - g_lastSigBar > InpCooldown)
     {
      g_lastSig = sig;
      if(s.inTrade) g_lastSigBar = s.bar;
      if(g_entry.TryEnter(sig, s, NyDayStartServer())) g_lastMsg = "Entrada: " + sig.reason;
      else { g_lastMsg = "Señal descartada: " + g_entry.LastReason(); g_log.Info(g_lastMsg + " (" + sig.reason + ")"); }
     }
  }

void OnTick()
  {
   g_shared.Update();
   g_exit.OnTick(g_ma.NyMinutesNow(), HM(InpFlatAt), InpNewsFilter, InpNewsBefore);
   if(!g_warm) { Warmup(); if(!g_warm) return; }
   datetime t1 = iTime(g_sym, PERIOD_M5, 1);
   if(t1 != 0 && t1 != g_lastBar)
     {
      g_lastBar = t1;
      OnNewBar();
     }
   if(InpDashboard && !MQLInfoInteger(MQL_TESTER)) Dashboard();
  }

void OnTimer()
  {
   // protecciones aunque el símbolo no reciba ticks
   g_shared.Update();
   g_exit.OnTick(g_ma.NyMinutesNow(), HM(InpFlatAt), InpNewsFilter, InpNewsBefore);
   g_exit.Cleanup();
  }

//──────────────────────────────── PANEL ─────────────────────────────
void Dashboard()
  {
   SMarket s; g_ma.Get(s);
   int m = g_ma.NyMinutesNow();
   string why;
   bool allowed = g_shared.IsTradingAllowed(why);
   int tr, cl; g_risk.DayStats(NyDayStartServer(), tr, cl);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   string txt = "US100 FTMO EA · " + (InpMode == STRAT_CONFLUENCE ? "Confluence" : "ORB retest") + "\n";
   txt += StringFormat("Hora NY %02d:%02d · %s\n", m / 60, m % 60, s.inTrade ? "ventana de entradas" : (s.inOR ? "Opening Range" : "fuera de ventana"));
   txt += StringFormat("OR %s  H %.2f  L %.2f · gap %.2f× · régimen %s\n", s.orDone ? "ok" : "pendiente",
                       s.orH == MA_NA ? 0 : s.orH, s.orL == MA_NA ? 0 : s.orL, s.gapRatio, s.regime == 1 ? "alcista" : s.regime == -1 ? "bajista" : "—");
   txt += StringFormat("VWAP %.2f (%.2fσ) · M5 %d · M15 %d · H1 %d · vol %.2f×\n", s.vwap == MA_NA ? 0 : s.vwap, s.vwapDsd, s.m5Trend, s.m15Trend, s.h1Trend, s.volRatio);
   txt += StringFormat("Score L %.0f%s · S %.0f%s · sweep %s\n", g_strat.ScoreLong(), g_strat.VetoLong() ? "(veto)" : "",
                       g_strat.ScoreShort(), g_strat.VetoShort() ? "(veto)" : "", s.lastSweepTxt);
   txt += StringFormat("Hoy: %d/%d ops · pérdidas seguidas %d/%d · riesgo %.2f%%\n", tr, InpMaxTrades, cl, InpMaxConsecLoss, g_risk.RiskPct());
   txt += StringFormat("Equity %.2f · suelo diario %.2f · suelo DD %.2f · riesgo agregado %.2f%%/%.2f%%\n",
                       eq, g_shared.DailyFloor(), g_shared.MaxFloor(), g_shared.AggregateRiskPct(-1), InpMaxAggRiskPct);
   txt += (allowed ? "Trading permitido" : "BLOQUEADO: " + why) + "\n";
   if(g_lastMsg != "") txt += g_lastMsg + "\n";
   Comment(txt);
  }
//+------------------------------------------------------------------+
