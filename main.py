import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import smtplib
from datetime import datetime
from email.message import EmailMessage
from binance.client import Client
from groq import Groq
from streamlit_gsheets import GSheetsConnection
import streamlit_autorefresh as st_autorefresh

# --- 1. AYARLAR VE OTOMATİK YENİLEME ---
st.set_page_config(page_title="AI Finansal Robot Pro", layout="wide", page_icon="🤖")
st_autorefresh.st_autorefresh(interval=5 * 60 * 1000, key="datarefresh")

# --- 2. BAĞLANTILAR (Google Sheets, Groq & Binance) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    try:
        data = conn.read()
        return data
    except Exception as e:
        st.error(f"Veri Bağlantı Hatası: {e}")
        return pd.DataFrame()

def ai_analiz_al(fiyat, rsi, sembol):
    try:
        client = Groq(api_key=st.secrets["GROQ_API_KEY"])
        prompt = f"{sembol} için anlık fiyat {fiyat} ve RSI değeri {rsi}. Kısa bir teknik analiz ve aksiyon tavsiyesi ver."
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content
    except:
        return "AI Analizi şu an yapılamıyor."

def bildirim_gonder(baslik, mesaj):
    msg = EmailMessage()
    msg.set_content(mesaj)
    msg['Subject'] = baslik
    msg['From'] = st.secrets["EMAIL_USER"]
    msg['To'] = st.secrets["MY_EMAIL"]
    try:
        with smtplib.SMTP_SSL('://gmail.com', 465) as smtp:
            smtp.login(st.secrets["EMAIL_USER"], st.secrets["EMAIL_PASS"])
            smtp.send_message(msg)
    except Exception as e:
        st.sidebar.error(f"E-posta Hatası: {e}")

# --- 3. BORSA İŞLEM FONKSİYONU ---
def islem_yap(sembol, miktar, yon):
    try:
        client = Client(st.secrets["BINANCE_API_KEY"], st.secrets["BINANCE_SECRET_KEY"])
        side = Client.SIDE_BUY if yon == "AL" else Client.SIDE_SELL
        order = client.create_order(symbol=sembol, side=side, type=Client.ORDER_TYPE_MARKET, quantity=miktar)
        return order
    except Exception as e:
        st.error(f"Binance API Hatası: {e}")
        return None

# --- 4. BACKTEST MOTORU ---
def backtest_stratejisi(df_v):
    bakiye, adet = 10000, 0
    for i in range(1, len(df_v)):
        fiyat, rsi = df_v.iloc[i]['Fiyat'], df_v.iloc[i]['RSI']
        if rsi < 30 and bakiye > fiyat:
            adet = bakiye / fiyat
            bakiye = 0
        elif rsi > 70 and adet > 0:
            bakiye = adet * fiyat
            adet = 0
    return bakiye if adet == 0 else adet * df_v.iloc[-1]['Fiyat']

# --- 5. ANA PANEL VERİ İŞLEME ---
df = get_data()
if not df.empty:
    df['Tarih'] = pd.to_datetime(df['Tarih'])
    
    st.sidebar.title("🎮 Robot Kontrol")
    varlik_listesi = df['Varlık'].unique()
    secilen = st.sidebar.selectbox("Varlık Seç:", varlik_listesi)
    
    v_df = df[df['Varlık'] == secilen].sort_values('Tarih')
    son_veri = v_df.iloc[-1]

    # Metrik Paneli
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fiyat", f"{son_veri['Fiyat']:,} ₺")
    c2.metric("RSI", round(son_veri['RSI'], 2))
    c3.metric("Onay Skoru", f"%{son_veri['Onay_Skoru']}")
    sinyal = "🚀 AL" if son_veri['RSI'] < 35 else ("⚠️ SAT" if son_veri['RSI'] > 65 else "⚖️ NÖTR")
    c4.metric("Sinyal", sinyal)

    # --- 6. GÖRSELLEŞTİRME VE AI KARARI ---
    st.divider()
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("💡 Robot Kararı & AI")
        if st.button("Güncel AI Analizi Al"):
            analiz = ai_analiz_al(son_veri['Fiyat'], son_veri['RSI'], secilen)
            st.info(analiz)
        
        if son_veri['RSI'] < 30:
            st.warning("RSI Aşırı Satım Bölgesinde!")
            if st.button(f"{secilen} Satın Al"):
                res = islem_yap(secilen.replace("₺", "USDT"), 0.001, "AL") # Örnek dönüşüm
                if res: 
                    st.success("İşlem Başarılı!")
                    bildirim_gonder("İşlem Gerçekleşti", f"{secilen} alımı yapıldı.")

    with col_right:
        # Mum Grafiği (Veride Açılış/Yüksek/Düşük varsa eklenebilir, yoksa Çizgiye devam)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=v_df['Tarih'], y=v_df['Fiyat'], mode='lines+markers', name="Fiyat", line=dict(color='#00ffcc')))
        fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # --- 7. SIDEBAR ARAÇLARI ---
    if st.sidebar.button("Backtest Çalıştır"):
        sonuc = backtest_stratejisi(v_df)
        st.sidebar.write(f"Başlangıç: 10.000₺")
        st.sidebar.write(f"Sonuç: **{sonuc:,.2f} ₺**")
else:
    st.warning("Veri bekleniyor... Lütfen Google Sheets bağlantısını kontrol edin.")
