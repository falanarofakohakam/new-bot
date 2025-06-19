# File: scalper_pro_strategy.py

import pandas as pd
import pandas_ta as ta
import numpy as np

from strategies.base_strategy import BaseStrategy

class ScalperProStrategy(BaseStrategy):
    """
    Strategi v5. Rombak total untuk kualitas sinyal maksimum.
    Entry menggunakan pola 'Three-Bar Reversal' yang kuat di dalam Q-Zone
    selama tren ADX yang terverifikasi.
    """
    
    name = "scalper_pro_v5"
    description = "15m Three-Bar Reversal in Q-Zone. High-quality, low-frequency."

    # --- PARAMETER STRATEGI ---
    TIMEFRAME = '15m'
    
    # --- Parameter Indikator untuk Q-Zone ---
    FAST_EMA_PERIOD = 9
    SLOW_EMA_PERIOD = 21
    
    # --- Parameter Filter Tren ---
    TREND_FILTER_EMA_PERIOD = 100
    ADX_PERIOD = 14
    # Mempertahankan ADX yang ketat untuk tren yang kuat
    ADX_MIN_STRENGTH = 25
    
    # --- Parameter Manajemen Risiko ---
    ATR_PERIOD = 14
    SL_ATR_MULTIPLIER = 1.5 
    RISK_REWARD_RATIO = 2.0

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """Metode utama yang menjalankan seluruh logika strategi."""
        
        if df.empty or len(df) < self.TREND_FILTER_EMA_PERIOD:
            return None

        # --- LANGKAH 1: Hitung semua indikator ---
        df.ta.ema(length=self.FAST_EMA_PERIOD, append=True)
        df.ta.ema(length=self.SLOW_EMA_PERIOD, append=True)
        df.ta.ema(length=self.TREND_FILTER_EMA_PERIOD, append=True)
        df.ta.atr(length=self.ATR_PERIOD, append=True)
        
        adx_df = df.ta.adx(length=self.ADX_PERIOD)
        df = pd.concat([df, adx_df], axis=1)

        # Membutuhkan setidaknya 4 candle untuk pola 3-bar
        for i in range(-4, 0):
            # Pastikan kita tidak keluar dari batas dataframe
            if (i + 3) >= len(df): continue 

            bar1 = df.iloc[i + 1]
            bar2 = df.iloc[i + 2]
            bar3 = df.iloc[i + 3] # Candle konfirmasi/entry

            # --- Ambil Nilai Indikator ---
            fast_ema_b1 = bar1.get(f'EMA_{self.FAST_EMA_PERIOD}')
            slow_ema_b1 = bar1.get(f'EMA_{self.SLOW_EMA_PERIOD}')
            trend_ema = bar3.get(f'EMA_{self.TREND_FILTER_EMA_PERIOD}')
            adx_val = bar3.get(f'ADX_{self.ADX_PERIOD}')
            atr_val = bar3.get(f'ATRr_{self.ATR_PERIOD}')
            
            if pd.isna(fast_ema_b1) or pd.isna(slow_ema_b1) or pd.isna(trend_ema) or \
               pd.isna(adx_val) or pd.isna(atr_val):
                continue
            
            # --- LANGKAH 2: Cek Sinyal LONG ---
            is_uptrend = bar3['close'] > trend_ema
            is_strong_trend = adx_val > self.ADX_MIN_STRENGTH
            
            if is_uptrend and is_strong_trend:
                # Kondisi 1: Setup Bar masuk ke Q-Zone
                is_setup_in_zone = bar1['low'] <= fast_ema_b1 and bar1['close'] >= slow_ema_b1
                
                # Kondisi 2: Pola Three-Bar Reversal Bullish
                is_three_bar_reversal = bar2['low'] < bar1['low'] and \
                                        bar3['close'] > bar2['high']
                
                if is_setup_in_zone and is_three_bar_reversal:
                    entry_price = bar3['close']
                    # Stop loss di bawah titik terendah dari pola (low bar2)
                    stop_loss = bar2['low'] - (atr_val * self.SL_ATR_MULTIPLIER)
                    risk = entry_price - stop_loss
                    if risk <= 0: continue
                    take_profit = entry_price + (risk * self.RISK_REWARD_RATIO)
                    
                    reason = f"Bullish Three-Bar Reversal in Q-Zone (ADX > {self.ADX_MIN_STRENGTH})"
                    return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

            # --- LANGKAH 3: Cek Sinyal SHORT ---
            is_downtrend = bar3['close'] < trend_ema
            
            if is_downtrend and is_strong_trend:
                # Kondisi 1: Setup Bar masuk ke Q-Zone
                is_setup_in_zone_short = bar1['high'] >= fast_ema_b1 and bar1['close'] <= slow_ema_b1
                
                # Kondisi 2: Pola Three-Bar Reversal Bearish
                is_three_bar_reversal_short = bar2['high'] > bar1['high'] and \
                                              bar3['close'] < bar2['low']

                if is_setup_in_zone_short and is_three_bar_reversal_short:
                    entry_price = bar3['close']
                    # Stop loss di atas titik tertinggi dari pola (high bar2)
                    stop_loss = bar2['high'] + (atr_val * self.SL_ATR_MULTIPLIER)
                    risk = stop_loss - entry_price
                    if risk <= 0: continue
                    take_profit = entry_price - (risk * self.RISK_REWARD_RATIO)
                    
                    reason = f"Bearish Three-Bar Reversal in Q-Zone (ADX > {self.ADX_MIN_STRENGTH})"
                    return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None
