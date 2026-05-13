import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
import time
import hmac
import base64
import json
from datetime import datetime

# ----------------- STREAMLIT AYAR -----------------
st.set_page_config(page_title="OKX Spot Bot", layout="wide", page_icon="📈")

API_KEY = st.secrets["OKX_API_KEY"]
API_SECRET = st.secrets["OKX_API_SECRET"]
PASSPHRASE = st.secrets["OKX_PASSPHRASE"]

BASE_URL = "https://www.okx.com"

# ----------------- OKX İMZA OLUŞTURMA -----------------
def sign(message, secret):
    return base64.b64encode(
        hmac.new(secret.encode(), message.encode(), digestmod="sha256").digest()
    ).decode()

def headers(method, path, body=""):
    ts = datetime.utcnow().isoformat("T", "milliseconds") + "Z"
    msg = ts + method + path + body
    signature = sign(msg, API_SECRET)

    return {
        "OK-ACCESS-KEY": API_KEY,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": PASSPHRASE,
        "Content-Type": "application/json"
    }

# ----------------- OKX VERİ ÇEKME -----------------
def get_candles(inst_id="BTC-USDT"):
    path = f"/api/v5/market/candles?instId={inst_id}&bar=1D&limit=180"
    r = requests.get(BASE_URL + path)
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
    # Önce fiyat çek
    ticker = requests.get(BASE_URL + f"/api/v5/market/ticker?instId={inst_id}").json()
    last = float(ticker["data"][1]["last"])
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

# ----------------- ARAYÜZ -----------------
st.sidebar.title("⚙️ OKX Spot Bot")
inst_id = st.sidebar.selectbox("Sembol", ["BTC-USDT", "ETH-USDT", "SOL-USDT", "AVAX-USDT"])
usdt_amount = st.sidebar.number_input("Alım Miktarı (USDT)", 10, 100000, 50)

df = get_candles(inst_id)

if df.empty:
    st.error("Veri çekilemedi.")
else:
    last = df.iloc[-1]
    fiyat = last["Close"]
    rsi = last["RSI"]
    sma = last["SMA20"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Fiyat", f"{fiyat:.4f} USDT")
    c2.metric("RSI", f"{rsi:.2f}")
    c3.metric("SMA20", f"{sma:.2f}")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["time"], y=df["Close"], name="Fiyat"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["SMA20"], name="SMA20"))
    fig.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("🟢 İşlem")
    if st.button("Piyasa Fiyatından AL"):
        f, qty, res = okx_buy(inst_id, usdt_amount)
        st.success(f"{inst_id} için {qty} adet ALINDI @ {f:.4f}")
        st.json(res)

    if st.button("Piyasa Fiyatından SAT"):
        qty = st.number_input("Satılacak Adet", 0.0001, 9999.0, 0.01)
        res = okx_sell(inst_id, qty)
        st.success(f"{inst_id} için {qty} adet SATILDI")
        st.json(res)
