# File: strategy_momentum_trend_rider.py

import pandas as pd
import pandas_ta as ta
import numpy as np

# Import dari file-file lain dalam proyek
from strategies.base_strategy import BaseStrategy
# Diasumsikan ada file 'utils.py' yang berisi fungsi fetch_klines
# seperti pada contoh yang Anda berikan.
import utils 

class MomentumTrendRiderStrategy(BaseStrategy):
    """
    Strategi "Momentum Trend Rider".
    Tujuan: Mengidentifikasi tren jangka pendek yang kuat di HTF 
    dan masuk pada saat pullback/koreksi di LTF dengan konfirmasi momentum.
    """
    
    # --- Properti Wajib dari BaseStrategy ---
    @property
    def name(self) -> str:
        return "momentum_trend_rider_v1"

    @property
    def description(self) -> str:
        return "Entry mengikuti tren HTF (EMA 50) saat terjadi pullback ke EMA 21 LTF dengan konfirmasi RSI."

    # --- PARAMETER STRATEGI ---
    
    # 1. Pengaturan Timeframe
    HTF_TIMEFRAME = '1h'
    LTF_TIMEFRAME = '15m'
    
    # 2. Indikator Kunci
    # EMA
    HTF_EMA_LENGTH = 50
    LTF_EMA_FAST_LENGTH = 21
    LTF_EMA_SLOW_LENGTH = 50
    
    # RSI
    RSI_LENGTH = 14
    RSI_UPPER_BOUND = 70
    RSI_LOWER_BOUND = 30
    RSI_MID_LINE = 50

    # Bollinger Bands
    BB_LENGTH = 20
    BB_STDDEV = 2.0

    # 3. Manajemen Risiko & Aturan Keluar
    RISK_REWARD_RATIO = 1.5
    # Lookback untuk mencari swing high/low terdekat untuk Stop Loss
    SL_LOOKBACK_PERIOD = 10 

    def _get_htf_trend(self, symbol: str) -> str | None:
        """
        Menganalisis timeframe tinggi (HTF) untuk menentukan tren utama.
        
        Returns:
            str | None: "BULLISH", "BEARISH", atau None jika data tidak cukup.
        """
        # Ambil data klines untuk HTF, cukup beberapa candle terakhir untuk cek EMA.
        df_htf = utils.fetch_klines(symbol, self.HTF_TIMEFRAME, limit=self.HTF_EMA_LENGTH + 5)
        
        if df_htf.empty or len(df_htf) < self.HTF_EMA_LENGTH:
            # print(f"Peringatan: Data HTF untuk {symbol} tidak cukup.")
            return None

        # Hitung EMA di HTF
        df_htf.ta.ema(length=self.HTF_EMA_LENGTH, append=True)
        
        last_candle_htf = df_htf.iloc[-1]
        htf_ema = last_candle_htf[f'EMA_{self.HTF_EMA_LENGTH}']
        htf_close = last_candle_htf['close']

        if pd.isna(htf_ema):
            return None

        # Tentukan Tren Utama
        if htf_close > htf_ema:
            return "BULLISH"
        elif htf_close < htf_ema:
            return "BEARISH"
        else:
            return None

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Metode utama untuk memeriksa sinyal trading pada timeframe rendah (LTF).
        Bot harus memanggil metode ini pada penutupan setiap candle 15M.

        Args:
            symbol (str): Simbol pair yang dianalisis (misal: 'BTCUSDT').
            df (pd.DataFrame): DataFrame berisi data klines dari LTF (15M).

        Returns:
            dict | None: Dictionary berisi detail sinyal jika ditemukan, atau None.
        """
        # Pastikan data LTF yang diberikan cukup untuk perhitungan indikator
        min_length = max(self.LTF_EMA_SLOW_LENGTH, self.BB_LENGTH, self.RSI_LENGTH)
        if df.empty or len(df) < min_length:
            return None

        # 1. Dapatkan Tren Utama dari HTF
        htf_trend = self._get_htf_trend(symbol)
        if not htf_trend:
            return None # Tidak ada tren jelas di HTF, jangan trading.

        # 2. Persiapan Indikator Kunci di LTF
        df.ta.ema(length=self.LTF_EMA_FAST_LENGTH, append=True)
        df.ta.ema(length=self.LTF_EMA_SLOW_LENGTH, append=True)
        df.ta.rsi(length=self.RSI_LENGTH, append=True)
        df.ta.bbands(length=self.BB_LENGTH, std=self.BB_STDDEV, append=True)

        # Ambil data candle terakhir di LTF untuk analisis
        last = df.iloc[-1]

        # Ambil nilai-nilai indikator dari candle terakhir
        ema_fast = last[f'EMA_{self.LTF_EMA_FAST_LENGTH}']
        ema_slow = last[f'EMA_{self.LTF_EMA_SLOW_LENGTH}']
        rsi = last[f'RSI_{self.RSI_LENGTH}']
        bb_middle = last[f'BBM_{self.BB_LENGTH}_{self.BB_STDDEV}']

        # Pastikan semua nilai indikator valid
        if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi) or pd.isna(bb_middle):
            return None

        entry_price = last['close']

        # --- ATURAN EKSEKUSI BOT ---

        # A. ATURAN UNTUK MEMBUKA POSISI LONG
        if htf_trend == "BULLISH":
            # Kondisi 1: Tren HTF - Sudah terpenuhi (htf_trend == "BULLISH")
            
            # Kondisi 2: Konfirmasi Tren LTF
            is_ltf_bullish_trend = ema_fast > ema_slow
            
            # Kondisi 3: Harga Melakukan Koreksi dan Memantul
            pullback_target = max(ema_fast, bb_middle)
            is_pullback_touch = last['low'] <= pullback_target
            is_bounce_up = last['close'] > last['open'] # Candle hijau

            # Kondisi 4: Konfirmasi Momentum RSI
            is_rsi_bullish = self.RSI_MID_LINE < rsi < self.RSI_UPPER_BOUND

            # Cek jika SEMUA kondisi LONG terpenuhi
            if is_ltf_bullish_trend and is_pullback_touch and is_bounce_up and is_rsi_bullish:
                # Tentukan Stop Loss di bawah swing low terdekat
                swing_low = df['low'].iloc[-self.SL_LOOKBACK_PERIOD:-1].min()
                stop_loss = swing_low

                # Tentukan Take Profit berdasarkan RRR
                risk_distance = entry_price - stop_loss
                if risk_distance <= 0: return None
                take_profit = entry_price + (risk_distance * self.RISK_REWARD_RATIO)
                
                reason = f"HTF Bullish, pullback ke EMA/BB ({pullback_target:.4f}) di LTF, RSI > {self.RSI_MID_LINE}"
                return {
                    'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 
                    'stop_loss': stop_loss, 'take_profit': take_profit, 
                    'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO
                }

        # B. ATURAN UNTUK MEMBUKA POSISI SHORT
        if htf_trend == "BEARISH":
            # Kondisi 1: Tren HTF - Sudah terpenuhi (htf_trend == "BEARISH")

            # Kondisi 2: Konfirmasi Tren LTF
            is_ltf_bearish_trend = ema_fast < ema_slow

            # Kondisi 3: Harga Melakukan Reli dan Ditolak
            rally_target = min(ema_fast, bb_middle)
            is_rally_touch = last['high'] >= rally_target
            is_rejection_down = last['close'] < last['open'] # Candle merah

            # Kondisi 4: Konfirmasi Momentum RSI
            is_rsi_bearish = self.RSI_LOWER_BOUND < rsi < self.RSI_MID_LINE

            # Cek jika SEMUA kondisi SHORT terpenuhi
            if is_ltf_bearish_trend and is_rally_touch and is_rejection_down and is_rsi_bearish:
                # Tentukan Stop Loss di atas swing high terdekat
                swing_high = df['high'].iloc[-self.SL_LOOKBACK_PERIOD:-1].max()
                stop_loss = swing_high

                # Tentukan Take Profit berdasarkan RRR
                risk_distance = stop_loss - entry_price
                if risk_distance <= 0: return None
                take_profit = entry_price - (risk_distance * self.RISK_REWARD_RATIO)

                reason = f"HTF Bearish, reli ke EMA/BB ({rally_target:.4f}) di LTF, RSI < {self.RSI_MID_LINE}"
                return {
                    'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 
                    'stop_loss': stop_loss, 'take_profit': take_profit, 
                    'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO
                }

        # Jika tidak ada kondisi yang terpenuhi, tidak ada sinyal
        return None