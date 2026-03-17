"""Handlers for browsing the product catalog."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import fetch_catalog, fetch_product
from bot.utils.keyboards import catalog_keyboard, product_detail_keyboard

logger = logging.getLogger(__name__)


async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the list of active products."""
    query = update.callback_query
    await query.answer()

    products = fetch_catalog()
    if not products:
        await query.edit_message_text("😔 Belum ada produk yang tersedia saat ini.")
        return

    await query.edit_message_text(
        "🛒 *Katalog Produk*\n\nPilih produk yang ingin kamu beli:",
        parse_mode="Markdown",
        reply_markup=catalog_keyboard(products),
    )


async def product_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show details for a specific product."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    text = (
        f"📦 *{product['name']}*\n\n"
        f"💰 Harga: Rp {product['price']:,}\n"
        f"📝 Deskripsi: {product.get('description', '-')}\n\n"
        "Apakah kamu ingin memesan produk ini?"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=product_detail_keyboard(product_id),
    )
