import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
from datetime import datetime
from binance.client import Client
import sqlite3

# ----------------- AYARLAR -----------------
st.set_page_config(page_title="AI Finansal Terminal Pro", layout="wide", page_icon="📈")

api_key = st.secrets["BINANCE_API_KEY"]
api_secret = st.secrets["BINANCE_API_SECRET"]

# Binance Global
binance = Client(api_key, api_secret)

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
CHAT_ID = st.secrets.get("CHAT_ID", "")

# ----------------- KRİPTO LİSTESİ (GLOBAL USDT PARİTELERİ) -----------------
def get_binance_global_usdt_symbols():
    try:
        info = binance.get_exchange_info()
        symbols = info["symbols"]
        usdt_pairs = [
            s["symbol"] for s in symbols
            if s["quoteAsset"] == "USDT" and s["status"] == "TRADING"
        ]
        return sorted(usdt_pairs)
    except:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "BNBUSDT"]

KRIPTO_LISTESI = get_binance_global_usdt_symbols()
BIST_LISTESI = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "AKBNK.IS"]  # Şimdilik pasif

# ----------------- TELEGRAM -----------------
def telegram_gonder(mesaj: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj})
    except:
        pass

# ----------------- VERİ ÇEKME (BINANCE GLOBAL) -----------------
def get_crypto_data(symbol):
    try:
        klines = binance.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1DAY, limit=180)

        df = pd.DataFrame(klines, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        df["time"] = pd.to_datetime(df["time"], unit="ms")
        df["Close"] = df["close"].astype(float)

        df["RSI"] = ta.rsi(df["Close"], length=14)
        df["SMA20"] = ta.sma(df["Close"], length=20)

        return df

    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return pd.DataFrame()

# ----------------- AI ANALİZ -----------------
def ai_analiz_al(hisse_kodu, fiyat, rsi, sma):
    return "Cloud ortamında Ollama desteklenmediği için AI analizi devre dışı."

# ----------------- AL / SAT (GLOBAL) -----------------
def binance_al(symbol, usdt_miktar):
    try:
        fiyat = float(binance.get_symbol_ticker(symbol=symbol)["price"])
        adet = round(usdt_miktar / fiyat, 6)

        order = binance.order_market_buy(
            symbol=symbol,
            quoteOrderQty=usdt_miktar
        )
        return fiyat, adet, order
    except Exception as e:
        return None, None, str(e)

def binance_sat(symbol, adet):
    try:
        order = binance.order_market_sell(
            symbol=symbol,
            quantity=adet
        )
        return order
    except Exception as e:
        return str(e)

# ----------------- KAYIT -----------------
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

# ----------------- ARAYÜZ -----------------
st.sidebar.subheader("⚙️ Trade Ayarları")
analiz_dongu = st.sidebar.number_input("Analiz Döngüsü (dakika)", 1, 120, 5)
yuzde_kar = st.sidebar.number_input("Satış Kar Yüzdesi (%)", 1, 50, 5)
yuzde_zarar = st.sidebar.number_input("Zarar Kes (%)", 1, 50, 3)
miktar = st.sidebar.number_input("Alım Miktarı (USDT)", 10, 100000, 50)

st.sidebar.title("🤖 AI Robot Kontrol")
kategori = st.sidebar.radio("Varlık Türü:", ["Kripto"])  # BIST şimdilik devre dışı
liste = KRIPTO_LISTESI
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
    c1.metric("Fiyat (USDT)", f"{fiyat:,.2f}")
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
        fig.add_trace(go.Scatter(x=df["time"], y=df["Close"], name="Fiyat"))
        fig.add_trace(go.Scatter(x=df["time"], y=df["SMA20"], name="SMA20"))
        fig.update_layout(template="plotly_dark", height=450, title=f"{secilen} Canlı Grafik")
        st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Veri çekilemedi. Binance Global bağlantısını kontrol edin.")
