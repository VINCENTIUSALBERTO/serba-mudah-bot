"""Admin-only handlers (approve / reject orders)."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from bot.config import ADMIN_IDS
from bot.database import (
    add_product,
    bulk_insert_accounts,
    fetch_all_products,
    fetch_order,
    fetch_product,
    soft_delete_product,
    update_order_status,
    update_product_fields,
)
from bot.handlers.order import _deliver_account

logger = logging.getLogger(__name__)

(
    ADD_PRODUCT_NAME,
    ADD_PRODUCT_PRICE,
    ADD_PRODUCT_DESC,
    ADD_PRODUCT_ACCOUNTS,
) = range(4)


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
    order = fetch_order(order_id)
    if not order:
        await query.edit_message_text("❌ Pesanan tidak ditemukan.")
        return

    product = order.get("products") or fetch_product(order.get("product_id"))

    if order.get("status") == "delivered":
        await query.edit_message_text("Pesanan sudah dikirim ke user.")
        return

    update_order_status(order_id, "approved")

    await query.edit_message_text(
        f"✅ Pesanan #{order_id} telah *disetujui*.",
        parse_mode="Markdown",
    )

    if product:
        await _deliver_account(context, order, product, refund_on_fail=False)


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
    order = fetch_order(order_id)
    update_order_status(order_id, "rejected")

    await query.edit_message_text(
        f"❌ Pesanan #{order_id} telah *ditolak*.",
        parse_mode="Markdown",
    )

    if order:
        try:
            await context.bot.send_message(
                chat_id=order["user_id"], text=f"❌ Pesanan #{order_id} ditolak oleh admin."
            )
        except Exception:  # pragma: no cover
            logger.warning("Failed to notify user about rejection for order %s", order_id)


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


async def add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin: start interactive flow to add a product."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return ConversationHandler.END

    context.user_data["add_product"] = {}
    await update.message.reply_text("🆕 Nama produk?")
    return ADD_PRODUCT_NAME


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture price from admin."""
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Nama produk tidak boleh kosong. Coba lagi.")
        return ADD_PRODUCT_NAME
    context.user_data.setdefault("add_product", {})["name"] = name
    await update.message.reply_text("💰 Harga produk? (angka)")
    return ADD_PRODUCT_PRICE


async def add_product_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture product description."""
    try:
        price = int((update.message.text or "").replace(".", "").replace(",", "").strip())
    except ValueError:
        await update.message.reply_text("Harga harus berupa angka. Coba lagi.")
        return ADD_PRODUCT_PRICE

    context.user_data.setdefault("add_product", {})["price"] = price
    await update.message.reply_text("📝 Deskripsi produk?")
    return ADD_PRODUCT_DESC


async def add_product_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for account stock lines."""
    description = (update.message.text or "").strip()
    context.user_data.setdefault("add_product", {})["description"] = description
    await update.message.reply_text(
        "📧 Kirim akun (satu per baris) dengan format `email:pass`.\n"
        "Akun akan otomatis dikirim ke pembeli setelah pembayaran berhasil.",
        parse_mode="Markdown",
    )
    return ADD_PRODUCT_ACCOUNTS


async def finalize_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create product and stock from collected answers."""
    accounts_raw = update.message.text or ""
    accounts = [line.strip() for line in accounts_raw.splitlines() if line.strip()]
    data = context.user_data.get("add_product") or {}
    if not data.get("name") or not data.get("price"):
        await update.message.reply_text("Data tidak lengkap, silakan ulangi /add_product.")
        return ConversationHandler.END

    product = add_product(
        name=data["name"],
        price=int(data["price"]),
        description=data.get("description"),
    )
    try:
        inserted = bulk_insert_accounts(product["id"], accounts)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to insert accounts for product %s: %s", product["id"], exc)
        inserted = []

    await update.message.reply_text(
        f"✅ Produk baru ditambahkan (ID {product['id']}): {product['name']} — Rp {product['price']:,}\n"
        f"Stok akun tersimpan: {len(inserted)}"
    )
    context.user_data.pop("add_product", None)
    return ConversationHandler.END


async def cancel_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel add product flow."""
    context.user_data.pop("add_product", None)
    await update.message.reply_text("❌ Penambahan produk dibatalkan.")
    return ConversationHandler.END


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

    await update.message.reply_text(f"🗑️ Produk ID {product_id} dinonaktifkan.")


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
