"""Admin-only handlers (approve / reject orders)."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import ADMIN_IDS
from bot.database import (
    add_product,
    fetch_all_products,
    soft_delete_product,
    update_order_status,
    update_product_fields,
)

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def admin_approve_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Approve an order (admin only)."""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
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

    if not is_admin(query.from_user.id):
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
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    # Placeholder — extend with real DB aggregation as needed
    await update.message.reply_text(
        "📊 *Statistik Bot*\n\n_(Fitur ini akan segera ditambahkan.)_",
        parse_mode="Markdown",
    )


def _parse_pipe_args(raw: str, expected_parts: int) -> list[str] | None:
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < expected_parts:
        return None
    return parts


async def add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: add new product using pipe-separated args."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    if not update.message or not update.message.text:
        return

    if len(update.message.text.split(" ", 1)) < 2:
        await update.message.reply_text("Format: /add_product Nama Produk|Harga|Deskripsi")
        return

    payload = update.message.text.split(" ", 1)[1]
    parts = _parse_pipe_args(payload, 3)
    if not parts:
        await update.message.reply_text("Format: /add_product Nama Produk|Harga|Deskripsi")
        return

    name, price_str, description = parts[0], parts[1], parts[2]
    try:
        price = int(price_str)
    except ValueError:
        await update.message.reply_text("Harga harus berupa angka. Contoh: /add_product Netflix 50000|Akun shared")
        return

    product = add_product(name=name, price=price, description=description)
    await update.message.reply_text(
        f"✅ Produk baru ditambahkan (ID {product['id']}): {product['name']} — Rp {product['price']:,}"
    )


async def edit_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: edit product price/description."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    if not update.message or not update.message.text:
        return

    tokens = update.message.text.split(" ", 2)
    if len(tokens) < 3:
        await update.message.reply_text("Format: /edit_product <product_id> Harga|Deskripsi")
        return

    try:
        product_id = int(tokens[1])
    except ValueError:
        await update.message.reply_text("product_id harus berupa angka.")
        return

    parts = _parse_pipe_args(tokens[2], 1)
    if not parts:
        await update.message.reply_text("Format: /edit_product <product_id> Harga|Deskripsi")
        return

    updates: dict = {}
    if parts[0]:
        try:
            updates["price"] = int(parts[0])
        except ValueError:
            await update.message.reply_text("Harga harus berupa angka.")
            return
    if len(parts) > 1 and parts[1] != "":
        updates["description"] = parts[1]

    if not updates:
        await update.message.reply_text("Tidak ada perubahan yang diberikan.")
        return

    product = update_product_fields(product_id, **updates)
    if not product:
        await update.message.reply_text("❌ Produk tidak ditemukan.")
        return

    await update.message.reply_text(
        f"✏️ Produk ID {product_id} diperbarui.\n"
        f"Harga: Rp {product.get('price', 0):,}\n"
        f"Deskripsi: {product.get('description', '-')}"
    )


async def delete_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: soft delete (inactivate) a product."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Format: /delete_product <product_id>")
        return

    try:
        product_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("product_id harus berupa angka.")
        return

    product = soft_delete_product(product_id)
    if not product:
        await update.message.reply_text("❌ Produk tidak ditemukan.")
        return

    await update.message.reply_text(f"🗑️ Produk ID {product_id} di-nonaktifkan.")


async def list_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: list all products including inactive ones."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    products = fetch_all_products()
    if not products:
        await update.message.reply_text("Belum ada produk.")
        return

    lines = ["📦 *Daftar Produk* (termasuk nonaktif):\n"]
    for p in products:
        status = "Aktif ✅" if p.get("is_active") else "Nonaktif ⛔"
        lines.append(
            f"• ID {p['id']}: {p['name']} — Rp {p['price']:,} ({status})\n  {p.get('description', '-')}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
