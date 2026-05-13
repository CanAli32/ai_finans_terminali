import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
import hmac
import hashlib
import time
import math
from datetime import datetime

# ----------------- STREAMLIT AYARLARI -----------------
st.set_page_config(page_title="Binance Spot Bot Pro", layout="wide", page_icon="📈")

# ----------------- SESSION STATE BAŞLATMA -----------------
if "trailing_aktif" not in st.session_state:
    st.session_state.trailing_aktif = False
if "en_yuksek_fiyat" not in st.session_state:
    st.session_state.en_yuksek_fiyat = 0.0
if "stop_fiyati" not in st.session_state:
    st.session_state.stop_fiyati = 0.0
if "trailing_miktar" not in st.session_state:
    st.session_state.trailing_miktar = 0.0
if "trailing_yuzde" not in st.session_state:
    st.session_state.trailing_yuzde = 1.0

# ----------------- GÜVENLİK KİLİDİ -----------------
def giris_kontrol():
    if "giris_basarili" not in st.session_state:
        st.title("🔒 Robot Erişim Kilidi")
        sifre = st.text_input("Erişim Şifresini Giriniz:", type="password")
        if st.button("Giriş Yap"):
            if sifre == "123456": 
                st.session_state.giris_basarili = True
                st.rerun()
            else:
                st.error("Hatalı Şifre!")
        return False
    return True

if not giris_kontrol():
    st.stop()

# ----------------- HESAP MODU VE TELEGRAM AYARLARI -----------------
st.sidebar.title("⚙️ Binance Yönetim Paneli")
hesap_modu = st.sidebar.radio("Hesap Türü:", ["Demo (Testnet)", "Gerçek Hesap"])

if hesap_modu == "Demo (Testnet)":
    BASE_URL = "https://testnet.binance.vision" 
    API_KEY = st.secrets.get("BINANCE_TESTNET_API_KEY")
    API_SECRET = st.secrets.get("BINANCE_TESTNET_API_SECRET")
else:
    BASE_URL = "https://api.binance.com"
    API_KEY = st.secrets.get("BINANCE_API_KEY")
    API_SECRET = st.secrets.get("BINANCE_API_SECRET")

TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")

# ----------------- TELEGRAM BİLDİRİM FONKSİYONU -----------------
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": f"🤖 *Binance Bot*\n{message}", "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        st.sidebar.error(f"Telegram Hatası: {e}")

# ----------------- BINANCE YARDIMCI FONKSİYONLAR -----------------
def generate_signature(query_string, secret):
    return hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def get_binance_headers():
    return {"X-MBX-APIKEY": API_KEY}

def round_step_size(quantity, step_size):
    if step_size <= 0: return quantity
    precision = int(round(-math.log10(step_size), 0))
    return float(f"{math.floor(quantity * (10 ** precision)) / (10 ** precision):.{precision}f}")

def get_symbol_step_size(symbol):
    try:
        url = f"{BASE_URL}/api/v3/exchangeInfo?symbol={symbol}"
        res = requests.get(url).json()
        for f in res['symbols'][0]['filters']:
            if f['filterType'] == 'LOT_SIZE': return float(f['stepSize'])
    except: return 0.00001
    return 0.00001

def get_current_price(symbol):
    try:
        r = requests.get(f"{BASE_URL}/api/v3/ticker/price?symbol={symbol}").json()
        return float(r["price"])
    except: return 0.0

# ----------------- EMİR VE HESAP İŞLEMLERİ -----------------
def get_account_balances():
    if not API_KEY or not API_SECRET: return pd.DataFrame()
    timestamp = int(time.time() * 1000)
    query = f"timestamp={timestamp}"
    signature = generate_signature(query, API_SECRET)
    url = f"{BASE_URL}/api/v3/account?{query}&signature={signature}"
    try:
        r = requests.get(url, headers=get_binance_headers())
        if r.status_code == 200:
            df_bal = pd.DataFrame(r.json().get("balances", []))
            if not df_bal.empty:
                df_bal["free"] = df_bal["free"].astype(float)
                df_bal["locked"] = df_bal["locked"].astype(float)
                return df_bal[(df_bal["free"] > 0) | (df_bal["locked"] > 0)]
    except: pass
    return pd.DataFrame()

