import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import requests
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="AI Finansal Takip Paneli", layout="wide", page_icon="📈")

# Stil Dosyası (Koyu Tema Desteği)
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---
def get_fng():
    try:
        r = requests.get("https://alternative.me").json()
        return r['data']['value'], r['data']['value_classification']
    except: return "50", "Nötr"

# --- VERİ YÜKLEME ---
if os.path.exists("Borsa_Analiz_Arsivi.xlsx"):
    df = pd.read_excel("Borsa_Analiz_Arsivi.xlsx")
    df['Tarih'] = pd.to_datetime(df['Tarih'])
    
    # --- SIDEBAR (YAN PANEL) ---
    st.sidebar.title("🎮 Kontrol Paneli")
    
    # Korku ve Açgözlülük Endeksi Göstergesi
    fng_val, fng_cls = get_fng()
    st.sidebar.subheader("🌍 Kripto Duyarlılığı")
    st.sidebar.metric("Fear & Greed Index", f"{fng_val}/100", fng_cls)
    
    st.sidebar.divider()
    
    # Filtreler
    piyasa_tipi = st.sidebar.multiselect("Piyasa Seçin:", ["BIST", "KRIPTO"], default=["BIST", "KRIPTO"])
    # Varlık seçimi (Hisse veya Kripto)
    varlik_listesi = df['Varlık'].unique()
    secilen_varlik = st.sidebar.selectbox("Detaylı İncele:", varlik_listesi)

    # --- ANA PANEL ---
    st.title("🤖 AI Otonom Yatırım İstasyonu")
    st.caption(f"Son Güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    # Üst Metrikler (Seçilen Varlığa Göre)
    varlik_df = df[df['Varlık'] == secilen_varlik]
    son_kayit = varlik_df.iloc[-1]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Son Fiyat", f"{son_kayit['Fiyat']:,}")
    with m2:
        st.metric("RSI (14)", son_kayit['RSI'])
    with m3:
        st.metric("Onay Skoru", son_kayit['Onay_Skoru'])
    with m4:
        trend = "YUKARI" if "2/2" in str(son_kayit['Onay_Skoru']) else "ZAYIF"
        st.metric("Trend Gücü", trend)

    st.divider()

    # Orta Bölüm: AI Analizi ve Grafik
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("💡 Yapay Zeka Kararı")
        st.info(son_kayit['AI_Analizi'])
        
    with col_right:
        st.subheader(f"📈 {secilen_varlik} Fiyat Geçmişi")
        fig = px.line(varlik_df, x='Tarih', y='Fiyat', markers=True, 
                     line_shape='spline', render_mode='svg')
        fig.update_layout(template="plotly_dark", margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # Alt Bölüm: Tüm Arşiv Tablosu
    st.subheader("📋 Analiz Arşivi (Tüm Kayıtlar)")
    st.dataframe(df.sort_values(by='Tarih', ascending=False), use_container_width=True)

    # --- CSV İNDİRME BUTONU ---
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Verileri CSV Olarak İndir", csv, "borsa_analiz.csv", "text/csv")

else:
    st.error("❌ Arşiv dosyası (Borsa_Analiz_Arsivi.xlsx) bulunamadı!")
    st.info("Lütfen önce ana botu çalıştırarak verilerin oluşmasını sağlayın.")
