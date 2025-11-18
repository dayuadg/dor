import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler

# Import fungsi-fungsi dari script asli Anda
from app.service.auth import AuthInstance
from app.client.ciam import get_otp, submit_otp
from app.client.engsel import get_balance, get_profile
from app.menus.util import format_quota_byte

# --- KONFIGURASI ---
BOT_TOKEN = "8366701965:AAELTbEeN8qb4y9d3xrIhiMP918QjGLQpCg"
ADMIN_ID = 7572364238  # Ganti dengan ID Telegram Anda (Cek di @userinfobot)

# State untuk ConversationHandler
PHONE, OTP = range(2)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- HELPER: Cek Otorisasi ---
async def authorized_only(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Bot ini privat. Anda tidak memiliki akses.")
        return False
    return True

# --- COMMAND: /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await authorized_only(update): return
    
    await update.message.reply_text(
        "🤖 **MyXL Bot Interface**\n"
        "Gunakan menu di bawah ini:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔑 Login Akun", callback_data='login_start')],
        [InlineKeyboardButton("💰 Cek Pulsa & Info", callback_data='info')],
        [InlineKeyboardButton("📦 Daftar Paket Saya", callback_data='my_pkg')],
        # Tambahkan menu lain seperti Beli Paket nanti
    ]
    return InlineKeyboardMarkup(keyboard)

# --- FLOW LOGIN (Menggantikan input terminal) ---
async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 Silakan kirim Nomor XL Anda (awalan 628...):")
    return PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = update.message.text.strip()
    
    # Validasi sederhana
    if not phone_number.startswith("62") or not phone_number.isdigit():
        await update.message.reply_text("⚠️ Nomor format salah. Harus angka dan diawali 62. Coba lagi:")
        return PHONE

    # Panggil fungsi asli get_otp dari ciam.py
    try:
        await update.message.reply_text("🔄 Meminta OTP ke server...")
        subscriber_id = get_otp(phone_number)
        
        if subscriber_id:
            context.user_data['phone'] = phone_number
            await update.message.reply_text("✅ OTP Terkirim via SMS.\nSilakan masukkan kode OTP 6 digit:")
            return OTP
        else:
            await update.message.reply_text("❌ Gagal meminta OTP. Pastikan nomor benar.")
            return ConversationHandler.END
            
    except Exception as e:
        await update.message.reply_text(f"Error System: {str(e)}")
        return ConversationHandler.END

async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp_code = update.message.text.strip()
    phone_number = context.user_data.get('phone')
    
    if not otp_code.isdigit() or len(otp_code) != 6:
        await update.message.reply_text("⚠️ OTP harus 6 digit angka. Coba lagi:")
        return OTP

    api_key = AuthInstance.api_key # Ambil API Key yang sudah ada di script
    
    try:
        await update.message.reply_text("🔄 Verifikasi OTP...")
        # Panggil fungsi asli submit_otp
        tokens = submit_otp(api_key, "SMS", phone_number, otp_code)
        
        if tokens:
            # Simpan session menggunakan logika AuthInstance yang ada
            AuthInstance.add_refresh_token(int(phone_number), tokens["refresh_token"])
            await update.message.reply_text(
                f"✅ **Login Berhasil!**\nNomor {phone_number} tersimpan.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            await update.message.reply_text("❌ OTP Salah atau Kadaluarsa.")
            
    except Exception as e:
        await update.message.reply_text(f"Error Login: {str(e)}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operasi dibatalkan.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# --- FITUR: INFO AKUN ---
async def check_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    active_user = AuthInstance.get_active_user()
    if not active_user:
        await query.edit_message_text("⚠️ Belum ada akun login. Silakan login dulu.", reply_markup=main_menu_keyboard())
        return

    try:
        await query.edit_message_text("🔄 Mengambil data...")
        
        tokens = active_user["tokens"]
        api_key = AuthInstance.api_key
        
        # Panggil fungsi asli
        balance_data = get_balance(api_key, tokens["id_token"])
        
        msg = f"👤 **Info Akun**\n"
        msg += f"Nomor: `{active_user['number']}`\n"
        msg += f"Tipe: {active_user['subscription_type']}\n"
        
        if balance_data:
            remaining = balance_data.get("remaining", 0)
            msg += f"💰 Pulsa: Rp {remaining:,}\n"
            msg += f"📅 Exp: {balance_data.get('expired_at', '-')}\n"
        
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=main_menu_keyboard())
        
    except Exception as e:
        await query.edit_message_text(f"Gagal mengambil info: {e}", reply_markup=main_menu_keyboard())

# --- MAIN RUNNER ---
if __name__ == '__main__':
    print("🤖 Bot sedang berjalan...")
    
    # Pastikan API Key ada (Prompt script asli jika belum ada)
    if not AuthInstance.api_key:
        print("❌ API Key belum diset. Jalankan main.py dulu sekali untuk setup key.")
        exit()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handler Login (Conversation)
    login_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(login_start, pattern='^login_start$')],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_otp)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(login_handler)
    application.add_handler(CallbackQueryHandler(check_info, pattern='^info$'))
    
    # Jalankan bot
    application.run_polling()