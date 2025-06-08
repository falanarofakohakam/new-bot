import os
from dotenv import load_dotenv

# Muat variabel dari file .env
load_dotenv()

# ==============================================================================
# KUNCI API & TOKEN (TIDAK BERUBAH)
# ==============================================================================
BINANCE_API_KEY      = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET   = os.getenv('BINANCE_API_SECRET')
TELEGRAM_TOKEN       = os.getenv('TELEGRAM_TOKEN')
GEMINI_API_KEY       = os.getenv('GEMINI_API_KEY')

# ==============================================================================
# PENGATURAN UMUM BOT (TIDAK BERUBAH)
# ==============================================================================
# Pengaturan ini berlaku untuk seluruh bot, bukan untuk strategi spesifik.
TOP_N_SYMBOLS        = int(os.getenv('TOP_N_SYMBOLS', 50))
VOLATILITY_THRESHOLD = float(os.getenv('VOLATILITY_THRESHOLD', 0.01))
BACKTEST_WORKERS     = int(os.getenv('BACKTEST_WORKERS', 4))

# Parameter strategi telah dipindahkan ke masing-masing file strategi.