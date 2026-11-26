//+------------------------------------------------------------------+
//| TradingLab 2.0 - Discovery Lab - EA exportado (determinista)     |
//| Genoma (sha256): d7ec70df127d080832ffa5224af94c2cd000d0ba3e2934c498d49402ada0e56f
//| Plantilla: ninguna - version n/a
//| Exportador: 1.1.0
//| Simbolo: US100 - TF: M5 - Cuenta: CFD-001 - Firma: ftmo
//| Magic: 122596831 - Riesgo: 0.5% - Perdida diaria: 5000 - Total: 10000
//| Sizing DSL: 1R (evaluacion); el EA usa el riesgo del perfil.     |
//| Sesion: 09:35-15:45 NY - flat 15:55 - dias (1=lun): 1,2,3,4,5
//| BOS/CHOCH: pivote mas reciente dentro de InpPivotScanBars.       |
//| Hora de barras: InpServerUtcOffsetMinutes = minutos del servidor  |
//| por delante de UTC (0 = barras UTC; GMT+2 -> 120; GMT+3 -> 180). |
//| Costes y fills intrabar: los aplica el broker, no el EA.          |
//| Sin fechas ni rutas: la misma entrada produce los mismos bytes.   |
//+------------------------------------------------------------------+

#include <Trade\Trade.mqh>

CTrade trade;

input double InpRiskPerTradePct = 0.5;
input double InpDailyLossLimit = 5000;
input double InpMaxLossLimit = 10000;
input long   InpMagic = 122596831;
input int    InpServerUtcOffsetMinutes = 0;
input int    InpSlippagePoints = 20;
input int    InpPivotScanBars = 5000;
input bool   InpEmitTrace = true;
input string InpTraceFile = "US100_M5_CFD-001_trace.csv";

const int SESSION_START = 575;
const int SESSION_END = 945;
const int FLAT_AT = 955;
const int FLAT_MODE = 0;
const int MANAGE_END = 955;
const int OR_MINUTES = 15;
const int MAX_TRADES_PER_DAY = 2;
const int COOLDOWN_BARS = 10;
const int STOP_KIND = 0;
const double STOP_MULT = 2;
const double STOP_FIXED = 0;
const int STOP_N = 14;
const int TARGET_KIND = 0;
const double TARGET_RR = 1.5;
const double TARGET_PCT = 0;
const double TARGET_FIXED = 0;
const double BE_AT_R = 0;
const double TRAIL_MULT = 0;
const int TRAIL_N = 14;
const int TIME_EXIT_BARS = 36;
const int WARMUP_BARS = 1440;


struct EmaState
{
   int    span;
   double alpha;
   int    count;
   int    size;
   double value;
   double hist[];
};

void EmaReset(EmaState &s, const int span)
{
   s.span = span;
   s.alpha = 2.0 / (span + 1.0);
   s.count = 0;
   s.size = 0;
   s.value = 0.0;
   ArrayResize(s.hist, 0);
}

void EmaAppend(EmaState &s, const double price)
{
   s.count++;
   if(s.count == 1) s.value = price;
   else s.value = (1.0 - s.alpha) * s.value + s.alpha * price;
   if(s.size >= ArraySize(s.hist)) ArrayResize(s.hist, s.size + 4096);
   s.hist[s.size] = (s.count >= s.span) ? s.value : EMPTY_VALUE;
   s.size++;
}

double EmaAt(EmaState &s, const int shift, bool &ok)
{
   int index = s.size - shift;
   if(index < 0 || index >= s.size) { ok = false; return 0.0; }
   double value = s.hist[index];
   if(value == EMPTY_VALUE) { ok = false; return 0.0; }
   ok = true;
   return value;
}

struct AdxState
{
   int    n;
   double alpha;
   int    count;
   double atr;
   double plus;
   double minus;
   bool   has_dx;
   int    dx_last;
   int    dx_count;
   double dx_ewm;
   int    size;
   double hist[];
};

void AdxReset(AdxState &s, const int n)
{
   s.n = n;
   s.alpha = 1.0 / (double)n;
   s.count = 0;
   s.atr = 0.0;
   s.plus = 0.0;
   s.minus = 0.0;
   s.has_dx = false;
   s.dx_last = -1;
   s.dx_count = 0;
   s.dx_ewm = 0.0;
   s.size = 0;
   ArrayResize(s.hist, 0);
}

