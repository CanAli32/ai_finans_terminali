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
st.set_page_config(page_title="Binance Spot Bot Pro", layout="wide", page_icon="📈")

# ----------------- SESSION STATE BAŞLATMA -----------------
# Uygulama başladığında değişkenleri tanımlamazsak hata alabiliriz
if "giris_basarili" not in st.session_state:
    st.session_state.giris_basarili = False
if "trailing_aktif" not in st.session_state:
    st.session_state.trailing_aktif = False
if "en_yuksek_fiyat" not in st.session_state:
    st.session_state.en_yuksek_fiyat = 0.0
if "stop_fiyati" not in st.session_state:
    st.session_state.stop_fiyati = 0.0

# ----------------- GÜVENLİK KİLİDİ -----------------
def giris_kontrol():
    if not st.session_state.giris_basarili:
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
    st.stop() # Şifre girilene kadar kodun geri kalanını çalıştırmaz

# ----------------- KONFİGÜRASYON -----------------
st.sidebar.title("⚙️ Yönetim Paneli")
hesap_modu = st.sidebar.radio("Hesap Türü:", ["Demo (Testnet)", "Gerçek Hesap"])

# ÖNEMLİ: URL'ler 'https://' ile başlamalıdır.
if hesap_modu == "Demo (Testnet)":
    BASE_URL = "https://testnet.binance.vision"
    API_KEY = st.secrets.get("BINANCE_TESTNET_API_KEY", "")
    API_SECRET = st.secrets.get("BINANCE_TESTNET_API_SECRET", "")
else:
    BASE_URL = "https://api.binance.com"
    API_KEY = st.secrets.get("BINANCE_API_KEY", "")
    API_SECRET = st.secrets.get("BINANCE_API_SECRET", "")

# ----------------- YARDIMCI FONKSİYONLAR -----------------
def get_current_price(symbol):
    try:
        r = requests.get(f"{BASE_URL}/api/v3/ticker/price", params={"symbol": symbol}, timeout=5)
        return float(r.json()["price"])
    except:
        return 0.0

def get_candles(symbol):
    try:
        url = f"{BASE_URL}/api/v3/klines"
        params = {"symbol": symbol, "interval": "1h", "limit": 100}
        r = requests.get(url, params=params, timeout=5).json()
        df = pd.DataFrame(r, columns=["ot", "open", "high", "low", "close", "vol", "ct", "qav", "nt", "tbb", "tbq", "i"])
        df["time"] = pd.to_datetime(df["ot"], unit="ms")
        df["Close"] = df["close"].astype(float)
        df["RSI"] = ta.rsi(df["Close"], length=14)
        return df
    except:
        return pd.DataFrame()

# ----------------- ANA PANEL -----------------
symbol = st.sidebar.selectbox("Sembol Seçin", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
df = get_candles(symbol)

if df.empty:
    st.warning("Veri çekilemiyor. Lütfen internet bağlantınızı veya API anahtarlarınızı kontrol edin.")
else:
    current_price = get_current_price(symbol)
    last_rsi = df.iloc[-1]["RSI"]

    col1, col2 = st.columns(2)
    col1.metric(f"{symbol} Fiyat", f"${current_price:,.2f}")
    col2.metric("RSI (14)", f"{last_rsi:.2f}")

    # Grafik
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
    fig.update_layout(template="plotly_dark", height=400, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # Manuel İşlem Alanı
    st.markdown("---")
    c_buy, c_sell = st.columns(2)
    if c_buy.button(f"AL {symbol}", use_container_width=True):
        st.info("Alım emri gönderiliyor... (API Yetkisi Gerekli)")
    
    if c_sell.button(f"SAT {symbol}", use_container_width=True):
        st.info("Satım emri gönderiliyor... (API Yetkisi Gerekli)")

# ----------------- CANLI TAKİP (FRAGMENT) -----------------
@st.fragment(run_every=5)
def live_tracker():
    if st.session_state.trailing_aktif:
        p = get_current_price(symbol)
        st.sidebar.write(f"Canlı Takip: {p}")
        # Buraya stop logic eklenebilir

live_tracker()
