//+------------------------------------------------------------------+
//| MT5_LiveExport.mq5 - Real-time data exporter for Dashboard       |
//| Exports LIVE OHLC data from your broker to JSON                  |
//+------------------------------------------------------------------+
#property copyright "(c)2025 Berelz Capital Engineering"
#property version   "1.0"
#property strict

#include <Trade\SymbolInfo.mqh>

//+------------------------------------------------------------------+
//| Input parameters                                                |
//+------------------------------------------------------------------+
input string   InpSymbol        = "XAUEUR";      // Symbol to export
input int      InpBarsCount     = 500;           // Number of bars to export
input int      InpUpdateSeconds = 5;             // Update interval (seconds)
input string   InpFileName      = "xaueur_live.json"; // Output filename

//+------------------------------------------------------------------+
//| Global variables                                                |
//+------------------------------------------------------------------+
datetime g_lastUpdate = 0;
string   g_symbol;

//+------------------------------------------------------------------+
//| Expert initialization                                           |
//+------------------------------------------------------------------+
int OnInit()
{
    // Determine symbol
    g_symbol = (InpSymbol == "") ? _Symbol : InpSymbol;

    // Check if symbol exists
    if(!SymbolSelect(g_symbol, true))
    {
        Print("ERROR: Symbol ", g_symbol, " not found in MarketWatch!");
        Print("Available symbols with XAU:");
        for(int i = 0; i < SymbolsTotal(false); i++)
        {
            string sym = SymbolName(i, false);
            if(StringFind(sym, "XAU") >= 0 || StringFind(sym, "GOLD") >= 0)
                Print("  - ", sym);
        }
        return INIT_FAILED;
    }

    // Initial export
    ExportData();

    Print("=== MT5 Live Export Started ===");
    Print("Symbol: ", g_symbol);
    Print("Bars: ", InpBarsCount);
    Print("Update: every ", InpUpdateSeconds, " seconds");
    Print("File: ", InpFileName);

    // Set timer for regular updates
    EventSetTimer(InpUpdateSeconds);

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("MT5 Live Export stopped");
}

//+------------------------------------------------------------------+
//| Timer function - exports data periodically                      |
//+------------------------------------------------------------------+
void OnTimer()
{
    ExportData();
}

//+------------------------------------------------------------------+
//| Tick function - exports on every tick for real-time price       |
//+------------------------------------------------------------------+
void OnTick()
{
    // Only update file every N seconds even if ticks come faster
    if(TimeCurrent() - g_lastUpdate >= InpUpdateSeconds)
    {
        ExportData();
    }
}

