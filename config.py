# config.py

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
VOLATILITY_THRESHOLD = float(os.getenv('VOLATILITY_THRESHOLD', 0.05))
BACKTEST_WORKERS     = int(os.getenv('BACKTEST_WORKERS', 10))

# Parameter strategi telah dipindahkan ke masing-masing file strategi.

# ==============================================================================
# KONFIGURASI PROXY (OPSIONAL)
# ==============================================================================
# Biarkan `None` jika tidak ingin menggunakan proxy.
# Jika Anda punya proxy, isi dengan format: "proto://user:pass@host:port"
#
# Contoh untuk proxy SOCKS5 dengan autentikasi:
# PROXY_URL = "socks5://user123:passwordxyz@123.45.67.89:1080"
#
# Contoh untuk proxy HTTP gratis tanpa autentikasi:
# PROXY_URL = "http://123.45.67.89:8080"
#
PROXY_URL = None