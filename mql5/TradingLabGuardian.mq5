//+------------------------------------------------------------------+
//|                                          TradingLabGuardian.mq5 |
//|                    Defensa de equity para cuentas demo           |
//|                                                                  |
//|  Lee MQL5/Files/tradinglab_guardian.json (lo genera              |
//|  `lab guardian export`) y vigila la equity de la cuenta.         |
//|                                                                  |
//|  ALERT: solo Print + ntfy.                                       |
//|  CLOSE: cierra las posiciones cuyo magic esté en la lista y      |
//|         escribe un flag de bloqueo hasta el reset diario.        |
//|                                                                  |
//|  Nunca toca posiciones con otro magic. Solo demo.                |
//+------------------------------------------------------------------+
#property copyright "TradingLab"
#property version   "1.00"
#property description "Guardian de equity: avisa o cierra solo los magics del laboratorio."

#include <Trade\Trade.mqh>

input string Mode = "ALERT";           // ALERT | CLOSE
input double DailyLossPct = 0.0;       // 0 = usar el JSON (porcentaje, ej. 4.5)
input double TrailingDDPct = 0.0;      // 0 = usar el JSON
input string NtfyUrl = "";             // ej. https://ntfy.sh/mi-topic
input string TestEquityFile = "";      // solo pruebas: CSV con una equity por linea

#define TL_JSON_FILE   "tradinglab_guardian.json"
#define TL_LOG_FILE    "tradinglab_guardian.log"
#define TL_BLOCK_FILE  "tradinglab_guardian_block.flag"
#define TL_BLOCK_VAR   "TradingLabGuardianBlocked"
#define TL_DAY_VAR     "TradingLabGuardianDay"
#define TL_START_VAR   "TradingLabGuardianDayStart"
#define TL_PEAK_VAR    "TradingLabGuardianPeak"
#define TL_INVALID     -99999

CTrade trade;

double g_daily_limit = 0.0;
double g_trailing_limit = 0.0;
int    g_offset_minutes = TL_INVALID;
string g_reset_tz = "";
string g_account = "";
long   g_magics[];
string g_mode = "ALERT";
bool   g_config_ok = false;
bool   g_blocked = false;
bool   g_alerted = false;
double g_day_start = 0.0;
double g_peak = 0.0;
long   g_day_key = 0;
datetime g_last_load = 0;
datetime g_last_close = 0;
double g_test_equity[];
int    g_test_index = 0;

//+------------------------------------------------------------------+
//| Log                                                              |
//+------------------------------------------------------------------+
void LogLine(const string message)
{
   int handle = FileOpen(TL_LOG_FILE, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return;
   FileSeek(handle, 0, SEEK_END);
   FileWrite(handle, TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS) + " " + message);
   FileClose(handle);
}

