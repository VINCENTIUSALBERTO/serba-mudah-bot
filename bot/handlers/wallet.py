"""Wallet & balance related handlers."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import PAYMENT_CHANNEL_ID
from bot.database import (
    attach_topup_proof,
    create_topup_request,
    ensure_user,
    fetch_payment_methods,
    fetch_topup,
    get_user_balance,
    increment_user_balance,
    update_topup_status,
)
from bot.handlers.order import PAYMENT_INFO
from bot.utils.auth import is_admin
from bot.utils.formatting import format_currency as _format_currency
from bot.utils.keyboards import (
    admin_topup_keyboard,
    main_menu_keyboard,
    topup_amount_keyboard,
    topup_cancel_keyboard,
    topup_type_keyboard,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
TOPUP_TYPE_SELECTION = 0
WAITING_TOPUP_AMOUNT = 1
WAITING_TOPUP_PROOF = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_payment_methods_text() -> str:
    """Build a formatted string listing all active payment methods."""
    methods = fetch_payment_methods()
    if not methods:
        return PAYMENT_INFO

    lines = ["💳 *Metode Pembayaran yang Tersedia*\n"]
    for m in methods:
        lines.append(f"🏦 *{m['provider_name']}*")
        lines.append(f"  No. Rekening: `{m['account_number']}`")
        lines.append(f"  Atas Nama: {m['account_holder']}\n")
    lines.append(
        "Silakan transfer ke salah satu rekening di atas, "
        "kemudian kirimkan bukti pembayaran."
    )
    return "\n".join(lines)


def _get_qris_file_ids() -> list[str]:
    """Return Telegram file_ids for active payment methods that have a QRIS image."""
    methods = fetch_payment_methods()
    return [m["qris_file_id"] for m in methods if m.get("qris_file_id")]


# ---------------------------------------------------------------------------
# Balance command
# ---------------------------------------------------------------------------


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /balance or /saldo to show user's balance."""
    user = update.effective_user
    ensure_user(user.id, user.username)
    balance = get_user_balance(user.id)
    context.user_data["balance"] = balance
    await update.message.reply_text(f"💰 Saldo kamu: {_format_currency(balance)}")


# ---------------------------------------------------------------------------
# Top-up conversation entry points
# ---------------------------------------------------------------------------


async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry from /topup command — show top-up type selection."""
    user = update.effective_user
    ensure_user(user.id, user.username)
    await update.message.reply_text(
        "💰 *Top Up Saldo*\n\nPilih metode top up yang kamu inginkan:",
        parse_mode="Markdown",
        reply_markup=topup_type_keyboard(),
    )
    return TOPUP_TYPE_SELECTION


async def topup_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry from main-menu 'Top Up Saldo' button — show top-up type selection."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    ensure_user(user.id, user.username)
    await query.edit_message_text(
        "💰 *Top Up Saldo*\n\nPilih metode top up yang kamu inginkan:",
        parse_mode="Markdown",
        reply_markup=topup_type_keyboard(),
    )
    return TOPUP_TYPE_SELECTION


# ---------------------------------------------------------------------------
# Top-up type selection
# ---------------------------------------------------------------------------


async def topup_auto_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Auto Top Up' — show Coming Soon message and end conversation."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🤖 *Top Up Otomatis*\n\n"
        "Fitur ini belum tersedia saat ini.\n"
        "Silakan gunakan *Top Up Manual* untuk melanjutkan top up.\n\n"
        "_Coming soon!_ 🚀",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Kembali ke Menu", callback_data="main_menu")]]
        ),
    )
    return ConversationHandler.END


async def topup_manual_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Manual Top Up' — ask user to choose / enter nominal."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💵 *Top Up Manual*\n\n"
        "Pilih nominal top up dari daftar berikut, atau ketik nominalmu sendiri "
        "(contoh: `75000` atau `75K`):",
        parse_mode="Markdown",
        reply_markup=topup_amount_keyboard(),
    )
    return WAITING_TOPUP_AMOUNT


# ---------------------------------------------------------------------------
# Amount selection
# ---------------------------------------------------------------------------


async def topup_quick_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a quick-amount button (e.g. topup_amount_50000)."""
    query = update.callback_query
    await query.answer()
    amount = int(query.data.split("_")[2])
    return await _process_topup_amount(update, context, amount, via_callback=True)


