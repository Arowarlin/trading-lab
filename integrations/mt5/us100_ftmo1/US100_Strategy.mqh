//+------------------------------------------------------------------+
//|                                             US100_Strategy.mqh   |
//|  Reglas de entrada. Dos modos:                                   |
//|   1) CONFLUENCE (por defecto, validado con datos 2021-2026):     |
//|      score 0-100 (sweep, FVG, VWAP, estructura, RVOL, OR) +      |
//|      vetos + régimen diario + filtro de gap.                     |
//|   2) ORB_RETEST (especificación original): ruptura del OR de     |
//|      15 min con cierre M5, retest o continuación, H1, M15, VWAP, |
//|      volatilidad. Sin ventaja demostrada en la investigación;    |
//|      se incluye para comparar en el Strategy Tester.             |
//+------------------------------------------------------------------+
#ifndef US100_STRATEGY_MQH
#define US100_STRATEGY_MQH

#include "US100_MarketAnalysis.mqh"

enum ENUM_STRAT_MODE { STRAT_CONFLUENCE = 0, STRAT_ORB_RETEST = 1 };
enum ENUM_CONFIRM    { CONFIRM_RETEST = 0, CONFIRM_CONTINUATION = 1, CONFIRM_EITHER = 2 };
enum ENUM_SL_TYPE    { SLT_ATR = 0, SLT_STRUCTURE = 1 };

struct SStrategyConfig
  {
   ENUM_STRAT_MODE mode;
   bool   aggressive;           // confluencia: modo agresivo (validado)
   int    minScore;
   double wSweep, wFvg, wVwap, wStruct, wRvol, wOr;
   bool   allowLong, allowShort;
   // filtros
   bool   useRegime;            // régimen diario SMA
   bool   useGap;  double gapMin;
   bool   useH1;                // bloquear contra tendencia H1 fuerte
   bool   useM15;               // bloquear contra estructura M15
   bool   useVolRegime; double volLo, volHi;
   double abnormalVol;          // bloquear si ATR/mediana supera este valor (0 = desactivado)
   double vwapExtSd;
   // ORB
   ENUM_CONFIRM confirm; double retestTolAtr; int confirmBars; double failAtr;
   // stop
   ENUM_SL_TYPE slType; double slAtr; double slBufAtr; double slMinAtr; double slMaxAtr;
  };

struct SSignal
  {
   int    dir;        // 1 = LONG, -1 = SHORT, 0 = nada
   double sl;         // precio de stop calculado al cierre de la vela
   double score;
   string reason;
  };

struct SOrbState { int st; long b; double ext; double worst; };   // st: 0 libre, 1 roto, 2 usado

