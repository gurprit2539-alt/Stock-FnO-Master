import datetime
import time
import yfinance as yf
import pandas as pd
import pytz
import os
import requests
import warnings
warnings.filterwarnings("ignore")

# ==============================================================================
# ⚙️ MASTER INSTITUTIONAL SETTINGS (V3.3)
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MAX_TRADES_PER_DAY = 12

# 👑 REPUTED F&O STOCKS WATCHLIST
REPUTED_STOCKS = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "SBIN.NS", "TCS.NS"]

TRADES_TAKEN_TODAY = 0
TODAYS_DATE = None
DAILY_SIGNALS_COUNT = 0
LAST_SIGNAL_DICT = {}

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def to_float(val):
    try:
        if isinstance(val, (pd.Series, pd.DataFrame)): return float(val.iloc[-1])
        if hasattr(val, 'item'): return float(val.item())
        return float(val)
    except:
        return 0.0

def clean_df(df):
    if df.empty: return df
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df.dropna()

def get_real_expiry(symbol):
    try:
        ticker = yf.Ticker(symbol)
        expiries = ticker.options
        if expiries:
            raw_date = expiries[0] 
            date_obj = datetime.datetime.strptime(raw_date, '%Y-%m-%d')
            return date_obj.strftime("%d-%b-%Y") 
    except Exception as e:
        pass
    return "Current Monthly Expiry"

def check_daily_reset():
    global TRADES_TAKEN_TODAY, DAILY_SIGNALS_COUNT, TODAYS_DATE, LAST_SIGNAL_DICT
    ist = pytz.timezone("Asia/Kolkata")
    current_date = datetime.datetime.now(ist).date()
    if TODAYS_DATE != current_date:
        TODAYS_DATE = current_date
        TRADES_TAKEN_TODAY = 0
        DAILY_SIGNALS_COUNT = 0
        LAST_SIGNAL_DICT.clear() 
        print(f"\n [🔄 NEW DAY] Memory reset for {current_date}.")

