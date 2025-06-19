# File: whale_tracker_strategy_v2.py

import pandas as pd
import pandas_ta as ta
import numpy as np

from strategies.base_strategy import BaseStrategy
# import utils # Uncomment if you use a utils file

class WhaleTrackerStrategyV2(BaseStrategy):
    """
    Strategi v2 yang mengikuti "Whales" dengan filter tren EMA dan
    candle konfirmasi untuk meningkatkan akurasi sinyal dan win rate.
    """
    
    # Properti wajib dari BaseStrategy
    name = "whale_tracker_v2"
    description = "v2: Mengikuti whale dengan filter tren EMA dan candle konfirmasi."

    # --- PARAMETER STRATEGI ---
    TIMEFRAME = '15m'
    MA_LOOKBACK = 30
    VOLUME_SPIKE_FACTOR = 5.0
    CANDLE_BODY_MIN_RATIO = 0.7

    # <<<--- PARAMETER BARU UNTUK FILTER & KONFIRMASI ---
    # Aktifkan/nonaktifkan filter baru dengan mudah
    USE_TREND_FILTER = True
    REQUIRE_CONFIRMATION_CANDLE = True
    
    # Periode EMA untuk menentukan tren pasar secara keseluruhan
    EMA_TREND_LENGTH = 50
    # <<<--- AKHIR PARAMETER BARU ---

    # --- Parameter Manajemen Risiko ---
    ATR_LENGTH = 14
    SL_ATR_BUFFER = 1
    # RRR disesuaikan menjadi lebih konservatif untuk win rate yang lebih tinggi
    RISK_REWARD_RATIO = 2 

    def _check_signal_conditions(self, df: pd.DataFrame) -> dict | None:
        """
        Fungsi inti untuk menganalisis sinyal dengan filter dan konfirmasi.
        Menganalisis candle sinyal (iloc[-3]) dan candle konfirmasi (iloc[-2]).
        """
        # Kita butuh minimal 3 candle: sebelum sinyal, sinyal, konfirmasi
        if len(df) < self.MA_LOOKBACK + 3:
            return None

        # Definisikan candle yang relevan
        signal_candle = df.iloc[-3]
        confirmation_candle = df.iloc[-2]
        
        # Pastikan data indikator pada candle sinyal tidak NaN
        volume_ma_value = signal_candle.get('volume_ma')
        atr_value = signal_candle.get(f'ATRr_{self.ATR_LENGTH}')
        ema_trend_value = signal_candle.get(f'EMA_{self.EMA_TREND_LENGTH}')

        if pd.isna(volume_ma_value) or pd.isna(atr_value) or pd.isna(ema_trend_value):
            return None

        # --- KONDISI INTI PADA "SIGNAL CANDLE" ---
        # 1. Cek lonjakan volume
        is_volume_spike = signal_candle['volume'] > (volume_ma_value * self.VOLUME_SPIKE_FACTOR)
        
        # 2. Cek kualitas body candle
        candle_range = signal_candle['high'] - signal_candle['low']
        if candle_range == 0: return None
        
        body_size = abs(signal_candle['close'] - signal_candle['open'])
        is_strong_body = (body_size / candle_range) >= self.CANDLE_BODY_MIN_RATIO

        # Jika kondisi dasar tidak terpenuhi, berhenti lebih awal
        if not (is_volume_spike and is_strong_body):
            return None

        # --- FILTER & KONFIRMASI ---
        
        # Cek Sinyal LONG
        if signal_candle['close'] > signal_candle['open']: # Candle sinyal hijau
            
            # 1. Filter Tren: Harga harus di atas EMA
            trend_ok = (signal_candle['close'] > ema_trend_value) if self.USE_TREND_FILTER else True
            
            # 2. Candle Konfirmasi: Candle berikutnya juga harus hijau
            confirmation_ok = (confirmation_candle['close'] > confirmation_candle['open']) if self.REQUIRE_CONFIRMATION_CANDLE else True
            
            if trend_ok and confirmation_ok:
                entry_price = confirmation_candle['close'] # Entry di penutupan candle konfirmasi
                stop_loss = signal_candle['low'] - (atr_value * self.SL_ATR_BUFFER)
                risk_distance = entry_price - stop_loss
                if risk_distance <= 0: return None
                take_profit = entry_price + (risk_distance * self.RISK_REWARD_RATIO)
                
                reason = f"Whale BUY on {self.TIMEFRAME} [Trend OK, Confirmed]"
                return {'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason}

        # Cek Sinyal SHORT
        elif signal_candle['close'] < signal_candle['open']: # Candle sinyal merah
            
            # 1. Filter Tren: Harga harus di bawah EMA
            trend_ok = (signal_candle['close'] < ema_trend_value) if self.USE_TREND_FILTER else True

            # 2. Candle Konfirmasi: Candle berikutnya juga harus merah
            confirmation_ok = (confirmation_candle['close'] < confirmation_candle['open']) if self.REQUIRE_CONFIRMATION_CANDLE else True

            if trend_ok and confirmation_ok:
                entry_price = confirmation_candle['close'] # Entry di penutupan candle konfirmasi
                stop_loss = signal_candle['high'] + (atr_value * self.SL_ATR_BUFFER)
                risk_distance = stop_loss - entry_price
                if risk_distance <= 0: return None
                take_profit = entry_price - (risk_distance * self.RISK_REWARD_RATIO)

                reason = f"Whale SELL on {self.TIMEFRAME} [Trend OK, Confirmed]"
                return {'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason}
            
        return None

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Metode utama yang dipanggil untuk memeriksa sinyal.
        Mempersiapkan data dan memanggil fungsi analisis.
        """
        if df.empty or len(df) < self.MA_LOOKBACK:
            return None

        # --- PERSIAPAN INDIKATOR ---
        # 1. Volume Moving Average
        df['volume_ma'] = df['volume'].rolling(self.MA_LOOKBACK).mean()
        
        # 2. ATR untuk Stop Loss
        df.ta.atr(length=self.ATR_LENGTH, append=True)
        
        # <<<--- PERUBAHAN: Hitung EMA untuk filter tren ---
        if self.USE_TREND_FILTER:
            df.ta.ema(length=self.EMA_TREND_LENGTH, append=True)

        # Panggil fungsi analisis inti
        signal_data = self._check_signal_conditions(df)

        if signal_data:
            return {
                'symbol': symbol,
                'signal': signal_data['signal'],
                'entry': signal_data['entry'],
                'stop_loss': signal_data['stop_loss'],
                'take_profit': signal_data['take_profit'],
                'reason': signal_data['reason'],
                'risk_reward_ratio': self.RISK_REWARD_RATIO
            }

        return None
