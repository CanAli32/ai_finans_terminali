import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import plotly.graph_objects as go
import requests
import smtplib
from email.message import EmailMessage
from binance.client import Client
from groq import Groq
from datetime import datetime

# --- 1. AYARLAR ---
st.set_page_config(page_title="AI Finansal Terminal Pro", layout="wide", page_icon="📈")

# Secrets'tan anahtarları çekiyoruz
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
BINANCE_API_KEY = st.secrets["BINANCE_API_KEY"]
BINANCE_SECRET_KEY = st.secrets["BINANCE_SECRET_KEY"]
TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
CHAT_ID = st.secrets["CHAT_ID"]

KRIPTO_LISTESI = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD"]
BIST_LISTESI = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "AKBNK.IS"]

# --- 2. FONKSİYONLAR ---

def telegram_gonder(mesaj):
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj})
    except: pass

def get_data(hisse_kodu):
    try:
        ticker = yf.Ticker(hisse_kodu)
        df = ticker.history(period="6mo", interval="1d")
        if not df.empty:
            df['RSI'] = ta.rsi(df['Close'], length=14)
            df['SMA20'] = ta.sma(df['Close'], length=20)
            return df
    except: return pd.DataFrame()
    return pd.DataFrame()

def ai_analiz_al(hisse_kodu, fiyat, rsi, sma):
    try:
        client = Groq(api_key=GROQ_API_KEY)
        prompt = f"{hisse_kodu} için Fiyat:{fiyat:.2f}, RSI:{rsi:.2f}, SMA20:{sma:.2f}. Türkçe kısa analiz ve YÖN ver."
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except: return "AI Analizi şu an yapılamıyor."

def islem_yap(sembol, yon):
    try:
        client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
        # Örnek: Sembolü Binance formatına çevir (BTC-USD -> BTCUSDT)
        binance_sym = sembol.replace("-USD", "USDT")
        # Test amaçlı miktar (Gerçek işlemde dikkatli olun!)
        # order = client.create_order(symbol=binance_sym, side=yon, type='MARKET', quantity=0.001)
        return True
    except Exception as e:
        st.error(f"Binance Hatası: {e}")
        return False

# --- 3. ARAYÜZ ---
st.sidebar.title("🤖 AI Robot Kontrol")
kategori = st.sidebar.radio("Varlık Türü:", ["Kripto", "BIST"])
secilen = st.sidebar.selectbox("Varlık Seç:", KRIPTO_LISTESI if kategori == "Kripto" else BIST_LISTESI)

df = get_data(secilen)

if not df.empty:
    son = df.iloc[-1]
    fiyat, rsi = son['Close'], (son['RSI'] if not pd.isna(son['RSI']) else 50.0)
    sma = son['SMA20'] if not pd.isna(son['SMA20']) else fiyat

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fiyat", f"{fiyat:,.2f}")
    c2.metric("RSI", f"{rsi:.2f}")
    onay = (1 if rsi < 35 else 0) + (1 if fiyat > sma else 0)
    c3.metric("Onay Skoru", f"{onay}/2")
    c4.metric("Sinyal", "🚀 AL" if onay == 2 else "⚖️ NÖTR")

    st.divider()
    col_l, col_r = st.columns([1, 2])

    with col_l:
        st.subheader("💡 AI Kararı")
        if st.button("Analiz Al"):
            analiz = ai_analiz_al(secilen, fiyat, rsi, sma)
            st.info(analiz)
            if "AL" in analiz.upper(): telegram_gonder(f"Sinyal: {secilen}\n{analiz}")
        
        if kategori == "Kripto":
            if st.button(f"Binance: {secilen} Satın Al"):
                if islem_yap(secilen, "BUY"): st.success("İşlem emri gönderildi!")

    with col_r:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Fiyat"))
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Veri yüklenemedi.")
