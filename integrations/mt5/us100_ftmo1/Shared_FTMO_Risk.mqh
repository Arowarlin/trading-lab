//+------------------------------------------------------------------+
//|                                           Shared_FTMO_Risk.mqh   |
//|  Presupuesto de riesgo COMPARTIDO entre varios EAs en la misma   |
//|  cuenta FTMO (p. ej. US100 + XAUUSD).                            |
//|                                                                  |
//|  · Sincronización con variables globales del terminal:           |
//|      FTMO_<login>_LOCK      mutex (GlobalVariableSetOnCondition) |
//|      FTMO_<login>_DAYKEY    día FTMO actual (medianoche Praga)   |
//|      FTMO_<login>_DAYREF    max(balance, equity) al reinicio     |
//|      FTMO_<login>_DAYHALT   1 = bloqueo diario de toda la cuenta |
//|      FTMO_<login>_KILL      1 = kill switch (todos se detienen)  |
//|      FTMO_<login>_RSV_<magic>  riesgo reservado (dinero)         |
//|      FTMO_<login>_RST_<magic>  hora de la reserva                |
//|  · Pérdidas sobre TODA la cuenta: equity incluye flotante,       |
//|    comisiones y swaps de cualquier EA u operación manual.        |
//|  · Riesgo agregado = riesgo hasta el SL de todas las posiciones  |
//|    + órdenes pendientes + reservas vigentes de otros EAs.        |
//|  · Utilidades de hora: Nueva York, Londres y Praga con reglas     |
//|    de horario de verano de EE. UU. y de la UE.                   |
//+------------------------------------------------------------------+
#ifndef SHARED_FTMO_RISK_MQH
#define SHARED_FTMO_RISK_MQH

#include "Shared_Logger.mqh"

//──────────────────────────── HORA ──────────────────────────────────
enum ENUM_SERVER_CLOCK
  {
   CLOCK_NY_PLUS_7 = 0,   // Servidor = hora NY + 7 (FTMO y la mayoría de brokers "NY close")
   CLOCK_AUTO_GMT  = 1,   // Automático: TimeTradeServer() - TimeGMT() (solo cuenta real/demo)
   CLOCK_MANUAL    = 2    // Desfase GMT manual en invierno + horario de verano de la UE
  };

class CTimeUtil
  {
private:
   static ENUM_SERVER_CLOCK s_mode;
   static int               s_manualOffsetH;
   static int               s_autoOffsetSec;

   // n-ésimo domingo (n>=1) de un mes, o último si n = -1. Devuelve el día del mes.
   static int NthSunday(const int year, const int mon, const int n)
     {
      MqlDateTime s; s.year = year; s.mon = mon; s.day = 1; s.hour = 0; s.min = 0; s.sec = 0;
      datetime first = StructToTime(s);
      MqlDateTime f; TimeToStruct(first, f);
      int firstSun = 1 + (7 - f.day_of_week) % 7;
      if(n > 0) return firstSun + 7 * (n - 1);
      int dim = DaysInMonth(year, mon);
      int d = firstSun;
      while(d + 7 <= dim) d += 7;
      return d;
     }
   static int DaysInMonth(const int y, const int m)
     {
      if(m == 2) return ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0) ? 29 : 28;
      if(m == 4 || m == 6 || m == 9 || m == 11) return 30;
      return 31;
     }
   static datetime Make(const int y, const int mo, const int d, const int h)
     {
      MqlDateTime s; s.year = y; s.mon = mo; s.day = d; s.hour = h; s.min = 0; s.sec = 0;
      return StructToTime(s);
     }

