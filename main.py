import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import plotly.graph_objects as go
import requests
from datetime import datetime
from binance.client import Client
import sqlite3

# ----------------- AYARLAR -----------------
st.set_page_config(page_title="AI Finansal Terminal Pro", layout="wide", page_icon="📈")

api_key = st.secrets["BINANCE_API_KEY"]
api_secret = st.secrets["BINANCE_API_SECRET"]
binance = Client(api_key, api_secret)

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
CHAT_ID = st.secrets.get("CHAT_ID", "")

KRIPTO_LISTESI = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD"]
BIST_LISTESI = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "AKBNK.IS"]

# ----------------- YARDIMCI FONKSİYONLAR -----------------
def telegram_gonder(mesaj: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj})
    except:
        pass


def get_crypto_data(hisse_kodu: str) -> pd.DataFrame:
    ticker = yf.Ticker(hisse_kodu)
    df = ticker.history(period="6mo", interval="1d")
    if not df.empty:
        df["RSI"] = ta.rsi(df["Close"], length=14)
        df["SMA20"] = ta.sma(df["Close"], length=20)
        return df
    return pd.DataFrame()


def ai_analiz_al(hisse_kodu, fiyat, rsi, sma):
    return "Cloud ortamında Ollama desteklenmediği için AI analizi devre dışı."


def binance_al(symbol, usdt_miktar):
    try:
        fiyat = float(binance.get_symbol_ticker(symbol=symbol)["price"])
        adet = round(usdt_miktar / fiyat, 6)
        order = binance.order_market_buy(symbol=symbol, quantity=adet)
        return fiyat, adet, order
    except Exception as e:
        return None, None, str(e)


def binance_sat(symbol, adet):
    try:
        order = binance.order_market_sell(symbol=symbol, quantity=adet)
        return order
    except Exception as e:
        return str(e)


def kaydet_sqlite(tarih, varlik, fiyat, rsi, onay, analiz):
    conn = sqlite3.connect("trade_kayitlari.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS islemler (
            Tarih TEXT,
            Varlik TEXT,
            Fiyat REAL,
            RSI REAL,
            Onay INTEGER,
            AI_Analizi TEXT
        )
    """)
    cursor.execute("INSERT INTO islemler VALUES (?, ?, ?, ?, ?, ?)",
                   (tarih, varlik, fiyat, rsi, onay, analiz))
    conn.commit()
    conn.close()


def kaydet_excel(tarih, varlik, fiyat, rsi, onay, analiz):
    dosya = "Borsa_Analizi_Arsivi.xlsx"
    yeni_veri = pd.DataFrame([{
        "Tarih": tarih,
        "Varlık": varlik,
        "Fiyat": fiyat,
        "RSI": rsi,
        "Onay_Skoru": onay,
        "AI_Analizi": analiz
    }])
    try:
        eski = pd.read_excel(dosya)
        df = pd.concat([eski, yeni_veri], ignore_index=True)
    except:
        df = yeni_veri
    df.to_excel(dosya, index=False)


# ----------------- SIDEBAR -----------------
st.sidebar.subheader("⚙️ Trade Ayarları")
analiz_dongu = st.sidebar.number_input("Analiz Döngüsü (dakika)", 1, 120, 5)
yuzde_kar = st.sidebar.number_input("Satış Kar Yüzdesi (%)", 1, 50, 5)
yuzde_zarar = st.sidebar.number_input("Zarar Kes (%)", 1, 50, 3)
miktar = st.sidebar.number_input("Alım Miktarı (USDT)", 10, 10000, 50)

st.sidebar.title("🤖 AI Robot Kontrol")
kategori = st.sidebar.radio("Varlık Türü:", ["Kripto", "BIST"])
liste = KRIPTO_LISTESI if kategori == "Kripto" else BIST_LISTESI
secilen = st.sidebar.selectbox("Varlık Seç:", liste)

# ----------------- VERİ ÇEKME -----------------
df = get_crypto_data(secilen)

if not df.empty:
    son_veri = df.iloc[-1]
    fiyat = son_veri["Close"]
    rsi = son_veri["RSI"] if not pd.isna(son_veri["RSI"]) else 50.0
    sma = son_veri["SMA20"] if not pd.isna(son_veri["SMA20"]) else fiyat

    onay_rsi = 1 if rsi < 35 else 0
    onay_trend = 1 if fiyat > sma else 0
    toplam_onay = onay_rsi + onay_trend

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fiyat", f"{fiyat:,.2f}")
    c2.metric("RSI (14)", f"{rsi:.2f}")
    c3.metric("Onay Skoru", f"{toplam_onay}/2")
    sinyal = "🚀 GÜÇLÜ AL" if toplam_onay == 2 else ("⚖️ NÖTR" if toplam_onay == 1 else "⚠️ BEKLE")
    c4.metric("Sinyal", sinyal)

    st.divider()

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("💡 Yapay Zeka Analizi")
        if st.button("AI Analizini Başlat"):
            analiz = ai_analiz_al(secilen, fiyat, rsi, sma)
            st.info(analiz)

            tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            kaydet_excel(tarih, secilen, fiyat, rsi, toplam_onay, analiz)
            kaydet_sqlite(tarih, secilen, fiyat, rsi, toplam_onay, analiz)

    with col_right:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Fiyat"))
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], name="SMA20"))
        fig.update_layout(template="plotly_dark", height=450, title=f"{secilen} Canlı Grafik")
        st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Veri çekilemedi. İnternet bağlantınızı veya sembolü kontrol edin.")
