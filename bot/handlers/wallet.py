"""Wallet & balance related handlers."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import PAYMENT_CHANNEL_ID
from bot.database import (
    create_topup_request,
    ensure_user,
    fetch_topup,
    get_user_balance,
    increment_user_balance,
    update_topup_status,
)
from bot.handlers.admin import is_admin
from bot.handlers.order import PAYMENT_INFO
from bot.utils.keyboards import admin_topup_keyboard

logger = logging.getLogger(__name__)


def _format_currency(amount: int) -> str:
    return f"Rp {amount:,}"


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /balance or /saldo to show user's balance."""
    user = update.effective_user
    ensure_user(user.id, user.username)
    balance = get_user_balance(user.id)
    context.user_data["balance"] = balance
    await update.message.reply_text(f"💰 Saldo kamu: {_format_currency(balance)}")


async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a manual top-up request."""
    user = update.effective_user
    ensure_user(user.id, user.username)

    if not context.args:
        await update.message.reply_text("Gunakan format: /topup <nominal>. Contoh: /topup 50000")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Nominal harus berupa angka. Contoh: /topup 50000")
        return

    if amount <= 0:
        await update.message.reply_text("Nominal top-up harus lebih besar dari 0.")
        return

    topup = create_topup_request(user.id, amount)

    await update.message.reply_text(
        f"🧾 Permintaan top-up #{topup['id']} dibuat.\n\n{PAYMENT_INFO}\n\n"
        "Setelah transfer, kirim bukti pembayaran dan tunggu konfirmasi admin.",
        parse_mode="Markdown",
    )

    if PAYMENT_CHANNEL_ID:
        await _notify_admin_topup(context, user.id, user.username, topup["id"], amount)


async def _notify_admin_topup(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str | None,
    topup_id: int,
    amount: int,
) -> None:
    """Send a notification to admin channel for approval."""
    try:
        user_label = f"@{username}" if username else f"User ID: {user_id}"
        text = (
            f"💳 *Top-up Baru #{topup_id}*\n\n"
            f"👤 User: {user_label}\n"
            f"💰 Nominal: {_format_currency(amount)}\n"
            f"📋 Status: Pending"
        )
        await context.bot.send_message(
            chat_id=PAYMENT_CHANNEL_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=admin_topup_keyboard(topup_id),
        )
    except Exception as exc:  # pragma: no cover - guard rail
        logger.error("Failed to send admin top-up notification: %s", exc)


async def admin_topup_approve_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Approve a pending top-up and add balance."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Kamu bukan admin.", show_alert=True)
        return

    topup_id = int(query.data.split("_")[2])
    topup = fetch_topup(topup_id)
    if not topup:
        await query.edit_message_text("❌ Top-up tidak ditemukan.")
        return
    if topup.get("status") != "pending":
        await query.edit_message_text("ℹ️ Top-up sudah diproses.")
        return

    updated_user = increment_user_balance(topup["user_id"], int(topup.get("amount", 0)))
    update_topup_status(topup_id, "approved")

    await query.edit_message_text(
        f"✅ Top-up #{topup_id} disetujui.\nSaldo baru: {_format_currency(int(updated_user.get('balance', 0)))}",
        parse_mode="Markdown",
    )

    try:
        await context.bot.send_message(
            chat_id=topup["user_id"],
            text=f"✅ Top-up kamu sudah disetujui.\nSaldo sekarang: {_format_currency(int(updated_user.get('balance', 0)))}",
        )
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to notify user for top-up approval: %s", exc)


async def admin_topup_reject_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Reject a pending top-up."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Kamu bukan admin.", show_alert=True)
        return

    topup_id = int(query.data.split("_")[2])
    topup = fetch_topup(topup_id)
    if not topup:
        await query.edit_message_text("❌ Top-up tidak ditemukan.")
        return
    if topup.get("status") != "pending":
        await query.edit_message_text("ℹ️ Top-up sudah diproses.")
        return

    update_topup_status(topup_id, "rejected")
    await query.edit_message_text(f"❌ Top-up #{topup_id} ditolak.", parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=topup["user_id"],
            text="❌ Top-up kamu ditolak. Silakan hubungi admin jika ada pertanyaan.",
        )
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to notify user for top-up rejection: %s", exc)


async def addsaldo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to add balance directly."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Format: /addsaldo <user_id> <nominal>")
        return

    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("User ID dan nominal harus angka. Contoh: /addsaldo 12345 50000")
        return

    updated_user = increment_user_balance(target_user_id, amount)
    await update.message.reply_text(
        f"✅ Saldo user {target_user_id} ditambah {amount:+,}.\n"
        f"Saldo sekarang: {_format_currency(int(updated_user.get('balance', 0)))}"
    )

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"Saldo kamu diupdate oleh admin. Saldo sekarang: {_format_currency(int(updated_user.get('balance', 0)))}",
        )
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to notify user for admin balance update: %s", exc)
