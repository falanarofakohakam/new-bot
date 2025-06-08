import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Import dari file-file lain dalam proyek
import config
import handlers
from strategies import AVAILABLE_STRATEGIES # Penting: Import ini memicu pemuatan strategi

# ==============================================================================
# SETUP LOGGING DASAR
# ==============================================================================
# Mengatur format pesan log agar informatif
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# FUNGSI UTAMA (MAIN)
# ==============================================================================
def main() -> None:
    """
    Fungsi utama untuk menginisialisasi, mengkonfigurasi, dan menjalankan bot.
    """
    
    # 1. Membuat Aplikasi Bot
    logger.info("Membangun aplikasi bot...")
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    # 2. Inisialisasi 'database' sementara bot (bot_data)
    #    Digunakan untuk menyimpan cache, daftar chat autoscan, dll.
    app.bot_data.setdefault('top_symbols_cache', {})
    app.bot_data.setdefault('last_signal_time', {})
    app.bot_data.setdefault('autoscan_chats', set())
    app.bot_data.setdefault('forwardtest_data', {'active': False, 'open_trades': [], 'closed_trades': []})

    # 3. Mendaftarkan Semua Handler
    logger.info("Mendaftarkan handlers...")
    
    # Handler untuk Tombol Inline (CallbackQuery)
    # Ini menangani SEMUA penekanan tombol di seluruh bot.
    app.add_handler(CallbackQueryHandler(handlers.button_callback_handler))

    # Handler untuk Perintah Manual
    # Ini berfungsi sebagai alternatif jika pengguna lebih suka mengetik.
    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("menu", handlers.start)) # Alias untuk memanggil menu
    app.add_handler(CommandHandler("analyze", handlers.analyze_handler))
    app.add_handler(CommandHandler("backtest", handlers.backtest_handler))
    app.add_handler(CommandHandler("multibacktest", handlers.multibacktest_handler))
    app.add_handler(CommandHandler("forwardtest", handlers.forwardtest_handler))
    app.add_handler(CommandHandler("order", handlers.order_handler))
    
    # 4. Memberi tahu di log bahwa bot siap dijalankan
    logger.info("="*50)
    logger.info(f"MEMUAT {len(AVAILABLE_STRATEGIES)} STRATEGI: {list(AVAILABLE_STRATEGIES.keys())}")
    logger.info("BOT TRADING (MULTI-STRATEGI) TELAH DIMULAI")
    logger.info("="*50)
    
    # 5. Menjalankan Bot
    # Bot akan terus berjalan dan memeriksa update (pesan/tombol baru)
    app.run_polling()

if __name__ == "__main__":
    # Blok ini memastikan fungsi main() hanya dijalankan saat script ini dieksekusi secara langsung
    main()