def scan_reputed_stocks():
    global TRADES_TAKEN_TODAY, DAILY_SIGNALS_COUNT, LAST_SIGNAL_DICT
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.datetime.now(ist)
    
    if TRADES_TAKEN_TODAY >= MAX_TRADES_PER_DAY: return
    print(f"\n🔓 SCANNING REPUTED STOCKS (V3.3) [{now_ist.strftime('%I:%M %p')}]")

    if now_ist.time() >= datetime.time(15, 20):
        print(" 🛑 Hard EOD Shield Active. Banning new entries.")
        return
    if datetime.time(11, 30) <= now_ist.time() <= datetime.time(13, 15):
        print(" 🛑 Mid-Day Decay Zone. Paused.")
        return

    for symbol in REPUTED_STOCKS:
        try:
            expiry_str = get_real_expiry(symbol)
            stock_name = symbol.replace(".NS", "")
            
            stock = clean_df(yf.download(symbol, period="5d", interval="5m", progress=False, threads=False))
            daily = clean_df(yf.download(symbol, period="2d", interval="1d", progress=False, threads=False))
            
            if stock.empty or len(stock) < 15 or daily.empty: continue

            current_block = now_ist.replace(minute=(now_ist.minute // 5) * 5, second=0, microsecond=0)
            stock = stock[stock.index < current_block]
            if stock.empty: continue

            # 🛡️ 1% DAILY MOMENTUM GATEKEEPER
            today_data = stock[stock.index.date == now_ist.date()]
            if not today_data.empty:
                day_high = to_float(today_data['High'].max())
                day_low = to_float(today_data['Low'].min())
                daily_range_pct = (day_high - day_low) / day_low
                if daily_range_pct < 0.01:
                    print(f" 🔕 Filtered: {stock_name} is dead today (Range: {daily_range_pct*100:.2f}%). Need > 1%.")
                    continue # स्टॉक ने 1% का मूव नहीं दिया, इसे तुरंत इग्नोर करें

            stock['Typ'] = (stock['High'] + stock['Low'] + stock['Close']) / 3
            stock['Date'] = stock.index.date
            stock['PV'] = stock['Typ'] * stock['Volume']
            stock['VWAP'] = stock.groupby('Date')['PV'].cumsum() / stock.groupby('Date')['Volume'].cumsum()
            stock['EMA_20'] = stock['Close'].ewm(span=20, adjust=False).mean()

            l_close = to_float(stock['Close'].iloc[-1])
            l_open = to_float(stock['Open'].iloc[-1])
            l_high = to_float(stock['High'].iloc[-1])
            l_low = to_float(stock['Low'].iloc[-1])
            l_vwap = to_float(stock['VWAP'].iloc[-1])
            l_ema = to_float(stock['EMA_20'].iloc[-1])
            
            pdh = to_float(daily['High'].iloc[-2]) if len(daily) > 1 else 999999
            pdl = to_float(daily['Low'].iloc[-2]) if len(daily) > 1 else 0

            body = abs(l_close - l_open)
            u_wick = l_high - max(l_open, l_close)
            l_wick = min(l_open, l_close) - l_low
            ce_wick_safe = bool(u_wick <= (body * 1.2))
            pe_wick_safe = bool(l_wick <= (body * 1.2))

            hour_high = to_float(stock['High'].iloc[-12:].max())
            hour_low = to_float(stock['Low'].iloc[-12:].min())
            if (hour_high - hour_low) / l_close < 0.002: continue 

            dist_vwap_pct = abs(l_close - l_vwap) / l_close
            dist_ema_pct = abs(l_close - l_ema) / l_close
            min_dist_passed = bool(dist_vwap_pct >= 0.0005 and dist_ema_pct >= 0.0005)
            fomo_safe = bool(dist_ema_pct <= 0.005)

            ema_now = to_float(stock['EMA_20'].iloc[-1])
            ema_3_ago = to_float(stock['EMA_20'].iloc[-4])
            slope_pct = ((ema_now - ema_3_ago) / ema_now) * 100

            signal, logic_str = None, ""

            if l_close > l_vwap and l_close > l_ema:
                if not ce_wick_safe or slope_pct < 0.05 or slope_pct > 0.3: continue
                if not min_dist_passed or not fomo_safe or abs(pdh - l_close)/l_close < 0.001: continue
                signal = "CE"
                logic_str = f"Bullish Trend (Slope: +{slope_pct:.2f}%) + High Momentum (>1%)"

            elif l_close < l_vwap and l_close < l_ema:
                if not pe_wick_safe or slope_pct > -0.05 or slope_pct < -0.3: continue
                if not min_dist_passed or not fomo_safe or abs(l_close - pdl)/l_close < 0.001: continue
                signal = "PE"
                logic_str = f"Bearish Trend (Slope: {slope_pct:.2f}%) + High Momentum (>1%)"

            if signal:
                if stock_name in LAST_SIGNAL_DICT and LAST_SIGNAL_DICT[stock_name] == signal:
                    continue
                
                LAST_SIGNAL_DICT[stock_name] = signal
                TRADES_TAKEN_TODAY += 1
                DAILY_SIGNALS_COUNT += 1
                
                # 🎯 ITM Strike Selection (स्लाइटली इन-द-मनी ताकि प्रीमियम तेज़ी से बढ़े)
                if l_close < 1000:
                    atm_strike = round(l_close / 10) * 10
                    final_strike = atm_strike - 10 if signal == "CE" else atm_strike + 10
                else:
                    atm_strike = round(l_close / 50) * 50
                    final_strike = atm_strike - 20 if signal == "CE" else atm_strike + 20
                
                msg = (f"*👑 STOCK F&O PRO MAX v3.3*\n\n"
                       f"⚡ Action: *BUY {signal}*\n"
                       f"📌 Asset: {stock_name} {final_strike} {signal} (ITM)\n"
                       f"📅 Live Expiry: {expiry_str}\n"
                       f"📉 Spot CMP: ₹{l_close:.2f}\n\n"
                       f"🧠 Logic: {logic_str}\n"
                       f"🛡️ Filters: 18 Gatekeepers (1% Daily Range Passed)\n"
                       f"📊 Quota: {TRADES_TAKEN_TODAY}/{MAX_TRADES_PER_DAY}\n\n"
                       f"👉 System Validated. Hit & Run (Scalp) recommended!")
                
                print(f" 🟢 🔥 NEW SIGNAL SENT: {stock_name} {signal}")
                send_telegram_msg(msg)

        except Exception as e:
            print(f" 🔴 Error processing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 STOCK F&O MASTER V3.3 ENGINE ONLINE")
    send_telegram_msg("🟢 *STOCK F&O V3.3 ACTIVE*\nCloud Engine Started (1% Range Filter + ITM Strikes Enabled)!")
    
    while True:
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(ist)

        if now_ist.weekday() >= 5:
            print("\n 🛑 Weekend detected. Market Closed.")
            break

        if now_ist.time() >= datetime.time(15, 41):
            send_telegram_msg(f"📊 *TODAY'S DAILY BRIEF*\n\n🔹 *Total Signals Detected:* {DAILY_SIGNALS_COUNT}\n🛑 *Market Closed.* Shutting Down.")
            print("\n 🛑 MARKET CLOSED (3:41 PM). Shutting Down.")
            break 

        if now_ist.time() < datetime.time(9, 30):
            time.sleep(60)
            continue

        check_daily_reset()
        scan_reputed_stocks()
        
        now = datetime.datetime.now(ist)
        next_minute = (now.minute // 5 + 1) * 5
        next_scan = now.replace(hour=(now.hour + 1) % 24, minute=0, second=20, microsecond=0) if next_minute >= 60 else now.replace(minute=next_minute, second=20, microsecond=0)
        time.sleep(max(10, (next_scan - now).total_seconds()))
