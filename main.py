import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
import hmac
import hashlib
import time

# ----------------- STREAMLIT AYARLARI -----------------
st.set_page_config(page_title="Binance Spot Testnet", layout="wide", page_icon="🧪")

if "giris_basarili" not in st.session_state:
    st.session_state.giris_basarili = False

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

# ----------------- YAPILANDIRMA -----------------
# Bölge engeli için api1, api2 veya api3 denenebilir. 
# Testnet için en stabil URL budur:
BASE_URL = "https://testnet.binance.vision" 
API_KEY = st.secrets.get("BINANCE_TESTNET_API_KEY", "")
API_SECRET = st.secrets.get("BINANCE_TESTNET_API_SECRET", "")

st.sidebar.success("✅ Ortam: Spot Testnet")

# ----------------- FONKSİYONLAR -----------------
def binance_request(method, endpoint, params=None, signed=False):
    url = f"{BASE_URL}{endpoint}"
    headers = {"X-MBX-APIKEY": API_KEY}
    
    if signed:
        timestamp = int(time.time() * 1000)
        query_string = f"timestamp={timestamp}"
        if params:
            # Parametreleri query string'e ekle
            p_str = "&".join([f"{k}={v}" for k, v in params.items()])
            query_string = f"{p_str}&{query_string}"
        
        signature = hmac.new(API_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        url = f"{url}?{query_string}&signature={signature}"
        params = None # URL'ye eklendiği için temizle

    try:
        if method == "GET":
            r = requests.get(url, params=params, headers=headers, timeout=10)
        else:
            r = requests.post(url, headers=headers, timeout=10)
        
        response = r.json()
        if "msg" in response and "Restricted" in response["msg"]:
            st.error("🚫 Binance Bölge Engeli: Streamlit Cloud sunucuları engellenmiş. Lütfen yerel bilgisayarınızda çalıştırın.")
        return response
    except Exception as e:
        return {"error": str(e)}

def get_current_price(symbol):
    res = binance_request("GET", "/api/v3/ticker/price", {"symbol": symbol})
    return float(res.get("price", 0.0))

# ----------------- ARAYÜZ -----------------
symbol = st.sidebar.selectbox("İşlem Çifti", ["BTCUSDT", "ETHUSDT", "BNBUSDT"])

# Grafik Verisi
res_klines = binance_request("GET", "/api/v3/klines", {"symbol": symbol, "interval": "1h", "limit": 50})
if isinstance(res_klines, list):
    df = pd.DataFrame(res_klines, columns=["ot", "open", "high", "low", "close", "v", "ct", "q", "n", "t", "tb", "i"])
    df["Close"] = df["close"].astype(float)
    fig = go.Figure(data=[go.Candlestick(x=pd.to_datetime(df["ot"], unit="ms"),
                open=df["open"], high=df["high"], low=df["low"], close=df["close"])])
    fig.update_layout(template="plotly_dark", height=400, title=f"{symbol} Canlı Veri")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Veri çekilemiyor. Bölge kısıtlaması devam ediyor olabilir.")

# İşlem Butonları
st.subheader("🛒 Hızlı Emir")
c1, c2 = st.columns(2)
qty = c1.number_input("Miktar", value=0.001, format="%.4f")

if c1.button("TEST AL", use_container_width=True):
    order = binance_request("POST", "/api/v3/order", {"symbol": symbol, "side": "BUY", "type": "MARKET", "quantity": qty}, signed=True)
    st.write(order)

if c2.button("TEST SAT", use_container_width=True):
    order = binance_request("POST", "/api/v3/order", {"symbol": symbol, "side": "SELL", "type": "MARKET", "quantity": qty}, signed=True)
    st.write(order)
