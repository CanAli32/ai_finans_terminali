import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import plotly.graph_objects as go
import requests
from datetime import datetime
from binance.spot import Spot
import sqlite3

# ----------------- AYARLAR -----------------
st.set_page_config(page_title="AI Finansal Terminal Pro", layout="wide", page_icon="📈")

api_key = st.secrets["BINANCE_API_KEY"]
api_secret = st.secrets["BINANCE_API_SECRET"]

# Binance TR endpoint
binance = Spot(
    api_key=api_key,
    api_secret=api_secret,
    base_url="https://api.binance.me"
)

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
CHAT_ID = st.secrets.get("CHAT_ID", "")

KRIPTO_LISTESI = ["BTCTRY", "ETHTRY", "SOLTRY", "AVAXTRY", "USDTTRY"]
BIST_LISTESI = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "AKBNK.IS"]

# ----------------- YARDIMCI FONKSİYONLAR -----------------
def telegram_gonder(mesaj: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj})
    except:
        pass


def get_crypto_data(hisse_kodu: str) -> pd.DataFrame:
    # Binance TR fiyatları TRY olduğu için yfinance'tan USD paritesi çekiyoruz
    # Örn: BTCTRY → BTC-USD
    if hisse_kodu.endswith("TRY"):
        symbol = hisse_kodu.replace("TRY", "-USD")
    else:
        symbol = hisse_kodu

    ticker = yf.Ticker(symbol