void AdxAppend(AdxState &s, const int shift)
{
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double tr = high - low;
   double up = 0.0;
   double down = 0.0;
   if(s.count > 0)
   {
      double prev_high = iHigh(_Symbol, _Period, shift + 1);
      double prev_low = iLow(_Symbol, _Period, shift + 1);
      double prev_close = iClose(_Symbol, _Period, shift + 1);
      up = high - prev_high;
      down = prev_low - low;
      tr = MathMax(tr, MathMax(MathAbs(high - prev_close), MathAbs(low - prev_close)));
   }
   double plus_dm = (up > down && up > 0.0) ? up : 0.0;
   double minus_dm = (down > up && down > 0.0) ? down : 0.0;
   if(s.count == 0)
   {
      s.atr = tr;
      s.plus = plus_dm;
      s.minus = minus_dm;
   }
   else
   {
      s.atr = (1.0 - s.alpha) * s.atr + s.alpha * tr;
      s.plus = (1.0 - s.alpha) * s.plus + s.alpha * plus_dm;
      s.minus = (1.0 - s.alpha) * s.minus + s.alpha * minus_dm;
   }
   double value = EMPTY_VALUE;
   int index = s.count;
   if(index >= s.n - 1 && s.atr != 0.0)
   {
      double plus = s.plus / s.atr;
      double minus = s.minus / s.atr;
      double denominator = plus + minus;
      if(denominator != 0.0)
      {
         double dx = MathAbs(plus - minus) / denominator * 100.0;
         if(!s.has_dx)
         {
            s.dx_ewm = dx;
            s.has_dx = true;
            s.dx_count = 1;
         }
         else
         {
            int gap = index - s.dx_last;
            double weight = 1.0 - MathPow(1.0 - s.alpha, (double)gap);
            s.dx_ewm = (1.0 - weight) * s.dx_ewm + weight * dx;
            s.dx_count++;
         }
         s.dx_last = index;
         if(s.dx_count >= s.n) value = s.dx_ewm;
      }
   }
   if(s.size >= ArraySize(s.hist)) ArrayResize(s.hist, s.size + 4096);
   s.hist[s.size] = value;
   s.size++;
   s.count++;
}

double AdxAt(AdxState &s, const int shift, bool &ok)
{
   int index = s.size - shift;
   if(index < 0 || index >= s.size) { ok = false; return 0.0; }
   double value = s.hist[index];
   if(value == EMPTY_VALUE) { ok = false; return 0.0; }
   ok = true;
   return value;
}

int NyOffsetSeconds(const datetime utc)
{
   MqlDateTime t;
   TimeToStruct(utc, t);
   int year = t.year;
   MqlDateTime a;
   a.year = year; a.mon = 3; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
   a.day_of_week = 0; a.day_of_year = 0;
   datetime first = StructToTime(a);
   int weekday = TimeDayOfWeek(first);
   int sunday = 1 + ((7 - weekday) % 7);
   datetime dst_start;
   datetime dst_end;
   if(year <= 2006)
   {
      a.mon = 4; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      first = StructToTime(a);
      weekday = TimeDayOfWeek(first);
      sunday = 1 + ((7 - weekday) % 7);
      a.day = sunday;
      a.hour = 7;
      dst_start = StructToTime(a);
      a.mon = 10; a.day = 31; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      datetime last = StructToTime(a);
      weekday = TimeDayOfWeek(last);
      a.day = 31 - weekday;
      a.hour = 6;
      dst_end = StructToTime(a);
   }
   else
   {
      a.mon = 3; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      first = StructToTime(a);
      weekday = TimeDayOfWeek(first);
      sunday = 1 + ((7 - weekday) % 7);
      a.day = sunday + 7;
      a.hour = 7;
      dst_start = StructToTime(a);
      a.mon = 11; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      a.day_of_week = 0; a.day_of_year = 0;
      first = StructToTime(a);
      weekday = TimeDayOfWeek(first);
      sunday = 1 + ((7 - weekday) % 7);
      a.day = sunday;
      a.hour = 6;
      dst_end = StructToTime(a);
   }
   if(utc >= dst_start && utc < dst_end) return -4 * 3600;
   return -5 * 3600;
}

datetime ServerToUtc(const datetime server)
{
   long value = (long)server - (long)InpServerUtcOffsetMinutes * 60;
   return (datetime)value;
}

datetime ServerToNy(const datetime server)
{
   datetime utc = ServerToUtc(server);
   long value = (long)utc + (long)NyOffsetSeconds(utc);
   return (datetime)value;
}

int NyMinute(const datetime ny)
{
   MqlDateTime t;
   TimeToStruct(ny, t);
   return t.hour * 60 + t.min;
}

int NyDateKey(const datetime ny)
{
   MqlDateTime t;
   TimeToStruct(ny, t);
   return t.year * 10000 + t.mon * 100 + t.day;
}

bool InSession(const datetime server)
{
   int minute = NyMinute(ServerToNy(server));
   if(SESSION_START < SESSION_END) return (minute >= SESSION_START && minute < SESSION_END);
   return (minute >= SESSION_START || minute < SESSION_END);
}

bool InEntryWindow(const datetime server)
{
   int minute = NyMinute(ServerToNy(server));
   if(SESSION_START < SESSION_END) return (minute >= SESSION_START && minute <= SESSION_END);
   return (minute >= SESSION_START || minute <= SESSION_END);
}

bool IsTradingWeekday(const datetime server)
{
   int dow = TimeDayOfWeek(ServerToNy(server));
   return dow == 1 || dow == 2 || dow == 3 || dow == 4 || dow == 5;
}

