"""Order flow handlers (place order, confirm, view history)."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import PAYMENT_CHANNEL_ID
from bot.database import create_order, fetch_product, fetch_user_orders
from bot.utils.keyboards import (
    admin_order_keyboard,
    confirm_order_keyboard,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)

# Payment instructions sent to the buyer after order creation
PAYMENT_INFO = (
    "💳 *Instruksi Pembayaran*\n\n"
    "Silakan transfer ke rekening berikut:\n"
    "• Bank: BCA\n"
    "• No. Rekening: 1234567890\n"
    "• Atas Nama: Serba Mudah\n\n"
    "Setelah transfer, kirim bukti pembayaran kepada admin.\n"
    "Pesanan kamu akan diproses setelah pembayaran dikonfirmasi. ✅"
)


async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask the user to confirm their order."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    text = (
        f"🛒 *Konfirmasi Pesanan*\n\n"
        f"Produk: *{product['name']}*\n"
        f"Harga: Rp {product['price']:,}\n\n"
        "Apakah kamu yakin ingin memesan?"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=confirm_order_keyboard(product_id),
    )


async def confirm_order_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Create the order in Supabase and notify the admin channel."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    user = query.from_user
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    order = create_order(
        user_id=user.id,
        product_id=product_id,
        username=user.username,
    )

    # Notify the buyer
    await query.edit_message_text(
        f"✅ Pesanan #{order['id']} berhasil dibuat!\n\n{PAYMENT_INFO}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )

    # Notify the admin channel (if configured)
    if PAYMENT_CHANNEL_ID:
        user_label = f"@{user.username}" if user.username else f"User ID: {user.id}"
        admin_text = (
            f"🛒 *Pesanan Baru #{order['id']}*\n\n"
            f"👤 User: {user_label}\n"
            f"📦 Produk: {product['name']}\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📋 Status: Pending"
        )
        await context.bot.send_message(
            chat_id=PAYMENT_CHANNEL_ID,
            text=admin_text,
            parse_mode="Markdown",
            reply_markup=admin_order_keyboard(order["id"]),
        )


async def my_orders_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the user their order history."""
    query = update.callback_query
    await query.answer()

    orders = fetch_user_orders(query.from_user.id)

    if not orders:
        await query.edit_message_text(
            "📦 Kamu belum memiliki pesanan.\n\nKembali ke menu utama:",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines = ["📦 *Pesanan Saya*\n"]
    for o in orders:
        product_info = o.get("products") or {}
        product_name = product_info.get("name", "?")
        price = product_info.get("price", 0)
        lines.append(
            f"• Order #{o['id']} — {product_name} "
            f"(Rp {price:,}) — *{o['status'].upper()}*"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
