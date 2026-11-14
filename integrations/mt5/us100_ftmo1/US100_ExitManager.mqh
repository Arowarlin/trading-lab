//+------------------------------------------------------------------+
//|                                          US100_ExitManager.mqh   |
//|  Salidas:                                                        |
//|   · Break even condicionado (cierre de vela ≥ N R a favor)       |
//|   · Trailing stop ATR opcional                                   |
//|   · Cierre forzoso al final del horario operativo (NY)           |
//|   · Cierre por noticias (opcional)                               |
//|   · Cierre por kill switch / bloqueo diario de la cuenta         |
//+------------------------------------------------------------------+
#ifndef US100_EXIT_MANAGER_MQH
#define US100_EXIT_MANAGER_MQH

#include <Trade/Trade.mqh>
#include "US100_EntryManager.mqh"

struct SExitConfig
  {
   string symbol;
   long   magic;
   bool   be;   double beR;  double beOffsetPts;   // BE condicionado
   bool   trail; double trailAtr;
   bool   closeOnNews;
   bool   killClosesAllManaged;   // con kill switch cierra también las posiciones de los otros EAs gestionados
  };

class CExitManager
  {
private:
   SExitConfig      m_cfg;
   CLogger         *m_log;
   CTrade           m_trade;
   CSharedFTMORisk *m_shared;
   CMarketAnalysis *m_ma;

   void CloseTicket(const ulong tk, const string why)
     {
      if(m_trade.PositionClose(tk)) m_log.Info(StringFormat("Posición %I64u cerrada: %s", tk, why));
      else m_log.Error(StringFormat("No se pudo cerrar %I64u (%s): %u", tk, why, m_trade.ResultRetcode()));
     }

public:
                     CExitManager() : m_log(NULL), m_shared(NULL), m_ma(NULL) {}

   void Init(const SExitConfig &cfg, CLogger *log, CSharedFTMORisk *shared, CMarketAnalysis *ma, const int deviation)
     {
      m_cfg = cfg; m_log = log; m_shared = shared; m_ma = ma;
      m_trade.SetExpertMagicNumber(m_cfg.magic);
      m_trade.SetDeviationInPoints(deviation);
      m_trade.SetTypeFillingBySymbol(m_cfg.symbol);
      m_trade.LogLevel(LOG_LEVEL_ERRORS);
     }

   void CloseMine(const string why)
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) == m_cfg.symbol && PositionGetInteger(POSITION_MAGIC) == m_cfg.magic)
            CloseTicket(tk, why);
        }
     }

   void CloseAllManaged(const string why)
     {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         long mg = PositionGetInteger(POSITION_MAGIC);
         if(mg == m_cfg.magic || m_shared.IsManaged(mg)) CloseTicket(tk, why);
        }
     }

   // En cada tick: protecciones de cuenta, horario y noticias
   void OnTick(const int nyMinNow, const int flatMin, const bool newsEnabled, const int newsBefore)
     {
      if(m_shared.IsKilled())
        {
         if(m_cfg.killClosesAllManaged) CloseAllManaged("Kill switch"); else CloseMine("Kill switch");
         return;
        }
      if(m_shared.IsDayHalted()) { CloseMine("Bloqueo diario de la cuenta"); return; }
      if(nyMinNow >= flatMin && nyMinNow < 1080) CloseMine("Fin del horario operativo");
      if(m_cfg.closeOnNews && m_ma.NewsBlocked(newsEnabled, newsBefore, 0)) CloseMine("Noticia de alto impacto");
     }

   // Al cierre de cada vela M5: break even condicionado y trailing (efectivos desde la vela siguiente)
   void OnBar(const SMarket &s)
     {
      if(!m_cfg.be && !m_cfg.trail) return;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != m_cfg.symbol || PositionGetInteger(POSITION_MAGIC) != m_cfg.magic) continue;
         bool   buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double ent = PositionGetDouble(POSITION_PRICE_OPEN);
         double sl  = PositionGetDouble(POSITION_SL);
         double tp  = PositionGetDouble(POSITION_TP);
         string key = CEntryManager::RiskKey(tk);
         double risk = GlobalVariableCheck(key) ? GlobalVariableGet(key) : MathAbs(ent - sl);
         if(risk <= 0) continue;
         double spr = SymbolInfoInteger(m_cfg.symbol, SYMBOL_SPREAD) * SymbolInfoDouble(m_cfg.symbol, SYMBOL_POINT);
         double nsl = sl;
         if(buy)
           {
            if(m_cfg.be && sl < ent && s.c >= ent + m_cfg.beR * risk) nsl = ent + m_cfg.beOffsetPts;
            if(m_cfg.trail) nsl = MathMax(nsl, s.h - m_cfg.trailAtr * s.atr);
           }
         else
           {
            if(m_cfg.be && sl > ent && s.c + spr <= ent - m_cfg.beR * risk) nsl = ent - m_cfg.beOffsetPts;
            if(m_cfg.trail) nsl = MathMin(nsl, s.l + spr + m_cfg.trailAtr * s.atr);
           }
         double ts = SymbolInfoDouble(m_cfg.symbol, SYMBOL_TRADE_TICK_SIZE);
         nsl = NormalizeDouble(MathRound(nsl / ts) * ts, (int)SymbolInfoInteger(m_cfg.symbol, SYMBOL_DIGITS));
         if(MathAbs(nsl - sl) >= ts)
           {
            if(m_trade.PositionModify(tk, nsl, tp)) m_log.Info(StringFormat("SL movido a %.2f", nsl));
            else m_log.Warn(StringFormat("No se pudo mover el SL: %u", m_trade.ResultRetcode()));
           }
        }
     }

   // Limpieza de variables globales de posiciones ya cerradas
   void Cleanup()
     {
      int total = GlobalVariablesTotal();
      for(int i = total - 1; i >= 0; i--)
        {
         string nm = GlobalVariableName(i);
         if(StringFind(nm, "US100_R_") != 0) continue;
         ulong tk = (ulong)StringToInteger(StringSubstr(nm, 8));
         if(!PositionSelectByTicket(tk)) GlobalVariableDel(nm);
        }
     }
  };

#endif
