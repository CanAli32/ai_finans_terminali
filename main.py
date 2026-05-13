import streamlit as st
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import requests
import hmac
import hashlib
import time
import math
from datetime import datetime

# ----------------- STREAMLIT AYARLARI -----------------
st.set_page_config(page_title="Binance Spot Bot Pro", layout="wide", page_icon="📈")

# ----------------- SESSION STATE BAŞLATMA -----------------
if "trailing_aktif" not in st.session_state:
    st.session_state.trailing_aktif = False
if "en_yuksek_fiyat" not in st.session_state:
    st.session_state.en_yuksek_fiyat = 0.0
if "stop_fiyati" not in st.session_state:
    st.session_state.stop_fiyati = 0.0
if "trailing_miktar" not in st.session_state:
    st.session_state.trailing_miktar = 0.0
if "trailing_yuzde" not in st.session_state:
    st.session_state.trailing_yuzde = 1.0

# ----------------- GÜVENLİK KİLİDİ -----------------
def giris_kontrol():
    if "giris_basarili" not in st.session_state:
        st.title("🔒 Robot Erişim Kilidi")
        sifre = st.text_input("Erişim Şifresini Giriniz:", type="password")
        if st.button("Giriş Yap"):
            if sifre == "123456": 
                st.session_state.giris_basarili = True
                st.rerun()
            else:
                st.error("Hatalı Şifre!")
        return False
    return True

if not giris_kontrol():
    st.stop()

# ----------------- HESAP MODU VE TELEGRAM AYARLARI -----------------
st.sidebar.title("⚙️ Binance Yönetim Paneli")
hesap_modu = st.sidebar.radio("Hesap Türü:", ["Demo (Testnet)", "Gerçek Hesap"])

# KESİN DÜZELTME: https:// protokol şemaları ve /api ekleri entegre edildi
if hesap_modu == "Demo (Testnet)":
    BASE_URL = "binance.vision" 
    API_KEY = st.secrets.get("BINANCE_TESTNET_API_KEY")
    API_SECRET = st.secrets.get("BINANCE_TESTNET_API_SECRET")
else:
    BASE_URL = "binance.com" 
    API_KEY = st.secrets.get("BINANCE_API_KEY")
    API_SECRET = st.secrets.get("BINANCE_API_SECRET")

TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")

# ----------------- TELEGRAM BİLDİRİM FONKSİYONU -----------------
def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"🤖 *Binance Bot Bildirimi*\n\n{message}",
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        st.sidebar.error(f"Telegram Hatası: {e}")

# ----------------- BINANCE YARDIMCI FONKSİYONLAR -----------------
def generate_signature(query_string, secret):
    return hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def get_binance_headers():
    return {"X-MBX-APIKEY": API_KEY}

def round_step_size(quantity, step_size):
    if step_size <= 0: return quantity
    precision = int(round(-math.log10(step_size), 0))
    return float(f"{math.floor(quantity * (10 ** precision)) / (10 ** precision):.{precision}f}")

def get_symbol_step_size(symbol):
    try:
        url = f"{BASE_URL}/v3/exchangeInfo?symbol={symbol}"
        res = requests.get(url).json()
        for f in res['symbols']['filters']:
            if f['filterType'] == 'LOT_SIZE': return float(f['stepSize'])
    except: return 0.00001
    return 0.00001

def get_current_price(symbol):
    try:
        r = requests.get(f"{BASE_URL}/v3/ticker/price?symbol={symbol}").json()
        return float(r["price"])
    except: return 0.0

# ----------------- EMİR VE HESAP İŞLEMLERİ -----------------
def get_account_balances():
    timestamp = int(time.time() * 1000)
    query = f"timestamp={timestamp}"
    url = f"{BASE_URL}/v3/account?{query}&signature={generate_signature(query, API_SECRET)}"
    r = requests.get(url, headers=get_binance_headers())
    if r.status_code == 200:
        df_bal = pd.DataFrame(r.json().get("balances", []))
        if not df_bal.empty:
            df_bal["free"] = df_bal["free"].astype(float)
            df_bal["locked"] = df_bal["locked"].astype(float)
            return df_bal[(df_bal["free"] > 0) | (df_bal["locked"] > 0)]
    return pd.DataFrame()