class CStrategy
  {
private:
   SStrategyConfig m_cfg;
   CLogger        *m_log;
   SOrbState       m_orb[2];      // [0] long, [1] short
   int             m_day;
   double          m_scoreL, m_scoreS;
   bool            m_vetoL, m_vetoS;
   string          m_lastBlock;

   void OrbReset() { for(int k = 0; k < 2; k++) { m_orb[k].st = 0; m_orb[k].b = 0; m_orb[k].ext = 0; m_orb[k].worst = 0; } }

   bool CommonFilters(const SMarket &s, const int dir, string &why)
     {
      if(dir == 1 && !m_cfg.allowLong)  { why = "LONG desactivado"; return false; }
      if(dir == -1 && !m_cfg.allowShort) { why = "SHORT desactivado"; return false; }
      if(m_cfg.useRegime && s.regime != dir) { why = "Contra el régimen diario"; return false; }
      if(m_cfg.useGap && s.gapRatio < m_cfg.gapMin) { why = StringFormat("Gap pequeño (%.2f < %.2f)", s.gapRatio, m_cfg.gapMin); return false; }
      if(m_cfg.useH1 && s.h1Trend == -dir) { why = "Contra tendencia H1 fuerte"; return false; }
      if(m_cfg.useM15 && s.m15Trend == -dir) { why = "Contra estructura M15"; return false; }
      if(m_cfg.useVolRegime && (s.volRatio < m_cfg.volLo || s.volRatio > m_cfg.volHi)) { why = StringFormat("Régimen de volatilidad fuera de rango (%.2f)", s.volRatio); return false; }
      if(m_cfg.abnormalVol > 0 && s.volRatio > m_cfg.abnormalVol) { why = StringFormat("Volatilidad anormal (%.2f)", s.volRatio); return false; }
      return true;
     }

   double StopFor(const SMarket &s, const int dir, const double structLevel)
     {
      double a = s.atr, c = s.c;
      double atrSl = c - dir * MathMax(m_cfg.slAtr * a, m_cfg.slMinAtr * a);
      if(m_cfg.slType == SLT_ATR || structLevel == MA_NA) return atrSl;
      double sl = structLevel - dir * m_cfg.slBufAtr * a;
      double dist = (c - sl) * dir;
      if(dist < m_cfg.slMinAtr * a) return c - dir * m_cfg.slMinAtr * a;
      if(dist > m_cfg.slMaxAtr * a) return atrSl;
      return sl;
     }

   bool EvalConfluence(const SMarket &s, SSignal &sig)
     {
      double ws = m_cfg.wSweep + m_cfg.wFvg + m_cfg.wVwap + m_cfg.wStruct + m_cfg.wRvol + m_cfg.wOr;
      if(ws <= 0) ws = 1;
      double nSw = m_cfg.wSweep * 100 / ws, nFv = m_cfg.wFvg * 100 / ws, nVw = m_cfg.wVwap * 100 / ws;
      double nSt = m_cfg.wStruct * 100 / ws, nRv = m_cfg.wRvol * 100 / ws, nOr = m_cfg.wOr * 100 / ws;
      double cSwL = (s.recBull && s.lastBullSw >= s.lastBearSw) ? 1 : 0;
      double cSwS = (s.recBear && s.lastBearSw >= s.lastBullSw) ? 1 : 0;
      double cFvL = (s.bullFvgNear && !s.inBearFvg) ? 1 : 0;
      double cFvS = (s.bearFvgNear && !s.inBullFvg) ? 1 : 0;
      double cVwL = s.aboveVwap ? (s.vwapDsd > m_cfg.vwapExtSd ? 0.5 : 1.0) : 0;
      double cVwS = s.belowVwap ? (-s.vwapDsd > m_cfg.vwapExtSd ? 0.5 : 1.0) : 0;
      double cStL = s.m5Trend == 1 ? 1 : 0, cStS = s.m5Trend == -1 ? 1 : 0;
      double cRv  = s.rvolOk ? 1.0 : (s.rvol >= 1.0 ? 0.5 : 0.0);
      double cOrL = 0, cOrS = 0;
      if(s.orDone)
        {
         cOrL = s.c > s.orH ? 1.0 : (s.c > s.orMid ? 0.5 : 0.0);
         cOrS = s.c < s.orL ? 1.0 : (s.c < s.orMid ? 0.5 : 0.0);
        }
      m_scoreL = nSw * cSwL + nFv * cFvL + nVw * cVwL + nSt * cStL + nRv * cRv + nOr * cOrL;
      m_scoreS = nSw * cSwS + nFv * cFvS + nVw * cVwS + nSt * cStS + nRv * cRv + nOr * cOrS;
      m_vetoL = cSwS == 1 || (s.m5Trend == -1 && s.belowVwap) || s.inBearFvg || s.rvolLow;
      m_vetoS = cSwL == 1 || (s.m5Trend == 1 && s.aboveVwap) || s.inBullFvg || s.rvolLow;

      bool mL, mS;
      if(m_cfg.aggressive)
        {
         mL = (cSwL == 1 || (s.brokeUp && s.c > s.orH)) && cVwL > 0;
         mS = (cSwS == 1 || (s.brokeDn && s.c < s.orL)) && cVwS > 0;
        }
      else
        {
         mL = cSwL == 1 && cVwL > 0 && cStL == 1;
         mS = cSwS == 1 && cVwS > 0 && cStS == 1;
        }
      int dir = 0;
      if(s.orDone && !m_vetoL && m_scoreL >= m_cfg.minScore && mL) dir = 1;
      else if(s.orDone && !m_vetoS && m_scoreS >= m_cfg.minScore && mS) dir = -1;
      if(dir == 0) return false;
      string why;
      if(!CommonFilters(s, dir, why)) { m_lastBlock = why; return false; }
      double structLvl = dir == 1 ? ((s.recBull && s.lastBullLow != MA_NA) ? s.lastBullLow : s.lastPL)
                                  : ((s.recBear && s.lastBearHigh != MA_NA) ? s.lastBearHigh : s.lastPH);
      sig.dir = dir; sig.sl = StopFor(s, dir, structLvl); sig.score = dir == 1 ? m_scoreL : m_scoreS;
      sig.reason = StringFormat("Confluencia %s score %.0f", dir == 1 ? "LONG" : "SHORT", sig.score);
      return true;
     }

   bool EvalOrb(const SMarket &s, SSignal &sig)
     {
      if(!s.orDone) return false;
      int found = 0; double worst = 0;
      for(int k = 0; k < 2; k++)
        {
         int d = k == 0 ? 1 : -1;
         double lvl = d == 1 ? s.orH : s.orL;
         if(m_orb[k].st == 0)
           {
            if((s.c - lvl) * d > 0) { m_orb[k].st = 1; m_orb[k].b = s.bar; m_orb[k].ext = d == 1 ? s.h : s.l; m_orb[k].worst = d == 1 ? s.l : s.h; }
            continue;
           }
         if(m_orb[k].st == 2) { if((lvl - s.c) * d > 0) m_orb[k].st = 0; continue; }
         if((lvl - s.c) * d > m_cfg.failAtr * s.atr) { m_orb[k].st = 0; continue; }   // falsa ruptura
         if(s.bar - m_orb[k].b > m_cfg.confirmBars) { m_orb[k].st = 2; continue; }
         m_orb[k].worst = d == 1 ? MathMin(m_orb[k].worst, s.l) : MathMax(m_orb[k].worst, s.h);
         bool retest = d == 1 ? (s.l <= lvl + m_cfg.retestTolAtr * s.atr && s.c > lvl && s.c > s.o)
                              : (s.h >= lvl - m_cfg.retestTolAtr * s.atr && s.c < lvl && s.c < s.o);
         bool cont = d == 1 ? s.c > m_orb[k].ext : s.c < m_orb[k].ext;
         bool ok = m_cfg.confirm == CONFIRM_RETEST ? retest : (m_cfg.confirm == CONFIRM_CONTINUATION ? cont : (retest || cont));
         if(ok && found == 0) { found = d; worst = m_orb[k].worst; m_orb[k].st = 2; }
         else m_orb[k].ext = d == 1 ? MathMax(m_orb[k].ext, s.h) : MathMin(m_orb[k].ext, s.l);
        }
      if(found == 0) return false;
      string why;
      if(!CommonFilters(s, found, why)) { m_lastBlock = why; return false; }
      if(found == 1 && !s.aboveVwap)  { m_lastBlock = "Precio bajo VWAP"; return false; }
      if(found == -1 && !s.belowVwap) { m_lastBlock = "Precio sobre VWAP"; return false; }
      double lvl = found == 1 ? s.orH : s.orL;
      double structLvl = found == 1 ? MathMin(worst, lvl) : MathMax(worst, lvl);
      double sl = structLvl - found * m_cfg.slBufAtr * s.atr;
      double dist = (s.c - sl) * found;
      if(dist > m_cfg.slMaxAtr * s.atr) { m_lastBlock = "Stop estructural demasiado lejano"; return false; }
      if(dist < m_cfg.slMinAtr * s.atr) sl = s.c - found * m_cfg.slMinAtr * s.atr;
      sig.dir = found; sig.sl = sl; sig.score = 0;
      sig.reason = StringFormat("ORB %s confirmada", found == 1 ? "LONG" : "SHORT");
      return true;
     }

public:
                     CStrategy() : m_log(NULL), m_day(0), m_scoreL(0), m_scoreS(0), m_vetoL(false), m_vetoS(false), m_lastBlock("") {}

   void Init(const SStrategyConfig &cfg, CLogger *log) { m_cfg = cfg; m_log = log; OrbReset(); }

   // Se llama en cada vela M5 cerrada (también durante el calentamiento)
   bool OnBar(const SMarket &s, SSignal &sig)
     {
      sig.dir = 0; sig.sl = 0; sig.score = 0; sig.reason = "";
      if(!s.valid) return false;
      if(s.nyDay != m_day) { m_day = s.nyDay; OrbReset(); }
      if(m_cfg.mode == STRAT_ORB_RETEST) return EvalOrb(s, sig);
      return EvalConfluence(s, sig);
     }

   double ScoreLong()  const { return m_scoreL; }
   double ScoreShort() const { return m_scoreS; }
   bool   VetoLong()   const { return m_vetoL; }
   bool   VetoShort()  const { return m_vetoS; }
   string LastBlock()  const { return m_lastBlock; }
  };

#endif