async def topup_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle free-text nominal input for manual top-up."""
    text = (update.message.text or "").strip()
    # Normalise common shorthand: trailing K / RB (case-insensitive)
    normalised = text.replace(".", "").replace(",", "")
    upper = normalised.upper()
    if upper.endswith("RB"):
        normalised = upper[:-2] + "000"
    elif upper.endswith("K"):
        normalised = upper[:-1] + "000"
    else:
        normalised = upper
    try:
        amount = int(normalised)
    except ValueError:
        await update.message.reply_text(
            "❌ Format tidak valid. Masukkan nominal dalam angka, contoh: `50000` atau `50K`.",
            parse_mode="Markdown",
            reply_markup=topup_amount_keyboard(),
        )
        return WAITING_TOPUP_AMOUNT

    if amount < 1_000:
        await update.message.reply_text(
            "❌ Nominal minimal top up adalah Rp 1.000.",
            reply_markup=topup_amount_keyboard(),
        )
        return WAITING_TOPUP_AMOUNT

    return await _process_topup_amount(update, context, amount, via_callback=False)


async def _process_topup_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    amount: int,
    *,
    via_callback: bool,
) -> int:
    """Create the top-up request, show payment instructions, and request proof."""
    user = update.effective_user
    topup = create_topup_request(user.id, amount)
    context.user_data["pending_topup_id"] = topup["id"]

    payment_text = _build_payment_methods_text()
    qris_file_ids = _get_qris_file_ids()

    instruction_text = (
        f"🧾 *Permintaan Top Up #{topup['id']}*\n"
        f"�� Nominal: *{_format_currency(amount)}*\n\n"
        f"{payment_text}\n\n"
        "📸 Kirimkan bukti transfer (foto/file/teks) untuk diproses admin."
    )

    if via_callback:
        query = update.callback_query
        # Send QRIS photo(s) as separate message(s) if available
        for file_id in qris_file_ids:
            await context.bot.send_photo(
                chat_id=user.id,
                photo=file_id,
                caption="📱 Scan QRIS berikut untuk pembayaran",
            )
        await query.edit_message_text(
            instruction_text,
            parse_mode="Markdown",
            reply_markup=topup_cancel_keyboard(),
        )
    else:
        for file_id in qris_file_ids:
            await update.message.reply_photo(
                photo=file_id,
                caption="📱 Scan QRIS berikut untuk pembayaran",
            )
        await update.message.reply_text(
            instruction_text,
            parse_mode="Markdown",
            reply_markup=topup_cancel_keyboard(),
        )

    return WAITING_TOPUP_PROOF


# ---------------------------------------------------------------------------
# Proof submission
# ---------------------------------------------------------------------------


async def receive_topup_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle uploaded transfer proof and notify admin channel."""
    topup_id = context.user_data.get("pending_topup_id")
    if not topup_id:
        await update.message.reply_text(
            "Tidak ada permintaan top-up yang menunggu. Gunakan /topup dulu."
        )
        return ConversationHandler.END

    proof_message_id = update.message.message_id
    attach_topup_proof(topup_id, proof_message_id)

    await update.message.reply_text(
        f"✅ Bukti transfer diterima untuk top-up #{topup_id}.\n"
        "Admin akan memverifikasi dan memproses top-up kamu secepatnya."
    )

    if PAYMENT_CHANNEL_ID:
        topup = fetch_topup(topup_id)
        await _notify_admin_topup(
            context,
            update.effective_user.id,
            update.effective_user.username,
            topup_id,
            int(topup.get("amount", 0)) if topup else 0,
            proof_message_id=proof_message_id,
        )

    context.user_data.pop("pending_topup_id", None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


async def cancel_topup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the pending top-up flow via /cancel command."""
    context.user_data.pop("pending_topup_id", None)
    user = update.effective_user
    await update.message.reply_text(
        "❌ Proses top-up dibatalkan.",
        reply_markup=main_menu_keyboard(is_admin=is_admin(user.id)),
    )
    return ConversationHandler.END


async def cancel_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the pending top-up flow via inline 'Batal' button."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_topup_id", None)
    await query.edit_message_text(
        "❌ Proses top-up dibatalkan.",
        reply_markup=main_menu_keyboard(is_admin=is_admin(query.from_user.id)),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Admin notification helpers
# ---------------------------------------------------------------------------


async def _notify_admin_topup(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str | None,
    topup_id: int,
    amount: int,
    proof_message_id: int | None = None,
) -> None:
    """Send a notification to the admin channel for approval."""
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


# ---------------------------------------------------------------------------
# Admin top-up approve / reject callbacks
# ---------------------------------------------------------------------------


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
            await query.edit_message_caption(caption="ℹ️ Top-up sudah diproses.")
        else:
            await query.edit_message_text(text="ℹ️ Top-up sudah diproses.")
        return

    updated_user = increment_user_balance(topup["user_id"], int(topup.get("amount", 0)))
    update_topup_status(topup_id, "approved")

    confirmation = (
        f"✅ Top-up #{topup_id} disetujui.\n"
        f"Saldo baru: {_format_currency(int(updated_user.get('balance', 0)))}"
    )
    if query.message.photo or query.message.document:
        await query.edit_message_caption(caption=confirmation, parse_mode="Markdown")
    else:
        await query.edit_message_text(confirmation, parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=topup["user_id"],
            text=(
                f"✅ Top-up kamu sebesar {_format_currency(int(topup.get('amount', 0)))} sudah disetujui.\n"
                f"Saldo sekarang: {_format_currency(int(updated_user.get('balance', 0)))}"
            ),
        )
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to notify user for top-up approval: %s", exc)

    if PAYMENT_CHANNEL_ID:
        try:
            user_label = (
                f"@{topup.get('username')}"
                if topup.get("username")
                else f"User ID: {topup.get('user_id')}"
            )
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


# ---------------------------------------------------------------------------
# Admin: direct balance addition
# ---------------------------------------------------------------------------


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
            text=(
                f"Saldo kamu diupdate oleh admin. "
                f"Saldo sekarang: {_format_currency(int(updated_user.get('balance', 0)))}"
            ),
        )
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to notify user for admin balance update: %s", exc)
