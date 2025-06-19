import pandas as pd
import pandas_ta as ta

from strategies.base_strategy import BaseStrategy
import utils

class BreakoutV4Strategy(BaseStrategy):
    name = "v4_breakout_v2"
    description = "Breakout v2: Searah tren HTF dengan Risk Management berbasis struktur."

    # --- PARAMETER SPESIFIK STRATEGI INI ---
    HTF_TIMEFRAME = '1h'
    LTF_TIMEFRAME = '15m'
    ADX_LENGTH = 14
    ADX_THRESHOLD = 22.0
    EMA_LENGTH_HTF = 50
    VOLUME_MA_LENGTH = 20
    VOLUME_FACTOR = 1.2
    LOOKBACK_PERIOD_LTF = 20
    RSI_LENGTH = 14
    RSI_BULL_CONFIRM = 55.0
    RSI_BEAR_CONFIRM = 45.0
    ATR_LENGTH = 14
    RISK_REWARD_RATIO = 3
    
    # <<<--- PERUBAHAN PARAMETER MANAJEMEN RISIKO ---
    # Mengganti ATR_MULTIPLIER dengan SL_BUFFER_ATR_MULTIPLIER untuk kejelasan
    # Ini adalah buffer DI BAWAH/ATAS struktur yang ditembus
    SL_BUFFER_ATR_MULTIPLIER = 0.5

    def check_signal(self, symbol: str, df_ltf: pd.DataFrame) -> dict | None:
        # 1. Cek Trend di Higher Timeframe (HTF)
        df_htf = utils.fetch_klines(symbol, self.HTF_TIMEFRAME, limit=200)
        if len(df_htf) < self.EMA_LENGTH_HTF: return None
        
        df_htf.ta.adx(length=self.ADX_LENGTH, append=True)
        df_htf.ta.ema(length=self.EMA_LENGTH_HTF, append=True)
        
        last_htf = df_htf.iloc[-1]
        if pd.isna(last_htf[f'ADX_{self.ADX_LENGTH}']) or pd.isna(last_htf[f'EMA_{self.EMA_LENGTH_HTF}']): return None
        if last_htf[f'ADX_{self.ADX_LENGTH}'] < self.ADX_THRESHOLD: return None
        htf_trend = 'BULLISH' if last_htf['close'] > last_htf[f'EMA_{self.EMA_LENGTH_HTF}'] else 'BEARISH'

        # 2. Analisa sinyal pada df_ltf yang diberikan
        if len(df_ltf) < self.LOOKBACK_PERIOD_LTF + 1: return None
        
        df_ltf.ta.rsi(length=self.RSI_LENGTH, append=True)
        df_ltf.ta.atr(length=self.ATR_LENGTH, append=True)
        df_ltf['vol_ma'] = df_ltf['volume'].rolling(self.VOLUME_MA_LENGTH).mean()

        c1 = df_ltf.iloc[-1]
        atr_value = c1[f'ATRr_{self.ATR_LENGTH}']
        if pd.isna(atr_value) or atr_value == 0 or pd.isna(c1['vol_ma']): return None
        
        lookback_df = df_ltf.iloc[-self.LOOKBACK_PERIOD_LTF-1:-1]
        recent_high, recent_low = lookback_df['high'].max(), lookback_df['low'].min()

        is_volume_spike = c1['volume'] > self.VOLUME_FACTOR * c1['vol_ma']
        entry_price = c1['close']
        
        # --- LOGIKA SINYAL LONG ---
        if htf_trend == 'BULLISH':
            is_breakout_up = c1['close'] > recent_high
            is_bullish_momentum = c1[f'RSI_{self.RSI_LENGTH}'] > self.RSI_BULL_CONFIRM
            is_green_candle = c1['close'] > c1['open']
            
            if is_volume_spike and is_breakout_up and is_bullish_momentum and is_green_candle:
                # <<<--- PERUBAHAN UTAMA: Perhitungan SL & TP ---
                # Stop Loss ditempatkan di bawah level resistance yang ditembus (recent_high)
                stop_loss = recent_high - (atr_value * self.SL_BUFFER_ATR_MULTIPLIER)
                
                risk_distance = entry_price - stop_loss
                if risk_distance <= 0: return None # Validasi agar SL tidak di atas entry
                
                take_profit = entry_price + (risk_distance * self.RISK_REWARD_RATIO)
                # <<<--- AKHIR PERUBAHAN ---
                
                return {'symbol': symbol, 'signal': 'LONG', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': f"Breakout R {recent_high:.4f} (HTF Bullish)", 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        # --- LOGIKA SINYAL SHORT ---
        if htf_trend == 'BEARISH':
            is_breakdown_down = c1['close'] < recent_low
            is_bearish_momentum = c1[f'RSI_{self.RSI_LENGTH}'] < self.RSI_BEAR_CONFIRM
            is_red_candle = c1['close'] < c1['open']

            if is_volume_spike and is_breakdown_down and is_bearish_momentum and is_red_candle:
                # <<<--- PERUBAHAN UTAMA: Perhitungan SL & TP ---
                # Stop Loss ditempatkan di atas level support yang ditembus (recent_low)
                stop_loss = recent_low + (atr_value * self.SL_BUFFER_ATR_MULTIPLIER)
                
                risk_distance = stop_loss - entry_price
                if risk_distance <= 0: return None # Validasi agar SL tidak di bawah entry
                
                take_profit = entry_price - (risk_distance * self.RISK_REWARD_RATIO)
                # <<<--- AKHIR PERUBAHAN ---
                
                return {'symbol': symbol, 'signal': 'SHORT', 'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit, 'reason': f"Breakdown S {recent_low:.4f} (HTF Bearish)", 'risk_reward_ratio': self.RISK_REWARD_RATIO}

        return None