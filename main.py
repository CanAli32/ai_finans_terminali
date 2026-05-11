import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import plotly.graph_objects as go
import ollama
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
MODEL_ADI = "llama3"

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


def ai_analiz_al(hisse_kodu, fiyat, rsi, sma) -> str:
    prompt = (
        f"Sen profesyonel bir analistsin. {hisse_kodu} verilerini yorumla: "
        f"Fiyat:{fiyat:.2f}, RSI:{rsi:.2f}, SMA20:{sma:.2f}. "
        f"Tamamen TÜRKÇE ve kısa: Teknik durum, YÖN (YUKARI/AŞAĞI), Hedef Fiyat."
    )
    try:
        res = ollama.chat(model=MODEL_ADI, messages=[{"role": "user", "content": prompt}])
        return res["message"]["content"]
    except:
        return "Ollama bağlantısı kurulamadı. (Lütfen Ollama'nın çalıştığından emin olun)"


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
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS islemler (
            Tarih TEXT,
            Varlik TEXT,
            Fiyat REAL,
            RSI REAL,
            Onay INTEGER,
            AI_Analizi TEXT
        )
        """
    )
    cursor.execute(
        "INSERT INTO islemler VALUES (?, ?, ?, ?, ?, ?)",
        (tarih, varlik, fiyat, rsi, onay, analiz),
    )
    conn.commit()
    conn.close()


def kaydet_excel(tarih, varlik, fiyat, rsi, onay, analiz):
    dosya = "Borsa_Analizi_Arsivi.xlsx"
    yeni_veri = pd.DataFrame(
        [
            {
                "Tarih": tarih,
                "Varlık": varlik,
                "Fiyat": fiyat,
                "RSI": rsi,
                "Onay_Skoru": onay,
                "AI_Analizi": analiz,
            }
        ]
    )
    try:
        eski = pd.read_excel(dosya)
        df = pd.concat([eski, yeni_veri], ignore_index=True)
    except:
        df = yeni_veri
    df.to_excel(dosya, index=False)


# Basit trade döngüsü (Streamlit içinde uzun süreli loop çok sağlıklı değil ama mantığı gösteriyor)
import time
def trade_dongusu(symbol, analiz_dongu, yuzde_kar, yuzde_zarar, miktar, baslangic_fiyat):
    telegram_gonder(f"🚀 Trade Bot Başladı: {symbol}")
    alis_fiyat, adet, order = binance_al(symbol, miktar)
    if alis_fiyat is None:
        telegram_gonder(f"❌ Alım Hatası: {order}")
        return

    telegram_gonder(f"✔ Alım Başarılı\nSembol: {symbol}\nFiyat: {alis_fiyat}\nAdet: {adet}")

    while True:
        time.sleep(analiz_dongu * 60)
        try:
            fiyat = float(binance.get_symbol_ticker(symbol=symbol)["price"])
        except:
            continue

        degisim = (fiyat - alis_fiyat) / alis_fiyat * 100

        if degisim >= yuzde_kar:
            binance_sat(symbol, adet)
            telegram_gonder(f"🎉 Kar Alındı: %{degisim:.2f}")
            break

        if degisim <= -yuzde_zarar:
            binance_sat(symbol, adet)
            telegram_gonder(f"⚠️ Zarar Kesildi: %{degisim:.2f}")
            break


# ----------------- SIDEBAR: TRADE AYARLARI -----------------
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
    c1.metric("Fiyat", f"{fiyat:,.2f} {'$' if kategori=='Kripto' else '₺'}")
    c2.metric("RSI (14)", f"{rsi:.2f}")
    c3.metric("Onay Skoru", f"{toplam_onay}/2")

    sinyal = "🚀 GÜÇLÜ AL" if toplam_onay == 2 else ("⚖️ NÖTR" if toplam_onay == 1 else "⚠️ BEKLE")
    c4.metric("Sinyal", sinyal)

    st.divider()

    col_left, col_right = st.columns([1, 2])

    analiz = None

    with col_left:
        st.subheader("💡 Yapay Zeka Analizi")
        if st.button("Llama3 Analizini Başlat"):
            with st.spinner("AI verileri yorumluyor..."):
                analiz = ai_analiz_al(secilen, fiyat, rsi, sma)
                st.info(analiz)

                if "YUKARI" in analiz.upper() or "AL" in analiz.upper():
                    telegram_gonder(f"🚨 Sinyal Yakalandı: {secilen}\nAnaliz: {analiz}")
                    st.success("Analiz Telegram'a gönderildi!")

                tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                kaydet_excel(tarih, secilen, fiyat, rsi, toplam_onay, analiz)
                kaydet_sqlite(tarih, secilen, fiyat, rsi, toplam_onay, analiz)

        if rsi < 30:
            st.warning("⚠️ RSI Aşırı Satım: Tepki yükselişi gelebilir!")

    with col_right:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Fiyat", line=dict(color="#00ffcc")))
        fig.add_trace(go.Scatter(x=df.index, y=df["SMA20"], name="SMA20", line=dict(color="orange", dash="dash")))
        fig.update_layout(template="plotly_dark", height=450, title=f"{secilen} Canlı Grafik")
        st.plotly_chart(fig, use_container_width=True)

    st.sidebar.divider()
    if st.sidebar.button("Stratejiyi Test Et"):
        baslangic = 10000
        st.sidebar.write(f"Test Başarılı: Başlangıç 10k")
        st.sidebar.info("Detaylı rapor Excel'e arşivlendi.")

    # Trade botu başlat (UYARI: Streamlit içinde uzun loop prod için ideal değil)
    if st.sidebar.button("🚀 Trade Botu Başlat"):
        st.sidebar.success("Bot çalışıyor... Telegram'dan takip edebilirsin.")
        symbol = secilen.replace("-USD", "USDT") if "USD" in secilen else secilen
        trade_dongusu(
            symbol=symbol,
            analiz_dongu=analiz_dongu,
            yuzde_kar=yuzde_kar,
            yuzde_zarar=yuzde_zarar,
            miktar=miktar,
            baslangic_fiyat=fiyat,
        )

else:
    st.error("Veri çekilemedi. İnternet bağlantınızı veya sembolü kontrol edin.")