//+------------------------------------------------------------------+
//| Export all data to JSON file                                    |
//+------------------------------------------------------------------+
void ExportData()
{
    g_lastUpdate = TimeCurrent();

    // Get current price info
    MqlTick tick;
    if(!SymbolInfoTick(g_symbol, tick))
    {
        Print("ERROR: Cannot get tick for ", g_symbol);
        return;
    }

    // Open file for writing
    int handle = FileOpen(InpFileName, FILE_WRITE | FILE_TXT | FILE_ANSI);
    if(handle == INVALID_HANDLE)
    {
        Print("ERROR: Cannot open file ", InpFileName);
        return;
    }

    // Start JSON
    FileWriteString(handle, "{\n");

    // Symbol info
    FileWriteString(handle, StringFormat("  \"symbol\": \"%s\",\n", g_symbol));
    FileWriteString(handle, "  \"timeframe\": \"M5\",\n");
    FileWriteString(handle, StringFormat("  \"updated\": \"%s\",\n", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)));
    FileWriteString(handle, "  \"source\": \"MT5_LIVE\",\n");

    // Current prices
    FileWriteString(handle, StringFormat("  \"bid\": %.2f,\n", tick.bid));
    FileWriteString(handle, StringFormat("  \"ask\": %.2f,\n", tick.ask));
    FileWriteString(handle, StringFormat("  \"spread\": %.1f,\n", (tick.ask - tick.bid) / SymbolInfoDouble(g_symbol, SYMBOL_POINT)));

    // Daily stats
    FileWriteString(handle, StringFormat("  \"daily_high\": %.2f,\n", SymbolInfoDouble(g_symbol, SYMBOL_LASTHIGH)));
    FileWriteString(handle, StringFormat("  \"daily_low\": %.2f,\n", SymbolInfoDouble(g_symbol, SYMBOL_LASTLOW)));
    FileWriteString(handle, StringFormat("  \"daily_open\": %.2f,\n", iOpen(g_symbol, PERIOD_D1, 0)));

    // Volume
    FileWriteString(handle, StringFormat("  \"tick_volume\": %d,\n", (int)tick.volume));

    // Export M5 bars
    FileWriteString(handle, "  \"bars\": [\n");

    MqlRates rates[];
    ArraySetAsSeries(rates, true);
    int copied = CopyRates(g_symbol, PERIOD_M5, 0, InpBarsCount, rates);

    if(copied > 0)
    {
        // Write bars in chronological order (oldest first)
        for(int i = copied - 1; i >= 0; i--)
        {
            string timeStr = TimeToString(rates[i].time, TIME_DATE|TIME_SECONDS);
            StringReplace(timeStr, ".", "-");  // Format: 2025-01-07 12:00:00

            FileWriteString(handle, StringFormat(
                "    {\"time\": \"%s\", \"o\": %.2f, \"h\": %.2f, \"l\": %.2f, \"c\": %.2f, \"v\": %d}%s\n",
                timeStr,
                rates[i].open,
                rates[i].high,
                rates[i].low,
                rates[i].close,
                (int)rates[i].tick_volume,
                (i > 0 ? "," : "")
            ));
        }
    }

    FileWriteString(handle, "  ],\n");

    // Export H1 bars for trend analysis
    FileWriteString(handle, "  \"bars_h1\": [\n");

    MqlRates ratesH1[];
    ArraySetAsSeries(ratesH1, true);
    int copiedH1 = CopyRates(g_symbol, PERIOD_H1, 0, 100, ratesH1);

    if(copiedH1 > 0)
    {
        for(int i = copiedH1 - 1; i >= 0; i--)
        {
            string timeStr = TimeToString(ratesH1[i].time, TIME_DATE|TIME_SECONDS);
            StringReplace(timeStr, ".", "-");

            FileWriteString(handle, StringFormat(
                "    {\"time\": \"%s\", \"o\": %.2f, \"h\": %.2f, \"l\": %.2f, \"c\": %.2f, \"v\": %d}%s\n",
                timeStr,
                ratesH1[i].open,
                ratesH1[i].high,
                ratesH1[i].low,
                ratesH1[i].close,
                (int)ratesH1[i].tick_volume,
                (i > 0 ? "," : "")
            ));
        }
    }

    FileWriteString(handle, "  ],\n");

    // Export D1 bars for box theory
    FileWriteString(handle, "  \"bars_d1\": [\n");

    MqlRates ratesD1[];
    ArraySetAsSeries(ratesD1, true);
    int copiedD1 = CopyRates(g_symbol, PERIOD_D1, 0, 30, ratesD1);

    if(copiedD1 > 0)
    {
        for(int i = copiedD1 - 1; i >= 0; i--)
        {
            string timeStr = TimeToString(ratesD1[i].time, TIME_DATE|TIME_SECONDS);
            StringReplace(timeStr, ".", "-");

            FileWriteString(handle, StringFormat(
                "    {\"time\": \"%s\", \"o\": %.2f, \"h\": %.2f, \"l\": %.2f, \"c\": %.2f, \"v\": %d}%s\n",
                timeStr,
                ratesD1[i].open,
                ratesD1[i].high,
                ratesD1[i].low,
                ratesD1[i].close,
                (int)ratesD1[i].tick_volume,
                (i > 0 ? "," : "")
            ));
        }
    }

    FileWriteString(handle, "  ],\n");

    // Account info
    FileWriteString(handle, "  \"account\": {\n");
    FileWriteString(handle, StringFormat("    \"balance\": %.2f,\n", AccountInfoDouble(ACCOUNT_BALANCE)));
    FileWriteString(handle, StringFormat("    \"equity\": %.2f,\n", AccountInfoDouble(ACCOUNT_EQUITY)));
    FileWriteString(handle, StringFormat("    \"margin\": %.2f,\n", AccountInfoDouble(ACCOUNT_MARGIN)));
    FileWriteString(handle, StringFormat("    \"free_margin\": %.2f,\n", AccountInfoDouble(ACCOUNT_MARGIN_FREE)));
    FileWriteString(handle, StringFormat("    \"profit\": %.2f,\n", AccountInfoDouble(ACCOUNT_PROFIT)));
    FileWriteString(handle, StringFormat("    \"leverage\": %d,\n", (int)AccountInfoInteger(ACCOUNT_LEVERAGE)));
    FileWriteString(handle, StringFormat("    \"currency\": \"%s\"\n", AccountInfoString(ACCOUNT_CURRENCY)));
    FileWriteString(handle, "  },\n");

    // Broker info
    FileWriteString(handle, "  \"broker\": {\n");
    FileWriteString(handle, StringFormat("    \"name\": \"%s\",\n", AccountInfoString(ACCOUNT_COMPANY)));
    FileWriteString(handle, StringFormat("    \"server\": \"%s\"\n", AccountInfoString(ACCOUNT_SERVER)));
    FileWriteString(handle, "  }\n");

    // Close JSON
    FileWriteString(handle, "}\n");

    FileClose(handle);

    // Log update
    static datetime lastLog = 0;
    if(TimeCurrent() - lastLog >= 60) // Log every minute
    {
        PrintFormat("EXPORT: %s @ %.2f/%.2f | %d M5 bars | %s",
                   g_symbol, tick.bid, tick.ask, copied,
                   TimeToString(TimeCurrent(), TIME_SECONDS));
        lastLog = TimeCurrent();
    }
}
//+------------------------------------------------------------------+
