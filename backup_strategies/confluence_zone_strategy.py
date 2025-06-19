# File: confluence_zone_strategy_v3.py

import pandas as pd
import pandas_ta as ta
import numpy as np

from strategies.base_strategy import BaseStrategy
import utils # Asumsikan utils.py memiliki fungsi fetch_klines(symbol, timeframe, limit)

class ConfluenceZoneStrategyV3(BaseStrategy):
    """
    Strategi v3 yang mencari zona konfluensi S&R antara 1h & 15m.
    Versi ini menggunakan kalkulasi Pivot Points manual untuk menghindari
    error library dan meningkatkan stabilitas.
    """
    
    name = "confluence_zone_v3"
    description = "v3: Entry di zona konfluensi S&R (Manual Pivots FIX)."

    # --- PARAMETER STRATEGI ---
    HTF = '1h'
    LTF = '15m'
    
    # --- Parameter Konfigurasi ---
    HTF_LOOKBACK = 100
    LTF_LOOKBACK = 200
    ZONE_PROXIMITY_PCT = 0.003
    
    # --- Parameter Filter ---
    EMA_TREND_LENGTH = 50
    RSI_PERIOD = 14
    VOLUME_MA_LENGTH = 20
    # Menggunakan parameter dari pengguna
    VOLUME_SPIKE_FACTOR = 1.2

    # --- Parameter Manajemen Risiko (menggunakan parameter dari pengguna) ---
    ATR_LENGTH = 14
    SL_BUFFER_FACTOR = 1.0
    RISK_REWARD_RATIO = 3.0

    def _calculate_manual_pivots(self, df: pd.DataFrame) -> dict:
        """
        Menghitung level Pivot Point Fibonacci secara manual berdasarkan
        High, Low, Close dari candle SEBELUMNYA.
        """
        if len(df) < 2:
            return {}
        
        # Pivot dihitung dari candle sebelumnya (periode sebelumnya)
        prev_candle = df.iloc[-2]
        high = prev_candle['high']
        low = prev_candle['low']
        close = prev_candle['close']
        
        pivot = (high + low + close) / 3
        price_range = high - low
        
        return {
            'S1': pivot - (price_range * 0.382),
            'S2': pivot - (price_range * 0.618),
            'S3': pivot - (price_range * 1.000),
            'R1': pivot + (price_range * 0.382),
            'R2': pivot + (price_range * 0.618),
            'R3': pivot + (price_range * 1.000)
        }

    def check_signal(self, symbol: str, df_ltf: pd.DataFrame) -> dict | None:
        """Metode utama yang menjalankan seluruh logika strategi."""
        try:
            df_htf = utils.fetch_klines(symbol, self.HTF, limit=self.HTF_LOOKBACK)
            if df_htf.empty or len(df_ltf) < self.LTF_LOOKBACK:
                return None
        except Exception as e:
            return None

        # <<<--- PERBAIKAN: Memanggil fungsi kalkulasi pivot manual ---
        zones_htf = self._calculate_manual_pivots(df_htf)
        zones_ltf = self._calculate_manual_pivots(df_ltf)

        if not zones_htf or not zones_ltf:
            return None
            
        bullish_confluence_zones = []
        for htf_s_level in ['S1', 'S2', 'S3']:
            for ltf_s_level in ['S1', 'S2', 'S3']:
                htf_s = zones_htf.get(htf_s_level)
                ltf_s = zones_ltf.get(ltf_s_level)
                if htf_s and ltf_s and abs(htf_s - ltf_s) / htf_s <= self.ZONE_PROXIMITY_PCT:
                    zone_top = max(htf_s, ltf_s)
                    zone_bottom = min(htf_s, ltf_s)
                    bullish_confluence_zones.append((zone_bottom, zone_top))

        bearish_confluence_zones = []
        for htf_r_level in ['R1', 'R2', 'R3']:
            for ltf_r_level in ['R1', 'R2', 'R3']:
                htf_r = zones_htf.get(htf_r_level)
                ltf_r = zones_ltf.get(ltf_r_level)
                if htf_r and ltf_r and abs(htf_r - ltf_r) / htf_r <= self.ZONE_PROXIMITY_PCT:
                    zone_top = max(htf_r, ltf_r)
                    zone_bottom = min(htf_r, ltf_r)
                    bearish_confluence_zones.append((zone_bottom, zone_top))

        df_ltf.ta.ema(length=self.EMA_TREND_LENGTH, append=True)
        df_ltf.ta.rsi(length=self.RSI_PERIOD, append=True)
        df_ltf.ta.atr(length=self.ATR_LENGTH, append=True)
        df_ltf['volume_ma'] = df_ltf['volume'].rolling(self.VOLUME_MA_LENGTH).mean()

        for i in range(-3, 0): 
            if (i + 1) >= len(df_ltf) or i >= len(df_ltf): continue 
            last_candle = df_ltf.iloc[i]
            confirmation_candle = df_ltf.iloc[i + 1]

            ema_val = confirmation_candle.get(f'EMA_{self.EMA_TREND_LENGTH}')
            rsi_val = confirmation_candle.get(f'RSI_{self.RSI_PERIOD}')
            atr_val = confirmation_candle.get(f'ATRr_{self.ATR_LENGTH}')
            vol_ma_val = confirmation_candle.get('volume_ma')

            if pd.isna(ema_val) or pd.isna(rsi_val) or pd.isna(atr_val) or pd.isna(vol_ma_val):
                continue
            
            # Cek Sinyal LONG
            is_uptrend = confirmation_candle['close'] > ema_val
            if is_uptrend and bullish_confluence_zones:
                for zone_bottom, zone_top in bullish_confluence_zones:
                    entered_zone = last_candle['low'] <= zone_top
                    exited_zone_up = confirmation_candle['close'] > zone_top and confirmation_candle['close'] > confirmation_candle['open']
                    
                    if entered_zone and exited_zone_up:
                        momentum_ok = rsi_val > 50
                        volume_ok = confirmation_candle['volume'] > vol_ma_val * self.VOLUME_SPIKE_FACTOR
                        
                        if momentum_ok and volume_ok:
                            entry_price = confirmation_candle['close']
                            stop_loss = zone_bottom - (atr_val * self.SL_BUFFER_FACTOR)
                            risk = entry_price - stop_loss
                            if risk <= 0: continue
                            take_profit = entry_price + (risk * self.RISK_REWARD_RATIO)
                            
                            reason = f"Reversal dari Zona Konfluensi Support ({zone_bottom:.4f}-{zone_top:.4f})"
                            return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

            # Cek Sinyal SHORT
            is_downtrend = confirmation_candle['close'] < ema_val
            if is_downtrend and bearish_confluence_zones:
                for zone_bottom, zone_top in bearish_confluence_zones:
                    entered_zone = last_candle['high'] >= zone_bottom
                    exited_zone_down = confirmation_candle['close'] < zone_bottom and confirmation_candle['close'] < confirmation_candle['open']

                    if entered_zone and exited_zone_down:
                        momentum_ok = rsi_val < 50
                        volume_ok = confirmation_candle['volume'] > vol_ma_val * self.VOLUME_SPIKE_FACTOR
                        
                        if momentum_ok and volume_ok:
                            entry_price = confirmation_candle['close']
                            stop_loss = zone_top + (atr_val * self.SL_BUFFER_FACTOR)
                            risk = stop_loss - entry_price
                            if risk <= 0: continue
                            take_profit = entry_price - (risk * self.RISK_REWARD_RATIO)

                            reason = f"Rejection dari Zona Konfluensi Resistance ({zone_bottom:.4f}-{zone_top:.4f})"
                            return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None