int SessionDayKey(const datetime server)
{
   datetime ny = ServerToNy(server);
   int minute = NyMinute(ny);
   int key = NyDateKey(ny);
   if(SESSION_START > SESSION_END && minute < SESSION_END)
   {
      key = NyDateKey(ny - (datetime)86400);
   }
   return key;
}

bool FlatFlag(const datetime server)
{
   datetime ny = ServerToNy(server);
   int minute = NyMinute(ny);
   int relative = (minute - SESSION_START + 1440) % 1440;
   int duration = (MANAGE_END - SESSION_START + 1440) % 1440;
   if(duration == 0) duration = 1440;
   int flat_relative = (FLAT_AT - SESSION_START + 1440) % 1440;
   return (relative >= flat_relative && relative <= duration);
}

bool HasBars(const int shift, const int count)
{
   if(shift < 0 || count <= 0) return false;
   return (shift + count <= Bars(_Symbol, _Period));
}

double TrAt(const int shift)
{
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double value = high - low;
   if(shift + 1 < Bars(_Symbol, _Period))
   {
      double prev_close = iClose(_Symbol, _Period, shift + 1);
      value = MathMax(value, MathMax(MathAbs(high - prev_close), MathAbs(low - prev_close)));
   }
   return value;
}

double SmaAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int k = 0; k < n; k++) sum += iClose(_Symbol, _Period, shift + k);
   ok = true;
   return sum / (double)n;
}

double RsiAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n + 1)) { ok = false; return 0.0; }
   double gain = 0.0;
   double loss = 0.0;
   for(int k = 0; k < n; k++)
   {
      double delta = iClose(_Symbol, _Period, shift + k) - iClose(_Symbol, _Period, shift + k + 1);
      if(delta > 0.0) gain += delta;
      else loss -= delta;
   }
   gain /= (double)n;
   loss /= (double)n;
   if(loss == 0.0) { ok = false; return 0.0; }
   ok = true;
   return 100.0 - 100.0 / (1.0 + gain / loss);
}

double AtrAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int k = 0; k < n; k++) sum += TrAt(shift + k);
   ok = true;
   return sum / (double)n;
}

double ZScoreAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int k = 0; k < n; k++) sum += iClose(_Symbol, _Period, shift + k);
   double mean = sum / (double)n;
   double variance = 0.0;
   for(int k = 0; k < n; k++)
   {
      double diff = iClose(_Symbol, _Period, shift + k) - mean;
      variance += diff * diff;
   }
   variance /= (double)(n - 1);
   if(variance <= 0.0) { ok = false; return 0.0; }
   ok = true;
   return (iClose(_Symbol, _Period, shift) - mean) / MathSqrt(variance);
}

double MacdAt(EmaState &fast, EmaState &slow, const int shift, bool &ok)
{
   bool fast_ok = false;
   bool slow_ok = false;
   double fast_value = EmaAt(fast, shift, fast_ok);
   double slow_value = EmaAt(slow, shift, slow_ok);
   if(!fast_ok || !slow_ok) { ok = false; return 0.0; }
   ok = true;
   return fast_value - slow_value;
}

double BollingerPctAt(const int shift, const int n, const double k, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double sum = 0.0;
   for(int j = 0; j < n; j++) sum += iClose(_Symbol, _Period, shift + j);
   double mean = sum / (double)n;
   double variance = 0.0;
   for(int j = 0; j < n; j++)
   {
      double diff = iClose(_Symbol, _Period, shift + j) - mean;
      variance += diff * diff;
   }
   variance /= (double)(n - 1);
   double width = 2.0 * k * MathSqrt(variance);
   if(width == 0.0) { ok = false; return 0.0; }
   double lower = mean - k * MathSqrt(variance);
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lower) / width;
}

double StochasticAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double highest = -DBL_MAX;
   double lowest = DBL_MAX;
   for(int j = 0; j < n; j++)
   {
      highest = MathMax(highest, iHigh(_Symbol, _Period, shift + j));
      lowest = MathMin(lowest, iLow(_Symbol, _Period, shift + j));
   }
   if(highest == lowest) { ok = false; return 0.0; }
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lowest) / (highest - lowest) * 100.0;
}

double CciAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double values[];
   ArrayResize(values, n);
   double sum = 0.0;
   for(int j = 0; j < n; j++)
   {
      double typical = (iHigh(_Symbol, _Period, shift + j) + iLow(_Symbol, _Period, shift + j) + iClose(_Symbol, _Period, shift + j)) / 3.0;
      values[j] = typical;
      sum += typical;
   }
   double mean = sum / (double)n;
   double deviation = 0.0;
   for(int j = 0; j < n; j++) deviation += MathAbs(values[j] - mean);
   deviation /= (double)n;
   if(deviation == 0.0) { ok = false; return 0.0; }
   double current = (iHigh(_Symbol, _Period, shift) + iLow(_Symbol, _Period, shift) + iClose(_Symbol, _Period, shift)) / 3.0;
   ok = true;
   return (current - mean) / (0.015 * deviation);
}

double DonchianPosAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n)) { ok = false; return 0.0; }
   double upper = -DBL_MAX;
   double lower = DBL_MAX;
   for(int j = 0; j < n; j++)
   {
      upper = MathMax(upper, iHigh(_Symbol, _Period, shift + j));
      lower = MathMin(lower, iLow(_Symbol, _Period, shift + j));
   }
   double width = upper - lower;
   if(width == 0.0) { ok = false; return 0.0; }
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lower) / width;
}

double KeltnerPosAt(const int shift, const int n, const double mult, EmaState &ema, bool &ok)
{
   bool ema_ok = false;
   bool atr_ok = false;
   double middle = EmaAt(ema, shift, ema_ok);
   double atr = AtrAt(shift, n, atr_ok);
   if(!ema_ok || !atr_ok) { ok = false; return 0.0; }
   double width = 2.0 * mult * atr;
   if(width == 0.0) { ok = false; return 0.0; }
   double lower = middle - mult * atr;
   ok = true;
   return (iClose(_Symbol, _Period, shift) - lower) / width;
}

double RealizedVolAt(const int shift, const int n, bool &ok)
{
   if(!HasBars(shift, n + 1)) { ok = false; return 0.0; }
   double returns[];
   ArrayResize(returns, n);
   double sum = 0.0;
   for(int j = 0; j < n; j++)
   {
      double current = iClose(_Symbol, _Period, shift + j);
      double previous = iClose(_Symbol, _Period, shift + j + 1);
      double value = (current - previous) / previous;
      returns[j] = value;
      sum += value;
   }
   double mean = sum / (double)n;
   double variance = 0.0;
   for(int j = 0; j < n; j++)
   {
      double diff = returns[j] - mean;
      variance += diff * diff;
   }
   variance /= (double)(n - 1);
   ok = true;
   return MathSqrt(variance);
}

double AtrPctRankAt(const int shift, const int n, const int lookback, bool &ok)
{
   ok = false;
   if(!HasBars(shift, n)) return 0.0;
   int minimum = (lookback / 2 > 10) ? lookback / 2 : 10;
   double current_atr = AtrAt(shift, n, ok);
   if(!ok) return 0.0;
   double current_close = iClose(_Symbol, _Period, shift);
   if(current_close <= 0.0) return 0.0;
   double current = current_atr / current_close;
   double window_sum = 0.0;
   for(int j = 0; j < n; j++) window_sum += TrAt(shift + j);
   int count = 0;
   int less = 0;
   int equal = 0;
   for(int k = 0; k < lookback; k++)
   {
      if(shift + k + n - 1 >= Bars(_Symbol, _Period)) break;
      double close_k = iClose(_Symbol, _Period, shift + k);
      if(close_k > 0.0)
      {
         double value = (window_sum / (double)n) / close_k;
         count++;
         if(value < current) less++;
         else if(value == current) equal++;
      }
      if(shift + k + n < Bars(_Symbol, _Period))
      {
         window_sum += TrAt(shift + k + n) - TrAt(shift + k);
      }
   }
   if(count < minimum || count == 0) return 0.0;
   double rank = (double)less + ((double)equal + 1.0) / 2.0;
   ok = true;
   return rank / (double)count;
}

double RangeCompressionAt(const int shift, const int n, bool &ok)
{
   bool atr_ok = false;
   double atr = AtrAt(shift, n, atr_ok);
   if(!atr_ok || atr == 0.0) { ok = false; return 0.0; }
   ok = true;
   return (iHigh(_Symbol, _Period, shift) - iLow(_Symbol, _Period, shift)) / atr;
}

double SwingHighAt(const int shift, const int left, const int right, bool &ok)
{
   int pivot = shift + right;
   if(pivot + left >= Bars(_Symbol, _Period)) { ok = false; return 0.0; }
   double value = iHigh(_Symbol, _Period, pivot);
   for(int k = -left; k <= right; k++)
   {
      if(iHigh(_Symbol, _Period, pivot - k) > value) { ok = false; return 0.0; }
   }
   ok = true;
   return value;
}

double SwingLowAt(const int shift, const int left, const int right, bool &ok)
{
   int pivot = shift + right;
   if(pivot + left >= Bars(_Symbol, _Period)) { ok = false; return 0.0; }
   double value = iLow(_Symbol, _Period, pivot);
   for(int k = -left; k <= right; k++)
   {
      if(iLow(_Symbol, _Period, pivot - k) < value) { ok = false; return 0.0; }
   }
   ok = true;
   return value;
}

bool BosUpAt(const int shift, const int left, const int right)
{
   for(int k = 0; k < InpPivotScanBars; k++)
   {
      bool ok = false;
      double level = SwingHighAt(shift + k, left, right, ok);
      if(ok) return (iClose(_Symbol, _Period, shift) > level);
      if(shift + k + right + left >= Bars(_Symbol, _Period)) break;
   }
   return false;
}

