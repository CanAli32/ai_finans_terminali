import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
from datetime import datetime
import sqlite3

import okx.Market_api as Market
import okx.Trade_api as Trade

# ----------------- AYARLAR -----------------
st.set_page_config(page_title="AI Finansal Terminal Pro (OKX)", layout="wide", page_icon="📈")

OKX_API_KEY = st.secrets["OKX_API_KEY"]
OKX_API_SECRET = st.secrets["OKX_API_SECRET"]
OKX_PASSPHRASE = st.secrets["OKX_PASSPHRASE"]

# flag: "0" = demo, "1" = real
FLAG = "1"

market_api = Market.MarketAPI(
    api_key=OKX_API_KEY,
    api_secret_key=OKX_API_SECRET,
    passphrase=OKX_PASSPHRASE,
    flag=FLAG
)

trade_api = Trade.TradeAPI(
    api_key=OKX_API_KEY,
    api_secret_key=OKX_API_SECRET,
    passphrase=OKX_PASSPHRASE,
    flag=FLAG
)

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
CHAT_ID = st.secrets.get("CHAT_ID", "")

# ----------------- TELEGRAM -----------------
def telegram_gonder(mesaj: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj})
    except:
        pass

# ----------------- OKX SEMBOL LİSTESİ (SPOT USDT) -----------------
def get_okx_usdt_symbols():
    try:
        res = market_api.get_tickers(instType="SPOT")
        data = res.get("data", [])
        usdt_pairs = [
            d["instId"] for d in data
            if d.get("quoteCcy") == "USDT" and d.get("state") == "live"
        ]
        return sorted(usdt_pairs)
    except Exception as e:
        st.warning(f"Sembol listesi alınamadı, varsayılan liste kullanılıyor. Hata: {e}")
        return ["BTC-USDT", "ETH-USDT", "SOL-USDT", "AVAX-USDT"]

KRIPTO_LISTESI = get_okx_usdt_symbols()

# ----------------- VERİ ÇEKME (OKX CANDLE) -----------------
def get_crypto_data(inst_id: str) -> pd.DataFrame:
    try:
        # bar: 1D = günlük
        res = market_api.get_candlesticks(instId=inst_id, bar="1D", limit="180")
        data = res.get("data", [])
        if not data:
            return pd.DataFrame()

        # OKX candlesticks: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        df = pd.DataFrame(data, columns=[
            "ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"
        ])

        df["time"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
        df["Close"] = df["close"].astype(float)

        df = df.sort_values("time")  # eski → yeni

        df["RSI"] = ta.rsi(df["Close"], length=14)
        df["SMA20"] = ta.sma(df["Close"], length=20)

        return df

    except Exception as e:
        st.error(f"Veri çekme hatası (OKX): {e}")
        return pd.DataFrame()

# ----------------- AI ANALİZ (PLACEHOLDER) -----------------
def ai_analiz_al(hisse_kodu, fiyat, rsi, sma):
    return "Cloud ortamında harici LLM kullanımı kapalı olduğu için AI analizi devre dışı."

# ----------------- AL / SAT (OKX SPOT) -----------------
def okx_al(inst_id: str, usdt_miktar: float):
    """
    OKX spot market buy:
    - tdMode: 'cash' (spot)
    - side: 'buy'
    - ordType: 'market'
    - sz: alınacak miktar (base ccy) veya
    - notional: USDT tutarı (bazı hesaplarda desteklenir)
    Burada basit yaklaşım: önce son fiyatı çekip yaklaşık miktar hesaplıyoruz.
    """
    try:
        # Son fiyat
        ticker = market_api.get_ticker(instId=inst_id)
        last = float(ticker["data"][0]["last"])
        qty = round(usdt_miktar / last, 6)

        order = trade_api.place_order(
            instId=inst_id,
            tdMode="cash",
            side="buy",
            ordType="market",
            sz=str(qty)
        )
        return last, qty, order
    except Exception as e:
        return None, None, str(e)

def okx_sat(inst_id: str, qty: float):
    try:
        order = trade_api.place_order(
            instId=inst_id,
            tdMode="cash",
            side="sell",
            ordType="market",
            sz=str(qty)
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
    cursor.execute(
        "INSERT INTO islemler VALUES (?, ?, ?, ?, ?, ?)",
        (tarih, varlik, fiyat, rsi, onay, analiz)
    )
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

st.sidebar.title("🤖 Robot Kontrol")
kategori = st.sidebar.radio("Varlık Türü:", ["Kripto"])
liste = KRIPTO_LISTESI
secilen = st.sidebar.selectbox("Varlık Seç (OKX Spot USDT):", liste)

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
    c1.metric("Fiyat (USDT)", f"{fiyat:,.4f}")
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

        st.subheader("🟢 Manuel İşlem")
        if st.button("Piyasa Fiyatından AL"):
            f, qty, sonuc = okx_al(secilen, miktar)
            if f is None:
                st.error(f"AL emri hatası: {sonuc}")
            else:
                st.success(f"{secilen} için ~{qty} adet ALINDI @ {f:.4f} USDT")
                telegram_gonder(f"AL EMRİ: {secilen} ~{qty} adet @ {f:.4f} USDT")

    with col_right:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["time"], y=df["Close"], name="Fiyat"))
        fig.add_trace(go.Scatter(x=df["time"], y=df["SMA20"], name="SMA20"))
        fig.update_layout(template="plotly_dark", height=450, title=f"{secilen} Canlı Grafik (OKX)")
        st.plotly_chart(fig, use_container_width=True)

else:
    st.error("Veri çekilemedi. OKX bağlantısını veya sembolü kontrol edin.")
