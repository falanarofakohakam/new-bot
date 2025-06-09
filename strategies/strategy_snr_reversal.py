import pandas as pd
import pandas_ta as ta
import numpy as np

# Import dari file-file lain dalam proyek
from strategies.base_strategy import BaseStrategy
import utils

class SnRReversalStrategy(BaseStrategy):
    # Nama dan deskripsi diperbarui untuk mencerminkan versi baru
    name = "snr_reversal_v3"
    description = "S&R Reversal v3: Entry di zona HTF dengan konfirmasi LTF + Volume."

    # --- PARAMETER STRATEGI ---
    HTF_TIMEFRAME = '1h'
    LTF_TIMEFRAME = '15m'
    
    HTF_LOOKBACK = 100
    SWING_LOOKBACK = 5

    # Parameter Manajemen Risiko
    ATR_LENGTH_LTF = 14
    SL_ATR_BUFFER = 1 
    RISK_REWARD_RATIO = 3

    # Parameter Filter Konfirmasi
    USE_RSI_FILTER = True
    RSI_LENGTH = 14
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30

    # <<<--- PARAMETER BARU UNTUK FILTER VOLUME ---
    USE_VOLUME_FILTER = True
    VOLUME_MA_LENGTH = 20
    # Volume candle konfirmasi harus 1.2x (20%) lebih besar dari rata-rata
    VOLUME_FACTOR = 1.2 
    # <<<--- AKHIR PARAMETER BARU ---

    def _find_major_zones(self, symbol: str):
        """Mendeteksi zona Support & Resistance mayor dari Higher Timeframe."""
        df_htf = utils.fetch_klines(symbol, self.HTF_TIMEFRAME, limit=self.HTF_LOOKBACK)
        if df_htf.empty or len(df_htf) < (self.SWING_LOOKBACK * 2 + 1):
            return None, None

        n = self.SWING_LOOKBACK
        df_htf['is_swh'] = df_htf['high'].rolling(n*2+1, center=True).max() == df_htf['high']
        df_htf['is_swl'] = df_htf['low'].rolling(n*2+1, center=True).min() == df_htf['low']

        major_resistance = df_htf[df_htf['is_swh']].iloc[-1]['high'] if not df_htf[df_htf['is_swh']].empty else None
        major_support = df_htf[df_htf['is_swl']].iloc[-1]['low'] if not df_htf[df_htf['is_swl']].empty else None
        
        return major_support, major_resistance

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Metode utama yang memeriksa sinyal berdasarkan data LTF,
        kini dengan tambahan konfirmasi volume.
        """
        self.TIMEFRAME = self.LTF_TIMEFRAME
        if df.empty or len(df) < 50: return None
        
        support_zone, resistance_zone = self._find_major_zones(symbol)
        if not support_zone and not resistance_zone: return None

        # --- PERSIAPAN INDIKATOR (TERMASUK VOLUME MA) ---
        df.ta.atr(length=self.ATR_LENGTH_LTF, append=True)
        if self.USE_RSI_FILTER:
            df.ta.rsi(length=self.RSI_LENGTH, append=True)
        # <<<--- PERUBAHAN: Hitung Volume Moving Average ---
        if self.USE_VOLUME_FILTER:
            df['volume_ma'] = df['volume'].rolling(self.VOLUME_MA_LENGTH).mean()

        last = df.iloc[-1]
        atr_value = last[f'ATRr_{self.ATR_LENGTH_LTF}']
        if pd.isna(atr_value): return None
        
        entry_price = last['close']

        # --- CEK SINYAL LONG DI ZONA SUPPORT ---
        if support_zone:
            is_in_support_zone = last['low'] <= support_zone
            is_reclaimed = last['close'] > support_zone
            is_bullish_candle = last['close'] > last['open']
            
            rsi_ok = True
            if self.USE_RSI_FILTER:
                rsi_value = last[f'RSI_{self.RSI_LENGTH}']
                if pd.notna(rsi_value) and rsi_value > self.RSI_OVERBOUGHT:
                    rsi_ok = False
            
            # <<<--- PERUBAHAN: Cek Kondisi Volume ---
            volume_ok = True
            if self.USE_VOLUME_FILTER:
                volume_ma = last.get('volume_ma')
                if pd.isna(volume_ma) or last['volume'] < (volume_ma * self.VOLUME_FACTOR):
                    volume_ok = False

            # Tambahkan `volume_ok` ke dalam kondisi final
            if is_in_support_zone and is_reclaimed and is_bullish_candle and rsi_ok and volume_ok:
                stop_loss = last['low'] - (atr_value * self.SL_ATR_BUFFER)
                risk_distance = entry_price - stop_loss
                if risk_distance <= 0: return None
                take_profit = entry_price + (risk_distance * self.RISK_REWARD_RATIO)
                
                reason = f"Reversal dari Support HTF ({support_zone:.4f}) + Volume"
                return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        # --- CEK SINYAL SHORT DI ZONA RESISTANCE ---
        if resistance_zone:
            is_in_resistance_zone = last['high'] >= resistance_zone
            is_rejected = last['close'] < resistance_zone
            is_bearish_candle = last['close'] < last['open']
            
            rsi_ok = True
            if self.USE_RSI_FILTER:
                rsi_value = last[f'RSI_{self.RSI_LENGTH}']
                if pd.notna(rsi_value) and rsi_value < self.RSI_OVERSOLD:
                    rsi_ok = False
            
            # <<<--- PERUBAHAN: Cek Kondisi Volume ---
            volume_ok = True
            if self.USE_VOLUME_FILTER:
                volume_ma = last.get('volume_ma')
                if pd.isna(volume_ma) or last['volume'] < (volume_ma * self.VOLUME_FACTOR):
                    volume_ok = False

            # Tambahkan `volume_ok` ke dalam kondisi final
            if is_in_resistance_zone and is_rejected and is_bearish_candle and rsi_ok and volume_ok:
                stop_loss = last['high'] + (atr_value * self.SL_ATR_BUFFER)
                risk_distance = stop_loss - entry_price
                if risk_distance <= 0: return None
                take_profit = entry_price - (risk_distance * self.RISK_REWARD_RATIO)

                reason = f"Rejection dari Resistance HTF ({resistance_zone:.4f}) + Volume"
                return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': reason, 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None