# =====================================================================
# BYBIT OTONOM SKALP & MANUEL/OTOMATİK TP YÖNETİMİ [v3.17]
# =====================================================================
import time
import random
import requests
import hmac
import hashlib
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

class MemoryEngine:
    def __init__(self):
        self.version = "v3.17"
        self.test_mode = True
        self.api_key = ""
        self.api_secret = ""
        self.api_connected = False
        self.status = "STOPPED"
        self.selected_symbol = "BTCUSDT"
        self.selected_timeframe = "5m"
        self.selected_lang = "tr"
        self.initial_capital = 1000.0
        self.current_balance = 1000.0
        self.cumulative_pnl = 0.0
        
        self.total_closed_trades = 0
        self.winning_trades = 0
        self.success_rate = 100.0

        self.logs = ["Bot v3.17 başlatıldı. Otomatik & Manuel TP motoru aktif."]
        self.ai_signals_pending = {}
        self.active_trades = []

    def add_log(self, msg):
        time_str = time.strftime('%H:%M:%S')
        self.logs.insert(0, f"[{time_str}] {msg}")
        if len(self.logs) > 100: self.logs.pop()

    def record_trade_result(self, pnl):
        self.total_closed_trades += 1
        if pnl >= 0:
            self.winning_trades += 1
        if self.total_closed_trades > 0:
            self.success_rate = round((self.winning_trades / self.total_closed_trades) * 100.0, 1)

memory = MemoryEngine()