def binance_buy(symbol, usdt_amount):
    last = get_current_price(symbol)
    if last == 0: return 0, 0, {"error": "Fiyat alınamadı"}
    qty = round_step_size(usdt_amount / last, get_symbol_step_size(symbol))
    timestamp = int(time.time() * 1000)
    query = f"symbol={symbol}&side=BUY&type=MARKET&quantity={qty}&timestamp={timestamp}"
    url = f"{BASE_URL}/v3/order?{query}&signature={generate_signature(query, API_SECRET)}"
    res = requests.post(url, headers=get_binance_headers()).json()
    
    if "orderId" in res:
        send_telegram_message(f"🟢 *MANUEL ALIM BAŞARILI*\nSembol: {symbol}\nMiktar: {qty}\nFiyat: {last} USDT\nMod: {hesap_modu}")
    return last, qty, res

def binance_sell(symbol, qty, is_trailing=False):
    qty = round_step_size(qty, get_symbol_step_size(symbol))
    timestamp = int(time.time() * 1000)
    query = f"symbol={symbol}&side=SELL&type=MARKET&quantity={qty}&timestamp={timestamp}"
    url = f"{BASE_URL}/v3/order?{query}&signature={generate_signature(query, API_SECRET)}"
    res = requests.post(url, headers=get_binance_headers()).json()
    
    if "orderId" in res:
        tip = "🛡️ TRAILING STOP" if is_trailing else "🔴 MANUEL SATIM"
        send_telegram_message(f"*{tip} BAŞARILI*\nSembol: {symbol}\nMiktar: {qty}\nMod: {hesap_modu}")
    return res

def get_candles(symbol="BTCUSDT"):
    r = requests.get(f"{BASE_URL}/v3/klines?symbol={symbol}&interval=1d&limit=180").json()
    if isinstance(r, dict) or not r: return pd.DataFrame()
    df = pd.DataFrame(r, columns=["open_time","open","high","low","close","volume","close_time","qav","num_trades","tbb","tbq","ignore"])
    df["time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms")
    df["Close"] = df["close"].astype(float)
    df = df.sort_values("time")
    df["RSI"] = ta.rsi(df["Close"], length=14)
    df["SMA20"] = ta.sma(df["Close"], length=20)
    return df