bool BosDownAt(const int shift, const int left, const int right)
{
   for(int k = 0; k < InpPivotScanBars; k++)
   {
      bool ok = false;
      double level = SwingLowAt(shift + k, left, right, ok);
      if(ok) return (iClose(_Symbol, _Period, shift) < level);
      if(shift + k + right + left >= Bars(_Symbol, _Period)) break;
   }
   return false;
}

bool ChochUpAt(const int shift, const int left, const int right)
{
   bool previous = false;
   if(shift + 1 < Bars(_Symbol, _Period)) previous = BosUpAt(shift + 1, left, right);
   return BosUpAt(shift, left, right) && !previous;
}

bool ChochDownAt(const int shift, const int left, const int right)
{
   bool previous = false;
   if(shift + 1 < Bars(_Symbol, _Period)) previous = BosDownAt(shift + 1, left, right);
   return BosDownAt(shift, left, right) && !previous;
}

bool EngulfingAt(const int shift)
{
   if(shift + 1 >= Bars(_Symbol, _Period)) return false;
   double open_ = iOpen(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double previous_open = iOpen(_Symbol, _Period, shift + 1);
   double previous_close = iClose(_Symbol, _Period, shift + 1);
   bool bullish = (close > open_) && (previous_close < previous_open) && (open_ <= previous_close) && (close >= previous_open);
   bool bearish = (close < open_) && (previous_close > previous_open) && (open_ >= previous_close) && (close <= previous_open);
   return bullish || bearish;
}

bool PinBarAt(const int shift, const double ratio)
{
   double open_ = iOpen(_Symbol, _Period, shift);
   double close = iClose(_Symbol, _Period, shift);
   double high = iHigh(_Symbol, _Period, shift);
   double low = iLow(_Symbol, _Period, shift);
   double body = MathAbs(close - open_);
   double upper = high - MathMax(open_, close);
   double lower = MathMin(open_, close) - low;
   return ((lower > ratio * body) && (lower > upper)) || ((upper > ratio * body) && (upper > lower));
}

bool InsideBarAt(const int shift)
{
   if(shift + 1 >= Bars(_Symbol, _Period)) return false;
   return (iHigh(_Symbol, _Period, shift) < iHigh(_Symbol, _Period, shift + 1)) &&
          (iLow(_Symbol, _Period, shift) > iLow(_Symbol, _Period, shift + 1));
}

bool RangeExpansionAt(const int shift, const int n, const double mult)
{
   if(!HasBars(shift, n + 1)) return false;
   double sum = 0.0;
   for(int k = 1; k <= n; k++) sum += iHigh(_Symbol, _Period, shift + k) - iLow(_Symbol, _Period, shift + k);
   double mean = sum / (double)n;
   double current = iHigh(_Symbol, _Period, shift) - iLow(_Symbol, _Period, shift);
   return current > mult * mean;
}

double PrevSessionLevelAt(const int shift, const bool want_high, bool &ok)
{
   ok = false;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   datetime time = iTime(_Symbol, _Period, shift);
   if(!InSession(time)) return 0.0;
   int key = SessionDayKey(time);
   int total = Bars(_Symbol, _Period);
   double value = want_high ? -DBL_MAX : DBL_MAX;
   bool found = false;
   for(int k = shift + 1; k < total; k++)
   {
      datetime other = iTime(_Symbol, _Period, k);
      if(!InSession(other)) continue;
      int other_key = SessionDayKey(other);
      if(other_key >= key) continue;
      int target = other_key;
      for(; k < total; k++)
      {
         datetime stamp = iTime(_Symbol, _Period, k);
         if(!InSession(stamp) || SessionDayKey(stamp) != target) break;
         double item = want_high ? iHigh(_Symbol, _Period, k) : iLow(_Symbol, _Period, k);
         value = want_high ? MathMax(value, item) : MathMin(value, item);
         found = true;
      }
      break;
   }
   if(!found) return 0.0;
   ok = true;
   return value;
}

double PrevDayLevelAt(const int shift, const bool want_high, bool &ok)
{
   ok = false;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   int key = NyDateKey(ServerToNy(iTime(_Symbol, _Period, shift)));
   int total = Bars(_Symbol, _Period);
   double value = want_high ? -DBL_MAX : DBL_MAX;
   bool found = false;
   for(int k = shift + 1; k < total; k++)
   {
      int other_key = NyDateKey(ServerToNy(iTime(_Symbol, _Period, k)));
      if(other_key >= key) continue;
      int target = other_key;
      for(; k < total; k++)
      {
         if(NyDateKey(ServerToNy(iTime(_Symbol, _Period, k))) != target) break;
         double item = want_high ? iHigh(_Symbol, _Period, k) : iLow(_Symbol, _Period, k);
         value = want_high ? MathMax(value, item) : MathMin(value, item);
         found = true;
      }
      break;
   }
   if(!found) return 0.0;
   ok = true;
   return value;
}

double OpeningRangeAt(const int shift, const bool want_high, bool &ok)
{
   ok = false;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   datetime time = iTime(_Symbol, _Period, shift);
   if(!InSession(time)) return 0.0;
   int key = SessionDayKey(time);
   int relative = (NyMinute(ServerToNy(time)) - SESSION_START + 1440) % 1440;
   if(relative < OR_MINUTES) return 0.0;
   double value = want_high ? -DBL_MAX : DBL_MAX;
   bool found = false;
   int total = Bars(_Symbol, _Period);
   for(int k = shift; k < total; k++)
   {
      datetime stamp = iTime(_Symbol, _Period, k);
      if(!InSession(stamp) || SessionDayKey(stamp) != key) break;
      int item_relative = (NyMinute(ServerToNy(stamp)) - SESSION_START + 1440) % 1440;
      if(item_relative < OR_MINUTES)
      {
         double item = want_high ? iHigh(_Symbol, _Period, k) : iLow(_Symbol, _Period, k);
         value = want_high ? MathMax(value, item) : MathMin(value, item);
         found = true;
      }
   }
   if(!found) return 0.0;
   ok = true;
   return value;
}

double DonchianLevelAt(const int shift, const int n, const bool want_high, bool &ok)
{
   if(!HasBars(shift + 1, n)) { ok = false; return 0.0; }
   double value = want_high ? -DBL_MAX : DBL_MAX;
   for(int k = 1; k <= n; k++)
   {
      double item = want_high ? iHigh(_Symbol, _Period, shift + k) : iLow(_Symbol, _Period, shift + k);
      value = want_high ? MathMax(value, item) : MathMin(value, item);
   }
   ok = true;
   return value;
}

double SessionReturnAt(const int shift, const int start_minute, const int end_minute, bool &ok)
{
   ok = false;
   if(start_minute >= end_minute) return 0.0;
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return 0.0;
   int total = Bars(_Symbol, _Period);
   datetime time = iTime(_Symbol, _Period, shift);
   int day_key = NyDateKey(ServerToNy(time));
   int oldest = shift;
   while(oldest + 1 < total)
   {
      if(NyDateKey(ServerToNy(iTime(_Symbol, _Period, oldest + 1))) != day_key) break;
      oldest++;
   }
   int start_pos = -1;
   int end_pos = -1;
   int start_shift = -1;
   int end_shift = -1;
   int position = 0;
   for(int k = oldest; k >= 0; k--)
   {
      datetime stamp = iTime(_Symbol, _Period, k);
      if(NyDateKey(ServerToNy(stamp)) != day_key) break;
      int minute = NyMinute(ServerToNy(stamp));
      if(start_pos < 0 && minute == start_minute) { start_pos = position; start_shift = k; }
      if(end_pos < 0 && minute == end_minute) { end_pos = position; end_shift = k; }
      position++;
   }
   if(start_pos < 0 || end_pos < 0 || end_pos <= start_pos) return 0.0;
   int newest = oldest - (position - 1);
   if(!(shift < end_shift && shift >= newest)) return 0.0;
   double begin = iOpen(_Symbol, _Period, start_shift);
   double finish = iClose(_Symbol, _Period, end_shift);
   if(begin <= 0.0) return 0.0;
   ok = true;
   return finish / begin - 1.0;
}




void InitIndicators()
{
}

void UpdateIndicatorsAt(const int shift)
{
}

double V_b46744b4f2ca(const int shift, bool &ok)
{
   return BollingerPctAt(shift, 20, 2, ok);
}

double V_18aff1a19c9e(const int shift, bool &ok)
{
   ok = true; return 0.050000000000000003;
}

bool B_3ddd3c7dd1c7(const int shift)
{
   bool _ok = false;
   double left = V_b46744b4f2ca(shift, _ok);
   if(!_ok) return false;
   double right = V_18aff1a19c9e(shift, _ok);
   if(!_ok) return false;
   return left < right;
}

double V_a6a8fb74f3a3(const int shift, bool &ok)
{
   return RsiAt(shift, 14, ok);
}

double V_f159295b4837(const int shift, bool &ok)
{
   ok = true; return 30;
}

bool B_14beaa294ea3(const int shift)
{
   bool _ok = false;
   double left = V_a6a8fb74f3a3(shift, _ok);
   if(!_ok) return false;
   double right = V_f159295b4837(shift, _ok);
   if(!_ok) return false;
   return left < right;
}

bool B_bd3d55b0ab0f(const int shift)
{
   bool _ok = false;
   return B_3ddd3c7dd1c7(shift) && B_14beaa294ea3(shift);
}

bool LongSignal(const int shift)
{
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;
   if((Bars(_Symbol, _Period) - 1 - shift) < WARMUP_BARS) return false;
   if(!InSession(iTime(_Symbol, _Period, shift))) return false;
   return B_bd3d55b0ab0f(shift);
}

bool ShortSignal(const int shift)
{
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;
   if((Bars(_Symbol, _Period) - 1 - shift) < WARMUP_BARS) return false;
   if(!InSession(iTime(_Symbol, _Period, shift))) return false;
   return false;
}


long g_magic = 0;
datetime g_last_bar = 0;
datetime g_entry_bar = 0;
double g_entry_price = 0.0;
double g_entry_risk = 0.0;
int g_day_key = 0;
int g_day_trades = 0;
double g_day_start_equity = 0.0;
double g_initial_equity = 0.0;
bool g_total_blocked = false;
int g_trace = INVALID_HANDLE;

bool FindPosition(ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong current = PositionGetTicket(i);
      if(current == 0) continue;
      if(!PositionSelectByTicket(current)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      ticket = current;
      return true;
   }
   return false;
}

void CloseOurPosition()
{
   ulong ticket = 0;
   if(FindPosition(ticket)) trade.PositionClose(ticket);
}

int BarsHeld()
{
   if(g_entry_bar == 0) return -1;
   int elapsed = iBarShift(_Symbol, _Period, g_entry_bar, false);
   return elapsed - 1;
}

void UpdateDayState(const datetime server)
{
   int key = SessionDayKey(server);
   if(key != g_day_key)
   {
      g_day_key = key;
      g_day_trades = 0;
      g_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   }
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(InpMaxLossLimit > 0.0 && g_initial_equity > 0.0 && equity <= g_initial_equity - InpMaxLossLimit)
   {
      g_total_blocked = true;
   }
}

bool RiskAllowsEntry(const datetime server)
{
   UpdateDayState(server);
   if(g_total_blocked) return false;
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(InpDailyLossLimit > 0.0 && g_day_start_equity > 0.0 &&
      equity <= g_day_start_equity - InpDailyLossLimit) return false;
   if(MAX_TRADES_PER_DAY > 0 && g_day_trades >= MAX_TRADES_PER_DAY) return false;
   return true;
}

bool CooldownAllows()
{
   if(COOLDOWN_BARS <= 0 || g_entry_bar == 0) return true;
   return iBarShift(_Symbol, _Period, g_entry_bar, false) >= COOLDOWN_BARS;
}

bool EntryWindowAllows(const int shift)
{
   if(shift < 0 || shift >= Bars(_Symbol, _Period)) return false;
   datetime time = iTime(_Symbol, _Period, shift);
   if(!IsTradingWeekday(time)) return false;
   if(!InEntryWindow(time)) return false;
   if(FlatFlag(time)) return false;
   return true;
}

bool BuildExit(const int signal_shift, const int side, const double entry,
               double &stop, double &target, bool &has_target, double &risk)
{
   double distance = 0.0;
   stop = 0.0;
   target = 0.0;
   has_target = false;
   risk = 0.0;
   if(STOP_KIND == 0)
   {
      bool ok = false;
      double atr = AtrAt(signal_shift, STOP_N, ok);
      if(!ok || atr <= 0.0) return false;
      distance = STOP_MULT * atr;
      stop = entry - side * distance;
   }
   else if(STOP_KIND == 1)
   {
      distance = entry * STOP_MULT / 100.0;
      stop = entry - side * distance;
   }
   else
   {
      stop = STOP_FIXED;
      distance = (entry - stop) * side;
   }
   if(distance <= 0.0 || distance >= DBL_MAX) return false;
   if(TARGET_KIND != 3)
   {
      if(TARGET_KIND == 0) target = entry + side * TARGET_RR * distance;
      else if(TARGET_KIND == 1) target = entry + side * entry * TARGET_PCT / 100.0;
      else target = TARGET_FIXED;
      if((side > 0 && target <= entry) || (side < 0 && target >= entry)) return false;
      has_target = true;
   }
   risk = distance;
   return true;
}

double CalcLots(const double risk_price)
{
   if(risk_price <= 0.0) return 0.0;
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_value <= 0.0 || tick_size <= 0.0) return 0.0;
   double risk_money = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPerTradePct / 100.0;
   if(risk_money <= 0.0) return 0.0;
   double per_lot = risk_price / tick_size * tick_value;
   if(per_lot <= 0.0) return 0.0;
   double lots = risk_money / per_lot;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minimum = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maximum = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step > 0.0) lots = MathFloor(lots / step) * step;
   lots = MathMin(lots, maximum);
   if(lots < minimum) return 0.0;
   return lots;
}

