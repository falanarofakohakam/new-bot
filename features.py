# features.py

import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
import asyncio
import concurrent.futures
from telegram.ext import ContextTypes

# Import dari file-file lain dalam proyek
import config
import utils
from strategies import AVAILABLE_STRATEGIES # Mengimpor kamus strategi yang sudah dimuat

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNGSI-FUNGSI BACKTESTING (GENERIK & STRATEGY-AGNOSTIC)
# ==============================================================================

def run_backtest(strategy_instance, symbol: str, days: int) -> dict | None:
    """
    Menjalankan backtest untuk SATU simbol dengan strategi TERTENTU.
    Fungsi ini sekarang memiliki return value yang konsisten dan detail.
    """
    logger.info(f"Memulai backtest strategi '{strategy_instance.name}' untuk {symbol} selama {days} hari.")
    
    primary_timeframe = getattr(strategy_instance, 'TIMEFRAME', '15m')
    # Hitung jumlah candle yang dibutuhkan berdasarkan durasi hari
    limit = min(days * 24 * (60 // int(primary_timeframe[:-1])), 1500)
    df_full = utils.fetch_klines(symbol, primary_timeframe, limit=limit)
    
    if len(df_full) < 200:
        logger.warning(f"Data tidak cukup untuk backtest {symbol} (kurang dari 200 candle).")
        return None

    trades = []
    # Loop dimulai dari candle ke-200 untuk memastikan ada data histori yang cukup
    for i in range(200, len(df_full)):
        df_slice = df_full.iloc[0:i].copy()
        signal = strategy_instance.check_signal(symbol, df_slice)
        
        if signal:
            current_time = df_full['open_time'].iloc[i]
            # Anti-spam: Mencegah sinyal beruntun dalam interval pendek
            if trades and (current_time - trades[-1]['entry_time'] < timedelta(minutes=int(primary_timeframe[:-1])*4)):
                continue

            entry_price, sl, tp = signal['entry'], signal['stop_loss'], signal['take_profit']
            trade_result = {'symbol': symbol, 'status': 'OPEN', 'entry_time': current_time, 'entry_price': entry_price, 'sl': sl, 'tp': tp, 'signal': signal['signal']}
            
            # Simulasi hasil trade dengan melihat data masa depan
            df_future = df_full.iloc[i:]
            for candle in df_future.itertuples():
                if signal['signal'] == 'LONG':
                    if candle.low <= sl:
                        trade_result.update({'status': 'LOSS', 'exit_time': candle.open_time, 'exit_price': sl}); break
                    elif candle.high >= tp:
                        trade_result.update({'status': 'WIN', 'exit_time': candle.open_time, 'exit_price': tp}); break
                else: # SHORT
                    if candle.high >= sl:
                        trade_result.update({'status': 'LOSS', 'exit_time': candle.open_time, 'exit_price': sl}); break
                    elif candle.low <= tp:
                        trade_result.update({'status': 'WIN', 'exit_time': candle.open_time, 'exit_price': tp}); break
            else:
                # Jika trade tidak ditutup sampai akhir data, tandai sebagai OPEN
                trade_result.update({'status': 'OPEN', 'exit_time': df_full.iloc[-1]['open_time'], 'exit_price': df_full.iloc[-1]['close']})
            
            trades.append(trade_result)
    
    # --- PERUBAHAN DIMULAI DI SINI ---

    # Struktur dictionary default jika tidak ada trade yang selesai
    default_result = {
        'symbol': symbol, 'period_days': days, 'total_trades': 0, 
        'wins': 0, 'losses': 0, 'win_rate': 0, 'profit_factor': 0,
        'long_wins': 0, 'long_losses': 0, 'short_wins': 0, 'short_losses': 0
    }

    if not trades: 
        return default_result

    closed_trades = [t for t in trades if t['status'] in ['WIN', 'LOSS']]
    if not closed_trades:
        default_result['total_trades'] = 0
        return default_result
    
    # Inisialisasi penghitung spesifik LONG/SHORT
    long_wins, long_losses, short_wins, short_losses = 0, 0, 0, 0
    for t in closed_trades:
        if t['signal'] == 'LONG':
            if t['status'] == 'WIN': long_wins += 1
            else: long_losses += 1
        elif t['signal'] == 'SHORT':
            if t['status'] == 'WIN': short_wins += 1
            else: short_losses += 1

    wins = long_wins + short_wins
    losses = long_losses + short_losses
    
    win_rate = wins / len(closed_trades) * 100 if closed_trades else 0
    
    rr = getattr(strategy_instance, 'RISK_REWARD_RATIO', 1.5)
    profit_factor = (wins * rr) / losses if losses > 0 else float('inf')
    
    # Return dengan struktur yang lengkap dan konsisten
    return {
        'symbol': symbol, 
        'period_days': days, 
        'total_trades': len(closed_trades), 
        'wins': wins, 
        'losses': losses, 
        'win_rate': win_rate, 
        'profit_factor': profit_factor,
        'long_wins': long_wins, 
        'long_losses': long_losses,
        'short_wins': short_wins, 
        'short_losses': short_losses
    }

def run_multi_backtest(strategy_instance, days: int) -> dict:
    """Menjalankan backtest untuk BANYAK simbol dengan strategi TERTENTU."""
    # Pass context dummy karena tidak ada interaksi telegram di sini
    symbols = utils.get_top_symbols({'bot_data':{}}) 
    logger.info(f"Memulai multi-backtest strategi '{strategy_instance.name}' untuk {len(symbols)} simbol...")
    
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.BACKTEST_WORKERS) as executor:
        futures = {executor.submit(run_backtest, strategy_instance, sym, days): sym for sym in symbols}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result: all_results.append(result)
            except Exception as e:
                logger.error(f"Error dalam future multi-backtest untuk simbol {futures[future]}: {e}")

    valid_results = [r for r in all_results if r and r.get('total_trades', 0) > 0]
    if not valid_results: 
        return {'total_symbols': len(symbols), 'total_trades': 0}
    
    # --- PERUBAHAN DIMULAI DI SINI ---
    
    total_trades = sum(r['total_trades'] for r in valid_results)
    total_wins = sum(r['wins'] for r in valid_results)
    total_losses = sum(r['losses'] for r in valid_results)

    # Akumulasi statistik LONG/SHORT dari semua simbol
    total_long_wins = sum(r.get('long_wins', 0) for r in valid_results)
    total_long_losses = sum(r.get('long_losses', 0) for r in valid_results)
    total_short_wins = sum(r.get('short_wins', 0) for r in valid_results)
    total_short_losses = sum(r.get('short_losses', 0) for r in valid_results)
    
    avg_win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
    
    rr = getattr(strategy_instance, 'RISK_REWARD_RATIO', 1.5)
    agg_profit_factor = (total_wins * rr) / total_losses if total_losses > 0 else float('inf')
    sorted_results = sorted(valid_results, key=lambda x: x['win_rate'], reverse=True)

    # Return dengan statistik LONG/SHORT yang diagregasi
    return {
        'total_symbols': len(valid_results), 
        'total_trades': total_trades, 
        'wins': total_wins, 
        'losses': total_losses, 
        'avg_win_rate': avg_win_rate, 
        'agg_profit_factor': agg_profit_factor, 
        'symbol_results': sorted_results,
        'total_long_wins': total_long_wins,
        'total_long_losses': total_long_losses,
        'total_short_wins': total_short_wins,
        'total_short_losses': total_short_losses
    }

# ==============================================================================
# FUNGSI BACKGROUND JOBS (AUTO SCAN & FORWARD TEST)
# ==============================================================================

async def continuous_scan_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Job Auto Scan yang disempurnakan.
    ALUR BARU:
    1. Cari sinyal LIVE dari SEMUA strategi.
    2. Jika ada, jalankan backtest 3 hari untuk SETIAP sinyal yang ditemukan.
    3. Ranking sinyal berdasarkan performa backtest.
    4. Kirim notifikasi tunggal berisi maksimal 5 sinyal terbaik.
    """
    logger.info("Auto Scan Job v4.5: Memulai...")
    
    # --- LANGKAH 1: TEMUKAN SEMUA SINYAL LIVE DARI SEMUA STRATEGI ---
    logger.info("Auto Scan: Mencari sinyal live...")
    symbols_to_scan = utils.get_top_symbols(context)
    if not symbols_to_scan: 
        logger.info("Auto Scan Job: Gagal mendapatkan daftar simbol.")
        return

    all_live_signals = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for strategy_name, strategy_instance in AVAILABLE_STRATEGIES.items():
            primary_timeframe = getattr(strategy_instance, 'TIMEFRAME', '15m')
            for symbol in symbols_to_scan:
                # Lampirkan instance strategi ke dalam data yang akan diproses
                future = executor.submit(
                    lambda s=symbol, si=strategy_instance, tf=primary_timeframe: (si, si.check_signal(s, utils.fetch_klines(s, tf, 200)))
                )
                futures.append(future)

        for future in concurrent.futures.as_completed(futures):
            try:
                strategy_instance, result = future.result()
                if result:
                    # Lampirkan instance strategi ke sinyal untuk digunakan nanti
                    result['strategy_instance'] = strategy_instance
                    all_live_signals.append(result)
            except Exception as e:
                logger.error(f"Error saat mencari sinyal live di Auto Scan: {e}")

    if not all_live_signals:
        logger.info("Auto Scan Job: Tidak ada sinyal live yang ditemukan dari semua strategi."); return
    
    logger.info(f"Auto Scan: Ditemukan {len(all_live_signals)} sinyal live. Memulai proses ranking...")

    # --- LANGKAH 2: RANKING SINYAL DENGAN BACKTEST 3 HARI ---
    ranked_signals = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.BACKTEST_WORKERS) as executor:
        future_to_signal = {
            executor.submit(run_backtest, signal['strategy_instance'], signal['symbol'], days=3): signal
            for signal in all_live_signals
        }
        for future in concurrent.futures.as_completed(future_to_signal):
            original_signal = future_to_signal[future]
            try:
                backtest_result = future.result()
                if backtest_result and backtest_result['total_trades'] > 0:
                    # Tambahkan hasil backtest ke dictionary sinyal
                    original_signal.update(backtest_result)
                    ranked_signals.append(original_signal)
            except Exception as e:
                logger.error(f"Error saat menjalankan backtest untuk ranking: {e}")

    if not ranked_signals:
        logger.info("Auto Scan Job: Tidak ada sinyal yang lolos kualifikasi backtest."); return
        
    # --- LANGKAH 3: SORTIR DAN PILIH 5 TERATAS ---
    sorted_signals = sorted(
        ranked_signals, 
        key=lambda x: (x.get('profit_factor', 0), x.get('win_rate', 0)), 
        reverse=True
    )
    top_5_signals = sorted_signals[:5]

    # --- LANGKAH 4: KIRIM NOTIFIKASI TUNGGAL ---
    now = datetime.now()
    last_signals = context.bot_data.setdefault('last_signal_time', {})
    
    # Cek anti-spam untuk sinyal teratas agar tidak mengirim hal yang sama berulang kali
    top_signal_key = top_5_signals[0]['symbol'] + top_5_signals[0]['strategy_instance'].name
    if last_signals.get(top_signal_key) and (now - last_signals.get(top_signal_key) < timedelta(hours=3)):
        logger.info(f"Auto Scan Job: Sinyal teratas {top_signal_key} sudah dikirim belum lama ini. Dilewati.")
        return

    # Buat pesan notifikasi
    message = "🔥 *Top Sinyal Auto Scan (Terbaik dari Semua Strategi)* 🔥\n\n"
    message += "_Sinyal-sinyal berikut adalah sinyal LIVE yang diurutkan berdasarkan performa backtest 3 hari terakhir._\n\n"

    for i, h in enumerate(top_5_signals):
        strategy_instance = h['strategy_instance']
        signal_emoji = "🟢" if h['signal'] == 'LONG' else "🔴"
        rr_ratio = getattr(strategy_instance, 'RISK_REWARD_RATIO', 'N/A')
        reason = f"[{strategy_instance.name.upper()}] {h['reason']}"
        
        message += (
            f"*{i+1}. {h['symbol']}* {signal_emoji} *{h['signal']}*\n"
            f"📄 *Alasan*: _{reason}_\n"
            f"➡️ *Entry*: `{h['entry']:.4f}` | *SL*: `{h['stop_loss']:.4f}` | *TP*: `{h['take_profit']:.4f}` (R:R {rr_ratio})\n"
            f"🚀 *Kinerja 3 Hari*: WR *{h['win_rate']:.1f}%* | PF *{h.get('profit_factor', 0):.2f}* ({h['total_trades']} trade)\n"
            f"-----------------------------------\n"
        )

    # Kirim ke semua chat yang berlangganan
    for chat_id in context.bot_data.get('autoscan_chats', set()):
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Gagal mengirim autoscan ke {chat_id}: {e}")
    
    # Perbarui waktu sinyal terakhir untuk anti-spam
    last_signals[top_signal_key] = now
    logger.info("Auto Scan Job: Notifikasi top 5 sinyal berhasil dikirim.")


async def forwardtest_job(context: ContextTypes.DEFAULT_TYPE):
    """Job untuk paper trading, sekarang juga menggunakan semua strategi."""
    ft_data = context.bot_data.get('forwardtest_data', {})
    if not ft_data.get('active'): return
    
    chat_id = ft_data['chat_id']
    open_trades = ft_data.get('open_trades', [])
    
    # 1. Cek posisi yang sudah terbuka
    still_open = []
    now_utc = datetime.now(timezone.utc)
    for trade in open_trades:
        try:
            price = float(utils.binance.futures_ticker(symbol=trade['symbol'])['lastPrice'])
            closed, result = False, ''
            if trade['signal'] == 'LONG' and (price >= trade['tp'] or price <= trade['sl']):
                closed, result = True, 'WIN' if price >= trade['tp'] else 'LOSS'
            elif trade['signal'] == 'SHORT' and (price <= trade['tp'] or price >= trade['sl']):
                closed, result = True, 'WIN' if price <= trade['tp'] else 'LOSS'
            
            if closed:
                trade.update({'status': result, 'close_time': now_utc, 'close_price': price})
                ft_data.setdefault('closed_trades', []).append(trade)
                emoji = "✅" if result == "WIN" else "❌"
                await context.bot.send_message(chat_id=chat_id, text=f"{emoji} *Forward Test Posisi Ditutup ({result})* untuk {trade['symbol']}", parse_mode='Markdown')
            else:
                still_open.append(trade)
        except Exception as e:
            logger.error(f"Forward test check error untuk {trade['symbol']}: {e}")
            still_open.append(trade)
    ft_data['open_trades'] = still_open

    # 2. Cari sinyal baru dari SEMUA strategi
    symbols_to_scan = utils.get_top_symbols(context)
    for strategy_name, strategy_instance in AVAILABLE_STRATEGIES.items():
        for symbol in symbols_to_scan:
            # Jangan buka posisi baru jika sudah ada posisi untuk simbol yang sama
            if any(t['symbol'] == symbol for t in ft_data['open_trades']):
                continue
            
            primary_timeframe = getattr(strategy_instance, 'TIMEFRAME', '15m')
            df = utils.fetch_klines(symbol, primary_timeframe, 200)
            if df.empty: continue
            
            h = strategy_instance.check_signal(symbol, df)
            if h:
                new_trade = {**h, 'entry_time': now_utc, 'status': 'OPEN'}
                ft_data['open_trades'].append(new_trade)
                signal_emoji = "🟢" if h['signal'] == 'LONG' else "🔴"
                reason = f"[{strategy_name.upper()}] {h['reason']}"
                msg = (f"📈 *Forward Test Posisi Baru Dibuka*\n\n"
                       f"*{h['symbol']}* {signal_emoji} *{h['signal']}*\n"
                       f"📄 *Alasan*: _{reason}_\n"
                       f"➡️ *Entry*: `{h['entry']:.4f}` | SL: `{h['stop_loss']:.4f}`")
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                
# ==============================================================================
# FUNGSI BARU UNTUK PERINGKAT KINERJA KOIN
# ==============================================================================

def find_top_performers(strategy_instance, days: int, top_n: int) -> list[dict]:
    """
    Menjalankan backtest pada banyak simbol untuk menemukan N teratas berdasarkan kinerja.
    
    PERUBAHAN: Sekarang mengembalikan list of dictionary hasil backtest, bukan hanya nama.
    """
    # Pass context dummy karena tidak ada interaksi telegram di sini
    symbols = utils.get_top_symbols({'bot_data':{}}) 
    logger.info(f"Mencari {top_n} koin terbaik dari {len(symbols)} koin selama {days} hari terakhir...")
    
    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.BACKTEST_WORKERS) as executor:
        futures = {executor.submit(run_backtest, strategy_instance, sym, days): sym for sym in symbols}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result and result.get('total_trades', 0) > 0:
                    all_results.append(result)
            except Exception as e:
                logger.error(f"Error dalam future find_top_performers: {e}")

    if not all_results:
        logger.warning("Tidak ada hasil backtest yang valid ditemukan untuk menentukan koin terbaik.")
        return []

    # Urutkan hasil berdasarkan Profit Factor (utama) dan Win Rate (sekunder)
    sorted_results = sorted(
        all_results, 
        key=lambda x: (x.get('profit_factor', 0), x.get('win_rate', 0)), 
        reverse=True
    )

    # Kembalikan seluruh data dari top N performers, bukan hanya nama simbolnya.
    top_performers_data = sorted_results[:top_n]
    
    performer_names = [res['symbol'] for res in top_performers_data]
    logger.info(f"Top {len(performer_names)} koin ditemukan: {performer_names}")
    
    return top_performers_data