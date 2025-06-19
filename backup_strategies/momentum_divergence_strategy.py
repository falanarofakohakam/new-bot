# File: momentum_divergence_strategy.py

import pandas as pd
import pandas_ta as ta
import numpy as np

from strategies.base_strategy import BaseStrategy

class MomentumDivergenceStrategy(BaseStrategy):
    """
    Strategi v1 yang dirancang untuk frekuensi trading harian yang lebih tinggi.
    Entry didasarkan pada RSI Divergence yang dikonfirmasi oleh breakout struktur
    dan volume, serta searah dengan tren utama (EMA 200).
    """
    
    name = "momentum_divergence_v1"
    description = "15m RSI Divergence with EMA 200 Trend Filter and Volume Confirmation."

    # --- PARAMETER STRATEGI ---
    TIMEFRAME = '15m'
    
    # --- Parameter Indikator ---
    TREND_FILTER_EMA_PERIOD = 200
    RSI_PERIOD = 14
    
    # Jarak candle untuk mencari titik divergence sebelumnya
    DIVERGENCE_LOOKBACK = 40
    
    # --- Parameter Konfirmasi Volume ---
    VOLUME_MA_PERIOD = 20
    VOLUME_FACTOR = 1.2 # Volume harus 1.2x (20%) di atas rata-rata
    
    # --- Parameter Manajemen Risiko ---
    ATR_PERIOD = 14
    SL_ATR_MULTIPLIER = 1.5 
    RISK_REWARD_RATIO = 2.0

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """Metode utama yang menjalankan seluruh logika strategi."""
        
        if df.empty or len(df) < self.TREND_FILTER_EMA_PERIOD:
            return None

        # --- LANGKAH 1: Hitung semua indikator ---
        df.ta.ema(length=self.TREND_FILTER_EMA_PERIOD, append=True)
        df.ta.rsi(length=self.RSI_PERIOD, append=True)
        df.ta.atr(length=self.ATR_PERIOD, append=True)
        df[f'VOLUME_MA_{self.VOLUME_MA_PERIOD}'] = df['volume'].rolling(self.VOLUME_MA_PERIOD).mean()

        # Kita periksa dari candle ke-2 terakhir ke belakang
        for i in range(len(df) - 2, self.DIVERGENCE_LOOKBACK, -1):
            
            # Titik terbaru dari potensi divergence
            p2_candle = df.iloc[i]
            # Candle konfirmasi setelah titik terbaru
            confirmation_candle = df.iloc[i + 1]
            
            # Ambil nilai indikator yang relevan
            trend_ema = p2_candle.get(f'EMA_{self.TREND_FILTER_EMA_PERIOD}')
            p2_rsi = p2_candle.get(f'RSI_{self.RSI_PERIOD}')
            atr_val = confirmation_candle.get(f'ATRr_{self.ATR_PERIOD}')
            vol_ma = confirmation_candle.get(f'VOLUME_MA_{self.VOLUME_MA_PERIOD}')

            if pd.isna(trend_ema) or pd.isna(p2_rsi) or pd.isna(atr_val) or pd.isna(vol_ma):
                continue

            # --- LANGKAH 2: Cari Bullish Divergence ---
            # Hanya cari sinyal LONG jika harga di atas EMA 200
            if p2_candle['close'] > trend_ema:
                # Cari titik terendah sebelumnya (p1)
                for j in range(i - 1, i - self.DIVERGENCE_LOOKBACK, -1):
                    p1_candle = df.iloc[j]
                    p1_rsi = p1_candle.get(f'RSI_{self.RSI_PERIOD}')

                    if pd.isna(p1_rsi): continue

                    # Kondisi Bullish Divergence: Lower Low di harga, Higher Low di RSI
                    if p2_candle['low'] < p1_candle['low'] and p2_rsi > p1_rsi:
                        
                        # Kondisi Konfirmasi: Candle berikutnya harus bullish, breakout, dan bervolume
                        is_confirmed_bullish = confirmation_candle['close'] > p2_candle['high'] and \
                                               confirmation_candle['volume'] > (vol_ma * self.VOLUME_FACTOR)
                        
                        if is_confirmed_bullish:
                            entry_price = confirmation_candle['close']
                            stop_loss = p2_candle['low'] - (atr_val * self.SL_ATR_MULTIPLIER)
                            risk = entry_price - stop_loss
                            if risk <= 0: continue
                            take_profit = entry_price + (risk * self.RISK_REWARD_RATIO)
                            
                            reason = "Bullish RSI Divergence Confirmed on 15m"
                            return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}
                        break # Hentikan pencarian p1 setelah divergence ditemukan

            # --- LANGKAH 3: Cari Bearish Divergence ---
            # Hanya cari sinyal SHORT jika harga di bawah EMA 200
            elif p2_candle['close'] < trend_ema:
                # Cari titik tertinggi sebelumnya (p1)
                for j in range(i - 1, i - self.DIVERGENCE_LOOKBACK, -1):
                    p1_candle = df.iloc[j]
                    p1_rsi = p1_candle.get(f'RSI_{self.RSI_PERIOD}')

                    if pd.isna(p1_rsi): continue

                    # Kondisi Bearish Divergence: Higher High di harga, Lower High di RSI
                    if p2_candle['high'] > p1_candle['high'] and p2_rsi < p1_rsi:
                        
                        # Kondisi Konfirmasi: Candle berikutnya harus bearish, breakout, dan bervolume
                        is_confirmed_bearish = confirmation_candle['close'] < p2_candle['low'] and \
                                               confirmation_candle['volume'] > (vol_ma * self.VOLUME_FACTOR)

                        if is_confirmed_bearish:
                            entry_price = confirmation_candle['close']
                            stop_loss = p2_candle['high'] + (atr_val * self.SL_ATR_MULTIPLIER)
                            risk = stop_loss - entry_price
                            if risk <= 0: continue
                            take_profit = entry_price - (risk * self.RISK_REWARD_RATIO)
                            
                            reason = "Bearish RSI Divergence Confirmed on 15m"
                            return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}
                        break # Hentikan pencarian p1 setelah divergence ditemukan
        
        return None
