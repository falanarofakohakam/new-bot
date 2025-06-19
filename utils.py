# utils.py

import logging
import pandas as pd
import numpy as np

# Cek dan perbaiki atribut NaN jika tidak ada
if not hasattr(np, 'NaN'):
    np.NaN = np.nan

import pandas_ta as ta # <-- Import pandas_ta setelah perbaikan

from binance.client import Client as BinanceClient
import google.generativeai as genai
from datetime import datetime, timedelta

# Import konfigurasi dari file config.py
import config

# Setup Logging
logger = logging.getLogger(__name__)

# ==============================================================================
# INISIALISASI KLIEN EKSTERNAL
# ==============================================================================

# Inisialisasi Klien Binance sekali saja saat modul diimpor
try:
    binance = BinanceClient(
        api_key=config.BINANCE_API_KEY,
        api_secret=config.BINANCE_API_SECRET,
        requests_params={'timeout': 20}
    )
    # Cek koneksi
    binance.ping()
    logger.info("Koneksi ke Binance API berhasil.")
except Exception as e:
    logger.error(f"Gagal menginisialisasi atau terhubung ke Binance API: {e}")
    binance = None

# Inisialisasi Model Gemini (Opsional)
gemini_model = None
if config.GEMINI_API_KEY:
    try:
        genai.configure(api_key=config.GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        logger.info("Model Gemini AI berhasil diinisialisasi.")
    except Exception as e:
        logger.error(f"Gagal menginisialisasi model Gemini: {e}")

# ==============================================================================
# FUNGSI-FUNGSI UTILITAS PENGAMBILAN DATA
# ==============================================================================

def fetch_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    """Mengambil data kline (OHLCV) dari Binance Futures."""
    if not binance:
        logger.error("Klien Binance tidak terinisialisasi.")
        return pd.DataFrame()
    try:
        data = binance.futures_klines(symbol=symbol, interval=interval, limit=limit)
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
            'quote_vol', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        
        return df[['open_time', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        logger.error(f"Fetch klines gagal untuk {symbol} ({interval}): {e}")
        return pd.DataFrame()

def get_top_symbols(context) -> list:
    """
    Mendapatkan daftar simbol teratas berdasarkan volume dan volatilitas.
    Fungsi ini sekarang fleksibel dan bisa menerima context asli atau dict.
    """
    # --- PERUBAHAN DIMULAI DI SINI ---
    bot_data = {}
    # Cek apakah context adalah objek asli dari handler (memiliki .bot_data)
    if hasattr(context, 'bot_data'):
        bot_data = context.bot_data
    # Cek apakah context adalah dict dummy dari backtester (memiliki key 'bot_data')
    elif isinstance(context, dict) and 'bot_data' in context:
        bot_data = context['bot_data']
    
    # Sekarang, gunakan variabel `bot_data` yang sudah pasti benar
    cache = bot_data.get('top_symbols_cache', {})
    if cache and (datetime.now() - cache.get('timestamp', datetime.min) < timedelta(hours=1)):
        return cache.get('symbols', [])
    # --- PERUBAHAN SELESAI DI SINI ---

    if not binance:
        logger.error("Klien Binance tidak terinisialisasi.")
        return []
        
    try:
        logger.info("Memperbarui cache top symbols...")
        tickers = binance.futures_ticker()
        df = pd.DataFrame(tickers)
        
        df = df[df['symbol'].str.contains('USDT') & ~df['symbol'].str.contains('_')]
        df['volume'] = df['quoteVolume'].astype(float)
        df['high'] = df['highPrice'].astype(float)
        df['low']  = df['lowPrice'].astype(float)
        df = df[df['low'] > 0]
        
        df['volatility'] = (df['high'] - df['low']) / df['low']
        df = df[df['volatility'] >= config.VOLATILITY_THRESHOLD]
        
        symbols = df.sort_values('volume', ascending=False).head(config.TOP_N_SYMBOLS)['symbol'].tolist()
        
        # Simpan kembali ke cache menggunakan `bot_data`
        bot_data['top_symbols_cache'] = {'symbols': symbols, 'timestamp': datetime.now()}
        return symbols
    except Exception as e:
        logger.error(f"Gagal mendapatkan top symbols: {e}")
        return []
# ==============================================================================
# FUNGSI-FUNGSI UNTUK FITUR ANALISA
# ==============================================================================

def get_technical_analysis(symbol: str, timeframe: str) -> dict:
    """Menganalisa satu simbol pada satu timeframe untuk fitur /analyze."""
    try:
        df = fetch_klines(symbol, timeframe, limit=250)
        if df.empty or len(df) < 200:
            return {'error': 'Data tidak cukup'}

        # --- PERUBAHAN DI SINI ---
        # Definisikan parameter analisa langsung di sini, tidak lagi dari config.py
        adx_len_analyze = 14
        rsi_len_analyze = 14
        ema_fast_len = 50
        ema_slow_len = 200
        
        df.ta.ema(length=ema_fast_len, append=True)
        df.ta.ema(length=ema_slow_len, append=True)
        df.ta.rsi(length=rsi_len_analyze, append=True)
        df.ta.adx(length=adx_len_analyze, append=True)
        
        last = df.iloc[-1]
        
        price = last['close']
        ema50 = last[f'EMA_{ema_fast_len}']
        ema200 = last[f'EMA_{ema_slow_len}']
        rsi = last[f'RSI_{rsi_len_analyze}']
        # Gunakan variabel lokal untuk mengakses kolom ADX
        adx = last[f'ADX_{adx_len_analyze}']
        # --- AKHIR PERUBAHAN ---
        
        if any(pd.isna(v) for v in [ema50, ema200, rsi, adx]):
             return {'error': 'Gagal menghitung indikator'}

        # Logika penentuan bias (tidak berubah)
        trend_bias = "Netral"
        if price > ema50 and ema50 > ema200: trend_bias = "Bullish Kuat"
        elif price > ema50 and price > ema200: trend_bias = "Bullish"
        elif price < ema50 and ema50 < ema200: trend_bias = "Bearish Kuat"
        elif price < ema50 and price < ema200: trend_bias = "Bearish"
        
        momentum_bias = "Netral"
        if rsi > 55: momentum_bias = "Bullish"
        elif rsi < 45: momentum_bias = "Bearish"
        
        strength_status = "Ranging"
        if adx > 22: strength_status = "Trending"
            
        return {
            'price': price, 
            'trend_bias': trend_bias, 
            'momentum_bias': momentum_bias, 
            'strength_status': strength_status, 
            'rsi': rsi, 
            'adx': adx
        }
    except Exception as e:
        logger.error(f"Error pada get_technical_analysis untuk {symbol} {timeframe}: {e}")
        return {'error': str(e)}

async def get_gemini_summary(analysis_text: str, symbol: str) -> str:
    """Meminta ringkasan dari Gemini AI berdasarkan hasil analisa teknikal."""
    if not gemini_model:
        return "Model AI tidak diaktifkan. Silakan periksa GEMINI_API_KEY Anda."
    try:
        prompt = (
            f"Anda adalah seorang analis teknikal crypto. Berdasarkan data teknikal untuk {symbol} di bawah, "
            "berikan kesimpulan singkat (2-3 kalimat) mengenai potensi pergerakan harga jangka pendek. "
            "Fokus pada sentimen umum dan sebutkan timeframe paling berpengaruh. "
            "Gunakan bahasa yang mudah dipahami.\n\n"
            f"--- DATA ANALISA ---\n{analysis_text}\n--- KESIMPULAN ANDA ---"
        )
        response = await gemini_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Gagal mendapatkan ringkasan dari Gemini: {e}")
        return "Gagal mendapatkan ringkasan dari AI."