# handlers.py

import logging
import asyncio
import concurrent.futures
from datetime import timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from binance.exceptions import BinanceAPIException

# Import dari file-file lain dalam proyek
import config
import utils
import features
from strategies import AVAILABLE_STRATEGIES # Mengimpor kamus strategi yang sudah dimuat

logger = logging.getLogger(__name__)

# ==============================================================================
# FUNGSI UNTUK MEMBANGUN MENU TOMBOL
# ==============================================================================

def build_main_menu() -> InlineKeyboardMarkup:
    """Membangun keyboard menu utama."""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Scan Sinyal", callback_data='scan_menu'),
            InlineKeyboardButton("🧐 Analisa Pair", callback_data='analyze_prompt')
        ],
        [
            InlineKeyboardButton("📊 Multi Backtest", callback_data='multibacktest_prompt'),
            InlineKeyboardButton("📈 Backtest Tunggal", callback_data='backtest_prompt')
        ],
        [
            InlineKeyboardButton("🔔 Auto Scan", callback_data='autoscan_menu'),
            InlineKeyboardButton("📝 Forward Test", callback_data='forwardtest_status')
        ],
        [
            InlineKeyboardButton("🚨 Real Order", callback_data='order_prompt')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_strategy_menu(command_prefix: str) -> InlineKeyboardMarkup:
    """Membangun menu pilihan strategi secara dinamis untuk scan atau backtest."""
    keyboard = []
    # Buat baris tombol, maksimal 2 tombol per baris
    row = []
    for name, strategy_instance in AVAILABLE_STRATEGIES.items():
        button_label = strategy_instance.name.replace('_', ' ').title()
        button = InlineKeyboardButton(f"📈 {button_label}", callback_data=f'{command_prefix}{name}')
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: # Tambahkan sisa tombol jika jumlahnya ganjil
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='main_menu')])
    return InlineKeyboardMarkup(keyboard)