//+------------------------------------------------------------------+
//| JSON minimo: el fichero lo genera Python con una forma fija      |
//+------------------------------------------------------------------+
bool ReadJson(string &text)
{
   int handle = FileOpen(TL_JSON_FILE, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
      return false;
   text = "";
   while(!FileIsEnding(handle))
      text += FileReadString(handle) + "\n";
   FileClose(handle);
   return (StringLen(text) > 0);
}

bool FindKey(const string text, const string key, int &pos)
{
   string token = "\"" + key + "\"";
   pos = StringFind(text, token);
   if(pos < 0)
      return false;
   pos = StringFind(text, ":", pos + StringLen(token));
   return (pos >= 0);
}

bool JsonNumber(const string text, const string key, double &value)
{
   int pos;
   if(!FindKey(text, key, pos))
      return false;
   string rest = StringSubstr(text, pos + 1);
   StringTrimLeft(rest);
   int len = StringLen(rest);
   int end = 0;
   while(end < len)
   {
      ushort ch = StringGetCharacter(rest, end);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-' || ch == '+' || ch == 'e' || ch == 'E')
         end++;
      else
         break;
   }
   if(end == 0)
      return false;
   value = StringToDouble(StringSubstr(rest, 0, end));
   return true;
}

bool JsonString(const string text, const string key, string &value)
{
   int pos;
   if(!FindKey(text, key, pos))
      return false;
   int start = StringFind(text, "\"", pos + 1);
   if(start < 0)
      return false;
   int end = StringFind(text, "\"", start + 1);
   if(end < 0)
      return false;
   value = StringSubstr(text, start + 1, end - start - 1);
   return true;
}

bool JsonIntArray(const string text, const string key, long &values[])
{
   int pos;
   if(!FindKey(text, key, pos))
      return false;
   int start = StringFind(text, "[", pos + 1);
   int end = StringFind(text, "]", start + 1);
   if(start < 0 || end < 0)
      return false;
   string body = StringSubstr(text, start + 1, end - start - 1);
   string parts[];
   int count = StringSplit(body, StringGetCharacter(",", 0), parts);
   ArrayResize(values, 0);
   for(int i = 0; i < count; i++)
   {
      StringTrimLeft(parts[i]);
      StringTrimRight(parts[i]);
      if(StringLen(parts[i]) == 0)
         continue;
      int size = ArraySize(values);
      ArrayResize(values, size + 1);
      values[size] = StringToInteger(parts[i]);
   }
   return (ArraySize(values) > 0);
}

//+------------------------------------------------------------------+
//| Configuracion                                                    |
//+------------------------------------------------------------------+
bool LoadConfig()
{
   string text;
   if(!ReadJson(text))
   {
      LogLine("ERROR no se pudo leer " + TL_JSON_FILE);
      return false;
   }

   double daily = 0.0;
   double trailing = 0.0;
   double offset = 0.0;
   string tz = "";
   string account = "";
   long magics[];
   if(!JsonNumber(text, "daily_loss_pct", daily) ||
      !JsonNumber(text, "max_drawdown_pct", trailing) ||
      !JsonNumber(text, "reset_utc_offset_minutes", offset) ||
      !JsonString(text, "reset_tz", tz) ||
      !JsonString(text, "account", account) ||
      !JsonIntArray(text, "magics", magics))
   {
      LogLine("ERROR JSON incompleto; re-exporta con lab guardian export");
      return false;
   }

   if(daily <= 0.0 || daily >= 1.0 || trailing <= 0.0 || trailing >= 1.0)
   {
      LogLine("ERROR limites del JSON fuera de rango");
      return false;
   }
   if(offset < -1440.0 || offset > 1440.0)
   {
      LogLine("ERROR reset_utc_offset_minutes invalido");
      return false;
   }

   double effective_daily = (DailyLossPct > 0.0) ? DailyLossPct / 100.0 : daily;
   double effective_trailing = (TrailingDDPct > 0.0) ? TrailingDDPct / 100.0 : trailing;
   if(effective_daily <= 0.0 || effective_daily >= 1.0 ||
      effective_trailing <= 0.0 || effective_trailing >= 1.0)
   {
      LogLine("ERROR inputs DailyLossPct/TrailingDDPct invalidos");
      return false;
   }

   g_daily_limit = effective_daily;
   g_trailing_limit = effective_trailing;
   g_offset_minutes = (int)offset;
   g_reset_tz = tz;
   g_account = account;
   ArrayResize(g_magics, ArraySize(magics));
   for(int i = 0; i < ArraySize(magics); i++)
      g_magics[i] = magics[i];
   g_config_ok = true;
   return true;
}

bool ManagedMagic(const long magic)
{
   for(int i = 0; i < ArraySize(g_magics); i++)
   {
      if(g_magics[i] == magic)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Dia local segun el offset del JSON                               |
//+------------------------------------------------------------------+
long DayKey(const datetime utc)
{
   if(g_offset_minutes == TL_INVALID)
      return 0;
   datetime local = utc + g_offset_minutes * 60;
   MqlDateTime parts;
   TimeToStruct(local, parts);
   return (long)parts.year * 10000 + parts.mon * 100 + parts.day;
}

//+------------------------------------------------------------------+
//| Equity: real o sintetica para pruebas                            |
//+------------------------------------------------------------------+
bool LoadTestEquity()
{
   ArrayResize(g_test_equity, 0);
   g_test_index = 0;
   if(StringLen(TestEquityFile) == 0)
      return true;

   int handle = FileOpen(TestEquityFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      LogLine("ERROR no se pudo abrir TestEquityFile=" + TestEquityFile);
      return false;
   }
   while(!FileIsEnding(handle))
   {
      string line = FileReadString(handle);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0)
         continue;
      double value = StringToDouble(line);
      if(value <= 0.0)
         continue;
      int size = ArraySize(g_test_equity);
      ArrayResize(g_test_equity, size + 1);
      g_test_equity[size] = value;
   }
   FileClose(handle);
   if(ArraySize(g_test_equity) == 0)
   {
      LogLine("ERROR TestEquityFile sin valores validos");
      return false;
   }
   return true;
}

double CurrentEquity()
{
   if(ArraySize(g_test_equity) == 0)
      return AccountInfoDouble(ACCOUNT_EQUITY);
   double value = g_test_equity[g_test_index];
   if(g_test_index < ArraySize(g_test_equity) - 1)
      g_test_index++;
   return value;
}

//+------------------------------------------------------------------+
//| Bloqueo de nuevas aperturas                                      |
//+------------------------------------------------------------------+
void WriteBlockFlag(const bool blocked, const string reason)
{
   if(!blocked)
   {
      FileDelete(TL_BLOCK_FILE);
      return;
   }
   int handle = FileOpen(TL_BLOCK_FILE, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      LogLine("WARN no se pudo escribir " + TL_BLOCK_FILE);
      return;
   }
   FileWrite(handle, "blocked_until_reset day=" + IntegerToString(g_day_key));
   FileWrite(handle, reason);
   FileClose(handle);
}

void SetBlocked(const bool blocked, const string reason)
{
   g_blocked = blocked;
   GlobalVariableSet(TL_BLOCK_VAR, blocked ? 1.0 : 0.0);
   GlobalVariableSet(TL_DAY_VAR, (double)g_day_key);
   WriteBlockFlag(blocked, reason);
}

//+------------------------------------------------------------------+
//| Dias: base y pico persistidos en variables globales              |
//+------------------------------------------------------------------+
void EnsureDay(const datetime now, const double equity)
{
   long key = DayKey(now);
   if(key == 0)
      return;

   if(g_day_key == 0)
   {
      long stored_day = (long)GlobalVariableGet(TL_DAY_VAR);
      double stored_start = GlobalVariableGet(TL_START_VAR);
      double stored_peak = GlobalVariableGet(TL_PEAK_VAR);
      bool stored_block = (GlobalVariableGet(TL_BLOCK_VAR) > 0.5);

      g_day_key = key;
      if(stored_day == key && stored_start > 0.0)
         g_day_start = stored_start;
      else
         g_day_start = equity;
      g_peak = MathMax(equity, stored_peak);
      g_blocked = (stored_block && stored_day == key);
      g_alerted = g_blocked;

      GlobalVariableSet(TL_DAY_VAR, (double)key);
      GlobalVariableSet(TL_START_VAR, g_day_start);
      GlobalVariableSet(TL_PEAK_VAR, g_peak);
      if(!g_blocked)
         GlobalVariableSet(TL_BLOCK_VAR, 0.0);

      LogLine("START day=" + IntegerToString(key) +
              " equity=" + DoubleToString(equity, 2) +
              " day_start=" + DoubleToString(g_day_start, 2) +
              " peak=" + DoubleToString(g_peak, 2) +
              " blocked=" + (g_blocked ? "yes" : "no"));
      return;
   }

   if(key != g_day_key)
   {
      g_day_key = key;
      g_day_start = equity;
      g_peak = MathMax(g_peak, equity);
      g_alerted = false;
      SetBlocked(false, "");
      GlobalVariableSet(TL_DAY_VAR, (double)key);
      GlobalVariableSet(TL_START_VAR, g_day_start);
      LogLine("RESET day=" + IntegerToString(key) +
              " equity=" + DoubleToString(equity, 2));
   }
}

//+------------------------------------------------------------------+
//| Cierre solo de los magics gestionados                            |
//+------------------------------------------------------------------+
bool CloseManaged()
{
   bool all_ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(!ManagedMagic(magic))
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      double volume = PositionGetDouble(POSITION_VOLUME);
      if(trade.PositionClose(ticket))
      {
         LogLine("CLOSE ticket=" + IntegerToString((long)ticket) +
                 " symbol=" + symbol +
                 " magic=" + IntegerToString(magic) +
                 " volume=" + DoubleToString(volume, 2));
      }
      else
      {
         all_ok = false;
         LogLine("ERROR close ticket=" + IntegerToString((long)ticket) +
                 " symbol=" + symbol +
                 " magic=" + IntegerToString(magic) +
                 " ret=" + IntegerToString(trade.ResultRetcode()) +
                 " " + trade.ResultRetcodeDescription());
      }
   }
   return all_ok;
}

//+------------------------------------------------------------------+
//| ntfy                                                             |
//+------------------------------------------------------------------+
void SendNtfy(const string title, const string message)
{
   if(StringLen(NtfyUrl) == 0)
      return;

   string headers = "Title: " + title + "\r\n";
   char data[];
   int length = StringToCharArray(message, data, 0, WHOLE_ARRAY, CP_UTF8);
   if(length > 0)
      ArrayResize(data, length - 1);
   else
      ArrayResize(data, 0);

   char result[];
   string result_headers = "";
   int code = WebRequest("POST", NtfyUrl, headers, 5000, data, result, result_headers);
   if(code == -1)
      LogLine("WARN ntfy fallo error=" + IntegerToString(GetLastError()));
   else
      LogLine("NTFY code=" + IntegerToString(code));
}

//+------------------------------------------------------------------+
//| Init / timer                                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   g_mode = Mode;
   StringToUpper(g_mode);
   if(g_mode != "ALERT" && g_mode != "CLOSE")
   {
      Print("TradingLabGuardian: Mode debe ser ALERT o CLOSE");
      return INIT_FAILED;
   }
   if(!LoadConfig())
   {
      Print("TradingLabGuardian: configuracion invalida; revisa ", TL_JSON_FILE);
      return INIT_FAILED;
   }
   if(!LoadTestEquity())
   {
      Print("TradingLabGuardian: TestEquityFile invalido");
      return INIT_FAILED;
   }

   g_last_load = TimeGMT();
   EventSetTimer(1);
   LogLine("INIT mode=" + g_mode +
           " account=" + g_account +
           " daily=" + DoubleToString(g_daily_limit, 4) +
           " trailing=" + DoubleToString(g_trailing_limit, 4) +
           " tz=" + g_reset_tz + " offset=" + IntegerToString(g_offset_minutes) +
           " test_equity=" + (ArraySize(g_test_equity) > 0 ? "yes" : "no"));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   LogLine("DEINIT reason=" + IntegerToString(reason));
}

