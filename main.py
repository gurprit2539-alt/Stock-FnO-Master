import datetime
import time
import yfinance as yf
import pandas as pd
import pytz
import os
import requests
import calendar
import warnings
warnings.filterwarnings("ignore")

# ==============================================================================
# 🎯 V5.0 SNIPER ENGINE: LIQUIDITY GRAB & VOLUME ANOMALY
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MAX_TRADES_PER_DAY = 12

# 👑 REPUTED F&O STOCKS WATCHLIST
REPUTED_STOCKS = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "SBIN.NS", "TCS.NS"]

TRADES_TAKEN_TODAY = 0
TODAYS_DATE = None
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

# 🗓️ 100% ACCURATE NSE EXPIRY CALCULATOR (Last Thursday Logic)
def get_nse_monthly_expiry():
    ist = pytz.timezone("Asia/Kolkata")
    today = datetime.datetime.now(ist)
    year, month = today.year, today.month
    
    cal = calendar.monthcalendar(year, month)
    thursdays = [week[3] for week in cal if week[3] != 0]
    expiry_date = datetime.date(year, month, thursdays[-1])
    
    # अगर आज की तारीख एक्सपायरी के आगे निकल गई, तो अगले महीने का निकालेगा
    if today.date() > expiry_date:
        month = month + 1 if month < 12 else 1
        year = year + 1 if month == 1 else year
        cal = calendar.monthcalendar(year, month)
        thursdays = [week[3] for week in cal if week[3] != 0]
        expiry_date = datetime.date(year, month, thursdays[-1])
        
    return expiry_date.strftime("%d-%b-%Y")

def check_daily_reset():
    global TRADES_TAKEN_TODAY, TODAYS_DATE, LAST_SIGNAL_DICT
    ist = pytz.timezone("Asia/Kolkata")
    current_date = datetime.datetime.now(ist).date()
    if TODAYS_DATE != current_date:
        TODAYS_DATE = current_date
        TRADES_TAKEN_TODAY = 0
        LAST_SIGNAL_DICT.clear() 
        print(f"\n [🔄 NEW DAY] Sniper Memory reset for {current_date}.")

