//+------------------------------------------------------------------+
//|                                          US100_RiskManager.mqh   |
//|  Riesgo propio del EA US100:                                     |
//|   · Verificación de especificaciones del símbolo del broker      |
//|   · Cálculo de lote por riesgo (tick value/size, step, min, max, |
//|     margen libre)                                                |
//|   · Contadores diarios: operaciones y pérdidas consecutivas      |
//+------------------------------------------------------------------+
#ifndef US100_RISK_MANAGER_MQH
#define US100_RISK_MANAGER_MQH

#include "Shared_FTMO_Risk.mqh"

struct SRiskConfig
  {
   string symbol;
   long   magic;
   double initialCapital;
   double riskPct;              // 0.35 %
   bool   useExceptional;       // permitir el riesgo excepcional (solo tras validación)
   double exceptionalPct;       // 0.50 %
   int    maxTradesDay;         // 3
   int    maxConsecLosses;      // 2
   int    maxSpreadPoints;
   bool   dynRisk;
   double dynBase;
   double dynDD1;
   double dynR1;
   double dynDD2;
   double dynR2;
   double dynDD3;
   double dynR3;
  };

class CRiskManager
  {
private:
   SRiskConfig m_cfg;
   CLogger    *m_log;
   double      m_tickSize, m_tickValue, m_volMin, m_volMax, m_volStep, m_contract;
   int         m_digits;

public:
                     CRiskManager() : m_log(NULL) {}

   bool Init(const SRiskConfig &cfg, CLogger *log)
     {
      m_cfg = cfg; m_log = log;
      if(!SymbolSelect(m_cfg.symbol, true)) { m_log.Error("Símbolo no disponible: " + m_cfg.symbol); return false; }
      return Refresh(true);
     }

   // Lee y valida las especificaciones del símbolo
   bool Refresh(const bool verbose)
     {
      m_tickSize  = SymbolInfoDouble(m_cfg.symbol, SYMBOL_TRADE_TICK_SIZE);
      m_tickValue = SymbolInfoDouble(m_cfg.symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
      if(m_tickValue <= 0) m_tickValue = SymbolInfoDouble(m_cfg.symbol, SYMBOL_TRADE_TICK_VALUE);
      m_volMin    = SymbolInfoDouble(m_cfg.symbol, SYMBOL_VOLUME_MIN);
      m_volMax    = SymbolInfoDouble(m_cfg.symbol, SYMBOL_VOLUME_MAX);
      m_volStep   = SymbolInfoDouble(m_cfg.symbol, SYMBOL_VOLUME_STEP);
      m_contract  = SymbolInfoDouble(m_cfg.symbol, SYMBOL_TRADE_CONTRACT_SIZE);
      m_digits    = (int)SymbolInfoInteger(m_cfg.symbol, SYMBOL_DIGITS);
      long mode   = SymbolInfoInteger(m_cfg.symbol, SYMBOL_TRADE_MODE);
      if(verbose)
         m_log.Info(StringFormat("Especificación %s · tick size %.5f · tick value %.5f %s · contrato %.2f · lote min %.2f max %.2f step %.2f · dígitos %d · modo %d",
                                 m_cfg.symbol, m_tickSize, m_tickValue, AccountInfoString(ACCOUNT_CURRENCY), m_contract,
                                 m_volMin, m_volMax, m_volStep, m_digits, (int)mode));
      if(m_tickSize <= 0 || m_tickValue <= 0 || m_volStep <= 0 || m_volMin <= 0)
        { m_log.Error("Especificación del símbolo incompleta: no se puede calcular el lote."); return false; }
      if(mode == SYMBOL_TRADE_MODE_DISABLED || mode == SYMBOL_TRADE_MODE_CLOSEONLY)
        { m_log.Error("El símbolo no permite abrir operaciones."); return false; }
      string up = m_cfg.symbol; StringToUpper(up);
      if(StringFind(up, "100") < 0 && StringFind(up, "NAS") < 0 && StringFind(up, "NDX") < 0 && StringFind(up, "USTEC") < 0 && StringFind(up, "NQ") < 0)
         m_log.Warn("El nombre del símbolo no parece el Nasdaq 100. Comprueba que el EA está en el instrumento correcto.");
      return true;
     }

   double RiskPct() const
     {
      if(!m_cfg.dynRisk) return m_cfg.useExceptional ? m_cfg.exceptionalPct : m_cfg.riskPct;
      if(m_cfg.initialCapital <= 0) return m_cfg.riskPct;
      double dd = MathMax(0.0, (m_cfg.initialCapital - AccountInfoDouble(ACCOUNT_EQUITY)) / m_cfg.initialCapital * 100.0);
      if(dd >= m_cfg.dynDD3) return m_cfg.dynR3;
      if(dd >= m_cfg.dynDD2) return m_cfg.dynR2;
      if(dd >= m_cfg.dynDD1) return m_cfg.dynR1;
      return m_cfg.dynBase;
     }
   double RiskMoney() const { return m_cfg.initialCapital * RiskPct() / 100.0; }

   double NormalizePrice(const double p) const
     {
      return NormalizeDouble(MathRound(p / m_tickSize) * m_tickSize, m_digits);
     }

   // Lote para perder 'RiskMoney' entre entry y sl. Devuelve 0 si no es posible.
   double LotsFor(const ENUM_ORDER_TYPE type, const double entry, const double sl, double &riskMoneyOut)
     {
      riskMoneyOut = 0;
      double dist = MathAbs(entry - sl);
      if(dist <= 0) return 0;
      // pérdida de 1 lote hasta el SL (OrderCalcProfit usa la conversión de divisa del broker)
      double lossPerLot = 0, p = 0;
      if(OrderCalcProfit(type, m_cfg.symbol, 1.0, entry, sl, p)) lossPerLot = MathAbs(p);
      if(lossPerLot <= 0) lossPerLot = dist / m_tickSize * m_tickValue;
      if(lossPerLot <= 0) return 0;
      double lots = MathFloor(RiskMoney() / lossPerLot / m_volStep) * m_volStep;
      lots = MathMin(lots, m_volMax);
      if(lots < m_volMin) { m_log.Warn(StringFormat("Lote %.3f por debajo del mínimo %.2f: se omite la operación.", lots, m_volMin)); return 0; }
      // margen
      double margin = 0;
      if(OrderCalcMargin(type, m_cfg.symbol, lots, entry, margin))
        {
         double free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
         if(margin > free * 0.9)
           {
            double scaled = MathFloor(lots * (free * 0.9 / margin) / m_volStep) * m_volStep;
            m_log.Warn(StringFormat("Margen insuficiente para %.2f lotes; se reduce a %.2f.", lots, scaled));
            lots = scaled;
            if(lots < m_volMin) return 0;
           }
        }
      int stepDigits = (int)MathMax(0, MathCeil(-MathLog10(m_volStep)));
      lots = NormalizeDouble(lots, stepDigits);
      riskMoneyOut = lots * lossPerLot;
      return lots;
     }

   bool SpreadOk() const
     {
      return SymbolInfoInteger(m_cfg.symbol, SYMBOL_SPREAD) <= m_cfg.maxSpreadPoints;
     }

   // Operaciones de hoy y pérdidas consecutivas (desde 'dayStart', solo este EA)
   void DayStats(const datetime dayStart, int &tradesOut, int &consecLossOut)
     {
      tradesOut = 0; consecLossOut = 0;
      if(!HistorySelect(dayStart, TimeCurrent() + 60)) return;
      int n = HistoryDealsTotal();
      for(int i = 0; i < n; i++)
        {
         ulong d = HistoryDealGetTicket(i);
         if(d == 0) continue;
         if(HistoryDealGetString(d, DEAL_SYMBOL) != m_cfg.symbol) continue;
         if(HistoryDealGetInteger(d, DEAL_MAGIC) != m_cfg.magic) continue;
         long entry = HistoryDealGetInteger(d, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_IN) tradesOut++;
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
           {
            double pnl = HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) + HistoryDealGetDouble(d, DEAL_COMMISSION);
            consecLossOut = pnl < 0 ? consecLossOut + 1 : 0;
           }
        }
     }

   bool DailyLimitsOk(const datetime dayStart, string &why)
     {
      int tr, cl; DayStats(dayStart, tr, cl);
      if(tr >= m_cfg.maxTradesDay) { why = StringFormat("Máximo de %d operaciones diarias", m_cfg.maxTradesDay); return false; }
      if(cl >= m_cfg.maxConsecLosses) { why = StringFormat("%d pérdidas consecutivas: sesión detenida", cl); return false; }
      return true;
     }
  };

#endif
