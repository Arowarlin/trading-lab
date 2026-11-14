//+------------------------------------------------------------------+
//|                                        US100_MarketAnalysis.mqh  |
//|  Motor de análisis por vela M5 cerrada (sin repintado):          |
//|   · Sesiones en hora de Nueva York (DST vía CTimeUtil)           |
//|   · Opening Range, niveles PDH/PDL, Overnight, Premarket         |
//|   · Liquidity sweeps, FVG M5 + M15, VWAP de sesión, RVOL         |
//|   · Estructura M5 y M15 (pivotes confirmados), tendencia H1      |
//|   · Régimen diario (SMA de cierres RTH), gap de apertura,        |
//|     régimen de volatilidad (ATR), noticias de alto impacto       |
//+------------------------------------------------------------------+
#ifndef US100_MARKET_ANALYSIS_MQH
#define US100_MARKET_ANALYSIS_MQH

#include "Shared_FTMO_Risk.mqh"

#define MA_NA EMPTY_VALUE

struct SMarketConfig
  {
   string          symbol;
   int             orMinutes;        // 15 = 9:30-9:45
   int             tradeStartHHMM;   // inicio de entradas (NY)
   int             tradeEndHHMM;     // fin de entradas (NY)
   int             flatHHMM;         // cierre forzoso (NY)
   int             atrLen;
   int             rvolLen;
   double          rvolThr, rvolLow;
   int             sweepCool, sweepWindow, fbWindow;
   bool            usePD, useON, usePM, useOR;
   double          fvgMinAtr, fvgProxAtr;
   int             fvgExt, fvgMax;
   ENUM_TIMEFRAMES fvgHtf;
   int             pivL, pivR;
   int             m15Piv;
   int             h1EmaLen, h1SlopeBars;
   int             regLen;
   int             gapLen;
   int             volLen;
  };

struct SMarket
  {
   bool     valid;
   long     bar;            // contador interno de velas
   datetime time;           // apertura de la vela (servidor)
   int      nyMin, nyDay;
   double   o, h, l, c, atr, rvol;
   bool     rvolOk, rvolLow;
   bool     inRTH, inOR, inTrade, inFlat;
   // opening range
   bool     orDone, brokeUp, brokeDn;
   double   orH, orL, orMid;
   // niveles
   double   pdh, pdl, onh, onl, pmh, pml;
   // sweeps
   bool     bullSweep, bearSweep, recBull, recBear;
   long     lastBullSw, lastBearSw;
   double   lastBullLow, lastBearHigh;
   string   lastSweepTxt;
   // fvg
   bool     bullFvgNear, bearFvgNear, inBullFvg, inBearFvg;
   int      fvgCount;
   // vwap
   double   vwap, vwapDsd;
   bool     aboveVwap, belowVwap;
   // estructura
   int      m5Trend, m15Trend, h1Trend;
   double   lastPH, lastPL;
   // régimen
   int      regime;          // +1 alcista, -1 bajista, 0 desconocido
   double   gapRatio;        // gap de hoy / mediana de gaps
   double   volRatio;        // ATR actual / mediana del ATR al final del OR
  };

struct SFvg { long idx; bool bull; double top, bot; };
struct SSess { double ch, cl, ph, pl; bool prevIn; };