void TraceEntry(const datetime server_time, const int side, const double entry,
                const double stop, const bool has_target, const double target)
{
   if(g_trace == INVALID_HANDLE) return;
   datetime utc = ServerToUtc(server_time);
   MqlDateTime t;
   TimeToStruct(utc, t);
   string stamp = StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                               t.year, t.mon, t.day, t.hour, t.min, t.sec);
   string side_text = (side > 0) ? "long" : "short";
   string target_text = has_target ? DoubleToString(target, 8) : "";
   FileWriteString(g_trace, stamp + "," + side_text + "," + DoubleToString(entry, 8) +
                   "," + DoubleToString(stop, 8) + "," + target_text + "\n");
}

void UpdateProtection(const int side, const ulong ticket)
{
   if(g_entry_risk <= 0.0) return;
   double close = iClose(_Symbol, _Period, 1);
   double current_stop = PositionGetDouble(POSITION_SL);
   double current_target = PositionGetDouble(POSITION_TP);
   double new_stop = current_stop;
   if(BE_AT_R > 0.0)
   {
      double current_r = (close - g_entry_price) * side / g_entry_risk;
      if(current_r >= BE_AT_R)
      {
         if(side > 0 && (new_stop == 0.0 || g_entry_price > new_stop)) new_stop = g_entry_price;
         if(side < 0 && (new_stop == 0.0 || g_entry_price < new_stop)) new_stop = g_entry_price;
      }
   }
   if(TRAIL_MULT > 0.0)
   {
      bool ok = false;
      double atr = AtrAt(1, TRAIL_N, ok);
      if(ok && atr > 0.0)
      {
         double level = close - side * TRAIL_MULT * atr;
         if(side > 0 && (new_stop == 0.0 || level > new_stop)) new_stop = level;
         if(side < 0 && (new_stop == 0.0 || level < new_stop)) new_stop = level;
      }
   }
   if(new_stop == current_stop || new_stop <= 0.0) return;
   double normalized = NormalizeDouble(new_stop, _Digits);
   if(normalized == NormalizeDouble(current_stop, _Digits)) return;
   trade.PositionModify(ticket, normalized, current_target);
}

