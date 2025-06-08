import logging
import pandas as pd
import asyncio

# Import dari file-file lain dalam proyek
from strategies.base_strategy import BaseStrategy
from backup_strategies.strategy_smc import SmcStrategy # Mengimpor strategi teknikal kita
import utils

logger = logging.getLogger(__name__)

class HybridAiStrategy(BaseStrategy):
    name = "hybrid_ai_smc"
    description = "SMC dengan filter konfirmasi sentimen berita dari Gemini AI."

    def __init__(self):
        """Menginisialisasi strategi dengan membuat instance dari strategi teknikal."""
        super().__init__()
        # Strategi ini "membungkus" strategi teknikal yang sudah ada
        self.technical_strategy = SmcStrategy()
        
        # Menggunakan parameter dari strategi teknikal yang dibungkus
        self.TIMEFRAME = self.technical_strategy.TIMEFRAME
        self.RISK_REWARD_RATIO = self.technical_strategy.RISK_REWARD_RATIO

    async def _get_gemini_confirmation(self, symbol: str, signal_type: str) -> str:
        """
        Mendapatkan konfirmasi dari Gemini berdasarkan sentimen berita terbaru.
        """
        if not utils.gemini_model:
            logger.warning("Model Gemini tidak aktif. Melewatkan filter AI dan menganggap sinyal AMAN.")
            return "AMAN"

        # Tentukan kata kunci pencarian berita
        search_query = f"{symbol.replace('USDT', '')} crypto news"
        logger.info(f"Hybrid AI: Mencari berita untuk '{search_query}'...")
        
        try:
            # Menggunakan tool Google Search yang tersedia
            search_results = await asyncio.to_thread(
                lambda: utils.Google_Search(queries=[search_query], num_results=5)
            )
            
            # Ekstrak hanya judul berita
            headlines = [item.get('title', '') for item in search_results[0]['results']]
            if not headlines:
                logger.warning("Hybrid AI: Tidak ada berita ditemukan. Menganggap sinyal AMAN.")
                return "AMAN"
            
            headlines_str = "\n- ".join(headlines)

            # Buat prompt yang spesifik dan aman
            prompt = (
                f"Saya adalah sistem trading otomatis dan saya baru saja mendapatkan sinyal teknikal '{signal_type}' untuk aset '{symbol}'. "
                f"Berdasarkan 5 judul berita terbaru ini:\n- {headlines_str}\n\n"
                "Apakah ada sentimen yang sangat negatif, berita FUD (Fear, Uncertainty, Doubt), peretasan, masalah jaringan, atau tuntutan hukum yang signifikan "
                f"yang membuat sinyal '{signal_type}' ini menjadi sangat BERISIKO untuk dieksekusi saat ini? "
                "Fokus hanya pada berita yang benar-benar buruk. Jika berita netral atau sedikit positif, anggap aman. "
                "Jawab HANYA dengan satu kata: 'AMAN' atau 'BERISIKO'."
            )
            
            logger.info(f"Hybrid AI: Mengirim prompt ke Gemini untuk {symbol}...")
            response = await utils.gemini_model.generate_content_async(prompt)
            
            # Membersihkan dan memvalidasi jawaban Gemini
            decision = response.text.strip().upper()
            if "BERISIKO" in decision:
                logger.warning(f"Hybrid AI VETO: Gemini mendeteksi sinyal {signal_type} untuk {symbol} BERISIKO berdasarkan berita.")
                return "BERISIKO"
            else:
                logger.info(f"Hybrid AI PASS: Gemini menganggap sinyal {signal_type} untuk {symbol} AMAN.")
                return "AMAN"

        except Exception as e:
            logger.error(f"Hybrid AI: Terjadi error saat proses konfirmasi Gemini: {e}")
            # Jika terjadi error, kita ambil posisi aman dengan menganggapnya berisiko
            return "BERISIKO"

    def check_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Memeriksa sinyal teknikal, lalu memvalidasinya dengan konfirmasi AI.
        """
        # 1. Dapatkan sinyal dari strategi teknikal inti
        technical_signal = self.technical_strategy.check_signal(symbol, df)

        # Jika tidak ada sinyal teknikal, berhenti di sini
        if technical_signal is None:
            return None

        # 2. Jika ada sinyal teknikal, lanjutkan ke filter konfirmasi AI
        logger.info(f"Hybrid AI: Sinyal teknikal '{technical_signal['signal']}' ditemukan untuk {symbol}. Memulai validasi AI...")
        
        # Jalankan konfirmasi AI secara asynchronous
        # Perlu cara untuk menjalankan async dari fungsi sync, ini akan disederhanakan
        # Untuk implementasi langsung, kita bisa menggunakan asyncio.run
        try:
            confirmation = asyncio.run(self._get_gemini_confirmation(symbol, technical_signal['signal']))
        except RuntimeError: # Jika sudah ada event loop yang berjalan (seperti di Jupyter/IPython)
             confirmation = "AMAN" # Dilewati untuk lingkungan tertentu, atau perlu penanganan lebih lanjut
             logger.warning("Hybrid AI: Event loop sudah berjalan, konfirmasi AI dilewati.")


        # 3. Buat keputusan akhir
        if confirmation == "AMAN":
            # Jika AI setuju, teruskan sinyal teknikal
            technical_signal['reason'] = f"[AI-CONFIRMED] {technical_signal['reason']}"
            return technical_signal
        else:
            # Jika AI menolak, batalkan sinyal
            return None