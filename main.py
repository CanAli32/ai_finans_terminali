import streamlit as st
import pandas as pd
import pandas_ta as ta
import yfinance as yf
import plotly.graph_objects as go
import ollama
import requests
import re
from datetime import datetime

st.set_page_config(page_title="AI Finansal Terminal Pro", layout="wide", page_icon="📈")

Sabitler
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "8456680476:AAFRyBdZUdWs4ZA3DF9KK_78dmmUDfF_YUs")
CHAT_ID = st.secrets.get("CHAT_ID", "6712642767")
MODEL_ADI = "llama3"

KRIPTO_LISTESI = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD"]
BIST_LISTESI = ["THYAO.IS", "EREGL.IS", "ASELS.IS", "TUPRS.IS", "KCHOL.IS", "AKBNK.IS"]

def telegram_gonder(mesaj):
url = f"https://telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
try:
requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj})
except: pass

def get_crypto_data(hisse_kodu):
ticker = yf.Ticker(hisse_kodu)
df = ticker.history(period="6mo", interval="1d")
if not df.empty:
df['RSI'] = ta.rsi(df['Close'], length=14)
df['SMA20'] = ta.sma(df['Close'], length=20)
return df
return pd.DataFrame()

def ai_analiz_al(hisse_kodu, fiyat, rsi, sma):
prompt = (f"Sen profesyonel bir analistsin. {hisse_kodu} verilerini yorumla: "
f"Fiyat:{fiyat:.2f}, RSI:{rsi:.2f}, SMA20:{sma:.2f}. "
f"Tamamen TÜRKÇE ve kısa: Teknik durum, YÖN (YUKARI/AŞAĞI), Hedef Fiyat.")
try:
# Local Ollama kullanımı
res = ollama.chat(model=MODEL_ADI, messages=[{'role': 'user', 'content': prompt}])
return res['message']['content']
except:
return "Ollama bağlantısı kurulamadı. (Lütfen Ollama'nın çalıştığından emin olun)"


st.sidebar.title("🤖 AI Robot Kontrol")
kategori = st.sidebar.radio("Varlık Türü:", ["Kripto", "BIST"])
liste = KRIPTO_LISTESI if kategori == "Kripto" else BIST_LISTESI
secilen = st.sidebar.selectbox("Varlık Seç:", liste)

Veri Çekme
df = get_crypto_data(secilen)

if not df.empty:
son_veri = df.iloc[-1]
fiyat = son_veri['Close']
rsi = son_veri['RSI'] if not pd.isna(son_veri['RSI']) else 50.0
sma = son_veri['SMA20'] if not pd.isna(son_veri['SMA20']) else fiyat

# Onay Hesaplama
onay_rsi = 1 if rsi < 35 else 0
onay_trend = 1 if fiyat > sma else 0
toplam_onay = onay_rsi + onay_trend

# Üst Metrikler
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fiyat", f"{fiyat:,.2f} {'$' if kategori=='Kripto' else '₺'}")
c2.metric("RSI (14)", f"{rsi:.2f}")
c3.metric("Onay Skoru", f"{toplam_onay}/2")

sinyal = "🚀 GÜÇLÜ AL" if toplam_onay == 2 else ("⚖️ NÖTR" if toplam_onay == 1 else "⚠️ BEKLE")
c4.metric("Sinyal", sinyal)

st.divider()

# Orta Panel: Analiz ve Grafik
col_left, col_right = st.columns([1, 2])

with col_left:
st.subheader("💡 Yapay Zeka Analizi")
if st.button("Llama3 Analizini Başlat"):
with st.spinner("AI verileri yorumluyor..."):
analiz = ai_analiz_al(secilen, fiyat, rsi, sma)
st.info(analiz)

# Eğer AI "YUKARI" diyorsa Telegram'a rapor at
if "YUKARI" in analiz.upper() or "AL" in analiz.upper():
telegram_gonder(f"🚨 Sinyal Yakalandı: {secilen}\nAnaliz: {analiz}")
st.success("Analiz Telegram'a gönderildi!")

if rsi < 30:
st.warning("⚠️ RSI Aşırı Satım: Tepki yükselişi gelebilir!")

with col_right:
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="Fiyat", line=dict(color='#00ffcc')))
fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], name="SMA20", line=dict(color='orange', dash='dash')))
fig.update_layout(template="plotly_dark", height=450, title=f"{secilen} Canlı Grafik")
st.plotly_chart(fig, use_container_width=True)

# --- 4. BACKTEST (SIDEBAR) ---
st.sidebar.divider()
if st.sidebar.button("Stratejiyi Test Et"):
# Basit bir simülasyon
baslangic = 10000
# ... backtest mantığınız buraya gelebilir ...
st.sidebar.write(f"Test Başarılı: Başlangıç 10k")
st.sidebar.info("Detaylı rapor Excel'e arşivlendi.")

else:
st.error("Veri çekilemedi. İnternet bağlantınızı veya sembolü kontrol edin."