public:
   static void Configure(const ENUM_SERVER_CLOCK mode, const int manualOffsetH)
     {
      s_mode = mode; s_manualOffsetH = manualOffsetH;
      if(mode == CLOCK_AUTO_GMT)
        {
         long diff = (long)(TimeTradeServer() - TimeGMT());
         s_autoOffsetSec = (int)(MathRound(diff / 900.0) * 900);   // múltiplo de 15 min
        }
     }

   // ¿Horario de verano de EE. UU.? (2º domingo de marzo 07:00 UTC → 1er domingo de noviembre 06:00 UTC)
   static bool IsUSDst(const datetime gmt)
     {
      MqlDateTime s; TimeToStruct(gmt, s);
      datetime a = Make(s.year, 3, NthSunday(s.year, 3, 2), 7);
      datetime b = Make(s.year, 11, NthSunday(s.year, 11, 1), 6);
      return gmt >= a && gmt < b;
     }
   // ¿Horario de verano de la UE? (último domingo de marzo 01:00 UTC → último domingo de octubre 01:00 UTC)
   static bool IsEUDst(const datetime gmt)
     {
      MqlDateTime s; TimeToStruct(gmt, s);
      datetime a = Make(s.year, 3, NthSunday(s.year, 3, -1), 1);
      datetime b = Make(s.year, 10, NthSunday(s.year, 10, -1), 1);
      return gmt >= a && gmt < b;
     }

   static datetime ServerToGMT(const datetime srv)
     {
      if(s_mode == CLOCK_NY_PLUS_7)
        {
         datetime ny = srv - 7 * 3600;
         // NY = GMT-5 (invierno) / GMT-4 (verano). Se evalúa el DST con la estimación de invierno.
         datetime g = ny + 5 * 3600;
         if(IsUSDst(g)) g = ny + 4 * 3600;
         return g;
        }
      if(s_mode == CLOCK_AUTO_GMT) return srv - s_autoOffsetSec;
      datetime g2 = srv - s_manualOffsetH * 3600;
      if(IsEUDst(g2)) g2 -= 3600;
      return g2;
     }
   static datetime ServerToNY(const datetime srv)
     {
      if(s_mode == CLOCK_NY_PLUS_7) return srv - 7 * 3600;
      datetime g = ServerToGMT(srv);
      return g - (IsUSDst(g) ? 4 : 5) * 3600;
     }
   static datetime ServerToLondon(const datetime srv)
     {
      datetime g = ServerToGMT(srv);
      return g + (IsEUDst(g) ? 1 : 0) * 3600;       // Reino Unido sigue la regla de DST de la UE
     }
   static datetime ServerToPrague(const datetime srv)
     {
      datetime g = ServerToGMT(srv);
      return g + (IsEUDst(g) ? 2 : 1) * 3600;
     }
   static int MinutesOfDay(const datetime t)  { MqlDateTime s; TimeToStruct(t, s); return s.hour * 60 + s.min; }
   static int DateKey(const datetime t)       { MqlDateTime s; TimeToStruct(t, s); return s.year * 10000 + s.mon * 100 + s.day; }
  };
ENUM_SERVER_CLOCK CTimeUtil::s_mode = CLOCK_NY_PLUS_7;
int               CTimeUtil::s_manualOffsetH = 2;
int               CTimeUtil::s_autoOffsetSec = 0;

//──────────────────────────── RIESGO COMPARTIDO ─────────────────────
struct SSharedRiskConfig
  {
   double initialCapital;     // capital inicial de la cuenta FTMO (100000)
   double maxAggRiskPct;      // riesgo agregado máximo (0.70 % del capital inicial)
   double dailyLossPct;       // pérdida diaria interna (1.25 %)
   double maxDrawdownPct;     // drawdown total interno (5 %, estático desde el capital inicial)
   double ftmoDailyPct;       // límite oficial FTMO diario (5 % 2-Step / 3 % 1-Step)
   double ftmoMaxPct;         // límite oficial FTMO máximo (10 %)
   int    reservationTTLsec;  // validez de una reserva sin confirmar
   bool   requireSL;          // bloquear si hay posiciones sin SL en la cuenta
   string managedMagics;      // magics que se cierran con el kill switch, separados por coma
  };

class CSharedFTMORisk
  {
private:
   SSharedRiskConfig m_cfg;
   CLogger          *m_log;
   string            m_pfx;
   long              m_managed[];

   string G(const string key) const { return m_pfx + key; }

   bool Lock(const int timeoutMs = 2000)
     {
      string nm = G("LOCK");
      if(!GlobalVariableCheck(nm)) GlobalVariableSet(nm, 0);
      uint start = GetTickCount();
      while(true)
        {
         if(GlobalVariableSetOnCondition(nm, 1, 0)) return true;
         if(GetTickCount() - start > (uint)timeoutMs)
           {
            // mutex huérfano (un EA se cerró con el lock tomado): se fuerza
            m_log.Warn("Mutex de riesgo ocupado demasiado tiempo: se libera por seguridad.");
            GlobalVariableSet(nm, 0);
            return GlobalVariableSetOnCondition(nm, 1, 0);
           }
         if(MQLInfoInteger(MQL_TESTER)) return true;   // en el Tester no hay concurrencia
         Sleep(5);
        }
     }
   void Unlock() { GlobalVariableSet(G("LOCK"), 0); }

   double Gv(const string key, const double def = 0) const
     {
      string nm = G(key);
      return GlobalVariableCheck(nm) ? GlobalVariableGet(nm) : def;
     }

   // pérdida monetaria si el precio va de 'from' hasta 'sl' (≥ 0)
   double LossToSL(const string sym, const bool isBuy, const double vol, const double from, const double sl) const
     {
      if(sl <= 0) return -1.0;    // sin SL: riesgo desconocido
      if(isBuy && sl >= from)  return 0.0;
      if(!isBuy && sl <= from) return 0.0;
      double p = 0;
      if(!OrderCalcProfit(isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, sym, vol, from, sl, p))
        {
         double tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS);
         double ts = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
         if(tv <= 0) tv = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
         if(ts <= 0) return -1.0;
         p = -MathAbs(from - sl) / ts * tv * vol;
        }
      return MathMax(0.0, -p);
     }

   void ParseMagics()
     {
      ArrayResize(m_managed, 0);
      string parts[];
      int n = StringSplit(m_cfg.managedMagics, ',', parts);
      for(int i = 0; i < n; i++)
        {
         string s = parts[i]; StringTrimLeft(s); StringTrimRight(s);
         if(s == "") continue;
         int k = ArraySize(m_managed); ArrayResize(m_managed, k + 1);
         m_managed[k] = StringToInteger(s);
        }
     }

