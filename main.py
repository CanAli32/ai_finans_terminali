import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import requests
import smtplib
from datetime import datetime
from email.message import EmailMessage
from binance.client import Client
from groq import Groq
from streamlit_gsheets import GSheetsConnection
import streamlit_autorefresh as st_autorefresh

# --- 1. AYARLAR VE OTOMATİK YENİLEME ---
st.set_page_config(page_title="AI Finansal Robot", layout="wide", page_icon="🤖")
st_autorefresh.st_autorefresh(interval=5 * 60 * 1000, key="datarefresh") # 5 dkda bir yenile

# --- 2. BAĞLANTILAR (Google Sheets & Groq) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    return conn.read(worksheet="Sayfa1")

def bildirim_gonder(baslik, mesaj):
    msg = EmailMessage()
    msg.set_content(mesaj)
    msg['Subject'] = baslik
    msg['From'] = st.secrets["EMAIL_USER"]
    msg['To'] = st.secrets["MY_EMAIL"]
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(st.secrets["EMAIL_USER"], st.secrets["EMAIL_PASS"])
            smtp.send_message(msg)
    except: pass

# --- 3. BORSA VE İŞLEM FONKSİYONLARI ---
def islem_yap(sembol, miktar, yon):
    client = Client(st.secrets["BINANCE_API_KEY"], st.secrets["BINANCE_SECRET_KEY"])
    try:
        side = 'BUY' if yon == "AL" else 'SELL'
        order = client.create_order(symbol=sembol, side=side, type='MARKET', quantity=miktar)
        return order
    except Exception as e:
        st.error(f"Borsa Hatası: {e}")
        return None

# --- 4. BACKTEST VE AI OPTİMİZASYON ---
def backtest_stratejisi(df_v):
    bakiye, adet, islemler = 10000, 0, []
    for i in range(1, len(df_v)):
        fiyat, rsi = df_v.iloc[i]['Fiyat'], df_v.iloc[i]['RSI']
        if rsi < 30 and bakiye > fiyat:
            adet = bakiye / fiyat
            bakiye = 0
            islemler.append(f"AL: {fiyat}")
        elif rsi > 70 and adet > 0:
            bakiye = adet * fiyat
            adet = 0
            islemler.append(f"SAT: {fiyat}")
    return bakiye if adet == 0 else adet * df_v.iloc[-1]['Fiyat']

# --- 5. ANA PANEL VE UI ---
df = get_data()
df['Tarih'] = pd.to_datetime(df['Tarih'])

st.sidebar.title("🎮 Robot Kontrol")
varlik_listesi = df['Varlık'].unique()
secilen = st.sidebar.selectbox("Varlık Seç:", varlik_listesi)

v_df = df[df['Varlık'] == secilen].sort_values('Tarih')
son = v_df.iloc[-1]

# Üst Metrikler
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fiyat", f"{son['Fiyat']:,} ₺")
c2.metric("RSI", son['RSI'])
c3.metric("Onay", son['Onay_Skoru'])
c4.metric("Sinyal", "🚀 GÜÇLÜ" if son['RSI'] < 35 else "⚖️ NÖTR")

# --- 6. OTONOM KARAR VE RİSK YÖNETİMİ ---
st.divider()
col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("💡 Robot Kararı")
    if son['RSI'] < 30:
        st.warning("ALIM KOŞULU OLUŞTU!")
        if st.button("Manuel Onaylı Satın Al"):
            res = islem_yap(secilen, 0.001, "AL")
            if res: bildirim_gonder("İşlem Başarılı", f"{secilen} Alındı.")
    
    # AI Strateji Notu
    st.info(f"AI Analizi: {son['AI_Analizi']}")

with col_right:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=v_df['Tarih'], y=v_df['Fiyat'], name="Fiyat"))
    fig.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig, use_container_width=True)

# --- 7. BACKTEST BUTONU ---
if st.sidebar.button("Backtest Çalıştır"):
    sonuc = backtest_stratejisi(v_df)
    st.sidebar.write(f"10.000₺ -> {sonuc:,.2f} ₺")