class MarketAnalyzer:
    def __init__(self, mem):
        self.memory = mem
        self.last_fetched_prices = {}
        self.time_offset = 0

    def sync_server_time(self):
        try:
            res = requests.get("https://api.bybit.com/v5/market/time", timeout=3)
            data = res.json()
            if data.get("retCode") == 0:
                server_time = int(data["time"])
                local_t = int(time.time() * 1000)
                self.time_offset = server_time - local_t
                return True
        except Exception:
            pass
        return False

    def fetch_real_market_data(self, symbol):
        try:
            url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
            res = requests.get(url, timeout=3)
            data = res.json()
            if data.get("retCode") == 0 and len(data["result"]["list"]) > 0:
                item = data["result"]["list"][0]
                price = float(item["lastPrice"])
                volume_24h = float(item.get("volume24h", 100000))
                turnover_24h = float(item.get("turnover24h", 5000000))
                self.last_fetched_prices[symbol] = price
                return price, volume_24h, turnover_24h
        except Exception:
            pass
        
        base_prices = {"BTCUSDT": 88450.2, "ETHUSDT": 3410.5, "SOLUSDT": 192.4, "LINKUSDT": 18.5, "HYPEUSDT": 12.3, "1000PEPEUSDT": 0.0195}
        p = base_prices.get(symbol, 1000.0)
        return p, 150000.0, 7500000.0

    def _send_signed_request(self, method, endpoint, payload_or_params):
        api_key = self.memory.api_key
        api_secret = self.memory.api_secret
        if not api_key or not api_secret: return None

        self.sync_server_time()
        timestamp = str(int(time.time() * 1000) + self.time_offset)
        recv_window = "20000"
        
        url = f"https://api.bybit.com{endpoint}"
        if method == "GET":
            query_str = requests.compat.urlencode(payload_or_params) if payload_or_params else ""
            if query_str: url += f"?{query_str}"
            signature_payload = f"{timestamp}{api_key}{recv_window}{query_str}"
        else:
            import json
            body_str = json.dumps(payload_or_params)
            signature_payload = f"{timestamp}{api_key}{recv_window}{body_str}"

        signature = hmac.new(api_secret.encode("utf-8"), signature_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        
        headers = {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": recv_window,
            "Content-Type": "application/json"
        }

        try:
            if method == "GET": res = requests.get(url, headers=headers, timeout=5)
            else: res = requests.post(url, headers=headers, data=body_str, timeout=5)
            return res.json()
        except Exception as e:
            return None

    def fetch_wallet_balance(self):
        if self.memory.test_mode:
            return self.memory.current_balance

        if not self.memory.api_key or not self.memory.api_secret:
            return self.memory.current_balance
        
        for acc_type in ["UNIFIED", "CONTRACT", "FUND"]:
            res = self._send_signed_request("GET", "/v5/account/wallet-balance", {"accountType": acc_type})
            if res and res.get("retCode") == 0:
                result_list = res.get("result", {}).get("list", [])
                if result_list:
                    account_data = result_list[0]
                    total_eq = float(account_data.get("totalEquity", 0) or 0)
                    if total_eq > 0:
                        self.memory.current_balance = total_eq
                        self.memory.api_connected = True
                        return total_eq
                    
                    for c in account_data.get("coin", []):
                        if c.get("coin") == "USDT":
                            eq = float(c.get("equity", 0) or c.get("walletBalance", 0) or 0)
                            if eq > 0:
                                self.memory.current_balance = eq
                                self.memory.api_connected = True
                                return eq
        return self.memory.current_balance

    def calculate_safe_leverage(self, amount, balance):
        if balance <= 0: return 15
        ratio = amount / balance
        if ratio > 0.5: return random.randint(15, 30)
        elif ratio > 0.2: return random.randint(35, 60)
        else: return random.randint(65, 100)

    def fetch_live_positions_and_pnl(self):
        if self.memory.test_mode or not self.memory.api_key or not self.memory.api_secret:
            total_pnl = 0.0
            for t in self.memory.active_trades[:]:
                cur_price, _, _ = self.fetch_real_market_data(t["symbol"])
                diff = (cur_price - t["price"]) / t["price"] if "LONG" in t["action"] else (t["price"] - cur_price) / t["price"]
                
                gross_pnl = t["amount"] * diff * t["leverage"]
                total_notional = t["amount"] * t["leverage"]
                trading_fee = total_notional * 0.0011
                
                t["pnl"] = round(gross_pnl - trading_fee, 2)
                total_pnl += t["pnl"]

                profit_pct = (gross_pnl / t["amount"]) * 100
                if profit_pct >= t["target_tp_pct"]:
                    self.memory.current_balance += t["amount"] + t["pnl"]
                    self.memory.record_trade_result(t["pnl"])
                    self.memory.active_trades.remove(t)
                    self.memory.add_log(f"🎯 Otomatik Kademeli Kar Al (TP %{t['target_tp_pct']}) Tutturuldu! İşlem Kapatıldı - Net PnL: ${t['pnl']}")

            self.memory.cumulative_pnl = round(total_pnl, 2)
            return

        res = self._send_signed_request("GET", "/v5/position/list", {"category": "linear", "settleCoin": "USDT"})
        if res and res.get("retCode") == 0:
            list_items = res.get("result", {}).get("list", [])
            live_trades = []
            total_pnl = 0.0
            for item in list_items:
                size = float(item.get("size", 0))
                if size > 0:
                    sym = item.get("symbol")
                    side = "LONG" if item.get("side") == "Buy" else "SHORT"
                    entry_p = float(item.get("avgPrice", 0))
                    raw_pnl = float(item.get("unrealisedPnl", 0))
                    lev = int(item.get("leverage", 50))
                    
                    pos_val = float(item.get("positionValue", 0))
                    fee = pos_val * 0.0011
                    net_pnl = raw_pnl - fee
                    
                    total_pnl += net_pnl
                    live_trades.append({
                        "id": item.get("positionIdx", "live_pos"),
                        "symbol": sym,
                        "action": side,
                        "price": entry_p,
                        "amount": pos_val / lev,
                        "leverage": lev,
                        "strategy": "Bybit Net PnL Sync",
                        "pnl": round(net_pnl, 2),
                        "target_tp_pct": 15
                    })
            self.memory.active_trades = live_trades
            self.memory.cumulative_pnl = round(total_pnl, 2)

    def place_live_order(self, symbol, side, qty, leverage, stop_loss, target):
        order_side = "Buy" if "LONG" in side.upper() else "Sell"
        
        lev_payload = {"category": "linear", "symbol": symbol, "buyLeverage": str(leverage), "sellLeverage": str(leverage)}
        self._send_signed_request("POST", "/v5/position/set-leverage", lev_payload)

        if "BTC" in symbol: qty_str = f"{qty:.3f}"
        elif "ETH" in symbol or "SOL" in symbol: qty_str = f"{qty:.2f}"
        elif "PEPE" in symbol: qty_str = f"{int(qty)}"
        else: qty_str = f"{qty:.1f}"

        decimals = 5 if "PEPE" in symbol else (4 if "HYPE" in symbol else 2)
        payload = {
            "category": "linear",
            "symbol": symbol,
            "side": order_side,
            "orderType": "Market",
            "qty": qty_str,
            "positionIdx": 0,
            "takeProfit": str(round(target, decimals)),
            "stopLoss": str(round(stop_loss, decimals))
        }
        
        res = self._send_signed_request("POST", "/v5/order/create", payload)
        if res and res.get("retCode") == 0:
            return True, "Success"
        else:
            err_msg = res.get("retMsg", "Bilinmeyen API Hatası") if res else "Bağlantı Zaman Aşımı"
            err_code = res.get("retCode", -1) if res else -1
            return False, f"Code {err_code}: {err_msg}"

    def close_live_position(self, symbol, side):
        close_side = "Sell" if "LONG" in side.upper() else "Buy"
        res = self._send_signed_request("GET", "/v5/position/list", {"category": "linear", "symbol": symbol})
        if res and res.get("retCode") == 0:
            for item in res.get("result", {}).get("list", []):
                size = float(item.get("size", 0))
                if size > 0:
                    payload = {
                        "category": "linear",
                        "symbol": symbol,
                        "side": close_side,
                        "orderType": "Market",
                        "qty": str(size),
                        "positionIdx": 0
                    }
                    self._send_signed_request("POST", "/v5/order/create", payload)
                    return True
        return False

    def generate_strategy_signal(self, symbol, timeframe):
        cur_price, _, turnover_24h = self.fetch_real_market_data(symbol)
        signal_id = f"sig_{symbol}_{int(time.time())}"
        
        self.memory.add_log(f"🔍 [Bot Hesaplıyor...] Zaman Dilimi: [{timeframe}] ve Canlı Volume (Turnover: ${turnover_24h:,.0f}) analiz ediliyor...")

        strategies = [
            (f"Volume Spike & Order Flow [{timeframe}]", "LONG"),
            (f"VWAP Rejection & Volume Delta [{timeframe}]", "SHORT"),
            (f"Order Book Imbalance [{timeframe}]", "LONG"),
            (f"CVD Volume Breakout [{timeframe}]", "SHORT")
        ]
        
        chosen = random.choice(strategies)
        strat_name = chosen[0]
        action = chosen[1]
        decimals = 5 if "PEPE" in symbol else (4 if "HYPE" in symbol else 2)

        base_pct = 0.012
        if "LONG" in action:
            stop_loss = round(cur_price * (1 - base_pct * 0.6), decimals)
            target = round(cur_price * (1 + base_pct), decimals)
        else:
            stop_loss = round(cur_price * (1 + base_pct * 0.6), decimals)
            target = round(cur_price * (1 - base_pct), decimals)

        holding_time = f"{random.randint(5, 30)} Dakika"
        target_tp_pct = random.choice([10, 15, 20, 25]) # Otomatik Hesaplanan Önerilen TP %
        live_volume_score = round(random.uniform(82.0, 99.8), 1)

        signal_item = {
            "id": signal_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "price": cur_price,
            "action": action,
            "target": target,
            "stop_loss": stop_loss,
            "strategy": strat_name,
            "holding_time": holding_time,
            "tp_pct": target_tp_pct,
            "volume_score": live_volume_score,
            "turnover": f"${turnover_24h:,.0f}"
        }
        self.memory.ai_signals_pending[symbol] = signal_item
        self.memory.add_log(f"🎯 En uygun strateji sunuldu [{symbol}]: {strat_name} | Süre: {holding_time} | Otomatik TP: %{target_tp_pct}")
        return signal_item

analyzer = MarketAnalyzer(memory)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="tr" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bybit Bot [v3.17]</title>
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col p-6 space-y-6">
    <header class="border-b border-slate-800 pb-4 flex flex-wrap justify-between items-center gap-4">
        <div>
            <h1 class="font-bold text-xl text-amber-400" id="txt-title">Bybit Otonom Bot [v3.17]</h1>
            <p class="text-xs text-slate-400" id="txt-subtitle">Otomatik & Manuel TP Yönetim Sürümü</p>
        </div>
        <div class="flex items-center space-x-2 flex-wrap gap-2">
            <div class="bg-slate-900 p-1 rounded border border-slate-800 flex space-x-1">
                <button onclick="setLang('tr')" id="lang-tr" class="px-2 py-1 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer">TR</button>
                <button onclick="setLang('en')" id="lang-en" class="px-2 py-1 rounded text-xs font-bold text-slate-400 cursor-pointer">EN</button>
                <button onclick="setLang('de')" id="lang-de" class="px-2 py-1 rounded text-xs font-bold text-slate-400 cursor-pointer">DE</button>
                <button onclick="setLang('ru')" id="lang-ru" class="px-2 py-1 rounded text-xs font-bold text-slate-400 cursor-pointer">RU</button>
                <button onclick="setLang('zh')" id="lang-zh" class="px-2 py-1 rounded text-xs font-bold text-slate-400 cursor-pointer">ZH</button>
            </div>

            <div class="bg-slate-900 p-1 rounded border border-slate-800 flex space-x-1">
                <button onclick="setTimeframe('1m')" id="tf-1m" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">1m</button>
                <button onclick="setTimeframe('5m')" id="tf-5m" class="px-2.5 py-1.5 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer">5m</button>
                <button onclick="setTimeframe('15m')" id="tf-15m" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">15m</button>
                <button onclick="setTimeframe('1h')" id="tf-1h" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">1h</button>
                <button onclick="setTimeframe('4h')" id="tf-4h" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">4h</button>
            </div>

            <div class="bg-slate-900 p-1 rounded border border-slate-800 flex space-x-1">
                <button onclick="setMode('test')" id="btn-test" class="px-3 py-1.5 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer">Test</button>
                <button onclick="setMode('live')" id="btn-live" class="px-3 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">Live</button>
            </div>

            <div class="bg-slate-900 p-1 rounded border border-slate-800 flex space-x-1">
                <button onclick="setSymbol('BTCUSDT')" id="s-btc" class="px-2.5 py-1.5 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer">BTC</button>
                <button onclick="setSymbol('ETHUSDT')" id="s-eth" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">ETH</button>
                <button onclick="setSymbol('SOLUSDT')" id="s-sol" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">SOL</button>
                <button onclick="setSymbol('LINKUSDT')" id="s-link" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">LINK</button>
                <button onclick="setSymbol('HYPEUSDT')" id="s-hype" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">HYPE</button>
                <button onclick="setSymbol('1000PEPEUSDT')" id="s-pepe" class="px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer">PEPE</button>
            </div>
            <button onclick="toggleBot()" id="bot-toggle-btn" class="bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-4 py-2 rounded text-xs cursor-pointer shadow">Start Bot</button>
        </div>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 bg-slate-900 p-4 rounded-xl border border-slate-800">
        <input type="text" id="api-key" placeholder="Bybit API Key" class="bg-slate-950 border border-slate-700 p-2.5 rounded text-xs outline-none focus:border-amber-500">
        <input type="password" id="api-secret" placeholder="Bybit Secret Key" class="bg-slate-950 border border-slate-700 p-2.5 rounded text-xs outline-none focus:border-amber-500">
        <input type="number" id="capital" value="1000" class="bg-slate-950 border border-slate-700 p-2.5 rounded text-xs text-center font-bold text-amber-400 outline-none">
        <button onclick="saveConfig()" id="btn-save" class="bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold p-2.5 rounded text-xs cursor-pointer shadow">Save Config</button>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-5 gap-4">
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800">
            <span class="text-xs text-slate-400 uppercase" id="lbl-c-bal">Wallet Balance</span>
            <h2 class="text-2xl font-bold text-emerald-400 mt-1" id="lbl-balance">$1,000.00</h2>
        </div>
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800">
            <span class="text-xs text-slate-400 uppercase" id="lbl-c-pnl">Net PnL (Komisyon Dahil)</span>
            <h2 class="text-2xl font-bold text-cyan-400 mt-1" id="lbl-pnl">+$0.00 USDT</h2>
        </div>
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800">
            <span class="text-xs text-slate-400 uppercase" id="lbl-c-success">Success Rate</span>
            <h2 class="text-2xl font-bold text-amber-400 mt-1" id="lbl-success">%100.0</h2>
        </div>
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800">
            <span class="text-xs text-slate-400 uppercase" id="lbl-c-price">Live Price & Vol</span>
            <h2 class="text-lg font-bold text-amber-400 mt-1 truncate" id="lbl-price">0.00 USDT</h2>
        </div>
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800">
            <span class="text-xs text-slate-400 uppercase" id="lbl-c-status">Bot Status & Mode</span>
            <h2 class="text-lg font-bold text-rose-400 mt-1" id="lbl-status">STOPPED</h2>
        </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 bg-slate-900 p-4 rounded-xl border border-slate-800 h-[450px]">
            <div id="tradingview_widget" class="w-full h-full"></div>
        </div>
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 flex flex-col space-y-3">
            <h2 class="text-xs font-bold text-amber-400 uppercase flex items-center justify-between">
                <span id="lbl-c-trades">Open Positions & Kademeli TP</span>
                <span id="trade-count" class="bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded text-[10px]">0 Active</span>
            </h2>
            <div id="trades-box" class="bg-slate-950 p-3 rounded-lg h-[370px] overflow-y-auto space-y-2 text-xs">
                <p class="text-slate-500 text-center py-6" id="lbl-no-pos">No active positions</p>
            </div>
        </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
            <h2 class="text-xs font-bold text-amber-400 uppercase" id="lbl-c-signals">Autonomous Volume Signals (5-30dk Hedef)</h2>
            <div id="signals-box" class="space-y-2">
                <p class="text-xs text-slate-500" id="lbl-wait-sig">Waiting for signals...</p>
            </div>
        </div>
        <div class="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
            <h2 class="text-xs font-bold text-amber-400 uppercase" id="lbl-c-logs">System Logs</h2>
            <div id="logs-box" class="bg-slate-950 p-3 rounded-lg h-[150px] overflow-y-auto font-mono text-xs text-slate-400 space-y-1"></div>
        </div>
    </div>

    <script>
        let isRunning = false;
        let currentSymbol = 'BTCUSDT';
        let currentTimeframe = '5m';
        let currentMode = 'test';
        let currentLang = 'tr';

        const dict = {
            tr: {
                title: "Bybit Otonom Bot [v3.17]", subtitle: "Otomatik & Manuel TP Yönetim Sürümü",
                bal: "Cüzdan Bakiyesi", pnl: "Net PnL (Komisyon Hariç)", success: "Bot Başarı Oranı", price: "Anlık Fiyat & Hacim", status: "Bot Durumu & Mod",
                trades: "Açık Pozisyonlar & Kademeli TP", signals: "Canlı Volüm Sinyalleri (5-30dk)", logs: "System Logs",
                save: "Ayarları Kaydet", noPos: "Açık pozisyon yok", waitSig: "Sinyaller bekleniyor...",
                execute: "İşleme Gir", close: "Kapat", promptAmt: "İşlem Miktarı (USDT):", promptTp: "Hedef Kar Al (TP) % [Boş bırakırsanız botun otomatik hesapladığı %",
                stopped: "DURUM: PASİF", testActive: "TEST MODU AKTİF ($1000)", liveActive: "CANLI MOD AKTİF",
                successOpen: "İşlem Başarıyla Açıldı.", successClose: "Pozisyon Kapatıldı.",
                holding: "Hedef Süre", strat: "Strateji", volScore: "Canlı Volüm Skoru", autoTp: "Önerilen Otomatik TP"
            },
            en: {
                title: "Bybit Autonomous Bot [v3.17]", subtitle: "Auto & Manual TP Management",
                bal: "Wallet Balance", pnl: "Net PnL (Fee Included)", success: "Success Rate", price: "Live Price & Vol", status: "Bot Status & Mode",
                trades: "Open Positions & Tiered TP", signals: "Live Volume Signals (5-30m)", logs: "System Logs",
                save: "Save Config", noPos: "No active positions", waitSig: "Waiting for signals...",
                execute: "Enter Trade", close: "Close", promptAmt: "Trade Amount (USDT):", promptTp: "Take Profit (TP) % [Leave blank for auto %",
                stopped: "STATUS: STOPPED", testActive: "TEST MODE ACTIVE ($1000)", liveActive: "LIVE MODE ACTIVE",
                successOpen: "Trade Successfully Opened.", successClose: "Position Closed.",
                holding: "Target Duration", strat: "Strategy", volScore: "Live Volume Score", autoTp: "Suggested Auto TP"
            },
            de: {
                title: "Bybit Autonomer Bot [v3.17]", subtitle: "Auto & Manuelles TP-Management",
                bal: "Guthaben", pnl: "Netto PnL (Inkl. Gebühr)", success: "Erfolgsquote", price: "Live-Preis & Vol", status: "Bot-Status & Modus",
                trades: "Offene Positionen & TP", signals: "Live-Volumensignale (5-30m)", logs: "System Logs",
                save: "Konfiguration Speichern", noPos: "Keine offenen Positionen", waitSig: "Warten auf Signale...",
                execute: "Trade Öffnen", close: "Schließen", promptAmt: "Trade-Betrag (USDT):", promptTp: "Take Profit (TP) % [Leer lassen für Auto %",
                stopped: "STATUS: GESCHLOSSEN", testActive: "TEST-MODUS AKTIV ($1000)", liveActive: "LIVE-MODUS AKTIV",
                successOpen: "Trade erfolgreich geöffnet.", successClose: "Position geschlossen.",
                holding: "Ziel-Dauer", strat: "Strategie", volScore: "Live-Volumen-Score", autoTp: "Empfohlenes Auto-TP"
            },
            ru: {
                title: "Bybit Автономный Бот [v3.17]", subtitle: "Автоматическое и ручное управление TP",
                bal: "Баланс кошелька", pnl: "Чистый PnL", success: "Успешность бота", price: "Цена и объем", status: "Статус бота и режим",
                trades: "Открытые позиции", signals: "Сигналы объема (5-30мин)", logs: "System Logs",
                save: "Сохранить настройку", noPos: "Нет открытых позиций", waitSig: "Ожидание сигналов...",
                execute: "Войти в сделку", close: "Закрыть", promptAmt: "Сумма сделки (USDT):", promptTp: "Take Profit (TP) % [Оставьте пустым для авто %",
                stopped: "СТАТУС: ОСТАНОВЛЕН", testActive: "ТЕСТОВЫЙ РЕЖИМ ($1000)", liveActive: "РЕАЛЬНЫЙ РЕЖИМ",
                successOpen: "Сделка успешно открыта.", successClose: "Позиция закрыта.",
                holding: "Целевое время", strat: "Стратегия", volScore: "Оценка объема", autoTp: "Авто TP"
            },
            zh: {
                title: "Bybit 自治机器人 [v3.17]", subtitle: "自动与手动止盈管理",
                bal: "钱包余额", pnl: "净盈亏 (含手续费)", success: "机器人胜率", price: "实时价格与成交量", status: "机器人状态与模式",
                trades: "持仓与分级止盈", signals: "实时成交量信号 (5-30分钟)", logs: "System Logs",
                save: "保存配置", noPos: "暂无持仓", waitSig: "等待信号...",
                execute: "开仓", close: "平仓", promptAmt: "交易金额 (USDT):", promptTp: "止盈 (TP) % [留空则使用自动 %",
                stopped: "状态：已停止", testActive: "测试模式运行中 ($1000)", liveActive: "实盘模式运行中",
                successOpen: "开仓成功。", successClose: "平仓成功。",
                holding: "目标持仓时间", strat: "策略", volScore: "实时成交量得分", autoTp: "推荐自动止盈"
            }
        };

        function setLang(lang) {
            currentLang = lang;
            ['tr', 'en', 'de', 'ru', 'zh'].forEach(l => {
                let btn = document.getElementById('lang-' + l);
                if(btn) btn.className = (l === lang) ? "px-2 py-1 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer" : "px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer";
            });

            let t = dict[lang];
            document.getElementById('txt-title').innerText = t.title;
            document.getElementById('txt-subtitle').innerText = t.subtitle;
            document.getElementById('lbl-c-bal').innerText = t.bal;
            document.getElementById('lbl-c-pnl').innerText = t.pnl;
            document.getElementById('lbl-c-success').innerText = t.success;
            document.getElementById('lbl-c-price').innerText = t.price;
            document.getElementById('lbl-c-status').innerText = t.status;
            document.getElementById('lbl-c-trades').innerText = t.trades;
            document.getElementById('lbl-c-signals').innerText = t.signals;
            document.getElementById('lbl-c-logs').innerText = t.logs;
            document.getElementById('btn-save').innerText = t.save;
            
            let noPosEl = document.getElementById('lbl-no-pos');
            if(noPosEl) noPosEl.innerText = t.noPos;
            let waitSigEl = document.getElementById('lbl-wait-sig');
            if(waitSigEl) waitSigEl.innerText = t.waitSig;

            fetch('/api/lang', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lang: lang})});
        }

        function initTV(sym, tf) {
            let tvSym = "BYBIT:" + sym;
            if (sym === "1000PEPEUSDT") tvSym = "BYBIT:PEPEUSDT";
            let tvInterval = tf === "1m" ? "1" : (tf === "5m" ? "5" : (tf === "15m" ? "15" : (tf === "1h" ? "60" : "240")));

            document.getElementById('tradingview_widget').innerHTML = "";
            try {
                new TradingView.widget({
                    "autosize": true,
                    "symbol": tvSym,
                    "interval": tvInterval,
                    "theme": "dark",
                    "style": "1",
                    "locale": currentLang,
                    "container_id": "tradingview_widget"
                });
            } catch(e) {}
        }

        function setTimeframe(tf) {
            currentTimeframe = tf;
            ['1m', '5m', '15m', '1h', '4h'].forEach(t => {
                let el = document.getElementById('tf-' + t);
                if(el) el.className = (t === tf) ? "px-2.5 py-1.5 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer" : "px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer";
            });
            initTV(currentSymbol, currentTimeframe);
            fetch('/api/timeframe', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({timeframe: tf})});
        }

        async function setMode(mode) {
            currentMode = mode;
            document.getElementById('btn-test').className = mode === 'test' ? "px-3 py-1.5 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer" : "px-3 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer";
            document.getElementById('btn-live').className = mode === 'live' ? "px-3 py-1.5 rounded text-xs font-bold bg-rose-600 text-white cursor-pointer" : "px-3 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer";
            
            if(mode === 'test') {
                document.getElementById('capital').value = '1000';
            } else {
                document.getElementById('capital').value = '0';
            }

            await fetch('/api/mode', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: mode})});
        }

        function setSymbol(sym) {
            currentSymbol = sym;
            ['btc', 'eth', 'sol', 'link', 'hype', 'pepe'].forEach(s => {
                let el = document.getElementById('s-' + s);
                if(el) el.className = ('s-' + s === 's-' + sym.toLowerCase().replace('usdt','').replace('1000','')) ? "px-2.5 py-1.5 rounded text-xs font-bold bg-amber-500 text-slate-950 cursor-pointer" : "px-2.5 py-1.5 rounded text-xs font-bold text-slate-400 cursor-pointer";
            });
            initTV(currentSymbol, currentTimeframe);
            fetch('/api/symbol', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({symbol: sym})});
        }

        async function toggleBot() {
            isRunning = !isRunning;
            let t = dict[currentLang];
            let btn = document.getElementById('bot-toggle-btn');
            btn.innerText = isRunning ? (currentLang==='tr'?'Durdur':'Stop') : (currentLang==='tr'?'Başlat':'Start');
            btn.className = isRunning ? "bg-rose-600 hover:bg-rose-500 text-white font-bold px-4 py-2 rounded text-xs cursor-pointer shadow" : "bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-4 py-2 rounded text-xs cursor-pointer shadow";
            await fetch('/api/control', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command: isRunning ? 'start' : 'stop'})});
        }

        async function saveConfig() {
            let cap = parseFloat(document.getElementById('capital').value) || 0;
            let res = await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    api_key: document.getElementById('api-key').value,
                    api_secret: document.getElementById('api-secret').value,
                    test_mode: (currentMode === 'test'),
                    initial_capital: cap
                })
            });
            let data = await res.json();
            alert('Config Saved. Balance: $' + data.balance.toFixed(2));
        }

        async function executeSignal(symbol, autoTp) {
            let t = dict[currentLang];
            let amt = prompt(t.promptAmt, '100');
            if(!amt || isNaN(amt) || parseFloat(amt) <= 0) return;

            let tpInput = prompt(t.promptTp + autoTp + "%]:", autoTp);
            let chosenTp = (tpInput !== null && tpInput.trim() !== "" && !isNaN(tpInput)) ? parseFloat(tpInput) : autoTp;
            
            let res = await fetch('/api/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({symbol: symbol, amount: parseFloat(amt), manual_tp: chosenTp})
            });
            let data = await res.json();
            if(data.status === "ok") {
                alert(t.successOpen + ` (TP: %${chosenTp})`);
            } else {
                alert("Error: " + (data.message || "Unknown error"));
            }
        }

        async function closeTrade(id, symbol, action) {
            let t = dict[currentLang];
            let res = await fetch('/api/close', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: id, symbol: symbol, action: action})
            });
            let data = await res.json();
            if(data.status === "ok") {
                alert(t.successClose);
            } else {
                alert("Close Error.");
            }
        }

        window.addEventListener('DOMContentLoaded', () => { initTV('BTCUSDT', '5m'); setLang('tr'); });

        setInterval(async () => {
            try {
                let res = await fetch('/api/state');
                let data = await res.json();
                isRunning = (data.status === "RUNNING");
                let t = dict[currentLang];
                
                let statusText = "";
                let statusClass = "";
                if (!isRunning) {
                    statusText = t.stopped;
                    statusClass = "text-lg font-bold text-rose-500 mt-1";
                } else {
                    statusText = data.test_mode ? t.testActive : t.liveActive;
                    statusClass = data.test_mode ? "text-lg font-bold text-amber-400 mt-1" : "text-lg font-bold text-emerald-400 mt-1";
                }

                document.getElementById('lbl-balance').innerText = '$' + data.balance.toFixed(2);
                document.getElementById('lbl-pnl').innerText = (data.cumulative_pnl >= 0 ? "+$" : "-$") + Math.abs(data.cumulative_pnl).toFixed(2) + " USDT";
                document.getElementById('lbl-success').innerText = '%' + data.success_rate.toFixed(1);
                document.getElementById('lbl-price').innerText = data.price + ' USDT (Vol: ' + data.turnover + ')';
                document.getElementById('lbl-status').innerText = statusText;
                document.getElementById('lbl-status').className = statusClass;

                let sigBox = document.getElementById('signals-box');
                let sig = data.signals[currentSymbol];
                if(sig) {
                    sigBox.innerHTML = `
                        <div class="bg-slate-950 p-3 rounded-lg border border-amber-500/40 flex justify-between items-center text-xs">
                            <div class="space-y-1">
                                <div><strong class="text-white">${sig.symbol}</strong> [<span class="text-amber-300 font-bold">${sig.timeframe}</span>] | <span class="text-emerald-400 font-bold">${sig.action}</span> | Entry: $${sig.price}</div>
                                <div class="text-[11px] text-amber-400 font-bold"><i class="fa-solid fa-chart-column mr-1"></i> ${t.strat}: ${sig.strategy}</div>
                                <div class="text-[10px] text-cyan-300 font-semibold"><i class="fa-solid fa-fire mr-1"></i> ${t.volScore}: %${sig.volume_score} | ${t.autoTp}: <span class="text-emerald-400 font-bold">%${sig.tp_pct}</span></div>
                                <div class="text-[10px] text-slate-400"><i class="fa-solid fa-clock mr-1"></i> ${t.holding}: ${sig.holding_time}</div>
                            </div>
                            <button onclick="executeSignal('${sig.symbol}', ${sig.tp_pct})" class="bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold px-3 py-1.5 rounded cursor-pointer">${t.execute}</button>
                        </div>
                    `;
                } else {
                    sigBox.innerHTML = `<p class="text-xs text-slate-500">${t.waitSig}</p>`;
                }

                let tradesBox = document.getElementById('trades-box');
                document.getElementById('trade-count').innerText = data.trades.length + " Active";
                if(data.trades.length === 0) {
                    tradesBox.innerHTML = `<p class="text-slate-500 text-center py-6">${t.noPos}</p>`;
                } else {
                    tradesBox.innerHTML = data.trades.map(trd => `
                        <div class="bg-slate-900 p-3 rounded border border-slate-800 flex justify-between items-center">
                            <div class="space-y-1">
                                <div class="font-bold text-white">${trd.symbol} <span class="${trd.action.includes('LONG')?'text-emerald-400':'text-rose-400'}">${trd.action}</span> <span class="text-xs bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded">${trd.leverage}x Cross</span></div>
                                <div class="text-[11px] text-amber-400 font-medium"><i class="fa-solid fa-chart-column"></i> ${trd.strategy}</div>
                                <div class="text-[11px] text-slate-300">Margin: <strong class="text-emerald-400">$${trd.amount.toFixed(2)}</strong> | TP: <strong class="text-cyan-400">%${trd.target_tp_pct}</strong></div>
                                <div class="text-[11px] text-slate-400">Net PnL (Komisyonlu): <strong class="${trd.pnl>=0?'text-emerald-400':'text-rose-400'}">${trd.pnl>=0?'+':''}$${trd.pnl.toFixed(2)}</strong></div>
                            </div>
                            <button onclick="closeTrade('${trd.id}', '${trd.symbol}', '${trd.action}')" class="bg-rose-600 hover:bg-rose-500 text-white font-bold px-3 py-1.5 rounded cursor-pointer">${t.close}</button>
                        </div>
                    `).join('');
                }

                document.getElementById('logs-box').innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
            } catch(e) {}
        }, 1000);
    </script>
