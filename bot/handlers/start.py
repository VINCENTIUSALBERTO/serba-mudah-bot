"""Handler for the /start command and main-menu navigation."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.utils.keyboards import main_menu_keyboard, help_keyboard

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "👋 Selamat datang di *Serba Mudah Bot*!\n\n"
    "Kami menyediakan akun premium dengan harga terjangkau.\n"
    "Pilih menu di bawah untuk memulai:"
)

HELP_TEXT = (
    "ℹ️ *Bantuan*\n\n"
    "• Ketik /start untuk membuka menu utama.\n"
    "• Pilih *Katalog Produk* untuk melihat daftar akun premium.\n"
    "• Pilih *Pesanan Saya* untuk melihat riwayat pembelian.\n\n"
    "Untuk pertanyaan lebih lanjut, hubungi admin kami."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command — show the main menu."""
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return the user to the main menu from an inline button."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        WELCOME_TEXT,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help text."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        HELP_TEXT,
        parse_mode="Markdown",
        reply_markup=help_keyboard(),
    )
