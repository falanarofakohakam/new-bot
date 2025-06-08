from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    Kelas dasar abstrak untuk semua strategi trading.
    Setiap strategi harus mewarisi kelas ini dan mengimplementasikan metodenya.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nama unik untuk strategi."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Deskripsi singkat tentang cara kerja strategi."""
        pass

    @abstractmethod
    def check_signal(self, symbol: str) -> dict | None:
        """
        Metode utama untuk memeriksa sinyal trading pada satu simbol.

        Args:
            symbol (str): Simbol pair yang akan dianalisis (misal: 'BTCUSDT').

        Returns:
            dict | None: Sebuah dictionary berisi detail sinyal jika ditemukan,
                         atau None jika tidak ada sinyal.
                         Contoh dict: {'symbol': 'BTCUSDT', 'signal': 'LONG', ...}
        """
        pass