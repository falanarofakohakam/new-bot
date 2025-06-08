import os
import importlib
import inspect
from .base_strategy import BaseStrategy

# Dictionary untuk menyimpan semua strategi yang ditemukan
# Format: {'nama_strategi': KelasStrategi}
AVAILABLE_STRATEGIES = {}

def load_strategies():
    """Mencari dan memuat semua kelas strategi dari folder ini."""
    
    # Path ke direktori 'strategies' saat ini
    strategy_dir = os.path.dirname(__file__)
    
    # Loop melalui semua file di direktori
    for filename in os.listdir(strategy_dir):
        # Hanya proses file python, bukan __init__.py atau base_strategy.py
        if filename.endswith('.py') and not filename.startswith('__') and not filename.startswith('base_'):
            # Hapus .py untuk mendapatkan nama modul
            module_name = filename[:-3]
            
            # Import modul secara dinamis
            module = importlib.import_module(f'strategies.{module_name}')
            
            # Cari kelas di dalam modul yang merupakan turunan dari BaseStrategy
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if issubclass(cls, BaseStrategy) and cls is not BaseStrategy:
                    # Instansiasi kelas dan simpan
                    instance = cls()
                    AVAILABLE_STRATEGIES[instance.name] = instance
                    print(f"Strategi '{instance.name}' berhasil dimuat.")

# Panggil fungsi load saat package di-import
load_strategies()