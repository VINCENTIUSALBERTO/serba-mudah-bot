"""Wallet & balance related handlers."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import PAYMENT_CHANNEL_ID
from bot.database import (
    attach_topup_proof,
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

WAITING_TOPUP_PROOF = 1


def _format_currency(amount: int) -> str:
    return f"Rp {amount:,}"


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /balance or /saldo to show user's balance."""
    user = update.effective_user
    ensure_user(user.id, user.username)
    balance = get_user_balance(user.id)
    context.user_data["balance"] = balance
    await update.message.reply_text(f"💰 Saldo kamu: {_format_currency(balance)}")


async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create a manual top-up request and ask for proof."""
    user = update.effective_user
    ensure_user(user.id, user.username)

    if not context.args:
        await update.message.reply_text("Gunakan format: /topup <nominal>. Contoh: /topup 50000")
        return ConversationHandler.END

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Nominal harus berupa angka. Contoh: /topup 50000")
        return ConversationHandler.END

    if amount <= 0:
        await update.message.reply_text("Nominal top-up harus lebih besar dari 0.")
        return ConversationHandler.END

    topup = create_topup_request(user.id, amount)
    context.user_data["pending_topup_id"] = topup["id"]

    await update.message.reply_text(
        f"🧾 Permintaan top-up #{topup['id']} dibuat.\n\n{PAYMENT_INFO}\n\n"
        "Balas dengan bukti transfer (foto/file) untuk diproses admin.",
        parse_mode="Markdown",
    )
    return WAITING_TOPUP_PROOF


async def receive_topup_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle uploaded transfer proof and notify admin."""
    topup_id = context.user_data.get("pending_topup_id")
    if not topup_id:
        await update.message.reply_text("Tidak ada permintaan top-up yang menunggu. Gunakan /topup dulu.")
        return ConversationHandler.END

    proof_message_id = update.message.message_id
    attach_topup_proof(topup_id, proof_message_id)

    await update.message.reply_text(
        f"✅ Bukti transfer diterima untuk top-up #{topup_id}. Admin akan memverifikasi secara manual."
    )

    if PAYMENT_CHANNEL_ID:
        await _notify_admin_topup(
            context,
            update.effective_user.id,
            update.effective_user.username,
            topup_id,
            fetch_topup(topup_id).get("amount", 0),
            proof_message_id=proof_message_id,
        )

    context.user_data.pop("pending_topup_id", None)
    return ConversationHandler.END


async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the pending top-up request flow."""
    context.user_data.pop("pending_topup_id", None)
    await update.message.reply_text("❌ Proses top-up dibatalkan.")
    return ConversationHandler.END


async def _notify_admin_topup(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str | None,
    topup_id: int,
    amount: int,
    proof_message_id: int | None = None,
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
        if proof_message_id:
            await context.bot.copy_message(
                chat_id=PAYMENT_CHANNEL_ID,
                from_chat_id=user_id,
                message_id=proof_message_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=admin_topup_keyboard(topup_id),
            )
        else:
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
        if query.message.photo or query.message.document:
            # Gunakan ini jika pesannya berupa gambar/dokumen (berisi caption)
            await query.edit_message_caption(caption="ℹ️ Top-up sudah diproses.")
        else:
            # Gunakan ini jika pesannya hanya teks biasa
            await query.edit_message_text(text="ℹ️ Top-up sudah diproses.")
        return

    updated_user = increment_user_balance(topup["user_id"], int(topup.get("amount", 0)))
    update_topup_status(topup_id, "approved")

    confirmation = (
        f"✅ Top-up #{topup_id} disetujui.\nSaldo baru: {_format_currency(int(updated_user.get('balance', 0)))}"
    )
    if query.message.photo or query.message.document:
        await query.edit_message_caption(caption=confirmation, parse_mode="Markdown")
    else:
        await query.edit_message_text(confirmation, parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=topup["user_id"],
            text=f"✅ Top-up kamu sudah disetujui.\nSaldo sekarang: {_format_currency(int(updated_user.get('balance', 0)))}",
        )
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to notify user for top-up approval: %s", exc)

    if PAYMENT_CHANNEL_ID:
        try:
            user_label = f"@{topup.get('username')}" if topup.get("username") else f"User ID: {topup.get('user_id')}"
            await context.bot.send_message(
                chat_id=PAYMENT_CHANNEL_ID,
                text=(
                    f"✅ Top-up #{topup_id} *disetujui* oleh admin.\n"
                    f"👤 {user_label}\n"
                    f"💰 Nominal: {_format_currency(int(topup.get('amount', 0)))}\n"
                    f"Saldo akhir: {_format_currency(int(updated_user.get('balance', 0)))}"
                ),
                parse_mode="Markdown",
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to notify channel for top-up approval: %s", exc)


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
        if query.message.photo or query.message.document:
            await query.edit_message_caption(caption="ℹ️ Top-up sudah diproses.")
        else:
            await query.edit_message_text("ℹ️ Top-up sudah diproses.")
        return

    update_topup_status(topup_id, "rejected")
    if query.message.photo or query.message.document:
        await query.edit_message_caption(
            caption=f"❌ Top-up #{topup_id} ditolak.", parse_mode="Markdown"
        )
    else:
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
