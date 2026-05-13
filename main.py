import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
import hmac
import hashlib
import time
import math

# ----------------- STREAMLIT AYARLARI -----------------
st.set_page_config(page_title="Binance Testnet Bot", layout="wide", page_icon="🧪")

# ----------------- SESSION STATE -----------------
if "giris_basarili" not in st.session_state:
    st.session_state.giris_basarili = False
if "trailing_aktif" not in st.session_state:
    st.session_state.trailing_aktif = False

# ----------------- GÜVENLİK KİLİDİ -----------------
def giris_kontrol():
    if not st.session_state.giris_basarili:
        st.title("🔒 Testnet Bot Erişimi")
        sifre = st.text_input("Erişim Şifresi:", type="password")
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

# ----------------- TESTNET YAPILANDIRMASI -----------------
# Sadece Testnet URL'leri tanımlandı
BASE_URL = "https://demo-fapi.binance.com/"
API_KEY = st.secrets.get("BINANCE_TESTNET_API_KEY", "")
API_SECRET = st.secrets.get("BINANCE_TESTNET_API_SECRET", "")

st.sidebar.success("✅ Mod: Demo (Testnet) Aktif")
st.sidebar.caption("Gerçek parayla işlem yapılmaz.")

# ----------------- BINANCE FONKSİYONLARI -----------------
def generate_signature(query_string):
    return hmac.new(API_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def get_current_price(symbol):
    headers = {
        "X-MBX-APIKEY": API_KEY,
        "User-Agent": "Mozilla/5.0"
    }
    try:
        r = requests.get(f"{BASE_URL}/api/v3/ticker/price", 
                         params={"symbol": symbol}, 
                         headers=headers,
                         timeout=5)
        return float(r.json()["price"])
    except:
        return 0.0


def get_account_balances():
    timestamp = int(time.time() * 1000)
    query = f"timestamp={timestamp}"
    signature = generate_signature(query)
    url = f"{BASE_URL}/api/v3/account?{query}&signature={signature}"
    headers = {"X-MBX-APIKEY": API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            df = pd.DataFrame(r.json().get("balances", []))
            return df[df["free"].astype(float) > 0]
    except: pass
    return pd.DataFrame()

def market_order(symbol, side, quantity):
    timestamp = int(time.time() * 1000)
    query = f"symbol={symbol}&side={side}&type=MARKET&quantity={quantity}&timestamp={timestamp}"
    signature = generate_signature(query)
    url = f"{BASE_URL}/api/v3/order?{query}&signature={signature}"
    headers = {"X-MBX-APIKEY": API_KEY}
    try:
        r = requests.post(url, headers=headers, timeout=5)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# ----------------- VERİ VE GRAFİK -----------------
symbol = st.sidebar.selectbox("İşlem Çifti", ["BTCUSDT", "ETHUSDT", "BNBUSDT"])
st.sidebar.markdown("---")

# Cüzdan Durumu
if st.sidebar.button("Cüzdanı Güncelle"):
    balances = get_account_balances()
    if not balances.empty:
        st.sidebar.dataframe(balances[["asset", "free"]], hide_index=True)

# Grafik Verisi
try:
    res = requests.get(f"{BASE_URL}/api/v3/klines", params={"symbol": symbol, "interval": "1h", "limit": 50}).json()
    df = pd.DataFrame(res, columns=["ot", "open", "high", "low", "close", "v", "ct", "q", "n", "t", "tb", "i"])
    df["Close"] = df["close"].astype(float)
    
    fig = go.Figure(data=[go.Candlestick(x=pd.to_datetime(df["ot"], unit="ms"),
                open=df["open"], high=df["high"], low=df["low"], close=df["close"])])
    fig.update_layout(template="plotly_dark", height=450, title=f"{symbol} Analiz")
    st.plotly_chart(fig, use_container_width=True)
except:
    st.error("Piyasa verisi alınamadı.")

# ----------------- İŞLEM PANELİ -----------------
st.subheader("🛒 Testnet Emir Paneli")
col_buy, col_sell = st.columns(2)

with col_buy:
    buy_amount = st.number_input("Alım Miktarı (Adet)", value=0.01, step=0.01)
    if st.button(f"TEST ALIM: {symbol}", type="primary", use_container_width=True):
        sonuc = market_order(symbol, "BUY", buy_amount)
        st.write(sonuc)

with col_sell:
    sell_amount = st.number_input("Satım Miktarı (Adet)", value=0.01, step=0.01)
    if st.button(f"TEST SATIM: {symbol}", type="secondary", use_container_width=True):
        sonuc = market_order(symbol, "SELL", sell_amount)
        st.write(sonuc)