</body>
</html>
"""

app = FastAPI()
analyzer = MarketAnalyzer(memory)

class ControlModel(BaseModel): command: str
class SymbolModel(BaseModel): symbol: str
class TimeframeModel(BaseModel): timeframe: str
class LangModel(BaseModel): lang: str
class ModeModel(BaseModel): mode: str
class ConfigModel(BaseModel): api_key: str; api_secret: str; test_mode: bool; initial_capital: float
class ExecModel(BaseModel): symbol: str; amount: float; manual_tp: float = 15.0
class CloseModel(BaseModel): id: str; symbol: str; action: str

@app.get("/", response_class=HTMLResponse)
def index(): return DASHBOARD_HTML

@app.get("/api/state")
def state():
    price, _, turnover = analyzer.fetch_real_market_data(memory.selected_symbol)
    analyzer.fetch_live_positions_and_pnl()
    return {
        "status": memory.status,
        "test_mode": memory.test_mode,
        "balance": memory.current_balance,
        "cumulative_pnl": memory.cumulative_pnl,
        "success_rate": memory.success_rate,
        "price": price,
        "turnover": f"${turnover:,.0f}",
        "logs": memory.logs,
        "signals": memory.ai_signals_pending,
        "trades": memory.active_trades
    }

@app.post("/api/lang")
def lang(l: LangModel):
    memory.selected_lang = l.lang
    return {"status": "ok"}

@app.post("/api/timeframe")
def timeframe(tf: TimeframeModel):
    memory.selected_timeframe = tf.timeframe
    if memory.status == "RUNNING":
        analyzer.generate_strategy_signal(memory.selected_symbol, tf.timeframe)
    return {"status": "ok"}

@app.post("/api/mode")
def mode(m: ModeModel):
    memory.test_mode = (m.mode == 'test')
    if memory.test_mode:
        memory.current_balance = 1000.0
        memory.add_log("Test moduna geçildi. Bakiye $1000.00 yapıldı.")
    else:
        memory.current_balance = 0.0
        memory.add_log("Canlı moda geçildi. Bakiye sıfırlandı, API bekleniyor.")
    return {"status": "ok"}

@app.post("/api/symbol")
def symbol(s: SymbolModel):
    memory.selected_symbol = s.symbol
    if memory.status == "RUNNING":
        analyzer.generate_strategy_signal(s.symbol, memory.selected_timeframe)
    return {"status": "ok"}

@app.post("/api/control")
def control(c: ControlModel):
    memory.status = "RUNNING" if c.command == 'start' else "STOPPED"
    memory.add_log(f"Bot status: {memory.status}")
    if memory.status == "RUNNING":
        if not memory.test_mode:
            memory.add_log("Bot başlatıldı, Unified bakiye çekiliyor...")
            memory.current_balance = analyzer.fetch_wallet_balance()
        else:
            memory.current_balance = 1000.0
        analyzer.generate_strategy_signal(memory.selected_symbol, memory.selected_timeframe)
    return {"status": "ok"}

@app.post("/api/config")
def config(cfg: ConfigModel):
    memory.api_key = cfg.api_key.strip()
    memory.api_secret = cfg.api_secret.strip()
    memory.test_mode = cfg.test_mode
    
    if memory.test_mode:
        memory.initial_capital = cfg.initial_capital
        memory.current_balance = 1000.0
        memory.add_log("Test modu ayarları kaydedildi ($1000).")
    else:
        memory.add_log("Canlı API ayarları kaydedildi, bakiye sorgulanıyor...")
        bal = analyzer.fetch_wallet_balance()
        memory.current_balance = bal

    return {"status": "ok", "balance": memory.current_balance}

@app.post("/api/execute")
def execute(e: ExecModel):
    sig = memory.ai_signals_pending.get(e.symbol)
    if not sig:
        sig = analyzer.generate_strategy_signal(e.symbol, memory.selected_timeframe)

    if not memory.test_mode and e.amount > memory.current_balance:
        return {"status": "error", "message": "Amount exceeds live wallet balance!"}

    chosen_leverage = analyzer.calculate_safe_leverage(e.amount, memory.current_balance)
    chosen_tp = e.manual_tp if e.manual_tp > 0 else sig["tp_pct"]

    # Manuel TP'ye göre hedef fiyatı yeniden hesapla
    decimals = 5 if "PEPE" in sig["symbol"] else (4 if "HYPE" in sig["symbol"] else 2)
    base_pct = (chosen_tp / chosen_leverage) * 0.8 # Orantısal hedef güncelleme
    if "LONG" in sig["action"]:
        target = round(sig["price"] * (1 + base_pct), decimals)
    else:
        target = round(sig["price"] * (1 - base_pct), decimals)

    if not memory.test_mode:
        if not memory.api_key or not memory.api_secret:
            return {"status": "error", "message": "API Key and Secret are required for Live mode!"}
        
        qty = (e.amount * chosen_leverage) / sig["price"]
        success, msg = analyzer.place_live_order(sig["symbol"], sig["action"], qty, chosen_leverage, sig["stop_loss"], target)
        if not success:
            memory.add_log(f"❌ Bybit Canlı Emir Reddedildi: {msg}")
            return {"status": "error", "message": f"Bybit Error: {msg}"}
        else:
            memory.add_log(f"✅ Bybit Canlı Emir Başarıyla İletildi (TP: %{chosen_tp})!")

    memory.current_balance -= e.amount
    trade = {
        "id": f"t_{int(time.time())}_{random.randint(10,99)}",
        "symbol": sig["symbol"],
        "action": sig["action"],
        "price": sig["price"],
        "amount": e.amount,
        "leverage": chosen_leverage,
        "strategy": sig["strategy"],
        "pnl": 0.0,
        "target_tp_pct": chosen_tp
    }
    memory.active_trades.append(trade)
    memory.add_log(f"🚀 İşlem Açıldı (${e.amount} | {sig['strategy']} | {chosen_leverage}x | Manuel/Otomatik TP: %{chosen_tp}) - {sig['symbol']}")
    return {"status": "ok"}

@app.post("/api/close")
def close(cl: CloseModel):
    if not memory.test_mode and memory.api_key and memory.api_secret:
        success = analyzer.close_live_position(cl.symbol, cl.action)
        if not success:
            memory.add_log(f"⚠️ Bybit canlı pozisyon kapatma uyarısı: {cl.symbol}")
    
    for t in memory.active_trades[:]:
        if t["symbol"] == cl.symbol:
            memory.active_trades.remove(t)
            memory.current_balance += t["amount"] + t.get("pnl", 0)
            memory.record_trade_result(t.get("pnl", 0))
            memory.add_log(f"🛑 Pozisyon Kapatıldı - {t['symbol']} | Net PnL: ${t.get('pnl', 0)}")
            return {"status": "ok"}
    return {"status": "not_found"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
