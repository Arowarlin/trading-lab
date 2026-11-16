//+------------------------------------------------------------------+
//|                                          US100_ExitManager.mqh   |
//|  Salidas:                                                        |
//|   · Break even condicionado (cierre de vela ≥ N R a favor)       |
//|   · Trailing stop ATR opcional                                   |
//|   · Cierre forzoso al final del horario operativo (NY)           |
//|   · Cierre efectivo en cierres tempranos (v3.1)                  |
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
   string earlyClose;             // calendario YYYYMMDD:HHMM separado por comas
  };

class CExitManager
  {
private:
   SExitConfig      m_cfg;
   CLogger         *m_log;
   CTrade           m_trade;
   CSharedFTMORisk *m_shared;
   CMarketAnalysis *m_ma;
   int              m_flatDay;
   int              m_flatBase;
   int              m_flatMin;

   void CloseTicket(const ulong tk, const string why)
     {
      if(m_trade.PositionClose(tk)) m_log.Info(StringFormat("Posición %I64u cerrada: %s", tk, why));
      else m_log.Error(StringFormat("No se pudo cerrar %I64u (%s): %u", tk, why, m_trade.ResultRetcode()));
     }

   static int HHMM(const int hhmm) { return (hhmm / 100) * 60 + hhmm % 100; }

   // Cierre del calendario de cierres tempranos para la fecha NY indicada.
   int CalendarCloseMin(const int dateKey) const
     {
      if(StringLen(m_cfg.earlyClose) == 0) return -1;
      string items[];
      int n = StringSplit(m_cfg.earlyClose, StringGetCharacter(",", 0), items);
      if(n <= 1 && StringFind(m_cfg.earlyClose, ";") >= 0)
         n = StringSplit(m_cfg.earlyClose, StringGetCharacter(";", 0), items);
      for(int i = 0; i < n; i++)
        {
         string item = items[i];
         StringTrimLeft(item);
         StringTrimRight(item);
         if(item == "") continue;
         int sep = StringFind(item, ":");
         if(sep < 0) sep = StringFind(item, "=");
         if(sep <= 0) continue;
         int day = (int)StringToInteger(StringSubstr(item, 0, sep));
         if(day != dateKey) continue;
         int hhmm = (int)StringToInteger(StringSubstr(item, sep + 1));
         return HHMM(hhmm);
        }
      return -1;
     }

   // Último fin de sesión del día actual, convertido a minutos de Nueva York.
   // Si el bróker no publica sesiones, devuelve -1.
   int SessionEndNyMin() const
     {
      datetime srvNow = TimeTradeServer();
      MqlDateTime d;
      TimeToStruct(srvNow, d);
      ENUM_DAY_OF_WEEK dow = (ENUM_DAY_OF_WEEK)d.day_of_week;
      datetime from, to;
      int endMin = -1;
      for(uint idx = 0; idx < 16; idx++)
        {
         if(!SymbolInfoSessionTrade(m_cfg.symbol, dow, idx, from, to)) break;
         int e = CTimeUtil::MinutesOfDay(to);
         if(e == 0) e = 1440;   // sesión que termina a medianoche
         if(e > endMin) endMin = e;
        }
      if(endMin < 0) return -1;
      d.hour = 0; d.min = 0; d.sec = 0;
      datetime midnight = StructToTime(d);
      datetime endSrv = midnight + endMin * 60;
      return CTimeUtil::MinutesOfDay(CTimeUtil::ServerToNY(endSrv));
     }

public:
                     CExitManager() : m_log(NULL), m_shared(NULL), m_ma(NULL), m_flatDay(-1), m_flatBase(-1), m_flatMin(-1) {}

   void Init(const SExitConfig &cfg, CLogger *log, CSharedFTMORisk *shared, CMarketAnalysis *ma, const int deviation)
     {
      m_cfg = cfg; m_log = log; m_shared = shared; m_ma = ma;
      m_trade.SetExpertMagicNumber(m_cfg.magic);
      m_trade.SetDeviationInPoints(deviation);
      m_trade.SetTypeFillingBySymbol(m_cfg.symbol);
      m_trade.LogLevel(LOG_LEVEL_ERRORS);
      m_flatDay = -1; m_flatBase = -1; m_flatMin = -1;
     }

   // Cierre efectivo del día: min(flat_at, fin de sesión - 10 min, calendario - 10 min).
   // El calendario también se aplica si el bróker publica una sesión semanal fija
   // que no conoce el cierre temprano puntual.
   int EffectiveFlatMin(const int baseFlatMin)
     {
      datetime srvNow = TimeTradeServer();
      int day = CTimeUtil::DateKey(CTimeUtil::ServerToNY(srvNow));
      if(day == m_flatDay && baseFlatMin == m_flatBase) return m_flatMin;
      int flat = baseFlatMin;
      int cal = CalendarCloseMin(day);
      if(cal >= 0)
        {
         int c = cal - 10;
         if(c < 0) c = 0;
         if(c < flat) flat = c;
        }
      int sess = SessionEndNyMin();
      if(sess >= 0)
        {
         int c = sess - 10;
         if(c < 0) c = 0;
         if(c < flat) flat = c;
        }
      m_flatDay = day; m_flatBase = baseFlatMin; m_flatMin = flat;
      return flat;
     }

   // Entradas nuevas: exige al menos minBeforeClose minutos hasta el cierre efectivo.
   bool EntryAllowed(const int nyMinNow, const int minBeforeClose, const int baseFlatMin)
     {
      return (EffectiveFlatMin(baseFlatMin) - nyMinNow) >= minBeforeClose;
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
      if(nyMinNow >= EffectiveFlatMin(flatMin)) CloseMine("Fin del horario operativo");
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