class CMarketAnalysis
  {
private:
   SMarketConfig m_cfg;
   CLogger      *m_log;
   SMarket       m_s;
   // estado
   double   m_atr, m_trSum; int m_trN;
   double   m_vbuf[]; int m_vpos, m_vcnt; double m_vsum;
   SSess    m_rth, m_on, m_pm;
   bool     m_prevInOR; long m_brkUp, m_brkDn;
   double   m_lvHist[8][3]; long m_swLast[8];
   SFvg     m_fvgs[]; datetime m_prevHtf;
   double   m_cPV, m_cV, m_cP2V; bool m_prevInV;
   bool     m_phB, m_plB;
   double   m_dcl[]; double m_gaps[]; double m_orAtr[];
   int      m_prevDay;
   // M15
   datetime m_lastM15; double m_m15PH, m_m15PL; bool m_m15PhB, m_m15PlB; int m_m15Trend;
   // H1
   int      m_hEma;
   // noticias
   datetime m_newsT; bool m_newsV;

   static int HM(const int hhmm) { return (hhmm / 100) * 60 + hhmm % 100; }
   static bool InS(const int m, const int a, const int b) { return a < b ? (m >= a && m < b) : (m >= a || m < b); }
   double Hi(const int sh) const { return iHigh(m_cfg.symbol, PERIOD_M5, sh); }
   double Lo(const int sh) const { return iLow(m_cfg.symbol, PERIOD_M5, sh); }
   double Cl(const int sh) const { return iClose(m_cfg.symbol, PERIOD_M5, sh); }
   double Op(const int sh) const { return iOpen(m_cfg.symbol, PERIOD_M5, sh); }

   void SessReset(SSess &s) { s.ch = MA_NA; s.cl = MA_NA; s.ph = MA_NA; s.pl = MA_NA; s.prevIn = false; }
   void SessUpd(SSess &s, const bool ins, const double h, const double l)
     {
      if(ins && !s.prevIn) { s.ch = h; s.cl = l; }
      else if(ins)         { s.ch = (s.ch == MA_NA) ? h : MathMax(s.ch, h); s.cl = (s.cl == MA_NA) ? l : MathMin(s.cl, l); }
      if(!ins && s.prevIn) { s.ph = s.ch; s.pl = s.cl; }
      s.prevIn = ins;
     }
   void Push(double &arr[], const double v, const int keep)
     {
      int n = ArraySize(arr); ArrayResize(arr, n + 1, 64); arr[n] = v;
      if(ArraySize(arr) > keep) ArrayRemove(arr, 0, ArraySize(arr) - keep);
     }
   double MedianLast(const double &arr[], const int len) const
     {
      int n = ArraySize(arr); if(n == 0) return 0;
      int k = MathMin(len, n);
      double tmp[]; ArrayResize(tmp, k);
      for(int i = 0; i < k; i++) tmp[i] = arr[n - k + i];
      ArraySort(tmp);
      return (k % 2 == 1) ? tmp[k / 2] : (tmp[k / 2 - 1] + tmp[k / 2]) / 2.0;
     }
   void AddFvg(const long idx, const bool bull, const double top, const double bot)
     {
      int n = ArraySize(m_fvgs); ArrayResize(m_fvgs, n + 1, 32);
      m_fvgs[n].idx = idx; m_fvgs[n].bull = bull; m_fvgs[n].top = top; m_fvgs[n].bot = bot;
     }
   void RemoveFvg(const int k)
     {
      int n = ArraySize(m_fvgs);
      for(int j = k; j < n - 1; j++) m_fvgs[j] = m_fvgs[j + 1];
      ArrayResize(m_fvgs, n - 1, 32);
     }

   // Estructura M15 con velas cerradas (pivotes con m15Piv a cada lado)
   void UpdateM15(const datetime m5Time)
     {
      int cur = iBarShift(m_cfg.symbol, PERIOD_M15, m5Time, false);
      if(cur < 0) return;
      int sh = cur + 1;                                  // última M15 cerrada
      datetime t = iTime(m_cfg.symbol, PERIOD_M15, sh);
      if(t == 0 || t == m_lastM15) return;
      // procesar todas las M15 cerradas pendientes (máx. 200 en el primer paso)
      int from = sh;
      if(m_lastM15 != 0)
        {
         int last = iBarShift(m_cfg.symbol, PERIOD_M15, m_lastM15, false);
         if(last > sh) from = last - 1; else from = sh;
        }
      else from = MathMin(sh + 200, Bars(m_cfg.symbol, PERIOD_M15) - 2 * m_cfg.m15Piv - 2);
      int P = m_cfg.m15Piv;
      for(int j = from; j >= sh; j--)
        {
         int c = j + P;
         double ch = iHigh(m_cfg.symbol, PERIOD_M15, c), cl = iLow(m_cfg.symbol, PERIOD_M15, c);
         bool isH = ch > 0, isL = cl > 0;
         for(int k = 1; k <= P; k++)
           {
            if(ch <= iHigh(m_cfg.symbol, PERIOD_M15, c + k)) isH = false;
            if(cl >= iLow(m_cfg.symbol, PERIOD_M15, c + k))  isL = false;
            if(ch <  iHigh(m_cfg.symbol, PERIOD_M15, c - k)) isH = false;
            if(cl >  iLow(m_cfg.symbol, PERIOD_M15, c - k))  isL = false;
           }
         if(isH) { m_m15PH = ch; m_m15PhB = false; }
         if(isL) { m_m15PL = cl; m_m15PlB = false; }
         double cc = iClose(m_cfg.symbol, PERIOD_M15, j);
         if(m_m15PH != MA_NA && !m_m15PhB && cc > m_m15PH) { m_m15PhB = true; m_m15Trend = 1; }
         if(m_m15PL != MA_NA && !m_m15PlB && cc < m_m15PL) { m_m15PlB = true; m_m15Trend = -1; }
        }
      m_lastM15 = t;
     }

   // Tendencia H1: +1 alcista fuerte, -1 bajista fuerte, 0 neutral (solo velas H1 cerradas)
   int H1Trend(const datetime m5Time)
     {
      if(m_hEma == INVALID_HANDLE) return 0;
      int sh = iBarShift(m_cfg.symbol, PERIOD_H1, m5Time, false);
      if(sh < 0) return 0;
      sh += 1;
      double e[];
      if(CopyBuffer(m_hEma, 0, sh, m_cfg.h1SlopeBars + 1, e) != m_cfg.h1SlopeBars + 1) return 0;
      // e[] en orden cronológico: e[0] = más antigua, e[last] = vela cerrada más reciente
      double emaNow = e[m_cfg.h1SlopeBars], emaOld = e[0];
      double c = iClose(m_cfg.symbol, PERIOD_H1, sh);
      if(c > emaNow && emaNow > emaOld) return 1;
      if(c < emaNow && emaNow < emaOld) return -1;
      return 0;
     }

   void ResetSnapshot()
     {
      m_s.valid = false; m_s.bar = 0; m_s.time = 0; m_s.nyMin = 0; m_s.nyDay = 0;
      m_s.o = 0; m_s.h = 0; m_s.l = 0; m_s.c = 0; m_s.atr = 0; m_s.rvol = 0;
      m_s.rvolOk = false; m_s.rvolLow = false;
      m_s.inRTH = false; m_s.inOR = false; m_s.inTrade = false; m_s.inFlat = false;
      m_s.orDone = false; m_s.brokeUp = false; m_s.brokeDn = false; m_s.orMid = MA_NA;
      m_s.pdh = MA_NA; m_s.pdl = MA_NA; m_s.onh = MA_NA; m_s.onl = MA_NA; m_s.pmh = MA_NA; m_s.pml = MA_NA;
      m_s.bullSweep = false; m_s.bearSweep = false; m_s.recBull = false; m_s.recBear = false;
      m_s.bullFvgNear = false; m_s.bearFvgNear = false; m_s.inBullFvg = false; m_s.inBearFvg = false; m_s.fvgCount = 0;
      m_s.vwapDsd = 0; m_s.aboveVwap = false; m_s.belowVwap = false;
      m_s.m5Trend = 0; m_s.m15Trend = 0; m_s.h1Trend = 0; m_s.regime = 0;
     }

public:
                     CMarketAnalysis() : m_log(NULL), m_hEma(INVALID_HANDLE) {}
                    ~CMarketAnalysis() { if(m_hEma != INVALID_HANDLE) IndicatorRelease(m_hEma); }

   bool Init(const SMarketConfig &cfg, CLogger *log)
     {
      m_cfg = cfg; m_log = log;
      m_atr = MA_NA; m_trSum = 0; m_trN = 0;
      ArrayResize(m_vbuf, MathMax(1, m_cfg.rvolLen)); m_vpos = 0; m_vcnt = 0; m_vsum = 0;
      SessReset(m_rth); SessReset(m_on); SessReset(m_pm);
      m_prevInOR = false; m_brkUp = -1; m_brkDn = -1;
      for(int k = 0; k < 8; k++) { m_lvHist[k][0] = MA_NA; m_lvHist[k][1] = MA_NA; m_lvHist[k][2] = MA_NA; m_swLast[k] = -1000000; }
      ArrayResize(m_fvgs, 0); m_prevHtf = 0;
      m_cPV = 0; m_cV = 0; m_cP2V = 0; m_prevInV = false;
      m_phB = false; m_plB = false;
      ArrayResize(m_dcl, 0); ArrayResize(m_gaps, 0); ArrayResize(m_orAtr, 0);
      m_prevDay = 0;
      m_lastM15 = 0; m_m15PH = MA_NA; m_m15PL = MA_NA; m_m15PhB = false; m_m15PlB = false; m_m15Trend = 0;
      m_newsT = 0; m_newsV = false;
      ResetSnapshot();
      m_s.orH = MA_NA; m_s.orL = MA_NA; m_s.lastPH = MA_NA; m_s.lastPL = MA_NA;
      m_s.lastBullSw = -1000000; m_s.lastBearSw = -1000000; m_s.lastBullLow = MA_NA; m_s.lastBearHigh = MA_NA;
      m_s.lastSweepTxt = "—"; m_s.vwap = MA_NA; m_s.gapRatio = 1.0; m_s.volRatio = 1.0;
      m_hEma = iMA(m_cfg.symbol, PERIOD_H1, m_cfg.h1EmaLen, 0, MODE_EMA, PRICE_CLOSE);
      if(m_hEma == INVALID_HANDLE) m_log.Warn("No se pudo crear la EMA H1: el filtro H1 queda neutral.");
      return true;
     }

   void Get(SMarket &out) const { out = m_s; }

   // Procesa la vela M5 cerrada 'sh' (sh ≥ 1)
   void ProcessBar(const int sh)
     {
      m_s.bar++;
      long i = m_s.bar;
      datetime bt = iTime(m_cfg.symbol, PERIOD_M5, sh);
      datetime ny = CTimeUtil::ServerToNY(bt);
      int m = CTimeUtil::MinutesOfDay(ny);
      int day = CTimeUtil::DateKey(ny);
      double o = Op(sh), h = Hi(sh), l = Lo(sh), c = Cl(sh);
      double v = (double)iTickVolume(m_cfg.symbol, PERIOD_M5, sh);
      m_s.time = bt; m_s.nyMin = m; m_s.nyDay = day; m_s.o = o; m_s.h = h; m_s.l = l; m_s.c = c;
      m_s.bullSweep = false; m_s.bearSweep = false;

      // ATR (Wilder)
      double pc = Cl(sh + 1);
      double tr = MathMax(h - l, MathMax(MathAbs(h - pc), MathAbs(l - pc)));
      if(m_atr == MA_NA) { m_trSum += tr; m_trN++; if(m_trN >= m_cfg.atrLen) m_atr = m_trSum / m_trN; }
      else m_atr = (m_atr * (m_cfg.atrLen - 1) + tr) / m_cfg.atrLen;
      m_s.atr = m_atr;

      // RVOL con tick volume
      if(m_vcnt < m_cfg.rvolLen) { m_vbuf[m_vcnt] = v; m_vsum += v; m_vcnt++; }
      else { m_vsum += v - m_vbuf[m_vpos]; m_vbuf[m_vpos] = v; m_vpos = (m_vpos + 1) % m_cfg.rvolLen; }
      double vs = m_vcnt > 0 ? m_vsum / m_vcnt : 0;
      m_s.rvol = vs > 0 ? v / vs : 0;
      m_s.rvolOk = m_s.rvol >= m_cfg.rvolThr; m_s.rvolLow = m_s.rvol < m_cfg.rvolLow;

      // Sesiones NY
      int orEnd = 570 + m_cfg.orMinutes;
      bool inRTH = InS(m, 570, 960), inON = InS(m, 1080, 570), inPM = InS(m, 480, 570);
      bool inOR  = InS(m, 570, orEnd);
      m_s.inRTH = inRTH; m_s.inOR = inOR;
      m_s.inTrade = InS(m, HM(m_cfg.tradeStartHHMM), HM(m_cfg.tradeEndHHMM));
      m_s.inFlat  = InS(m, HM(m_cfg.flatHHMM), 1080);

      // Régimen diario y gap de apertura
      if(!inRTH && m_rth.prevIn)
        {
         Push(m_dcl, Cl(sh + 1), m_cfg.regLen + 5);
         int n = ArraySize(m_dcl);
         if(n >= m_cfg.regLen)
           {
            double sma = 0;
            for(int k = n - m_cfg.regLen; k < n; k++) sma += m_dcl[k];
            sma /= m_cfg.regLen;
            m_s.regime = m_dcl[n - 1] > sma ? 1 : (m_dcl[n - 1] < sma ? -1 : 0);
           }
        }
      if(inRTH && !m_rth.prevIn && ArraySize(m_dcl) > 0)
        {
         double g = MathAbs(o - m_dcl[ArraySize(m_dcl) - 1]);
         double med = ArraySize(m_gaps) >= 5 ? MedianLast(m_gaps, m_cfg.gapLen) : 0;
         m_s.gapRatio = med > 0 ? g / med : 1.0;
         Push(m_gaps, g, m_cfg.gapLen + 5);
        }
      SessUpd(m_rth, inRTH, h, l);
      SessUpd(m_on, inON, h, l);
      SessUpd(m_pm, inPM, h, l);
      m_s.pdh = m_rth.ph; m_s.pdl = m_rth.pl; m_s.onh = m_on.ph; m_s.onl = m_on.pl; m_s.pmh = m_pm.ph; m_s.pml = m_pm.pl;

      // Opening Range
      if(inOR && !m_prevInOR)
        { m_s.orH = h; m_s.orL = l; m_s.orDone = false; m_s.brokeUp = false; m_s.brokeDn = false; m_brkUp = -1; m_brkDn = -1; }
      else if(inOR)
        { m_s.orH = MathMax(m_s.orH, h); m_s.orL = MathMin(m_s.orL, l); }
      if(!inOR && m_prevInOR && m_s.orH != MA_NA)
        {
         m_s.orDone = true;
         if(m_atr != MA_NA)
           {
            double med = ArraySize(m_orAtr) >= 5 ? MedianLast(m_orAtr, m_cfg.volLen) : 0;
            m_s.volRatio = med > 0 ? m_atr / med : 1.0;
            Push(m_orAtr, m_atr, m_cfg.volLen + 5);
           }
        }
      m_prevInOR = inOR;
      m_s.orMid = (m_s.orH != MA_NA && m_s.orL != MA_NA) ? (m_s.orH + m_s.orL) / 2.0 : MA_NA;
      if(m_s.orDone && !m_s.brokeUp && c > m_s.orH) { m_s.brokeUp = true; m_brkUp = i; }
      if(m_s.orDone && !m_s.brokeDn && c < m_s.orL) { m_s.brokeDn = true; m_brkDn = i; }
      if(m_s.brokeUp && m_brkUp >= 0 && i - m_brkUp > 0 && i - m_brkUp <= m_cfg.fbWindow && c < m_s.orH) m_s.brokeUp = false;
      if(m_s.brokeDn && m_brkDn >= 0 && i - m_brkDn > 0 && i - m_brkDn <= m_cfg.fbWindow && c > m_s.orL) m_s.brokeDn = false;

      // Liquidity sweeps: 0..3 máximos (PDH, ONH, PMH, ORH) · 4..7 mínimos
      double lv[8]; bool use[8];
      lv[0] = m_rth.ph; lv[1] = m_on.ph; lv[2] = m_pm.ph; lv[3] = m_s.orDone ? m_s.orH : MA_NA;
      lv[4] = m_rth.pl; lv[5] = m_on.pl; lv[6] = m_pm.pl; lv[7] = m_s.orDone ? m_s.orL : MA_NA;
      use[0] = m_cfg.usePD; use[1] = m_cfg.useON; use[2] = m_cfg.usePM; use[3] = m_cfg.useOR;
      use[4] = m_cfg.usePD; use[5] = m_cfg.useON; use[6] = m_cfg.usePM; use[7] = m_cfg.useOR;
      string names[8] = {"PDH", "ONH", "PMH", "ORH", "PDL", "ONL", "PML", "ORL"};
      double c1 = Cl(sh + 1), c2 = Cl(sh + 2);
      string bn = "", sn = "";
      for(int k = 0; k < 8; k++)
        {
         m_lvHist[k][0] = m_lvHist[k][1]; m_lvHist[k][1] = m_lvHist[k][2]; m_lvHist[k][2] = lv[k];
         if(!use[k] || lv[k] == MA_NA || m_lvHist[k][0] != lv[k]) continue;
         bool raw;
         if(k < 4) raw = c < lv[k] && (h > lv[k] || (c1 > lv[k] && c2 <= lv[k]));
         else      raw = c > lv[k] && (l < lv[k] || (c1 < lv[k] && c2 >= lv[k]));
         if(raw && i - m_swLast[k] > m_cfg.sweepCool)
           {
            m_swLast[k] = i;
            if(k < 4) { m_s.bearSweep = true; if(sn == "") sn = names[k]; }
            else      { m_s.bullSweep = true; if(bn == "") bn = names[k]; }
           }
        }
      if(m_s.bullSweep) { m_s.lastBullSw = i; m_s.lastBullLow = MathMin(l, Lo(sh + 1)); m_s.lastSweepTxt = "Alcista " + bn; }
      if(m_s.bearSweep) { m_s.lastBearSw = i; m_s.lastBearHigh = MathMax(h, Hi(sh + 1)); m_s.lastSweepTxt = "Bajista " + sn; }
      m_s.recBull = i - m_s.lastBullSw <= m_cfg.sweepWindow;
      m_s.recBear = i - m_s.lastBearSw <= m_cfg.sweepWindow;

      if(m_atr == MA_NA) { m_s.valid = false; return; }

      // FVG M5
      double gu = l - Hi(sh + 2), gd = Lo(sh + 2) - h;
      if(gu > 0 && gu >= m_cfg.fvgMinAtr * m_atr) AddFvg(i, true, l, Hi(sh + 2));
      if(gd > 0 && gd >= m_cfg.fvgMinAtr * m_atr) AddFvg(i, false, Lo(sh + 2), h);
      // FVG de temporalidad superior (solo velas cerradas)
      if(PeriodSeconds(m_cfg.fvgHtf) > PeriodSeconds(PERIOD_M5))
        {
         int hs = iBarShift(m_cfg.symbol, m_cfg.fvgHtf, bt, false);
         if(hs >= 0)
           {
            datetime ht = iTime(m_cfg.symbol, m_cfg.fvgHtf, hs);
            if(ht != m_prevHtf && m_prevHtf != 0)
              {
               double hH1 = iHigh(m_cfg.symbol, m_cfg.fvgHtf, hs + 1), hL1 = iLow(m_cfg.symbol, m_cfg.fvgHtf, hs + 1);
               double hH3 = iHigh(m_cfg.symbol, m_cfg.fvgHtf, hs + 3), hL3 = iLow(m_cfg.symbol, m_cfg.fvgHtf, hs + 3);
               if(hH1 > 0 && hH3 > 0)
                 {
                  double hgu = hL1 - hH3, hgd = hL3 - hH1;
                  if(hgu > 0 && hgu >= m_cfg.fvgMinAtr * m_atr) AddFvg(i, true, hL1, hH3);
                  if(hgd > 0 && hgd >= m_cfg.fvgMinAtr * m_atr) AddFvg(i, false, hL3, hH1);
                 }
              }
            m_prevHtf = ht;
           }
        }
      while(ArraySize(m_fvgs) > m_cfg.fvgMax) RemoveFvg(0);
      m_s.bullFvgNear = false; m_s.bearFvgNear = false; m_s.inBullFvg = false; m_s.inBearFvg = false;
      for(int k = ArraySize(m_fvgs) - 1; k >= 0; k--)
        {
         bool filled = m_fvgs[k].bull ? (l <= m_fvgs[k].bot) : (h >= m_fvgs[k].top);
         if(filled || i - m_fvgs[k].idx > m_cfg.fvgExt) { RemoveFvg(k); continue; }
         if(m_fvgs[k].bull)
           {
            if(c >= m_fvgs[k].bot && c - m_fvgs[k].top <= m_cfg.fvgProxAtr * m_atr) m_s.bullFvgNear = true;
            if(c >= m_fvgs[k].bot && c <= m_fvgs[k].top) m_s.inBullFvg = true;
           }
         else
           {
            if(c <= m_fvgs[k].top && m_fvgs[k].bot - c <= m_cfg.fvgProxAtr * m_atr) m_s.bearFvgNear = true;
            if(c >= m_fvgs[k].bot && c <= m_fvgs[k].top) m_s.inBearFvg = true;
           }
        }
      m_s.fvgCount = ArraySize(m_fvgs);

      // VWAP de sesión 09:30-16:00 NY (tick volume)
      if(inRTH && !m_prevInV) { m_cPV = 0; m_cV = 0; m_cP2V = 0; }
      if(inRTH)
        {
         double src = (h + l + c) / 3.0;
         m_cPV += src * v; m_cV += v; m_cP2V += src * src * v;
        }
      m_prevInV = inRTH;
      m_s.aboveVwap = false; m_s.belowVwap = false; m_s.vwapDsd = 0; m_s.vwap = MA_NA;
      if(m_cV > 0)
        {
         m_s.vwap = m_cPV / m_cV;
         double sd = MathSqrt(MathMax(m_cP2V / m_cV - m_s.vwap * m_s.vwap, 0.0));
         m_s.vwapDsd = sd > 0 ? (c - m_s.vwap) / sd : 0;
         m_s.aboveVwap = c > m_s.vwap; m_s.belowVwap = c < m_s.vwap;
        }

      // Estructura M5 (pivotes confirmados con pivR velas de retraso)
      int cs = sh + m_cfg.pivR;
      double ph = Hi(cs), pl = Lo(cs);
      bool isPH = true, isPL = true;
      for(int k = 1; k <= m_cfg.pivL; k++) { if(ph <= Hi(cs + k)) isPH = false; if(pl >= Lo(cs + k)) isPL = false; }
      for(int k = 1; k <= m_cfg.pivR; k++) { if(ph <  Hi(cs - k)) isPH = false; if(pl >  Lo(cs - k)) isPL = false; }
      if(isPH) { m_s.lastPH = ph; m_phB = false; }
      if(isPL) { m_s.lastPL = pl; m_plB = false; }
      if(m_s.lastPH != MA_NA && !m_phB && c > m_s.lastPH) { m_phB = true; m_s.m5Trend = 1; }
      if(m_s.lastPL != MA_NA && !m_plB && c < m_s.lastPL) { m_plB = true; m_s.m5Trend = -1; }

      // M15 y H1 solo cuando hacen falta (ventana de entradas) para ahorrar CPU
      if(m_s.inTrade || m_s.inOR)
        {
         UpdateM15(bt);
         m_s.m15Trend = m_m15Trend;
         m_s.h1Trend = H1Trend(bt);
        }
      m_s.valid = true;
     }

   // Noticias USD de alto impacto (solo cuenta real/demo; el Tester no tiene calendario)
   bool NewsBlocked(const bool enabled, const int beforeMin, const int afterMin)
     {
      if(!enabled || MQLInfoInteger(MQL_TESTER)) return false;
      datetime now = TimeTradeServer();
      if(m_newsT != 0 && now - m_newsT < 60) return m_newsV;
      m_newsT = now; m_newsV = false;
      MqlCalendarValue vals[];
      if(!CalendarValueHistory(vals, now - afterMin * 60, now + beforeMin * 60, "US", "USD")) return false;
      for(int k = 0; k < ArraySize(vals); k++)
        {
         MqlCalendarEvent ev;
         if(CalendarEventById(vals[k].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
           { m_newsV = true; break; }
        }
      return m_newsV;
     }

   int NyMinutesNow() const { return CTimeUtil::MinutesOfDay(CTimeUtil::ServerToNY(TimeTradeServer())); }
  };

#endif