void OnTick()
{
}

void OnTimer()
{
   if(!g_config_ok)
      return;

   datetime now = TimeGMT();
   if(now - g_last_load >= 60)
   {
      g_last_load = now;
      if(!LoadConfig())
         LogLine("WARN recarga fallida; mantengo la configuracion anterior");
      else
         LogLine("CONFIG account=" + g_account +
                 " daily=" + DoubleToString(g_daily_limit, 4) +
                 " trailing=" + DoubleToString(g_trailing_limit, 4));
   }
   if(!g_config_ok)
      return;

   double equity = CurrentEquity();
   if(equity <= 0.0)
      return;

   EnsureDay(now, equity);
   if(g_day_key == 0)
      return;

   if(equity > g_peak)
   {
      g_peak = equity;
      GlobalVariableSet(TL_PEAK_VAR, g_peak);
   }

   double daily_loss = (g_day_start > 0.0)
                       ? MathMax(0.0, (g_day_start - equity) / g_day_start)
                       : 0.0;
   double trailing_dd = (g_peak > 0.0)
                        ? MathMax(0.0, (g_peak - equity) / g_peak)
                        : 0.0;

   // Si ya esta bloqueado, sigue cerrando cualquier posicion gestionada
   // que aparezca, aunque la equity se haya recuperado.
   if(g_blocked && g_mode == "CLOSE")
   {
      if(now - g_last_close >= 2)
      {
         g_last_close = now;
         CloseManaged();
      }
   }

   if(daily_loss < g_daily_limit && trailing_dd < g_trailing_limit)
      return;

   string reason = "";
   if(daily_loss >= g_daily_limit)
      reason = "daily loss " + DoubleToString(daily_loss * 100.0, 2) +
               "% >= " + DoubleToString(g_daily_limit * 100.0, 2) + "%";
   if(trailing_dd >= g_trailing_limit)
   {
      if(StringLen(reason) > 0)
         reason += "; ";
      reason += "trailing dd " + DoubleToString(trailing_dd * 100.0, 2) +
                "% >= " + DoubleToString(g_trailing_limit * 100.0, 2) + "%";
   }

   if(!g_alerted)
   {
      g_alerted = true;
      Print("TradingLabGuardian ", g_account, ": ", reason);
      LogLine("TRIGGER " + reason +
              " equity=" + DoubleToString(equity, 2) +
              " day_start=" + DoubleToString(g_day_start, 2) +
              " peak=" + DoubleToString(g_peak, 2));
      SendNtfy("TradingLab Guardian",
               g_account + ": " + reason +
               " equity=" + DoubleToString(equity, 2));
   }

   if(g_mode == "CLOSE" && !g_blocked)
   {
      SetBlocked(true, reason);
      LogLine("BLOCK day=" + IntegerToString(g_day_key) +
              " nuevas aperturas bloqueadas hasta el reset");
      CloseManaged();
   }
}
//+------------------------------------------------------------------+
