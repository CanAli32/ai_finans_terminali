import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
import hmac
import base64
import json
from datetime import datetime

# ----------------- STREAMLIT AYARLARI -----------------
st.set_page_config(page_title="OKX Spot Bot Pro", layout="wide", page_icon="📈")

# ----------------- GÜVENLİK KİLİDİ -----------------
def giris_kontrol():
    if "giris_basarili" not in st.session_state:
        st.title("🔒 Robot Erişim Kilidi")
        sifre = st.text_input("Erişim Şifresini Giriniz:", type="password")
        if st.button("Giriş Yap"):
            if sifre == "123456": # Şifrenizi buradan değiştirebilirsiniz
                st.session_state.giris_basarili = True
                st.rerun()
            else:
                st.error("Hatalı Şifre!")
        return False
    return True

if not giris_kontrol():
    st.stop()

# ----------------- HESAP MODU VE BULUT AYARLARI -----------------
st.sidebar.title("⚙️ OKX Yönetim Paneli")

# HATA ÇÖZÜMÜ: Buradan Canlı veya Demo seçimi yapabilirsiniz
hesap_modu = st.sidebar.radio("Hesap Türü:", ["Demo (Testnet)", "Gerçek Hesap"])

if hesap_modu == "Demo (Testnet)":
    BASE_URL = "https://www.okx.com" # Demo için de ana url kullanılır ancak header değişir
    IS_DEMO = True
else:
    BASE_URL = "https://www.okx.com"
    IS_DEMO = False

# API Bilgilerini Çekme
API_KEY = st.secrets["OKX_API_KEY"]
API_SECRET = st.secrets["OKX_API_SECRET"]
PASSPHRASE = st.secrets["OKX_PASSPHRASE"]

# ----------------- OKX İMZA OLUŞTURMA -----------------
def sign(message, secret):
    return base64.b64encode(
        hmac.new(secret.encode(), message.encode(), digestmod="sha256").digest()
    ).decode()

def headers(method, path, body=""):
    # OKX milisaniye hassasiyetinde UTC zamanı bekler
    ts = datetime.utcnow().isoformat("T", "milliseconds") + "Z"
    msg = ts + method + path + body
    signature = sign(msg, API_SECRET)

    head = {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }
    
    # HATA ÇÖZÜMÜ: Eğer Demo modu seçildiyse OKX simulated header'ını ekliyoruz
    if IS_DEMO:
        head["x-simulated-id"] = "1"
        
    return head

# ----------------- OKX VERİ ÇEKME -----------------
def get_candles(inst_id="BTC-USDT"):
    path = f"/api/v5/market/candles?instId={inst_id}&bar=1D&limit=180"
    
    # Mum verileri için demo ve canlı ayrımı header simülasyonu ile yapılır
    h = headers("GET", path) if IS_DEMO else {}
    r = requests.get(BASE_URL + path, headers=h)
    
    data = r.json().get("data", [])

    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=[
        "ts","open","high","low","close","vol","volCcy","volCcyQuote","confirm"
    ])

    df["time"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
    df["Close"] = df["close"].astype(float)
    df = df.sort_values("time")

    df["RSI"] = ta.rsi(df["Close"], length=14)
    df["SMA20"] = ta.sma(df["Close"], length=20)

    return df

# ----------------- OKX MARKET BUY -----------------
def okx_buy(inst_id, usdt_amount):
    # Son fiyatı çek
    h_m = headers("GET", f"/api/v5/market/ticker?instId={inst_id}")
    ticker = requests.get(BASE_URL + f"/api/v5/market/ticker?instId={inst_id}", headers=h_m).json()
    last = float(ticker["data"][0]["last"])
    qty = round(usdt_amount / last, 6)

    body = json.dumps({
        "instId": inst_id,
        "tdMode": "cash",
        "side": "buy",
        "ordType": "market",
        "sz": str(qty)
    })

    path = "/api/v5/trade/order"
    h = headers("POST", path, body)
    r = requests.post(BASE_URL + path, headers=h, data=body)

    return last, qty, r.json()

# ----------------- OKX MARKET SELL -----------------
def okx_sell(inst_id, qty):
    body = json.dumps({
        "instId": inst_id,
        "tdMode": "cash",
        "side": "sell",
        "ordType": "market",
        "sz": str(qty)
    })

    path = "/api/v5/trade/order"
    h = headers("POST", path, body)
    r = requests.post(BASE_URL + path, headers=h, data=body)

    return r.json()

# ----------------- DYNAMIC ARAYÜZ PANELDEN -----------------
inst_id = st.sidebar.selectbox("Sembol Seçimi", ["BTC-USDT", "ETH-USDT", "SOL-USDT", "AVAX-USDT"])
usdt_amount = st.sidebar.number_input("Alım Tutarı (USDT)", 10, 100000, 50)

df = get_candles(inst_id)

if df.empty:
    st.error("Piyasa verileri alınamadı. API Key veya sunucu bağlantısını kontrol edin.")
else:
    last = df.iloc[-1]
    fiyat = last["Close"]
    rsi = last["RSI"] if not pd.isna(last["RSI"]) else 50.0
    sma = last["SMA20"] if not pd.isna(last["SMA20"]) else fiyat

    # Üst Gösterge Kartları
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Anlık Fiyat", f"{fiyat:,.4f} USDT")
    c2.metric("RSI (14)", f"{rsi:.2f}")
    c3.metric("SMA (20)", f"{sma:,.2f}")
    
    onay = (1 if rsi < 35 else 0) + (1 if fiyat > sma else 0)
    c4.metric("Sinyal Skoru", f"{onay}/2", delta="AL SİNYALİ" if onay == 2 else "BEKLE")

    # Teknik Grafik
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["time"], y=df["Close"], name="Fiyat", line=dict(color='#00ffcc')))
    fig.add_trace(go.Scatter(x=df["time"], y=df["SMA20"], name="SMA20", line=dict(color='orange', dash='dash')))
    fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Emir Gönderme Alanı
    st.markdown(f"### 🤖 Emir Yönetimi ({hesap_modu})")
    col_buy, col_sell = st.columns(2)

    with col_buy:
        st.subheader("🟢 Alım Yap")
        if st.button(f"{inst_id} Satın Al ({usdt_amount} USDT)"):
            with st.spinner("Emir iletiliyor..."):
                f, qty, res = okx_buy(inst_id, usdt_amount)
                if "code" in res and res["code"] == "0":
                    st.success(f"Başarılı! {qty} adet {inst_id} alındı. Fiyat: {f}")
                st.json(res)

    with col_sell:
        st.subheader("🔴 Satım Yap")
        satilacak_adet = st.number_input("Satılacak Miktar (Adet)", 0.0001, 10000.0, 0.01, step=0.01, key="sell_qty_input")
        if st.button(f"{inst_id} Market Fiyatından SAT"):
            with st.spinner("Emir iletiliyor..."):
                res = okx_sell(inst_id, satilacak_adet)
                if "code" in res and res["code"] == "0":
                    st.success(f"Başarılı! {satilacak_adet} adet {inst_id} satıldı.")
                st.json(res)