# ----------------- ARABİRİM PANELİ -----------------
symbol = st.sidebar.selectbox("Sembol Seçimi", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT"])
usdt_amount = st.sidebar.number_input("Alım Tutarı (USDT)", 10, 100000, 50)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Cüzdan Durumu")
if st.sidebar.button("Bakiyeleri Güncelle"): st.cache_data.clear()
with st.sidebar:
    df_balances = get_account_balances()
    if not df_balances.empty: st.dataframe(df_balances[["asset", "free", "locked"]], hide_index=True)
    else: st.caption("Bakiye yüklenemedi veya anahtarlar eksik.")

df = get_candles(symbol)
if df.empty:
    st.error("Piyasa verileri alınamadı. API Bağlantısını kontrol edin.")
else:
    last_row = df.iloc[-1]
    fiyat = last_row["Close"]
    rsi = last_row["RSI"] if not pd.isna(last_row["RSI"]) else 50.0
    sma = last_row["SMA20"] if not pd.isna(last_row["SMA20"]) else fiyat

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Anlık Fiyat", f"{fiyat:,.4f} USDT")
    c2.metric("RSI (14)", f"{rsi:.2f}")
    c3.metric("SMA (20)", f"{sma:,.2f}")
    onay = (1 if rsi < 35 else 0) + (1 if fiyat > sma else 0)
    c4.metric("Sinyal Skoru", f"{onay}/2", delta="AL SİNYALİ" if onay == 2 else "BEKLE")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["time"], y=df["Close"], name="Fiyat", line=dict(color='#00ffcc')))
    fig.add_trace(go.Scatter(x=df["time"], y=df["SMA20"], name="SMA20", line=dict(color='orange', dash='dash')))
    fig.update_layout(template="plotly_dark", height=300, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # ----------------- RİSK YÖNETİMİ & TAKİP MODÜLÜ (FRAGMENT) -----------------
    @st.fragment(run_every=3)
    def trailing_stop_ve_alarm_paneli():
        st.markdown("### 🛡️ Canlı Takip & Risk Yönetimi (3s Periyot)")
        
        col_input1, col_input2, col_input3 = st.columns(3)
        with col_input1:
            yuzde = st.number_input("İz Süren Stop Yüzdesi (%)", 0.5, 20.0, 1.5, step=0.1)
        with col_input2:
            miktar = st.number_input("Stop Takip Miktarı (Adet)", 0.00001, 1000.0, 0.01, format="%.5f")
        with col_input3:
            alarm_fiyat = st.number_input("Fiyat Alarmı Seviyesi (USDT)", 0.0, 1000000.0, fiyat)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if not st.session_state.trailing_aktif:
                if st.button("🟢 İz Süren Stop Başlat", use_container_width=True):
                    current = get_current_price(symbol)
                    st.session_state.trailing_aktif = True
                    st.session_state.en_yuksek_fiyat = current
                    st.session_state.stop_fiyati = current * (1 - (yuzde / 100))
                    st.session_state.trailing_miktar = miktar
                    st.session_state.trailing_yuzde = yuzde
                    send_telegram_message(f"🚀 *İz Süren Stop Takibi Başlatıldı*\nSembol: {symbol}\nBaşlangıç Stopu: {st.session_state.stop_fiyati} USDT")
                    st.rerun()
            else:
                if st.button("🔴 İz Süren Stop Durdur", use_container_width=True):
                    st.session_state.trailing_aktif = False
                    send_telegram_message(f"⏹️ *İz Süren Stop Takibi İptal Edildi*\nSembol: {symbol}")
                    st.rerun()

        anlik_fiyat = get_current_price(symbol)
        
        if abs(anlik_fiyat - alarm_fiyat) / alarm_fiyat < 0.002:
            st.toast(f"🚨 ALARM: {symbol} Hedef Fiyata Ulaştı: {anlik_fiyat}!", icon="⏰")
            send_telegram_message(f"⏰ *FİYAT ALARMI TETİKLENDİ*\nSembol: {symbol}\nFiyat: {anlik_fiyat} USDT")

        if st.session_state.trailing_aktif:
            if anlik_fiyat > st.session_state.en_yuksek_fiyat:
                st.session_state.en_yuksek_fiyat = anlik_fiyat
                st.session_state.stop_fiyati = anlik_fiyat * (1 - (st.session_state.trailing_yuzde / 100))
            
            if anlik_fiyat <= st.session_state.stop_fiyati:
                st.warning("⚠️ Stop seviyesi kırıldı! Market satışı gerçekleştiriliyor...")
                res = binance_sell(symbol, st.session_state.trailing_miktar, is_trailing=True)
                st.session_state.trailing_aktif = False
                if "orderId" in res:
                    st.success("🤖 Trailing Stop başarıyla tetiklendi ve varlık satıldı!")
                else:
                    st.error("Stop emri başarısız.")
                st.json(res)
                st.rerun()

            c_stat1, c_stat2, c_stat3 = st.columns(3)
            c_stat1.metric("Anlık Canlı Fiyat", f"{anlik_fiyat:,.4f}")
            c_stat2.metric("Görülen En Yüksek", f"{st.session_state.en_yuksek_fiyat:,.4f}")
            c_stat3.metric("Dinamik Stop Seviyesi", f"{st.session_state.stop_fiyati:,.4f}", delta=f"-{st.session_state.trailing_yuzde}%")

    trailing_stop_ve_alarm_paneli()

    # ----------------- KLASİK MANUEL EMİR YÖNETİMİ -----------------
    st.markdown("### 🤖 Manuel Emir Yönetimi")
    col_buy, col_sell = st.columns(2)

    with col_buy:
        st.subheader("🟢 Manuel Alım")
        if st.button(f"{symbol} Satın Al ({usdt_amount} USDT)"):
            with st.spinner("Emir iletiliyor..."):
                f, qty, res = binance_buy(symbol, usdt_amount)
                if "orderId" in res: st.success(f"Başarılı! {qty} adet alındı.")
                else: st.error("Emir reddedildi.")
                st.json(res)

    with col_sell:
        st.subheader("🔴 Manuel Satım")
        satilacak_adet = st.number_input("Satılacak Miktar (Adet)", 0.00001, 10000.0, 0.01, step=0.01, format="%.5f", key="sell_qty_input")
        if st.button(f"{symbol} Market Fiyatından SAT"):
            with st.spinner("Emir iletiliyor..."):
                res = binance_sell(symbol, satilacak_adet, is_trailing=False)
                if "orderId" in res: st.success(f"Başarılı! {satilacak_adet} adet satıldı.")
                else: st.error("Emir reddedildi.")
                st.json(res)
