import pandas as pd
import pandas_ta as ta
import numpy as np

# Import dari file-file lain dalam proyek
from strategies.base_strategy import BaseStrategy
import utils

class SnRReversalStrategy(BaseStrategy):
    name = "snr_reversal"
    description = "S&R Reversal: Entry di zona S&R HTF dengan konfirmasi LTF."

    # --- PARAMETER STRATEGI ---
    HTF_TIMEFRAME = '1h'  # Timeframe untuk menentukan zona S&R mayor
    LTF_TIMEFRAME = '15m' # Timeframe untuk mencari sinyal entry
    
    HTF_LOOKBACK = 100    # Jumlah candle HTF untuk dicari swing points
    SWING_LOOKBACK = 5    # n candle kiri/kanan untuk validasi swing point di HTF

    # Parameter Manajemen Risiko
    ATR_LENGTH_LTF = 14
    ATR_MULTIPLIER = 1.0 # Multiplier ATR untuk buffer Stop Loss
    RISK_REWARD_RATIO = 1.5

    # Parameter Filter Konfirmasi
    USE_RSI_FILTER = True
    RSI_LENGTH = 14
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30

    def _find_major_zones(self, symbol: str):
        """Mendeteksi zona Support & Resistance mayor dari Higher Timeframe."""
        df_htf = utils.fetch_klines(symbol, self.HTF_TIMEFRAME, limit=self.HTF_LOOKBACK)
        if df_htf.empty or len(df_htf) < (self.SWING_LOOKBACK * 2 + 1):
            return None, None

        n = self.SWING_LOOKBACK
        # Cari swing high terbaru
        df_htf['is_swh'] = df_htf['high'].rolling(n*2+1, center=True).max() == df_htf['high']
        # Cari swing low terbaru
        df_htf['is_swl'] = df_htf['low'].rolling(n*2+1, center=True).min() == df_htf['low']

        major_resistance = df_htf[df_htf['is_swh']].iloc[-1]['high'] if not df_htf[df_htf['is_swh']].empty else None
        major_support = df_htf[df_htf['is_swl']].iloc[-1]['low'] if not df_htf[df_htf['is_swl']].empty else None
        
        return major_support, major_resistance

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Metode utama yang memeriksa sinyal berdasarkan data LTF yang diberikan,
        setelah memvalidasi dengan zona S&R dari HTF.
        """
        # Pastikan kita menggunakan timeframe yang benar
        # Atribut TIMEFRAME akan digunakan oleh 'features.py' untuk fetch data ini
        self.TIMEFRAME = self.LTF_TIMEFRAME

        if df.empty or len(df) < 50: return None
        
        # --- LANGKAH 1: DAPATKAN ZONA S&R MAYOR DARI HTF ---
        support_zone, resistance_zone = self._find_major_zones(symbol)
        
        if not support_zone and not resistance_zone:
            return None # Tidak bisa menemukan zona S&R yang jelas

        # --- LANGKAH 2: PERSIAPAN INDIKATOR PADA LTF ---
        df.ta.atr(length=self.ATR_LENGTH_LTF, append=True)
        if self.USE_RSI_FILTER:
            df.ta.rsi(length=self.RSI_LENGTH, append=True)

        last = df.iloc[-1]
        atr_value = last[f'ATRr_{self.ATR_LENGTH_LTF}']
        if pd.isna(atr_value): return None
        
        entry_price = last['close']

        # --- LANGKAH 3: CEK SINYAL LONG DI ZONA SUPPORT ---
        if support_zone:
            # Kondisi 1: Harga menyentuh atau sedikit menembus zona support
            is_in_support_zone = last['low'] <= support_zone
            # Kondisi 2: Harga ditutup kembali di atas zona support (konfirmasi pantulan)
            is_reclaimed = last['close'] > support_zone
            # Kondisi 3: Candle adalah candle bullish (hijau)
            is_bullish_candle = last['close'] > last['open']
            
            rsi_ok = True
            if self.USE_RSI_FILTER:
                rsi_value = last[f'RSI_{self.RSI_LENGTH}']
                if pd.notna(rsi_value) and rsi_value > self.RSI_OVERBOUGHT:
                    rsi_ok = False # Hindari membeli saat sudah overbought

            if is_in_support_zone and is_reclaimed and is_bullish_candle and rsi_ok:
                stop_loss = support_zone - (atr_value * self.ATR_MULTIPLIER)
                take_profit = entry_price + (entry_price - stop_loss) * self.RISK_REWARD_RATIO
                reason = f"Reversal dari zona Support HTF ({support_zone:.4f})"
                return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        # --- LANGKAH 4: CEK SINYAL SHORT DI ZONA RESISTANCE ---
        if resistance_zone:
            # Kondisi 1: Harga menyentuh atau sedikit menembus zona resistance
            is_in_resistance_zone = last['high'] >= resistance_zone
            # Kondisi 2: Harga ditutup kembali di bawah zona resistance (konfirmasi penolakan)
            is_rejected = last['close'] < resistance_zone
            # Kondisi 3: Candle adalah candle bearish (merah)
            is_bearish_candle = last['close'] < last['open']
            
            rsi_ok = True
            if self.USE_RSI_FILTER:
                rsi_value = last[f'RSI_{self.RSI_LENGTH}']
                if pd.notna(rsi_value) and rsi_value < self.RSI_OVERSOLD:
                    rsi_ok = False # Hindari menjual saat sudah oversold

            if is_in_resistance_zone and is_rejected and is_bearish_candle and rsi_ok:
                stop_loss = resistance_zone + (atr_value * self.ATR_MULTIPLIER)
                take_profit = entry_price - (stop_loss - entry_price) * self.RISK_REWARD_RATIO
                reason = f"Rejection dari zona Resistance HTF ({resistance_zone:.4f})"
                return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None