def scan_sniper_setups():
    global TRADES_TAKEN_TODAY, LAST_SIGNAL_DICT
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.datetime.now(ist)
    
    if TRADES_TAKEN_TODAY >= MAX_TRADES_PER_DAY: return
    print(f"\n🔓 SCANNING V5.0 INSTITUTIONAL TRAPS [{now_ist.strftime('%I:%M %p')}]")

    if now_ist.time() >= datetime.time(15, 20):
        print(" 🛑 Hard EOD Shield Active. Banning new entries.")
        return

    for symbol in REPUTED_STOCKS:
        try:
            stock_name = symbol.replace(".NS", "")
            expiry_str = get_nse_monthly_expiry()
            
            # 🕰️ डुअल टाइमफ्रेम डेटा फेच (15m ट्रेंड के लिए, 1m स्नाइपर एंट्री के लिए)
            df_15m = clean_df(yf.download(symbol, period="5d", interval="15m", progress=False, threads=False))
            df_1m = clean_df(yf.download(symbol, period="2d", interval="1m", progress=False, threads=False))
            
            if df_15m.empty or df_1m.empty or len(df_1m) < 25: continue

            # 📊 15m Trend Identification
            df_15m['EMA_20'] = df_15m['Close'].ewm(span=20, adjust=False).mean()
            trend_15m = "BULLISH" if to_float(df_15m['Close'].iloc[-1]) > to_float(df_15m['EMA_20'].iloc[-1]) else "BEARISH"

            # 🎯 1-Minute Sniper Data
            l_open = to_float(df_1m['Open'].iloc[-1])
            l_high = to_float(df_1m['High'].iloc[-1])
            l_low = to_float(df_1m['Low'].iloc[-1])
            l_close = to_float(df_1m['Close'].iloc[-1])
            l_vol = to_float(df_1m['Volume'].iloc[-1])
            
            # 🚨 3x VOLUME ANOMALY (ऑपरेटर का पैसा ट्रैक करने के लिए)
            avg_vol_20 = to_float(df_1m['Volume'].iloc[-21:-1].mean())
            is_vol_anomaly = bool(l_vol >= (avg_vol_20 * 3.0))

            # 🪤 LIQUIDITY GRAB (Trap Fader Logic)
            prev_5_low = to_float(df_1m['Low'].iloc[-6:-1].min())
            prev_5_high = to_float(df_1m['High'].iloc[-6:-1].max())
            
            body = abs(l_close - l_open)
            lower_wick = min(l_close, l_open) - l_low
            upper_wick = l_high - max(l_close, l_open)

            signal, logic_str = None, ""

            # 🟢 CE SETUP: 15m Bullish + Fake Breakdown on 1m (SL Hunt) + Massive Buy Volume
            if trend_15m == "BULLISH" and is_vol_anomaly:
                # कैंडल ने पिछले 5 मिनट का लो तोड़ा, लेकिन भयंकर वॉल्यूम के साथ रिकवर होकर लंबी पूंछ (Wick) बनाई
                if l_low < prev_5_low and lower_wick >= (1.5 * body):
                    signal = "CE"
                    logic_str = f"Liquidity Grab (SL Hunted) + 3x Volume Anomaly"
                    sl_point = l_low # 1-मिनट कैंडल का लो हमारा पक्का SL है

            # 🔴 PE SETUP: 15m Bearish + Fake Breakout on 1m (SL Hunt) + Massive Sell Volume
            elif trend_15m == "BEARISH" and is_vol_anomaly:
                # कैंडल ने पिछले 5 मिनट का हाई तोड़ा, लेकिन भयंकर वॉल्यूम के साथ रिजेक्ट होकर शूटिंग स्टार बनाया
                if l_high > prev_5_high and upper_wick >= (1.5 * body):
                    signal = "PE"
                    logic_str = f"Liquidity Grab (Fakeout) + 3x Volume Anomaly"
                    sl_point = l_high # 1-मिनट कैंडल का हाई हमारा पक्का SL है

            if signal:
                if stock_name in LAST_SIGNAL_DICT and LAST_SIGNAL_DICT[stock_name] == signal:
                    continue
                
                LAST_SIGNAL_DICT[stock_name] = signal
                TRADES_TAKEN_TODAY += 1
                
                # 🎯 ITM Strike Selection
                if l_close < 1000:
                    atm_strike = round(l_close / 10) * 10
                    final_strike = atm_strike - 10 if signal == "CE" else atm_strike + 10
                else:
                    atm_strike = round(l_close / 50) * 50
                    final_strike = atm_strike - 20 if signal == "CE" else atm_strike + 20
                
                msg = (f"*👑 STOCK SNIPER V5.0 (No Lag)*\n\n"
                       f"⚡ Action: *BUY {signal}*\n"
                       f"📌 Asset: {stock_name} {final_strike} {signal} (ITM)\n"
                       f"📅 Live Expiry: {expiry_str}\n"
                       f"📉 Spot CMP: ₹{l_close:.2f}\n\n"
                       f"🧠 Logic: {logic_str}\n"
                       f"🛡️ Strict SL: ₹{sl_point:.2f} (1m Trap Wick)\n"
                       f"📊 Quota: {TRADES_TAKEN_TODAY}/{MAX_TRADES_PER_DAY}\n\n"
                       f"👉 Operator Trapped! Execute Quick Scalp Now.")
                
                print(f" 🟢 🔥 SNIPER ENTRY: {stock_name} {signal}")
                send_telegram_msg(msg)

        except Exception as e:
            print(f" 🔴 Error processing {symbol}: {e}")

if __name__ == "__main__":
    print("🚀 V5.0 SNIPER ENGINE ONLINE")
    send_telegram_msg("🟢 *STOCK SNIPER V5.0 ACTIVE*\nShifted to 1-Min Timeframe! 3x Volume Anomaly & Trap Finder Engine Started.")
    
    while True:
        ist = pytz.timezone("Asia/Kolkata")
        now_ist = datetime.datetime.now(ist)

        if now_ist.weekday() >= 5: break
        if now_ist.time() >= datetime.time(15, 30): break 
        if now_ist.time() < datetime.time(9, 30):
            time.sleep(60)
            continue

        check_daily_reset()
        scan_sniper_setups()
        
        # चूँकि यह 1-मिनट का स्नाइपर है, बॉट अब हर 1 मिनट (60 सेकंड) में स्कैन करेगा
        time.sleep(60)
