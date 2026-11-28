// TradingLabBridge.cs · FUT-J4 · NO COMPILADO NI PROBADO (escrito en un contenedor sin NinjaTrader).
// Pendiente: compilar en NinjaTrader 8 (NinjaScript Editor) y probar SOLO en Sim101 o Playback.
// Lee intents de <Documentos>\TradingLab\nt8_bridge\outbox, los envía con el enfoque NO gestionado
// (SubmitOrderUnmanaged + stop y objetivo OCO) y escribe un ack en inbox. Rechaza cualquier cuenta que
// no empiece por "Sim" o "Playback" y cualquier intent por encima de MaxContracts.
#region Using declarations
using System;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class TradingLabBridge : Strategy
    {
        private string outbox, inbox;
        private DateTime lastPoll = DateTime.MinValue;

        [NinjaScriptProperty] public string BridgeDir { get; set; }
        [NinjaScriptProperty] public int MaxContracts { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "TradingLabBridge";
                Calculate = Calculate.OnEachTick;
                IsUnmanaged = true;                       // solo métodos no gestionados
                BridgeDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                                         "TradingLab", "nt8_bridge");
                MaxContracts = 5;
            }
            else if (State == State.Configure)
            {
                outbox = Path.Combine(BridgeDir, "outbox");
                inbox = Path.Combine(BridgeDir, "inbox");
                Directory.CreateDirectory(outbox);
                Directory.CreateDirectory(inbox);
            }
            else if (State == State.DataLoaded)
            {
                string acct = Account.Name ?? "";
                if (!(acct.StartsWith("Sim") || acct.StartsWith("Playback")))
                    throw new Exception("TradingLabBridge solo funciona en cuentas Sim o Playback (cuenta: " + acct + ")");
            }
        }

        protected override void OnBarUpdate()
        {
            if (State != State.Realtime || (DateTime.Now - lastPoll).TotalSeconds < 1) return;
            lastPoll = DateTime.Now;
            foreach (string file in Directory.GetFiles(outbox, "*.json"))
            {
                string id = Path.GetFileNameWithoutExtension(file);
                string ack;
                try
                {
                    var json = File.ReadAllText(file);
                    int qty = int.Parse(Extract(json, "qty"));
                    string side = Extract(json, "side");
                    double stop = double.Parse(Extract(json, "stop_price"), System.Globalization.CultureInfo.InvariantCulture);
                    if (qty < 1 || qty > MaxContracts) throw new Exception("qty fuera de límites");
                    var action = side == "buy" ? OrderAction.Buy : OrderAction.SellShort;
                    var exitAction = side == "buy" ? OrderAction.Sell : OrderAction.BuyToCover;
                    string oco = "TL-" + id;
                    SubmitOrderUnmanaged(0, action, OrderType.Market, qty, 0, 0, "", "TL-entry-" + id);
                    SubmitOrderUnmanaged(0, exitAction, OrderType.StopMarket, qty, 0, stop, oco, "TL-stop-" + id);
                    string target = Extract(json, "target_price");
                    if (target != "null" && target != "")
                        SubmitOrderUnmanaged(0, exitAction, OrderType.Limit, qty,
                            double.Parse(target, System.Globalization.CultureInfo.InvariantCulture), 0, oco, "TL-target-" + id);
                    ack = "{\"intent_id\":\"" + id + "\",\"status\":\"submitted_sim\",\"account\":\"" + Account.Name + "\"}";
                }
                catch (Exception ex)
                {
                    ack = "{\"intent_id\":\"" + id + "\",\"status\":\"rejected\",\"error\":\"" + ex.Message.Replace("\"", "'") + "\"}";
                }
                File.WriteAllText(Path.Combine(inbox, id + ".ack.json"), ack);
                File.Move(file, file + ".done");
            }
        }

        // Extractor mínimo de un campo plano del JSON del puente (sin dependencias externas).
        private static string Extract(string json, string key)
        {
            int i = json.IndexOf("\"" + key + "\":", StringComparison.Ordinal);
            if (i < 0) return "";
            int s = i + key.Length + 3;
            while (s < json.Length && json[s] == ' ') s++;
            bool quoted = json[s] == '"';
            if (quoted) s++;
            int e = s;
            while (e < json.Length && (quoted ? json[e] != '"' : json[e] != ',' && json[e] != '}')) e++;
            return json.Substring(s, e - s).Trim();
        }
    }
}
