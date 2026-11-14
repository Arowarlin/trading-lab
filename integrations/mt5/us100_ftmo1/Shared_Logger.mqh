//+------------------------------------------------------------------+
//|                                              Shared_Logger.mqh   |
//|  Registro común para los EAs de la cuenta FTMO (US100 / XAUUSD). |
//|  Escribe en el Diario de MT5 y, opcionalmente, en un archivo CSV |
//|  diario en MQL5\Files\FTMO_Logs\ .                               |
//+------------------------------------------------------------------+
#ifndef SHARED_LOGGER_MQH
#define SHARED_LOGGER_MQH

enum ENUM_FTMO_LOG
  {
   FTLOG_DEBUG = 0,
   FTLOG_INFO  = 1,
   FTLOG_WARN  = 2,
   FTLOG_ERROR = 3
  };

class CLogger
  {
private:
   string         m_tag;
   ENUM_FTMO_LOG m_level;
   bool           m_toFile;
   string         m_fileDate;
   int            m_handle;

   string LevelName(const ENUM_FTMO_LOG lv) const
     {
      switch(lv)
        {
         case FTLOG_DEBUG: return "DEBUG";
         case FTLOG_INFO:  return "INFO";
         case FTLOG_WARN:  return "WARN";
         default:        return "ERROR";
        }
     }

   void EnsureFile()
     {
      if(!m_toFile) return;
      string today = TimeToString(TimeCurrent(), TIME_DATE);
      if(m_handle != INVALID_HANDLE && today == m_fileDate) return;
      if(m_handle != INVALID_HANDLE) FileClose(m_handle);
      StringReplace(today, ".", "-");
      string name = "FTMO_Logs\\" + m_tag + "_" + today + ".csv";
      m_handle = FileOpen(name, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ, ';');
      if(m_handle != INVALID_HANDLE)
        {
         FileSeek(m_handle, 0, SEEK_END);
         m_fileDate = TimeToString(TimeCurrent(), TIME_DATE);
        }
     }

public:
                     CLogger() : m_tag("EA"), m_level(FTLOG_INFO), m_toFile(false), m_fileDate(""), m_handle(INVALID_HANDLE) {}
                    ~CLogger() { if(m_handle != INVALID_HANDLE) FileClose(m_handle); }

   void Init(const string tag, const ENUM_FTMO_LOG level, const bool toFile)
     {
      m_tag = tag; m_level = level;
      // En el Strategy Tester no se escriben archivos para no ralentizar la prueba
      m_toFile = toFile && !(bool)MQLInfoInteger(MQL_TESTER);
      if(m_toFile) FolderCreate("FTMO_Logs");
     }

   void Log(const ENUM_FTMO_LOG lv, const string msg)
     {
      if(lv < m_level) return;
      string line = StringFormat("[%s][%s] %s", m_tag, LevelName(lv), msg);
      Print(line);
      if(m_toFile)
        {
         EnsureFile();
         if(m_handle != INVALID_HANDLE)
           {
            FileWrite(m_handle, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), m_tag, LevelName(lv), msg);
            FileFlush(m_handle);
           }
        }
     }

   void Debug(const string msg) { Log(FTLOG_DEBUG, msg); }
   void Info(const string msg)  { Log(FTLOG_INFO, msg); }
   void Warn(const string msg)  { Log(FTLOG_WARN, msg); }
   void Error(const string msg) { Log(FTLOG_ERROR, msg); }
  };

#endif
