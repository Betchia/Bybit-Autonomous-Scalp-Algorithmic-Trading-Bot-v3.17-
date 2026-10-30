# 🚀 Bybit Autonomous Scalp & Algorithmic Trading Bot [v3.17]

An autonomous, multi-language, web-based algorithmic scalping and trading bot built for **Bybit V5 Unified Trading Account (UTA)** API. It features real-time volume analysis, automatic/manual Take-Profit (TP) configuration, multi-symbol tracking, TradingView integration, and live PnL tracking.

---

## ✨ Key Features & Architecture

* **Autonomous Volume & Order Flow Analysis:** Scans live market conditions, order book depth, and 24h turnover across multiple timeframes (`1m`, `5m`, `15m`, `1h`, `4h`).
* **Dual Execution Modes:**
  * **Test Mode:** Runs safely on a simulated `$1,000` virtual balance with real-time price feeds.
  * **Live Mode:** Direct, secure connection to Bybit V5 API (`/v5/order/create`, `/v5/position/list`) with automated leverage and risk management.
* **Auto & Manual TP (Take-Profit) Control:** 
  * Bot automatically calculates the optimal TP percentage based on market volatility and volume scores.
  * Traders can manually override the recommended TP percentage when entering a trade.
* **Smart Success Rate Analytics:** Tracks closed positions in real-time, factoring in exchange trading fees (`0.11%` notional fee) to calculate and display the live win/success rate percentage.
* **Multi-Language Support:** Fully localized user interface supporting **Turkish (TR), English (EN), German (DE), Russian (RU), and Chinese (ZH)**.
* **Embedded TradingView Charts:** Real-time interactive charts with dynamic symbol and timeframe switching.

---

## 🛠️ Tech Stack

* **Backend:** Python 3.10+, FastAPI, Uvicorn
* **Frontend:** TailwindCSS, Vanilla JavaScript, FontAwesome, TradingView Widgets
* **API Integration:** HMAC-SHA256 Request Signing for Bybit V5 REST API

---

## 📦 Installation & Setup Guide

### Prerequisites
* Python `3.10` or higher installed on your machine.
* pip (Python package manager).

### Step 1: Clone the Repository
```bash
git clone [https://github.com/betchia/bybit-autonomous-scalp-bot.git](https://github.com/betchia/bybit-autonomous-scalp-bot.git)
cd bybit-autonomous-scalp-bot

Step 2: Install Dependencies
Install the required Python packages using pip:

Bash
pip install fastapi uvicorn requests pydantic
Step 3: Run the Bot
Execute the main application script:

Bash
python main.py
The application will start locally at:
👉 http://127.0.0.1:8000

Open this URL in your web browser. (Recommended to use Ctrl + F5 for a hard refresh upon first load).

💡 User Manual & Usage Instructions
1. General Interface Overview
Top Header Bar: Language selector (TR, EN, DE, RU, ZH), timeframe switcher (1m to 4h), Mode toggle (Test vs Live), symbol selector (BTC, ETH, SOL, LINK, HYPE, PEPE), and the Start/Stop Bot master switch.

API Config Panel: Enter your Bybit API Key and Secret Key here if you are switching to Live Mode.

Metrics Dashboard: Displays Wallet Balance, Net PnL (including fee deductions), Bot Success Rate (%), Live Price & Turnover, and System Status.

2. Operating Modes
Test Mode (Default): Operates with a virtual $1,000 balance. Great for testing strategies and checking user interface reactions without financial risk.

Live Mode: Connects directly to your Bybit account. Note: Ensure your API keys have futures trading permissions enabled and IP restrictions properly configured.

3. Executing Trades
Click "Start Bot" to activate the autonomous market analyzer.

The bot will generate signals based on volume spikes and order flow in the Autonomous Volume Signals box.

Click "Enter Trade" next to any signal.

Enter your desired Trade Amount (USDT).

In the next prompt, you can either accept the Suggested Auto TP % (calculated by the bot) or input your own Manual TP %.

The trade will instantly appear in the Open Positions & Tiered TP panel.

⚙️ Configuration & API Permissions
To use Live Mode, your Bybit API Key must have the following permissions enabled:

Contract -> Orders (Read & Write)

Contract -> Positions (Read & Write)

📄 License
Distributed under the MIT License. See LICENSE for more information.
