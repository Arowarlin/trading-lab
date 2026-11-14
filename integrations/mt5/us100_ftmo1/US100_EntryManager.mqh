//+------------------------------------------------------------------+
//|                                         US100_EntryManager.mqh   |
//|  Convierte una señal en orden a mercado:                         |
//|   ventana horaria → noticias → spread → límites diarios →        |
//|   SL/TP → lote → reserva atómica de riesgo compartido → envío    |
//+------------------------------------------------------------------+
#ifndef US100_ENTRY_MANAGER_MQH
#define US100_ENTRY_MANAGER_MQH

#include <Trade/Trade.mqh>
#include "US100_Strategy.mqh"
#include "US100_RiskManager.mqh"

struct SEntryConfig
  {
   string symbol;
   long   magic;
   double rr;               // múltiplo del riesgo para el TP
   double minSlPoints;      // SL mínimo en unidades de precio
   double maxSlPoints;      // SL máximo en unidades de precio (0 = sin límite)
   int    deviationPoints;
   bool   newsFilter; int newsBefore; int newsAfter;
   bool   useRoom; double roomR;   // exigir espacio hasta PDH/ONH (o PDL/ONL) ≥ roomR × riesgo
  };

class CEntryManager
  {
private:
   SEntryConfig     m_cfg;
   CLogger         *m_log;
   CTrade           m_trade;
   CRiskManager    *m_risk;
   CSharedFTMORisk *m_shared;
   CMarketAnalysis *m_ma;
   string           m_lastReason;

public:
                     CEntryManager() : m_log(NULL), m_risk(NULL), m_shared(NULL), m_ma(NULL), m_lastReason("") {}

   void Init(const SEntryConfig &cfg, CLogger *log, CRiskManager *risk, CSharedFTMORisk *shared, CMarketAnalysis *ma)
     {
      m_cfg = cfg; m_log = log; m_risk = risk; m_shared = shared; m_ma = ma;
      m_trade.SetExpertMagicNumber(m_cfg.magic);
      m_trade.SetDeviationInPoints(m_cfg.deviationPoints);
      m_trade.SetTypeFillingBySymbol(m_cfg.symbol);
      m_trade.LogLevel(LOG_LEVEL_ERRORS);
     }

   string LastReason() const { return m_lastReason; }

   static string RiskKey(const ulong posTicket) { return "US100_R_" + IntegerToString((long)posTicket); }

   bool HasPosition() const
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) == m_cfg.symbol && PositionGetInteger(POSITION_MAGIC) == m_cfg.magic) return true;
        }
      return false;
     }

   // Devuelve true si se abrió la operación
   bool TryEnter(const SSignal &sig, const SMarket &s, const datetime dayStart)
     {
      m_lastReason = "";
      if(sig.dir == 0) return false;
      string why;
      if(!s.inTrade || s.inFlat)                 { m_lastReason = "Fuera de la ventana de entradas"; return false; }
      if(HasPosition())                           { m_lastReason = "Ya hay una posición abierta"; return false; }
      if(!m_shared.IsTradingAllowed(why))         { m_lastReason = why; return false; }
      if(!m_risk.DailyLimitsOk(dayStart, why))    { m_lastReason = why; return false; }
      if(!m_risk.SpreadOk())                      { m_lastReason = "Spread demasiado alto"; return false; }
      if(m_ma.NewsBlocked(m_cfg.newsFilter, m_cfg.newsBefore, m_cfg.newsAfter)) { m_lastReason = "Ventana de noticias de alto impacto"; return false; }

      MqlTick tk;
      if(!SymbolInfoTick(m_cfg.symbol, tk)) { m_lastReason = "Sin precio"; return false; }
      ENUM_ORDER_TYPE type = sig.dir == 1 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double entry = sig.dir == 1 ? tk.ask : tk.bid;
      double sl = sig.sl;
      double dist = (entry - sl) * sig.dir;
      if(dist < m_cfg.minSlPoints)
        {
         dist = MathMax(m_cfg.minSlPoints, 0.3 * s.atr);
         sl = entry - sig.dir * dist;
        }
      if(m_cfg.maxSlPoints > 0 && dist > m_cfg.maxSlPoints) { m_lastReason = "Stop demasiado amplio"; return false; }
      double tp = entry + sig.dir * m_cfg.rr * dist;
      // espacio hasta el siguiente nivel de liquidez opuesto (opcional)
      if(m_cfg.useRoom)
        {
         double a = sig.dir == 1 ? s.pdh : s.pdl, b = sig.dir == 1 ? s.onh : s.onl, near = 0;
         if(a != MA_NA && (a - entry) * sig.dir > 0) near = MathAbs(a - entry);
         if(b != MA_NA && (b - entry) * sig.dir > 0) near = near == 0 ? MathAbs(b - entry) : MathMin(near, MathAbs(b - entry));
         if(near > 0 && near < m_cfg.roomR * dist) { m_lastReason = "Poco recorrido hasta el siguiente nivel"; return false; }
        }
      sl = m_risk.NormalizePrice(sl); tp = m_risk.NormalizePrice(tp);
      long stopsLvl = SymbolInfoInteger(m_cfg.symbol, SYMBOL_TRADE_STOPS_LEVEL);
      double minStop = stopsLvl * SymbolInfoDouble(m_cfg.symbol, SYMBOL_POINT);
      if(MathAbs(entry - sl) < minStop || MathAbs(tp - entry) < minStop) { m_lastReason = "SL/TP dentro del stops level del broker"; return false; }

      double riskMoney = 0;
      double lots = m_risk.LotsFor(type, entry, sl, riskMoney);
      if(lots <= 0) { m_lastReason = "Lote no válido"; return false; }

      if(!m_shared.Reserve(m_cfg.magic, riskMoney, why)) { m_lastReason = "Riesgo compartido: " + why; m_log.Info(m_lastReason); return false; }
      // MT5 recorta los comentarios a 31 caracteres: se usa un formato corto
      string cmt = StringFormat("US100 %s s%.0f", sig.dir == 1 ? "L" : "S", sig.score);
      bool ok = sig.dir == 1 ? m_trade.Buy(lots, m_cfg.symbol, 0, sl, tp, cmt)
                             : m_trade.Sell(lots, m_cfg.symbol, 0, sl, tp, cmt);
      uint rc = m_trade.ResultRetcode();
      bool done = ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
      m_shared.Release(m_cfg.magic);   // la posición ya cuenta en el riesgo agregado
      if(!done)
        {
         m_lastReason = StringFormat("Orden rechazada %u %s", rc, m_trade.ResultRetcodeDescription());
         m_log.Error(m_lastReason);
         return false;
        }
      // riesgo inicial por posición (para el break even condicionado)
      ulong posTicket = 0;
      if(HasPosition()) posTicket = (ulong)PositionGetInteger(POSITION_TICKET);
      if(posTicket > 0)
        {
         double fill = PositionGetDouble(POSITION_PRICE_OPEN);
         GlobalVariableSet(RiskKey(posTicket), MathAbs(fill - sl));
        }
      m_log.Info(StringFormat("%s %.2f lotes @ %.2f · SL %.2f · TP %.2f · riesgo %.2f %s (%.2f%%) · %s",
                              sig.dir == 1 ? "BUY" : "SELL", lots, entry, sl, tp, riskMoney, AccountInfoString(ACCOUNT_CURRENCY),
                              m_risk.RiskPct(), sig.reason));
      return true;
     }
  };

#endif