public:
                     CSharedFTMORisk() : m_log(NULL), m_pfx("") {}

   bool Init(const SSharedRiskConfig &cfg, CLogger *log)
     {
      m_cfg = cfg; m_log = log;
      m_pfx = "FTMO_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_";
      ParseMagics();
      if(m_cfg.initialCapital <= 0) { m_log.Error("Capital inicial inválido."); return false; }
      Update();
      return true;
     }

   //── día FTMO (medianoche CE(S)T, Praga) ─────────────────────────
   int FtmoDayKey() const { return CTimeUtil::DateKey(CTimeUtil::ServerToPrague(TimeTradeServer())); }

   double DayRef()        const { return Gv("DAYREF", AccountInfoDouble(ACCOUNT_BALANCE)); }
   double DailyFloor()    const { return DayRef() - m_cfg.dailyLossPct / 100.0 * m_cfg.initialCapital; }
   double MaxFloor()      const { return m_cfg.initialCapital * (1.0 - m_cfg.maxDrawdownPct / 100.0); }
   double FtmoDailyFloor() const { return DayRef() - m_cfg.ftmoDailyPct / 100.0 * m_cfg.initialCapital; }
   double FtmoMaxFloor()  const { return m_cfg.initialCapital * (1.0 - m_cfg.ftmoMaxPct / 100.0); }
   bool   IsKilled()      const { return Gv("KILL") > 0.5; }
   bool   IsDayHalted()   const { return Gv("DAYHALT") > 0.5; }

   bool IsManaged(const long magic) const
     {
      for(int i = 0; i < ArraySize(m_managed); i++) if(m_managed[i] == magic) return true;
      return false;
     }

   // Llamar en cada tick por cada EA
   void Update()
     {
      int key = FtmoDayKey();
      if((int)Gv("DAYKEY") != key)
        {
         if(Lock())
           {
            if((int)Gv("DAYKEY") != key)
              {
               double bal = AccountInfoDouble(ACCOUNT_BALANCE), eq = AccountInfoDouble(ACCOUNT_EQUITY);
               GlobalVariableSet(G("DAYKEY"), key);
               GlobalVariableSet(G("DAYREF"), MathMax(bal, eq));
               GlobalVariableSet(G("DAYHALT"), 0);
               m_log.Info(StringFormat("Nuevo día FTMO %d · referencia %.2f · suelo interno %.2f", key, MathMax(bal, eq), DailyFloor()));
              }
            Unlock();
           }
        }
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      if(!IsDayHalted() && eq <= DailyFloor())
        {
         GlobalVariableSet(G("DAYHALT"), 1);
         m_log.Warn(StringFormat("Pérdida diaria interna alcanzada (equity %.2f ≤ %.2f): bloqueo de la cuenta hasta el próximo día FTMO.", eq, DailyFloor()));
        }
      if(!IsKilled() && (eq <= MaxFloor() || eq <= FtmoMaxFloor()))
         Kill(StringFormat("Drawdown máximo interno alcanzado (equity %.2f ≤ %.2f)", eq, MaxFloor()));
     }

   void Kill(const string why)
     {
      GlobalVariableSet(G("KILL"), 1);
      m_log.Error("KILL SWITCH: " + why);
     }
   void ResetKill() { GlobalVariableSet(G("KILL"), 0); m_log.Warn("Kill switch reiniciado manualmente."); }

   bool IsTradingAllowed(string &reason) const
     {
      if(IsKilled())    { reason = "Kill switch activo"; return false; }
      if(IsDayHalted()) { reason = "Bloqueo diario de la cuenta"; return false; }
      return true;
     }

   //── riesgo agregado de toda la cuenta (dinero) ───────────────────
   // devuelve false si existe alguna posición/orden sin SL y requireSL está activo
   bool AggregateRisk(double &riskMoney, double &remainingMoney, const long excludeMagicReservation) const
     {
      riskMoney = 0; remainingMoney = 0;
      bool ok = true;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         string sym = PositionGetString(POSITION_SYMBOL);
         bool   buy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
         double vol = PositionGetDouble(POSITION_VOLUME);
         double op  = PositionGetDouble(POSITION_PRICE_OPEN);
         double cur = PositionGetDouble(POSITION_PRICE_CURRENT);
         double sl  = PositionGetDouble(POSITION_SL);
         double r0  = LossToSL(sym, buy, vol, op, sl);
         double r1  = LossToSL(sym, buy, vol, cur, sl);
         if(r0 < 0 || r1 < 0) { ok = false; continue; }
         riskMoney += r0; remainingMoney += r1;
        }
      for(int i = OrdersTotal() - 1; i >= 0; i--)
        {
         ulong tk = OrderGetTicket(i);
         if(tk == 0) continue;
         ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
         bool buy = (ot == ORDER_TYPE_BUY_LIMIT || ot == ORDER_TYPE_BUY_STOP || ot == ORDER_TYPE_BUY_STOP_LIMIT || ot == ORDER_TYPE_BUY);
         double r = LossToSL(OrderGetString(ORDER_SYMBOL), buy, OrderGetDouble(ORDER_VOLUME_CURRENT),
                             OrderGetDouble(ORDER_PRICE_OPEN), OrderGetDouble(ORDER_SL));
         if(r < 0) { ok = false; continue; }
         riskMoney += r; remainingMoney += r;
        }
      // reservas de otros EAs todavía no convertidas en posición
      datetime now = TimeCurrent();
      int total = GlobalVariablesTotal();
      string rp = m_pfx + "RSV_";
      for(int i = 0; i < total; i++)
        {
         string nm = GlobalVariableName(i);
         if(StringFind(nm, rp) != 0) continue;
         string mg = StringSubstr(nm, StringLen(rp));
         if(StringToInteger(mg) == excludeMagicReservation) continue;
         double rv = GlobalVariableGet(nm);
         double rt = Gv("RST_" + mg);
         if(rv > 0 && now - (datetime)rt <= m_cfg.reservationTTLsec) { riskMoney += rv; remainingMoney += rv; }
        }
      return ok || !m_cfg.requireSL;
     }

   //── reserva atómica de riesgo antes de enviar una orden ──────────
   bool Reserve(const long magic, const double newRiskMoney, string &reason)
     {
      string why;
      if(!IsTradingAllowed(why)) { reason = why; return false; }
      if(!Lock()) { reason = "No se pudo obtener el mutex de riesgo"; return false; }
      double agg, rem;
      bool slOk = AggregateRisk(agg, rem, magic);
      double cap = m_cfg.maxAggRiskPct / 100.0 * m_cfg.initialCapital;
      double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
      double roomDaily = eq - DailyFloor();          // margen hasta el corte diario interno
      double roomMax   = eq - MaxFloor();            // margen hasta el corte máximo interno
      bool ok = true;
      if(!slOk)                         { ok = false; reason = "Hay posiciones u órdenes sin SL en la cuenta"; }
      else if(agg + newRiskMoney > cap + 1e-6)
        { ok = false; reason = StringFormat("Riesgo agregado %.2f + %.2f > tope %.2f (%.2f%%)", agg, newRiskMoney, cap, m_cfg.maxAggRiskPct); }
      else if(rem + newRiskMoney > roomDaily)
        { ok = false; reason = StringFormat("Si todo toca el SL se superaría la pérdida diaria (margen %.2f)", roomDaily); }
      else if(rem + newRiskMoney > roomMax)
        { ok = false; reason = StringFormat("Si todo toca el SL se superaría el drawdown máximo (margen %.2f)", roomMax); }
      if(ok)
        {
         string mg = IntegerToString(magic);
         GlobalVariableSet(G("RSV_" + mg), newRiskMoney);
         GlobalVariableSet(G("RST_" + mg), (double)TimeCurrent());
        }
      Unlock();
      return ok;
     }

   // Dinero de riesgo que este EA puede usar ahora sin superar ningún tope (≥ 0)
   double AvailableRisk(const long magic)
     {
      string why;
      if(!IsTradingAllowed(why)) return 0;
      double agg, rem;
      if(!AggregateRisk(agg, rem, magic)) return 0;
      double cap = m_cfg.maxAggRiskPct / 100.0 * m_cfg.initialCapital;
      double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
      double a1 = cap - agg;
      double a2 = (eq - DailyFloor()) - rem;
      double a3 = (eq - MaxFloor()) - rem;
      return MathMax(0.0, MathMin(a1, MathMin(a2, a3)));
     }

   void Release(const long magic)
     {
      string mg = IntegerToString(magic);
      GlobalVariableSet(G("RSV_" + mg), 0);
     }

   double AggregateRiskPct(const long excludeMagic)
     {
      double a, r; AggregateRisk(a, r, excludeMagic);
      return a / m_cfg.initialCapital * 100.0;
     }
  };

#endif