void OnNewBar(const datetime previous)
{
   int shift = 1;
   if(shift >= Bars(_Symbol, _Period)) return;
   int elapsed = 1;
   if(previous != 0)
   {
      elapsed = iBarShift(_Symbol, _Period, previous, false);
      if(elapsed < 1) elapsed = 1;
   }
   for(int missed = elapsed; missed >= 1; missed--) UpdateIndicatorsAt(missed);
   bool long_signal = LongSignal(shift);
   bool short_signal = ShortSignal(shift);
   datetime entry_time = iTime(_Symbol, _Period, 0);
   UpdateDayState(entry_time);
   ulong ticket = 0;
   bool has_position = FindPosition(ticket);
   if(has_position)
   {
      long position_type = PositionGetInteger(POSITION_TYPE);
      int side = (position_type == POSITION_TYPE_BUY) ? 1 : -1;
      if((side > 0 && short_signal) || (side < 0 && long_signal))
      {
         CloseOurPosition();
         has_position = false;
      }
      else if(FlatFlag(iTime(_Symbol, _Period, 1)))
      {
         CloseOurPosition();
         has_position = false;
      }
      else if(TIME_EXIT_BARS > 0 && BarsHeld() >= TIME_EXIT_BARS)
      {
         CloseOurPosition();
         has_position = false;
      }
      if(has_position) UpdateProtection(side, ticket);
   }
   if(has_position) return;
   int side = long_signal ? 1 : (short_signal ? -1 : 0);
   if(side == 0) return;
   if(!RiskAllowsEntry(entry_time)) return;
   if(!EntryWindowAllows(1) || !EntryWindowAllows(0)) return;
   if(!CooldownAllows()) return;
   double entry = iOpen(_Symbol, _Period, 0);
   double stop = 0.0;
   double target = 0.0;
   double risk = 0.0;
   bool has_target = false;
   if(!BuildExit(1, side, entry, stop, target, has_target, risk)) return;
   double lots = CalcLots(risk);
   if(lots <= 0.0) return;
   g_day_trades++;
   g_entry_bar = entry_time;
   g_entry_price = entry;
   g_entry_risk = risk;
   TraceEntry(entry_time, side, entry, stop, has_target, target);
   double normalized_stop = NormalizeDouble(stop, _Digits);
   double normalized_target = has_target ? NormalizeDouble(target, _Digits) : 0.0;
   if(side > 0) trade.Buy(lots, _Symbol, 0.0, normalized_stop, normalized_target, "F12a");
   else trade.Sell(lots, _Symbol, 0.0, normalized_stop, normalized_target, "F12a");
}


int OnInit()
{
   g_magic = InpMagic;
   trade.SetExpertMagicNumber((ulong)InpMagic);
   trade.SetDeviationInPoints((ulong)InpSlippagePoints);
   g_initial_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_day_start_equity = g_initial_equity;
   datetime start_time = iTime(_Symbol, _Period, 0);
   if(start_time > 0) g_day_key = SessionDayKey(start_time);
   InitIndicators();
   // sin indicadores con estado
   if(InpEmitTrace)
   {
      g_trace = FileOpen(InpTraceFile, FILE_WRITE | FILE_TXT | FILE_ANSI);
      if(g_trace != INVALID_HANDLE)
         FileWriteString(g_trace, "bar_time,side,entry,stop,target\n");
   }
   g_last_bar = iTime(_Symbol, _Period, 0);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_trace != INVALID_HANDLE) FileClose(g_trace);
}

void OnTick()
{
   datetime current = iTime(_Symbol, _Period, 0);
   if(current == g_last_bar) return;
   datetime previous = g_last_bar;
   g_last_bar = current;
   OnNewBar(previous);
}
