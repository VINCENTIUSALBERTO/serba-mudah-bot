"""Handler for the /start command and main-menu navigation."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import ensure_user, get_user_balance
from bot.handlers.admin import is_admin
from bot.utils.keyboards import main_menu_keyboard, help_keyboard

logger = logging.getLogger(__name__)

WELCOME_TITLE = "👋 Selamat datang di *Serba Mudah Bot*!"


def _format_currency(amount: int) -> str:
    return f"Rp {int(amount):,}"


def _user_commands_text(is_admin_user: bool) -> str:
    commands = [
        "• `/start` — Kembali ke menu utama",
        "• `/help` — Lihat semua perintah",
        "• `/balance` atau `/saldo` — Cek saldo",
        "• `/topup <nominal>` — Ajukan top-up saldo",
        "• Menu *Katalog Produk* — Lihat & beli produk",
        "• Menu *Pesanan Saya* — Riwayat pembelian",
    ]
    if is_admin_user:
        commands.append("• `/admin` — Panduan fitur admin")
    return "\n".join(commands)


def _build_start_text(user, balance: int, is_admin_user: bool) -> str:
    username = f"@{user.username}" if user.username else "-"
    admin_note = "\n🛠 Kamu terdaftar sebagai *admin*." if is_admin_user else ""
    return (
        f"{WELCOME_TITLE}\n\n"
        "Kami menyediakan akun premium dengan harga terjangkau. Pilih menu di bawah untuk memulai.\n\n"
        "👤 *Profil*\n"
        f"Nama: {user.full_name}\n"
        f"Username: {username}\n"
        f"Saldo: {_format_currency(balance)}"
        f"{admin_note}\n\n"
        "⚙️ *Perintah utama*\n"
        f"{_user_commands_text(is_admin_user)}\n\n"
        "Gunakan tombol di bawah untuk navigasi cepat."
    )


def _help_text(is_admin_user: bool) -> str:
    extra_admin = "\n\n🛠 *Perintah Admin*\n• /admin — Lihat ringkasan fitur admin" if is_admin_user else ""
    return (
        "ℹ️ *Bantuan*\n\n"
        "Bot jual akun premium dengan proses cepat. Gunakan perintah atau tombol menu berikut:\n\n"
        f"{_user_commands_text(is_admin_user)}"
        f"{extra_admin}\n\n"
        "Butuh bantuan? Hubungi admin melalui tombol di bawah."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command — show the main menu."""
    user = update.effective_user
    ensure_user(user.id, user.username)
    context.user_data["balance"] = get_user_balance(user.id)
    is_admin_user = is_admin(user.id)
    text = _build_start_text(user, context.user_data["balance"], is_admin_user)

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return the user to the main menu from an inline button."""
    query = update.callback_query
    await query.answer()
    balance = context.user_data.get("balance") or get_user_balance(query.from_user.id)
    is_admin_user = is_admin(query.from_user.id)
    await query.edit_message_text(
        _build_start_text(query.from_user, balance, is_admin_user),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
    )


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help text."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _help_text(is_admin(query.from_user.id)),
        parse_mode="Markdown",
        reply_markup=help_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to /help command."""
    user = update.effective_user
    await update.message.reply_text(
        _help_text(is_admin(user.id)),
        parse_mode="Markdown",
        reply_markup=help_keyboard(),
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unknown /commands with friendly feedback."""
    user = update.effective_user
    is_admin_user = is_admin(user.id)
    await update.message.reply_text(
        "❓ Perintah tidak ditemukan.\n\n"
        "Berikut perintah yang tersedia:\n"
        f"{_user_commands_text(is_admin_user)}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin=is_admin_user),
    )
