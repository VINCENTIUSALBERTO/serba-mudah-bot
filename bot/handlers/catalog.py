"""Handlers for browsing the product catalog."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.database import ensure_user, fetch_catalog, fetch_product, get_available_stock, get_user_balance
from bot.utils.keyboards import catalog_keyboard, product_detail_keyboard

logger = logging.getLogger(__name__)


async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the list of active products."""
    query = update.callback_query
    await query.answer()

    ensure_user(query.from_user.id, query.from_user.username)
    balance = get_user_balance(query.from_user.id)
    context.user_data["balance"] = balance

    products = fetch_catalog()
    stock_map = {p["id"]: get_available_stock(p["id"]) for p in products}
    if not products:
        await query.edit_message_text("😔 Belum ada produk yang tersedia saat ini.")
        return

    text = (
        "👤 *User Profile*\n"
        f"Nama: {query.from_user.name}\n"
        f"Saldo: Rp {balance:,}\n\n"
       "🛒 *Katalog Produk*\nPilih produk yang ingin kamu beli: ")

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=catalog_keyboard(products, stock_map),
    )


async def product_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show details for a specific product."""
    query = update.callback_query
    await query.answer()

    ensure_user(query.from_user.id, query.from_user.username)
    balance = get_user_balance(query.from_user.id)
    context.user_data["balance"] = balance

    product_id = int(query.data.split("_")[1])
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    available = get_available_stock(product_id)
    quantity = max(1, context.user_data.setdefault("quantities", {}).get(product_id, 1))
    if available > 0:
        quantity = min(quantity, available)
    context.user_data.setdefault("quantities", {})[product_id] = quantity

    total_price = int(product["price"]) * quantity
    stock_line = "Stok: ❌ Habis" if available <= 0 else f"Stok tersedia: {available}"

    text = (
        "👤 *User Profile*\n"
        f"Nama: {query.from_user.name}\n"
        f"Saldo: Rp {balance:,}\n\n"
        f"📦 *{product['name']}*\n\n"
        f"💰 Harga: Rp {product['price']:,}\n"
        f"📝 Deskripsi: {product.get('description', '-')}\n"
        f"{stock_line}\n"
        f"Jumlah: {quantity}\n"
        f"Total: Rp {total_price:,}\n\n"
        "Atur jumlah lalu pilih metode pembayaran."
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=product_detail_keyboard(product_id, quantity, available, total_price),
    )


async def _update_quantity(
    update: Update, context: ContextTypes.DEFAULT_TYPE, delta: int
) -> None:
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    product = fetch_product(product_id)
    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    available = get_available_stock(product_id)
    quantities = context.user_data.setdefault("quantities", {})
    current = max(1, quantities.get(product_id, 1))
    balance = get_user_balance(query.from_user.id)

    if available <= 0:
        quantities[product_id] = 1
        text = (
            "👤 *User Profile*\n"
            f"Nama: {query.from_user.name}\n"
            f"Saldo: Rp {balance:,}\n\n"
            f"📦 *{product['name']}*\n\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"📝 Deskripsi: {product.get('description', '-')}\n"
            "Stok: ❌ Habis\n\n"
            "Silakan pilih produk lain atau kembali ke katalog."
        )
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=product_detail_keyboard(product_id, 1, available, int(product["price"])),
        )
        return

    new_qty = current + delta
    if new_qty < 1:
        await query.answer("Jumlah minimal 1.", show_alert=True)
        new_qty = 1
    elif new_qty > available:
        await query.answer("Stok tidak mencukupi untuk jumlah tersebut.", show_alert=True)
        new_qty = available

    quantities[product_id] = new_qty

    context.user_data["balance"] = balance
    total_price = int(product["price"]) * new_qty
    stock_line = "Stok: ❌ Habis" if available <= 0 else f"Stok tersedia: {available}"

    text = (
        "👤 *User Profile*\n"
        f"Nama: {query.from_user.name}\n"
        f"Saldo: Rp {balance:,}\n\n"
        f"📦 *{product['name']}*\n\n"
        f"💰 Harga: Rp {product['price']:,}\n"
        f"📝 Deskripsi: {product.get('description', '-')}\n"
        f"{stock_line}\n"
        f"Jumlah: {new_qty}\n"
        f"Total: Rp {total_price:,}\n\n"
        "Atur jumlah lalu pilih metode pembayaran."
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=product_detail_keyboard(product_id, new_qty, available, total_price),
    )


async def increase_quantity_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Increase purchase quantity."""
    await _update_quantity(update, context, 1)


async def decrease_quantity_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Decrease purchase quantity."""
    await _update_quantity(update, context, -1)


async def stockout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inform user when stock is empty."""
    query = update.callback_query
    await query.answer("Stok produk ini habis. Silakan pilih produk lain.", show_alert=True)