def binance_buy(symbol, usdt_amount):
    last = get_current_price(symbol)
    if last == 0: return 0, 0, {"error": "Fiyat alınamadı"}
    qty = round_step_size(usdt_amount / last, get_symbol_step_size(symbol))
    timestamp = int(time.time() * 1000)
    query = f"symbol={symbol}&side=BUY&type=MARKET&quantity={qty}&timestamp={timestamp}"
    url = f"{BASE_URL}/api/v3/order?{query}&signature={generate_signature(query, API_SECRET)}"
    res = requests.post(url, headers=get_binance_headers()).json()
    if "orderId" in res:
        send_telegram_message(f"🟢 *ALIM BAŞARILI*\n{symbol} - {qty} adet")
    return last, qty, res

def binance_sell(symbol, qty, is_trailing=False):
    qty = round_step_size(qty, get_symbol_step_size(symbol))
    timestamp = int(time.time() * 1000)
    query = f"symbol={symbol}&side=SELL&type=MARKET&quantity={qty}&timestamp={timestamp}"
    url = f"{BASE_URL}/api/v3/order?{query}&signature={generate_signature(query, API_SECRET)}"
    res = requests.post(url, headers=get_binance_headers()).json()
    if "orderId" in res:
        tip = "🛡️ TRAILING" if is_trailing else "🔴 MANUEL"
        send_telegram_message(f"{tip} SATIŞ BAŞARILI\n{symbol} - {qty} adet")
    return res

def get_candles(symbol="BTCUSDT"):
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval=1d&limit=100"
    try:
        r = requests.get(url).json()
        df = pd.DataFrame(r, columns=["open_time","open","high","low","close","volume","close_time","qav","num_trades","tbb","tbq","ignore"])
        df["time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["Close"] = df["close"].astype(float)
        df["RSI"] = ta.rsi(df["Close"], length=14)
        df["SMA20"] = ta.sma(df["Close"], length=20)
        return df
    except: return pd.DataFrame()

# ----------------- UI / GÖRSELLEŞTİRME -----------------
symbol = st.sidebar.selectbox("Sembol", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
usdt_amount = st.sidebar.number_input("Alım Tutarı (USDT)", 10, 1000, 50)

df = get_candles(symbol)
if not df.empty:
    fiyat = get_current_price(symbol)
    rsi = df.iloc[-1]["RSI"]
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Fiyat", f"{fiyat}")
    col2.metric("RSI", f"{rsi:.2f}")
    col3.metric("Trend", "AL" if rsi < 40 else "SATIŞ/BEKLE")

    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
    fig.update_layout(darkmode=True, height=400)
    st.plotly_chart(fig, use_container_width=True)

    # TRAILING STOP FRAGMENT
    @st.fragment(run_every=3)
    def tracking_logic():
        anlik = get_current_price(symbol)
        if st.session_state.trailing_aktif:
            if anlik > st.session_state.en_yuksek_fiyat:
                st.session_state.en_yuksek_fiyat = anlik
                st.session_state.stop_fiyati = anlik * (1 - (st.session_state.trailing_yuzde / 100))
            
            if anlik <= st.session_state.stop_fiyati:
                binance_sell(symbol, st.session_state.trailing_miktar, True)
                st.session_state.trailing_aktif = False
                st.rerun()
            
            st.info(f"Takipte: Stop Seviyesi {st.session_state.stop_fiyati:.2f}")

    tracking_logic()

    # Butonlar
    if st.button("Satın Al"):
        binance_buy(symbol, usdt_amount)
