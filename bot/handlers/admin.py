"""Admin-only handlers (approve / reject orders)."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ADMIN_IDS
from bot.database import update_order_status

logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def admin_approve_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Approve an order (admin only)."""
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Kamu bukan admin.", show_alert=True)
        return

    order_id = int(query.data.split("_")[2])
    update_order_status(order_id, "approved")

    await query.edit_message_text(
        f"✅ Pesanan #{order_id} telah *disetujui*.",
        parse_mode="Markdown",
    )


async def admin_reject_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Reject an order (admin only)."""
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Kamu bukan admin.", show_alert=True)
        return

    order_id = int(query.data.split("_")[2])
    update_order_status(order_id, "rejected")

    await query.edit_message_text(
        f"❌ Pesanan #{order_id} telah *ditolak*.",
        parse_mode="Markdown",
    )


async def admin_stats_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /stats — show a quick summary (admin only)."""
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    # Placeholder — extend with real DB aggregation as needed
    await update.message.reply_text(
        "📊 *Statistik Bot*\n\n_(Fitur ini akan segera ditambahkan.)_",
        parse_mode="Markdown",
    )
