# File: trend_rider_strategy.py

import pandas as pd
import pandas_ta as ta
import numpy as np

from strategies.base_strategy import BaseStrategy
# import utils # Uncomment if you use a utils file

class TrendRiderStrategy(BaseStrategy):
    """
    Strategi Trend Following v2 yang masuk pasar saat terjadi pullback ke EMA
    dan dikonfirmasi oleh berbagai pola candlestick kuat (Engulfing, Hammer/Shooting Star, Morning/Evening Star).
    Dirancang untuk win rate yang tinggi.
    """
    
    # Properti wajib dari BaseStrategy
    name = "trend_rider_v2"
    description = "Trend following dengan entry pullback ke EMA + multiple candle confirmations."

    # --- PARAMETER STRATEGI ---
    TIMEFRAME = '15m'
    
    # Parameter Indikator untuk Tren
    FAST_EMA_LENGTH = 21
    SLOW_EMA_LENGTH = 50
    
    # --- Parameter Manajemen Risiko ---
    ATR_LENGTH = 14
    # Buffer untuk SL agar tidak terlalu dekat dengan harga low/high candle
    SL_BUFFER_FACTOR = 1
    # RRR diatur ke 1.5 untuk memaksimalkan win rate
    RISK_REWARD_RATIO = 3

    # --- FUNGSI DETEKSI POLA CANDLESTICK ---

    def _is_bullish_engulfing(self, df: pd.DataFrame, index: int) -> bool:
        """Memeriksa apakah candle di index adalah Bullish Engulfing."""
        if index < 1: return False
        current = df.iloc[index]
        previous = df.iloc[index - 1]
        
        is_bullish_candle = current['close'] > current['open']
        is_previous_bearish = previous['close'] < previous['open']
        if not (is_bullish_candle and is_previous_bearish): return False
        
        return current['close'] > previous['open'] and current['open'] < previous['close']

    def _is_bearish_engulfing(self, df: pd.DataFrame, index: int) -> bool:
        """Memeriksa apakah candle di index adalah Bearish Engulfing."""
        if index < 1: return False
        current = df.iloc[index]
        previous = df.iloc[index - 1]

        is_bearish_candle = current['close'] < current['open']
        is_previous_bullish = previous['close'] > previous['open']
        if not (is_bearish_candle and is_previous_bullish): return False
            
        return current['open'] > previous['close'] and current['close'] < previous['open']

    def _is_hammer(self, df: pd.DataFrame, index: int) -> bool:
        """Memeriksa apakah candle di index adalah Hammer (sinyal bullish)."""
        candle = df.iloc[index]
        body_size = abs(candle['close'] - candle['open'])
        if body_size == 0: return False
        
        lower_wick = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
        upper_wick = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
        
        # Badan kecil, sumbu bawah panjang, sumbu atas sangat pendek
        return lower_wick > body_size * 2 and upper_wick < body_size * 0.5

    def _is_shooting_star(self, df: pd.DataFrame, index: int) -> bool:
        """Memeriksa apakah candle di index adalah Shooting Star (sinyal bearish)."""
        candle = df.iloc[index]
        body_size = abs(candle['close'] - candle['open'])
        if body_size == 0: return False

        upper_wick = candle['high'] - candle['close'] if candle['close'] > candle['open'] else candle['high'] - candle['open']
        lower_wick = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
        
        # Badan kecil, sumbu atas panjang, sumbu bawah sangat pendek
        return upper_wick > body_size * 2 and lower_wick < body_size * 0.5

    def _is_morning_star(self, df: pd.DataFrame, index: int) -> bool:
        """Memeriksa pola Morning Star 3-candle (sinyal bullish) yang berakhir di index."""
        if index < 2: return False
        c1 = df.iloc[index - 2] # Candle pertama (bearish besar)
        c2 = df.iloc[index - 1] # Candle kedua (doji/kecil)
        c3 = df.iloc[index]     # Candle ketiga (bullish)

        # C1 harus bearish, C3 harus bullish
        if not (c1['close'] < c1['open'] and c3['close'] > c3['open']): return False
        
        # Badan C2 harus kecil dan berada di bawah badan C1
        c2_body = abs(c2['close'] - c2['open'])
        if not (c2_body < abs(c1['close'] - c1['open']) and max(c2['open'], c2['close']) < c1['close']): return False
        
        # C3 harus ditutup di atas titik tengah badan C1
        return c3['close'] > (c1['open'] + c1['close']) / 2

    def _is_evening_star(self, df: pd.DataFrame, index: int) -> bool:
        """Memeriksa pola Evening Star 3-candle (sinyal bearish) yang berakhir di index."""
        if index < 2: return False
        c1 = df.iloc[index - 2] # Candle pertama (bullish besar)
        c2 = df.iloc[index - 1] # Candle kedua (doji/kecil)
        c3 = df.iloc[index]     # Candle ketiga (bearish)
        
        # C1 harus bullish, C3 harus bearish
        if not (c1['close'] > c1['open'] and c3['close'] < c3['open']): return False
        
        # Badan C2 harus kecil dan berada di atas badan C1
        c2_body = abs(c2['close'] - c2['open'])
        if not (c2_body < abs(c1['close'] - c1['open']) and min(c2['open'], c2['close']) > c1['close']): return False
        
        # C3 harus ditutup di bawah titik tengah badan C1
        return c3['close'] < (c1['open'] + c1['close']) / 2


    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Metode utama yang dipanggil untuk memeriksa sinyal dengan berbagai konfirmasi.
        """
        min_candles = self.SLOW_EMA_LENGTH + 5
        if df.empty or len(df) < min_candles:
            return None

        # --- PERSIAPAN INDIKATOR ---
        df.ta.ema(length=self.FAST_EMA_LENGTH, append=True)
        df.ta.ema(length=self.SLOW_EMA_LENGTH, append=True)
        df.ta.atr(length=self.ATR_LENGTH, append=True)

        last_candle_idx = -1
        last_candle = df.iloc[last_candle_idx]
        
        fast_ema = last_candle.get(f'EMA_{self.FAST_EMA_LENGTH}')
        slow_ema = last_candle.get(f'EMA_{self.SLOW_EMA_LENGTH}')
        atr_value = last_candle.get(f'ATRr_{self.ATR_LENGTH}')

        if pd.isna(fast_ema) or pd.isna(slow_ema) or pd.isna(atr_value):
            return None

        # --- CEK SINYAL LONG ---
        is_uptrend = fast_ema > slow_ema
        if is_uptrend:
            # Periksa setiap pola konfirmasi bullish
            patterns = {
                "Bullish Engulfing": {"func": self._is_bullish_engulfing, "candles": 2, "sl_ref": "low"},
                "Hammer": {"func": self._is_hammer, "candles": 1, "sl_ref": "low"},
                "Morning Star": {"func": self._is_morning_star, "candles": 3, "sl_ref": "low_star"}
            }
            
            for name, p in patterns.items():
                if p['func'](df, last_candle_idx):
                    # Cek apakah terjadi pullback dalam formasi candle
                    pullback_occurred = False
                    sl_price_ref = df.iloc[last_candle_idx][p['sl_ref']] if p['sl_ref'] != "low_star" else min(df.iloc[last_candle_idx-2]['low'], df.iloc[last_candle_idx-1]['low'], df.iloc[last_candle_idx]['low'])

                    for i in range(p['candles']):
                        if df.iloc[last_candle_idx - i]['low'] <= df.iloc[last_candle_idx - i].get(f'EMA_{self.FAST_EMA_LENGTH}'):
                            pullback_occurred = True
                            break
                    
                    if pullback_occurred:
                        entry_price = last_candle['close']
                        stop_loss = sl_price_ref - (atr_value * self.SL_BUFFER_FACTOR)
                        risk_distance = entry_price - stop_loss
                        
                        if risk_distance <= 0: continue
                        take_profit = entry_price + (risk_distance * self.RISK_REWARD_RATIO)
                        
                        reason = f"Uptrend, Pullback to EMA({self.FAST_EMA_LENGTH}) + {name}."
                        return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}


        # --- CEK SINYAL SHORT ---
        is_downtrend = fast_ema < slow_ema
        if is_downtrend:
            # Periksa setiap pola konfirmasi bearish
            patterns = {
                "Bearish Engulfing": {"func": self._is_bearish_engulfing, "candles": 2, "sl_ref": "high"},
                "Shooting Star": {"func": self._is_shooting_star, "candles": 1, "sl_ref": "high"},
                "Evening Star": {"func": self._is_evening_star, "candles": 3, "sl_ref": "high_star"}
            }

            for name, p in patterns.items():
                if p['func'](df, last_candle_idx):
                    pullback_occurred = False
                    sl_price_ref = df.iloc[last_candle_idx][p['sl_ref']] if p['sl_ref'] != "high_star" else max(df.iloc[last_candle_idx-2]['high'], df.iloc[last_candle_idx-1]['high'], df.iloc[last_candle_idx]['high'])

                    for i in range(p['candles']):
                        if df.iloc[last_candle_idx - i]['high'] >= df.iloc[last_candle_idx - i].get(f'EMA_{self.FAST_EMA_LENGTH}'):
                            pullback_occurred = True
                            break

                    if pullback_occurred:
                        entry_price = last_candle['close']
                        stop_loss = sl_price_ref + (atr_value * self.SL_BUFFER_FACTOR)
                        risk_distance = stop_loss - entry_price

                        if risk_distance <= 0: continue
                        take_profit = entry_price - (risk_distance * self.RISK_REWARD_RATIO)
                        
                        reason = f"Downtrend, Pullback to EMA({self.FAST_EMA_LENGTH}) + {name}."
                        return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None