def build_autoscan_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> InlineKeyboardMarkup:
    """Membangun keyboard menu untuk Auto Scan."""
    autoscan_chats = context.bot_data.get('autoscan_chats', set())
    button_text, callback_data = ("❌ Nonaktifkan Auto Scan", 'autoscan_stop') if chat_id in autoscan_chats else ("✅ Aktifkan Auto Scan", 'autoscan_start')
    keyboard = [
        [InlineKeyboardButton(button_text, callback_data=callback_data)],
        [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# HANDLER UTAMA (START & TOMBOL)
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim atau mengedit pesan untuk menampilkan menu utama."""
    user = update.effective_user
    text = "Menu Utama Bot Trading v4.5. Silakan pilih fitur:"
    
    # Cek apakah interaksi berasal dari klik tombol atau perintah /start
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=build_main_menu())
        except Exception as e:
            logger.warning(f"Gagal edit pesan menu: {e}. Mengirim pesan baru.")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=build_main_menu())
    else:
        await update.message.reply_html(rf"Halo, {user.mention_html()}! Selamat datang.", reply_markup=build_main_menu())

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani semua aksi dari penekanan tombol inline."""
    query = update.callback_query
    await query.answer()
    action = query.data

    # --- Navigasi Menu ---
    if action == 'main_menu':
        await start(update, context)

    elif action == 'scan_menu':
        await query.edit_message_text("Pilih strategi untuk melakukan Scan:", reply_markup=build_strategy_menu('run_scan_'))

    elif action == 'backtest_prompt':
        await query.edit_message_text("Pilih strategi untuk Backtest Tunggal:", reply_markup=build_strategy_menu('prompt_backtest_'))

    elif action == 'multibacktest_prompt':
        await query.edit_message_text("Pilih strategi untuk Multi Backtest:", reply_markup=build_strategy_menu('prompt_multibacktest_'))
    
    # --- Eksekusi Aksi dari Menu ---
    elif action.startswith('run_scan_'):
        await run_scan_action(query, context, action)

    elif action.startswith('prompt_backtest_') or action.startswith('prompt_multibacktest_'):
        await prompt_for_backtest_params(query, context, action)

    elif action == 'analyze_prompt':
        await query.message.reply_text("Ketik perintah analisa:\nContoh: `/analyze BTCUSDT ETHUSDT`")
    
    elif action == 'order_prompt':
        await query.message.reply_text("BAHAYA! Fitur ini untuk order sungguhan.\nKetik perintah jika yakin:\nContoh: `/order BTCUSDT BUY 0.01`")

    # --- Menu Auto Scan & Forward Test ---
    elif action == 'autoscan_menu':
        await query.edit_message_text("Pengaturan Auto Scan:", reply_markup=build_autoscan_menu(context, query.message.chat_id))
    
    elif action == 'autoscan_start':
        await manage_autoscan(context, query, start_job=True)

    elif action == 'autoscan_stop':
        await manage_autoscan(context, query, start_job=False)

    elif action == 'forwardtest_status':
        await forwardtest_handler(update, context, from_button=True)

# ==============================================================================
# FUNGSI LOGIKA AKSI TOMBOL (Agar button_callback_handler tetap bersih)
# ==============================================================================

async def run_scan_action(query, context, action):
    """
    Fungsi yang dieksekusi saat tombol strategi scan ditekan.
    ALUR BARU: Langsung mencari dan menampilkan sinyal live tanpa backtest/ranking.
    """
    strategy_name = action.replace('run_scan_', '')
    strategy_instance = AVAILABLE_STRATEGIES.get(strategy_name)
    if not strategy_instance:
        await query.message.reply_text("Strategi tidak ditemukan.")
        return

    # --- PERUBAHAN: Pesan awal yang lebih sederhana ---
    await query.edit_message_text(
        f"🔍 *Mencari sinyal live* untuk strategi `{strategy_name}` pada {config.TOP_N_SYMBOLS} pair teratas...",
        parse_mode='Markdown'
    )
    
    # === KODE LAMA YANG DINONAKTIFKAN (DIJADIKAN COMMENT) ===
    # # --- LANGKAH 1: Peringkat Koin via Backtest (DINONAKTIFKAN) ---
    # try:
    #     top_5_data = await asyncio.to_thread(
    #         features.find_top_performers,
    #         strategy_instance=strategy_instance,
    #         days=3,
    #         top_n=5
    #     )
    # except Exception as e:
    #     logger.error(f"Gagal saat mencari top performers: {e}")
    #     await query.message.reply_text(f"Terjadi error saat mencari koin terbaik: {e}")
    #     return
    # if not top_5_data:
    #     await query.message.reply_text("Tidak dapat menemukan koin dengan kinerja yang cukup baik dalam 3 hari terakhir.")
    #     await query.message.reply_text("Pilih fitur selanjutnya:", reply_markup=build_main_menu())
    #     return
    # # --- LANGKAH 2: Tampilkan Hasil Peringkat Backtest (DINONAKTIFKAN) ---
    # top_5_symbols_from_ranking = [result['symbol'] for result in top_5_data]
    # ranking_text = f"✅ *Top 5 Koin Performa Terbaik (Backtest 3 Hari)*\n..."
    # await query.message.reply_text(ranking_text, parse_mode='Markdown')
    # === AKHIR KODE LAMA ===

    # --- LOGIKA BARU: LANGSUNG SCAN SEMUA SIMBOL ---
    symbols_to_scan = utils.get_top_symbols(context)
    hits = []
    primary_timeframe = getattr(strategy_instance, 'TIMEFRAME', '15m')
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_symbol = {
            executor.submit(strategy_instance.check_signal, sym, utils.fetch_klines(sym, primary_timeframe, 200)): sym
            for sym in symbols_to_scan # <-- Scan semua simbol, bukan hanya top 5
        }
        for future in concurrent.futures.as_completed(future_to_symbol):
            try:
                result = future.result()
                if result: hits.append(result)
            except Exception as e:
                logger.error(f"Error saat scan live simbol: {e}")

    # --- Tampilkan Hasil Akhir (Sinyal Live) ---
    if not hits:
        await query.message.reply_text(f"Tidak ada sinyal live yang ditemukan saat ini untuk strategi `{strategy_name}`.", parse_mode='Markdown')
    else:
        text = f"🎯 *Sinyal Live Ditemukan (Strategi: `{strategy_name}`)*\n\n"
        for h in hits:
            signal_emoji = "🟢" if h['signal'] == 'LONG' else "🔴"
            rr_ratio = h.get('risk_reward_ratio', 'N/A')
            text += (f"*{h['symbol']}* {signal_emoji} *{h['signal']}*\n"
                     f"📄 *Alasan*: _{h['reason']}_\n➡️ *Entry*: `{h['entry']:.4f}`\n"
                     f"🛡️ *SL*: `{h['stop_loss']:.4f}`\n🎯 *TP*: `{h['take_profit']:.4f}` (R:R {rr_ratio})\n\n")
        await query.message.reply_text(text, parse_mode='Markdown')
    
    # Tampilkan kembali menu utama setelah semua proses selesai
    await query.message.reply_text("Pilih fitur selanjutnya:", reply_markup=build_main_menu())

async def prompt_for_backtest_params(query, context, action):
    """Menyimpan pilihan strategi dan meminta parameter backtest."""
    parts = action.split('_')
    command_type = parts[1]
    strategy_name = '_'.join(parts[2:])
    context.user_data['selected_strategy'] = strategy_name
    prompt_text = f"Strategi '{strategy_name}' dipilih. "
    if command_type == 'backtest':
        prompt_text += "Ketik perintah:\nContoh: `/backtest BTCUSDT 30`"
    else:
        prompt_text += "Ketik perintah:\nContoh: `/multibacktest 30`"
    await query.edit_message_text(prompt_text)

async def manage_autoscan(context, query, start_job: bool):
    """Mengaktifkan atau menonaktifkan auto scan."""
    job_name = 'continuous_scan_job'
    chat_id = query.message.chat_id
    autoscan_chats = context.bot_data.setdefault('autoscan_chats', set())

    if start_job:
        autoscan_chats.add(chat_id)
        if not context.job_queue.get_jobs_by_name(job_name):
            context.job_queue.run_repeating(features.continuous_scan_job, interval=timedelta(minutes=15), first=1, name=job_name)
        text = "✅ *Auto Scan Telah Diaktifkan!*"
    else:
        autoscan_chats.discard(chat_id)
        if not autoscan_chats:
            jobs = context.job_queue.get_jobs_by_name(job_name)
            for job in jobs: job.schedule_removal()
        text = "❌ *Auto Scan Telah Dinonaktifkan.*"
    
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=build_autoscan_menu(context, chat_id))

# ==============================================================================
# HANDLER PERINTAH MANUAL (FALLBACK)
# ==============================================================================

async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Format: `/analyze SYMBOL1 [SYMBOL2]...`"); return
    symbols = [arg.upper() for arg in context.args]
    msg = await update.message.reply_text(f"🧠 Menganalisa {', '.join(symbols)}...")
    timeframes_to_analyze = ['5m', '15m', '30m', '1h', '4h']
    full_analysis_text = ""
    for symbol in symbols:
        analysis_text_for_symbol = f"💎 *Analisa Teknikal untuk {symbol}*\n"
        price_found, all_tf_results = False, {}
        tasks = [asyncio.to_thread(utils.get_technical_analysis, symbol, tf) for tf in timeframes_to_analyze]
        results = await asyncio.gather(*tasks)
        for i, analysis in enumerate(results):
            tf = timeframes_to_analyze[i]
            all_tf_results[tf] = analysis
            if not price_found and 'price' in analysis:
                analysis_text_for_symbol += f"_Harga Saat Ini: `{analysis['price']:.4f}`_\n\n"; price_found = True
        for tf, analysis in all_tf_results.items():
            if 'error' in analysis:
                # Bungkus pesan error dengan backtick ` ` agar aman untuk Markdown
                analysis_text_for_symbol += f"*Timeframe {tf}:* ⚠️ Gagal (`{analysis['error']}`)\n"
                continue
            trend_emoji = "🟢" if "Bullish" in analysis['trend_bias'] else "🔴" if "Bearish" in analysis['trend_bias'] else "⚪️"
            momentum_emoji = "🟢" if "Bullish" in analysis['momentum_bias'] else "🔴" if "Bearish" in analysis['momentum_bias'] else "⚪️"
            strength_emoji = "🔥" if "Trending" in analysis['strength_status'] else "❄️"
            analysis_text_for_symbol += (f"*{tf.upper()}:*\n  {trend_emoji} Trend: *{analysis['trend_bias']}*\n  {momentum_emoji} Momentum: *{analysis['momentum_bias']}* (RSI: {analysis['rsi']:.2f})\n  {strength_emoji} Kekuatan: *{analysis['strength_status']}* (ADX: {analysis['adx']:.2f})\n\n")
        full_analysis_text += analysis_text_for_symbol + "---\n\n"
    if utils.gemini_model and len(symbols) == 1:
        summary_title = "\n\n🤖 *Ringkasan dari Gemini AI:*\n"
        gemini_summary = await utils.get_gemini_summary(full_analysis_text, symbols[0])
        full_analysis_text += summary_title + f"_{gemini_summary}_"
    await msg.edit_text(full_analysis_text, parse_mode='Markdown')

async def backtest_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    strategy_name = context.user_data.get('selected_strategy')
    if not strategy_name:
        await update.message.reply_text("Pilih strategi dari menu `/start` terlebih dahulu."); return
    strategy_instance = AVAILABLE_STRATEGIES.get(strategy_name)
    if not strategy_instance:
        await update.message.reply_text(f"Strategi '{strategy_name}' tidak valid."); return
    if len(context.args) != 2:
        await update.message.reply_text("Format: `/backtest SYMBOL HARI`"); return
    symbol, days_str = context.args[0].upper(), context.args[1]
    try:
        days = int(days_str)
        if not 1 <= days <= 180: await update.message.reply_text("Hari harus antara 1-180."); return
    except ValueError:
        await update.message.reply_text("Jumlah hari harus angka."); return
    await update.message.reply_text(f"⏳ Memulai backtest *{symbol}* dgn strategi *{strategy_name}*...", parse_mode='Markdown')
    try:
        results = await asyncio.to_thread(features.run_backtest, strategy_instance, symbol, days)
        if not results or results.get('total_trades', 0) == 0:
            await update.message.reply_text(f"🚫 Tidak ada sinyal ditemukan.", parse_mode='Markdown'); return
        
        # --- PERUBAHAN DIMULAI DI SINI ---
        rr_ratio = getattr(strategy_instance, 'RISK_REWARD_RATIO', 'N/A')
        
        # Hitung total trade per sisi untuk ditampilkan
        total_long = results.get('long_wins', 0) + results.get('long_losses', 0)
        total_short = results.get('short_wins', 0) + results.get('short_losses', 0)

        text = (f"**Hasil Backtest: `{strategy_instance.name}`**\n"
                f"Periode: {results['period_days']} hari, {results['symbol']}\n\n"
                f"Total Trade: {results['total_trades']}\n"
                f"✅ Menang: {results['wins']}\n"
                f"❌ Kalah: {results['losses']}\n"
                f"📈 Win Rate: *{results['win_rate']:.2f}%*\n"
                f"💰 Profit Factor: *{results.get('profit_factor', 0):.2f}* (R:R {rr_ratio})\n\n"
                f"**Rincian Posisi:**\n"
                f"🟢 Long: {total_long} trade ({results.get('long_wins', 0)} W / {results.get('long_losses', 0)} L)\n"
                f"🔴 Short: {total_short} trade ({results.get('short_wins', 0)} W / {results.get('short_losses', 0)} L)")
        # --- AKHIR PERUBAHAN ---
        
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error saat backtest: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error: {e}")
        
async def multibacktest_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    strategy_name = context.user_data.get('selected_strategy')
    if not strategy_name:
        await update.message.reply_text("Pilih strategi dari menu `/start`."); return
    strategy_instance = AVAILABLE_STRATEGIES.get(strategy_name)
    if not strategy_instance:
        await update.message.reply_text(f"Strategi '{strategy_name}' tidak valid."); return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Format: `/multibacktest JUMLAH_HARI`"); return
    try:
        days = int(context.args[0])
        if not 1 <= days <= 90: await update.message.reply_text("Hari harus antara 1-90."); return
    except ValueError:
        await update.message.reply_text("Jumlah hari harus angka."); return
    await update.message.reply_text(f"⏳ Memulai multi-backtest dgn strategi *{strategy_name}*...", parse_mode='Markdown')
    try:
        results = await asyncio.to_thread(features.run_multi_backtest, strategy_instance, days)
        if results.get('total_trades', 0) == 0:
            await update.message.reply_text("🚫 Tidak ada trade dihasilkan."); return
            
        # --- PERUBAHAN DIMULAI DI SINI ---
        rr_ratio = getattr(strategy_instance, 'RISK_REWARD_RATIO', 'N/A')
        
        # Hitung total trade per sisi untuk ditampilkan
        total_long_trades = results.get('total_long_wins', 0) + results.get('total_long_losses', 0)
        total_short_trades = results.get('total_short_wins', 0) + results.get('total_short_losses', 0)
        
        text = (f"📊 **Hasil Multi-Backtest: `{strategy_instance.name}`**\n"
                f"Periode: {days} hari | Simbol: {results['total_symbols']}\n\n"
                f"🔢 Total Trade: *{results['total_trades']}*\n"
                f"✅ Menang: *{results['wins']}*\n"
                f"❌ Kalah: *{results['losses']}*\n"
                f"📈 Avg Win Rate: *{results['avg_win_rate']:.2f}%*\n"
                f"💰 Agg Profit Factor: *{results['agg_profit_factor']:.2f}* (R:R {rr_ratio})\n\n"
                f"**Rincian Posisi Agregat:**\n"
                f"🟢 Long: {total_long_trades} trade ({results.get('total_long_wins', 0)} W / {results.get('total_long_losses', 0)} L)\n"
                f"🔴 Short: {total_short_trades} trade ({results.get('total_short_wins', 0)} W / {results.get('total_short_losses', 0)} L)\n\n"
                f"**Top 5 Simbol (Win Rate):**\n")
        # --- AKHIR PERUBAHAN ---
        
        for i, res in enumerate(results['symbol_results'][:5]):
            text += f"{i+1}. *{res['symbol']}*: {res['win_rate']:.2f}% ({res['total_trades']} trades, PF: {res.get('profit_factor', 0):.2f})\n"
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error saat multi-backtest: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error: {e}")
        
async def forwardtest_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button: bool = False):
    message_interface = update.callback_query.message if from_button else update.message
    chat_id = message_interface.chat_id
    
    # Menangani kasus ketika dipanggil dari tombol ('status') vs dari perintah
    if from_button:
        action = 'status'
    else:
        action = context.args[0].lower() if context.args else 'status'

    job_name = f'forwardtest_job_{chat_id}' # Job name unik per chat
    ft_data = context.bot_data.setdefault('forwardtest_data', {}).setdefault(chat_id, {'active': False, 'open_trades': [], 'closed_trades': []})
    
    if action == 'start':
        if ft_data['active']:
            await message_interface.reply_text("Forward test sudah aktif untuk chat ini.")
            return
        ft_data.update({'active': True, 'open_trades': [], 'closed_trades': []})
        context.job_queue.run_repeating(features.forwardtest_job, interval=timedelta(minutes=5), first=1, name=job_name, data={'chat_id': chat_id})
        await message_interface.reply_text("✅ *Mode Forward Test Diaktifkan untuk chat ini!*")
    elif action == 'stop':
        if not ft_data['active']:
            await message_interface.reply_text("Forward test tidak aktif untuk chat ini.")
            return
        ft_data['active'] = False
        jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in jobs:
            job.schedule_removal()
        await message_interface.reply_text("❌ *Mode Forward Test Dinonaktifkan untuk chat ini.*")
    elif action == 'status':
        if not ft_data.get('active') and not ft_data.get('closed_trades'):
            await message_interface.reply_text("Mode forward test tidak aktif untuk chat ini.", parse_mode='Markdown')
            return
            
        status_text = "*(Aktif)*" if ft_data.get('active') else "*(Tidak Aktif)*"
        text = f"📊 *Status Forward Test {status_text}*\n\n"
        
        open_trades = ft_data.get('open_trades', [])
        text += f"**Posisi Terbuka ({len(open_trades)})**\n"
        if not open_trades:
            text += "_Tidak ada posisi terbuka._\n"
        else:
            for trade in open_trades:
                text += f"- *{trade['symbol']} ({trade['signal']})* | Entry: `{trade['entry']:.4f}`\n"
        
        closed_trades = ft_data.get('closed_trades', [])
        wins = sum(1 for t in closed_trades if t['status'] == 'WIN')
        losses = len(closed_trades) - wins
        win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0
        
        # Asumsi R:R default jika tidak ada di trade (bisa disesuaikan)
        total_r = sum(t.get('risk_reward_ratio', config.RISK_REWARD_RATIO) for t in closed_trades if t['status'] == 'WIN') - losses
        
        text += f"\n**Hasil ({len(closed_trades)} Trade)**\n✅ Menang: {wins} | ❌ Kalah: {losses}\n"
        text += f"📈 Win Rate: *{win_rate:.2f}%* | 💰 Profit: *{total_r:.2f}R*"
        
        await message_interface.reply_text(text, parse_mode='Markdown')


async def order_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) != 3:
            await update.message.reply_text("Format: `/order SYMBOL SIDE QTY`"); return
        sym, side, qty_str = context.args
        res = utils.binance.futures_create_order(symbol=sym.upper(), side=side.upper(), type='MARKET', quantity=float(qty_str))
        await update.message.reply_text(f"✅ Order berhasil: ID {res['orderId']}", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("Format QTY salah.")
    except BinanceAPIException as e:
        await update.message.reply_text(f"❌ Gagal order: `{e.message}`", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Gagal order: {e}")
        await update.message.reply_text(f"❌ Gagal order: Terjadi error internal.")