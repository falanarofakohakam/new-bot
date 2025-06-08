import pandas as pd
import pandas_ta as ta

# Import dari file-file lain dalam proyek
from strategies.base_strategy import BaseStrategy
import utils # Diperlukan untuk beberapa fungsi pembantu jika ada

class SmcStrategy(BaseStrategy):
    # Properti wajib dari BaseStrategy
    name = "smc_fvg_ob"
    description = "SMC: Entry pada Fair Value Gap & Order Block."

    # --- PARAMETER SPESIFIK UNTUK STRATEGI INI ---
    TIMEFRAME = '15m'
    LOOKBACK_CANDLES = 100  # Jumlah candle ke belakang untuk dianalisis
    ATR_LENGTH = 14
    RISK_REWARD_RATIO = 2.0  # R:R lebih tinggi cocok untuk strategi presisi seperti SMC
    
    # Faktor untuk mendefinisikan 'pergerakan impulsif' saat mencari Order Block
    OB_IMPULSE_FACTOR = 1.5 

    def _find_fvgs(self, df: pd.DataFrame, limit=5):
        """Mendeteksi Fair Value Gaps (FVG) terbaru dalam DataFrame."""
        fvgs = []
        # Iterasi dari candle kedua hingga sebelum candle terakhir
        for i in range(1, len(df) - 1):
            # Bullish FVG: Low candle (i-1) lebih tinggi dari High candle (i+1)
            if df['low'].iloc[i-1] > df['high'].iloc[i+1]:
                fvgs.append({
                    'type': 'bullish',
                    'top': df['low'].iloc[i-1],
                    'bottom': df['high'].iloc[i+1],
                    'index': i
                })
            # Bearish FVG: High candle (i-1) lebih rendah dari Low candle (i+1)
            elif df['high'].iloc[i-1] < df['low'].iloc[i+1]:
                fvgs.append({
                    'type': 'bearish',
                    'top': df['low'].iloc[i+1],
                    'bottom': df['high'].iloc[i-1],
                    'index': i
                })
        # Urutkan berdasarkan candle terbaru dan ambil beberapa saja
        return sorted(fvgs, key=lambda x: x['index'], reverse=True)[:limit]
    
    def _find_order_blocks(self, df: pd.DataFrame, limit=3):
        """Mendeteksi Order Blocks (OB) sederhana."""
        obs = []
        # Rata-rata range candle sebagai acuan 'pergerakan impulsif'
        avg_range = (df['high'] - df['low']).mean()

        for i in range(1, len(df)):
            current_range = df['high'].iloc[i] - df['low'].iloc[i]
            
            # Cek jika pergerakan candle saat ini 'impulsif'
            if current_range > avg_range * self.OB_IMPULSE_FACTOR:
                # Bullish OB: candle sebelumnya bearish (merah), candle sekarang bullish (hijau)
                if df['close'].iloc[i-1] < df['open'].iloc[i-1] and df['close'].iloc[i] > df['open'].iloc[i]:
                    obs.append({
                        'type': 'bullish',
                        'top': df['high'].iloc[i-1],
                        'bottom': df['low'].iloc[i-1],
                        'index': i-1
                    })
                # Bearish OB: candle sebelumnya bullish (hijau), candle sekarang bearish (merah)
                elif df['close'].iloc[i-1] > df['open'].iloc[i-1] and df['close'].iloc[i] < df['open'].iloc[i]:
                    obs.append({
                        'type': 'bearish',
                        'top': df['high'].iloc[i-1],
                        'bottom': df['low'].iloc[i-1],
                        'index': i-1
                    })
        return sorted(obs, key=lambda x: x['index'], reverse=True)[:limit]

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Metode utama yang memeriksa sinyal berdasarkan data yang diberikan.
        """
        if df.empty or len(df) < self.LOOKBACK_CANDLES: 
            return None
        
        # Hitung ATR untuk manajemen risiko
        df.ta.atr(length=self.ATR_LENGTH, append=True)
        
        last = df.iloc[-1]
        atr_value = last[f'ATRr_{self.ATR_LENGTH}']
        if pd.isna(atr_value) or atr_value == 0: 
            return None

        # Cari FVG dan OB dalam data yang tersedia
        recent_fvgs = self._find_fvgs(df)
        recent_obs = self._find_order_blocks(df)
        
        entry_price = last['close']

        # --- LOGIKA SINYAL LONG ---
        # Prioritaskan FVG, lalu OB
        for fvg in recent_fvgs:
            # Jika FVG bullish, dan harga saat ini masuk ke zona FVG lalu bereaksi naik
            if fvg['type'] == 'bullish' and last['low'] <= fvg['top'] and last['close'] > fvg['bottom']:
                stop_loss = fvg['bottom'] - atr_value 
                take_profit = entry_price + (entry_price - stop_loss) * self.RISK_REWARD_RATIO
                return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': f"Reaksi dari Bullish FVG", 'risk_reward_ratio': self.RISK_REWARD_RATIO}
        
        for ob in recent_obs:
            # Jika OB bullish, dan harga saat ini masuk ke zona OB lalu bereaksi naik
            if ob['type'] == 'bullish' and last['low'] <= ob['top'] and last['close'] > ob['bottom']:
                stop_loss = ob['bottom'] - atr_value
                take_profit = entry_price + (entry_price - stop_loss) * self.RISK_REWARD_RATIO
                return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': f"Reaksi dari Bullish OB", 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        # --- LOGIKA SINYAL SHORT ---
        for fvg in recent_fvgs:
            # Jika FVG bearish, dan harga saat ini masuk ke zona FVG lalu bereaksi turun
            if fvg['type'] == 'bearish' and last['high'] >= fvg['bottom'] and last['close'] < fvg['top']:
                stop_loss = fvg['top'] + atr_value
                take_profit = entry_price - (stop_loss - entry_price) * self.RISK_REWARD_RATIO
                return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': f"Reaksi dari Bearish FVG", 'risk_reward_ratio': self.RISK_REWARD_RATIO}
        
        for ob in recent_obs:
            # Jika OB bearish, dan harga saat ini masuk ke zona OB lalu bereaksi turun
            if ob['type'] == 'bearish' and last['high'] >= ob['bottom'] and last['close'] < ob['top']:
                stop_loss = ob['top'] + atr_value
                take_profit = entry_price - (stop_loss - entry_price) * self.RISK_REWARD_RATIO
                return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': f"Reaksi dari Bearish OB", 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        # Jika tidak ada sinyal yang ditemukan
        return None
    
    
    import pandas as pd
import pandas_ta as ta
import numpy as np

# Import dari file-file lain dalam proyek
from strategies.base_strategy import BaseStrategy
import utils

class SmcStrategy(BaseStrategy):
    name = "smc_v2_smart"
    description = "SMC v2: Entry pada FVG/OB valid dengan konfirmasi HTF & BoS."

    # --- PARAMETER STRATEGI ---
    TIMEFRAME = '15m'
    LOOKBACK_CANDLES = 200 # Butuh lebih banyak data untuk swing points & BoS
    
    # Parameter Filter Tren HTF
    HTF_TIMEFRAME = '1h'
    HTF_EMA_LENGTH = 200

    # Parameter Manajemen Risiko
    ATR_LENGTH = 14
    RISK_REWARD_RATIO = 2.0
    
    # Parameter Pola SMC
    OB_IMPULSE_FACTOR = 1.5
    SWING_LOOKBACK = 10 # Jumlah candle kiri/kanan untuk menentukan swing point

    # --- FUNGSI HELPER UNTUK DETEKSI POLA ---

    def _find_swing_points(self, df: pd.DataFrame):
        """Mendeteksi Swing Highs dan Swing Lows untuk Break of Structure (BoS)."""
        highs = []
        lows = []
        n = self.SWING_LOOKBACK
        for i in range(n, len(df) - n):
            # Swing High: high[i] adalah yang tertinggi di antara 2n+1 candle
            if df['high'].iloc[i] == df['high'].iloc[i-n:i+n+1].max():
                highs.append({'index': i, 'price': df['high'].iloc[i]})
            # Swing Low: low[i] adalah yang terendah di antara 2n+1 candle
            if df['low'].iloc[i] == df['low'].iloc[i-n:i+n+1].min():
                lows.append({'index': i, 'price': df['low'].iloc[i]})
        return sorted(highs, key=lambda x: x['index'], reverse=True), sorted(lows, key=lambda x: x['index'], reverse=True)

    def _find_order_blocks(self, df: pd.DataFrame, swing_highs, swing_lows, limit=3):
        """Mendeteksi Order Blocks (OB) yang divalidasi dengan Break of Structure (BoS)."""
        obs = []
        avg_range = (df['high'] - df['low']).mean()
        for i in range(self.SWING_LOOKBACK, len(df)):
            current_range = df['high'].iloc[i] - df['low'].iloc[i]
            if current_range > avg_range * self.OB_IMPULSE_FACTOR:
                # Cek Bullish OB (candle sebelumnya bearish, sekarang bullish)
                if df['close'].iloc[i-1] < df['open'].iloc[i-1] and df['close'].iloc[i] > df['open'].iloc[i]:
                    # Cari swing high terdekat SEBELUM OB terbentuk
                    relevant_highs = [sh for sh in swing_highs if sh['index'] < i]
                    if relevant_highs and df['high'].iloc[i] > relevant_highs[0]['price']:
                        obs.append({'type': 'bullish', 'top': df['high'].iloc[i-1], 'bottom': df['low'].iloc[i-1], 'index': i-1})
                # Cek Bearish OB (candle sebelumnya bullish, sekarang bearish)
                elif df['close'].iloc[i-1] > df['open'].iloc[i-1] and df['close'].iloc[i] < df['open'].iloc[i]:
                    # Cari swing low terdekat SEBELUM OB terbentuk
                    relevant_lows = [sl for sl in swing_lows if sl['index'] < i]
                    if relevant_lows and df['low'].iloc[i] < relevant_lows[0]['price']:
                        obs.append({'type': 'bearish', 'top': df['high'].iloc[i-1], 'bottom': df['low'].iloc[i-1], 'index': i-1})
        return sorted(obs, key=lambda x: x['index'], reverse=True)[:limit]

    def _find_fvgs(self, df: pd.DataFrame, limit=5):
        """Mendeteksi Fair Value Gaps (FVG) terbaru dalam DataFrame."""
        fvgs = []
        # Iterasi dari candle kedua hingga sebelum candle terakhir
        for i in range(1, len(df) - 1):
            # Bullish FVG: Low candle (i-1) lebih tinggi dari High candle (i+1)
            if df['low'].iloc[i-1] > df['high'].iloc[i+1]:
                fvgs.append({
                    'type': 'bullish',
                    'top': df['low'].iloc[i-1],
                    'bottom': df['high'].iloc[i+1],
                    'index': i
                })
            # Bearish FVG: High candle (i-1) lebih rendah dari Low candle (i+1)
            elif df['high'].iloc[i-1] < df['low'].iloc[i+1]:
                fvgs.append({
                    'type': 'bearish',
                    'top': df['low'].iloc[i+1],
                    'bottom': df['high'].iloc[i-1],
                    'index': i
                })
        # Urutkan berdasarkan candle terbaru dan ambil beberapa saja
        return sorted(fvgs, key=lambda x: x['index'], reverse=True)[:limit]

    def _is_zone_invalidated(self, df: pd.DataFrame, zone: dict):
        """Memeriksa apakah zona FVG atau OB sudah tidak valid (tertembus)."""
        candles_after_zone = df.iloc[zone['index'] + 2:]
        if zone['type'] == 'bullish':
            # Jika ada candle setelahnya yang low-nya menembus dasar zona, maka tidak valid
            return any(candles_after_zone['low'] < zone['bottom'])
        elif zone['type'] == 'bearish':
            # Jika ada candle setelahnya yang high-nya menembus puncak zona, maka tidak valid
            return any(candles_after_zone['high'] > zone['top'])
        return False

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """Metode utama yang memeriksa sinyal berdasarkan semua aturan yang disempurnakan."""
        if df.empty or len(df) < self.LOOKBACK_CANDLES: return None
        
        # === LANGKAH 1: FILTER TREN MAKRO (HTF) ===
        df_htf = utils.fetch_klines(symbol, self.HTF_TIMEFRAME, limit=self.HTF_EMA_LENGTH + 5)
        if len(df_htf) < self.HTF_EMA_LENGTH: return None
        df_htf.ta.ema(length=self.HTF_EMA_LENGTH, append=True)
        last_htf = df_htf.iloc[-1]
        htf_ema = last_htf[f'EMA_{self.HTF_EMA_LENGTH}']
        if pd.isna(htf_ema): return None
        htf_trend = 'BULLISH' if last_htf['close'] > htf_ema else 'BEARISH'

        # === LANGKAH 2: PERSIAPAN DATA DAN INDIKATOR LTF ===
        df.ta.atr(length=self.ATR_LENGTH, append=True)
        last = df.iloc[-1]
        atr_value = last[f'ATRr_{self.ATR_LENGTH}']
        if pd.isna(atr_value) or atr_value == 0: return None
        entry_price = last['close']
        
        # Cari semua pola dan struktur pasar
        swing_highs, swing_lows = self._find_swing_points(df)
        recent_fvgs = self._find_fvgs(df)
        recent_obs = self._find_order_blocks(df, swing_highs, swing_lows)

        # === LANGKAH 3: PENCARIAN SINYAL SESUAI ARAH TREN ===
        if htf_trend == 'BULLISH':
            # Cari Sinyal LONG
            zones_to_check = sorted(recent_fvgs + recent_obs, key=lambda x: x['index'], reverse=True)
            for zone in zones_to_check:
                if zone['type'] == 'bullish':
                    # Periksa apakah zona masih valid
                    if self._is_zone_invalidated(df, zone): continue
                    
                    # Periksa kondisi entry: harga masuk zona dan candle reaksi berwarna hijau
                    is_mitigated = last['low'] <= zone['top'] and last['close'] > zone['bottom']
                    is_confirmation_candle = last['close'] > last['open']
                    
                    if is_mitigated and is_confirmation_candle:
                        stop_loss = zone['bottom'] - (atr_value * 0.5) # SL sedikit di bawah zona
                        take_profit = entry_price + (entry_price - stop_loss) * self.RISK_REWARD_RATIO
                        reason = f"Reaksi dari Bullish {'OB' if 'avg_range' not in zone else 'FVG'} (HTF Bullish)"
                        return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        elif htf_trend == 'BEARISH':
            # Cari Sinyal SHORT
            zones_to_check = sorted(recent_fvgs + recent_obs, key=lambda x: x['index'], reverse=True)
            for zone in zones_to_check:
                if zone['type'] == 'bearish':
                    if self._is_zone_invalidated(df, zone): continue
                    
                    is_mitigated = last['high'] >= zone['bottom'] and last['close'] < zone['top']
                    is_confirmation_candle = last['close'] < last['open']

                    if is_mitigated and is_confirmation_candle:
                        stop_loss = zone['top'] + (atr_value * 0.5) # SL sedikit di atas zona
                        take_profit = entry_price - (stop_loss - entry_price) * self.RISK_REWARD_RATIO
                        reason = f"Reaksi dari Bearish {'OB' if 'avg_range' not in zone else 'FVG'} (HTF Bearish)"
                        return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None
    