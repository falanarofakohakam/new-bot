import logging
import pandas as pd
import pandas_ta as ta
import numpy as np

# Import dari file lain dalam proyek Anda
import utils 
# Import kelas dasar (BaseStrategy) dari file base_strategy.py
from .base_strategy import BaseStrategy 

# Setup logger
logger = logging.getLogger(__name__)

class DaytradeConfluenceStrategy(BaseStrategy):
    """
    Strategi Day Trading Confluence yang mewarisi dari BaseStrategy.
    VERSI INI TIDAK MENGGUNAKAN KONFIRMASI VOLUME.
    """
    # --- ATRIBUT KELAS WAJIB ---
    name = "daytrade_confluence"
    description = "Strategi Day Trading dengan konfirmasi S/R 1H, Fibonacci, dan candle pembalikan (tanpa cek volume)."
    
    def __init__(self):
        # --- Atribut Konfigurasi Strategi ---
        self.TIMEFRAME = "15m"
        self.RISK_REWARD_RATIO = 2.0
        
        # Panggil konstruktor kelas dasar untuk inisialisasi logger.
        super().__init__()

        # --- Parameter Internal Khusus Strategi Ini ---
        self.SL_BUFFER_PERCENT = 1.5      # Buffer 1.5% untuk SL
        self.PIVOT_LOOKBACK = 10          # Jarak candle untuk validasi pivot
        self.SR_PROXIMITY_PERCENT = 0.5   # Jarak (dalam %) dari harga ke S/R 1H
        # VOLUME_SPIKE_FACTOR telah dihapus

    def _find_pivots(self, df: pd.DataFrame, n: int) -> pd.Series:
        """Helper untuk menemukan pivot high dan low."""
        pivots = pd.Series(np.nan, index=df.index)
        
        for i in range(n, len(df) - n):
            is_pivot_high = df['high'].iloc[i] > df['high'].iloc[i-n:i].max() and \
                            df['high'].iloc[i] > df['high'].iloc[i+1:i+1+n].max()
            is_pivot_low = df['low'].iloc[i] < df['low'].iloc[i-n:i].min() and \
                           df['low'].iloc[i] < df['low'].iloc[i+1:i+1+n].min()

            if is_pivot_high:
                pivots.iloc[i] = df['high'].iloc[i]
            elif is_pivot_low:
                pivots.iloc[i] = df['low'].iloc[i]
        
        return pivots.ffill().bfill()

    def _is_reversal_candle(self, df: pd.DataFrame, index: int) -> str | None:
        """Memeriksa apakah candle di indeks tertentu adalah candle pembalikan."""
        if index < 1: return None
        current, prev = df.iloc[index], df.iloc[index - 1]
        # Bullish Engulfing
        if current['close'] > prev['open'] and current['open'] < prev['close'] and current['close'] > current['open'] and prev['close'] < prev['open']: return 'BULLISH'
        # Bearish Engulfing
        if current['open'] > prev['close'] and current['close'] < prev['open'] and current['close'] < current['open'] and prev['close'] > prev['open']: return 'BEARISH'
        return None

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """Fungsi utama untuk memeriksa sinyal berdasarkan logika confluence."""
        if len(df) < 100:
            self.logger.warning(f"Data tidak cukup untuk {symbol} ({len(df)} candle).")
            return None

        # --- PERBAIKAN KINERJA ---
        # Data 1H diambil HANYA SATU KALI di awal, bukan di dalam loop.
        try:
            df_1h = utils.fetch_klines(symbol, '1h', limit=500)
            if df_1h.empty:
                self.logger.warning(f"Gagal mengambil data 1H untuk {symbol}.")
                return None
            pivots_1h = self._find_pivots(df_1h, self.PIVOT_LOOKBACK)
            sr_levels_1h = pivots_1h.dropna().unique()
        except Exception as e:
            self.logger.error(f"Error saat fetch data 1H atau kalkulasi pivot: {e}")
            return None

        # --- Kalkulasi Indikator untuk timeframe utama ---
        # Kalkulasi EMA Volume telah dihapus
        pivots_15m = self._find_pivots(df, self.PIVOT_LOOKBACK)
            
        # --- Loop dari candle terbaru untuk mencari sinyal ---
        for i in range(len(df) - 1, len(df) - 5, -1):
            if i < 50: continue

            recent_pivots = pivots_15m.iloc[:i+1].dropna()
            if len(recent_pivots) < 2: continue

            last_pivot, prev_pivot = recent_pivots.iloc[-1], recent_pivots.iloc[-2]
            potential_signal = 'LONG' if last_pivot > prev_pivot else 'SHORT'
            swing_high, swing_low = (last_pivot, prev_pivot) if potential_signal == 'LONG' else (prev_pivot, last_pivot)
            
            swing_range = swing_high - swing_low
            if swing_range <= 0: continue

            # --- Cek Kondisi Confluence ---
            fib_levels = {
                '0.382': swing_high - (swing_range * 0.382), '0.500': swing_high - (swing_range * 0.500), '0.618': swing_high - (swing_range * 0.618)
            } if potential_signal == 'LONG' else {
                '0.382': swing_low + (swing_range * 0.382), '0.500': swing_low + (swing_range * 0.500), '0.618': swing_low + (swing_range * 0.618)
            }

            candle = df.iloc[i]
            fib_level_hit = next((name for name, price in fib_levels.items() if candle['low'] <= price <= candle['high']), None)
            
            if not fib_level_hit: continue
            
            # ### PERUBAHAN ###: Cek volume telah dihapus dari sini.
            
            reversal_type = self._is_reversal_candle(df, i)
            if not reversal_type or reversal_type != ('BULLISH' if potential_signal == 'LONG' else 'BEARISH'): continue

            entry_price = candle['close']
            
            relevant_sr_1h = [sr for sr_time, sr in pivots_1h.dropna().items() if sr_time <= candle['open_time']]
            sr_confluence = any(abs(entry_price - sr) / entry_price * 100 < self.SR_PROXIMITY_PERCENT for sr in relevant_sr_1h)
            if not sr_confluence: continue

            # --- Jika SEMUA kondisi terpenuhi, buat sinyal ---
            self.logger.info(f"SINYAL DITEMUKAN untuk {symbol} ({potential_signal}) pada candle ke-{i}")

            sl_raw = swing_low if potential_signal == 'LONG' else swing_high
            sl_price, tp_price = self._calculate_sl_tp(
                potential_signal, entry_price, sl_raw, self.RISK_REWARD_RATIO, self.SL_BUFFER_PERCENT
            )
            
            if sl_price == 0 or tp_price == 0: continue

            return {
                'symbol': symbol,
                'signal': potential_signal,
                'entry': entry_price,
                'stop_loss': sl_price,
                'take_profit': tp_price,
                'reason': f"Reversal di Fib {fib_level_hit} + Konfirmasi S/R 1H.", # 'Volume Spike' dihapus
                'risk_reward_ratio': self.RISK_REWARD_RATIO
            }
            
        return None
