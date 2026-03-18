"""Order flow handlers (place order, confirm, view history)."""

import logging
from urllib.parse import quote_plus

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.config import PAYMENT_CHANNEL_ID
from bot.database import (
    create_order,
    fetch_order,
    fetch_product,
    fetch_user_orders,
    get_available_stock,
    get_user_balance,
    increment_user_balance,
    reserve_product_accounts,
    update_order_status,
)
from bot.utils.keyboards import (
    admin_order_keyboard,
    main_menu_keyboard,
    order_history_keyboard,
    payment_method_keyboard,
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


def _format_currency(amount: int) -> str:
    return f"Rp {int(amount):,}"


def _get_quantity(context: ContextTypes.DEFAULT_TYPE, product_id: int, default: int = 1) -> int:
    quantity_map = context.user_data.setdefault("quantities", {})
    quantity = quantity_map.get(product_id, default)
    quantity = max(1, int(quantity or 1))
    quantity_map[product_id] = quantity
    return quantity


async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask the user to confirm their order."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[1])
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    available = get_available_stock(product_id)
    if available <= 0:
        await query.edit_message_text("❌ Stok produk ini sedang habis.")
        return

    quantity = _get_quantity(context, product_id)
    if quantity > available:
        quantity = available
        context.user_data.setdefault("quantities", {})[product_id] = quantity

    total_price = int(product["price"]) * quantity
    text = (
        f"🛒 *Konfirmasi Pesanan*\n\n"
        f"Produk: *{product['name']}*\n"
        f"Harga: Rp {product['price']:,}\n"
        f"Jumlah: {quantity}\n"
        f"Total: {_format_currency(total_price)}\n\n"
        "Pilih metode pembayaran:"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_method_keyboard(product_id),
    )


async def _send_admin_notification(
    context,
    user,
    order,
    product,
    payment_method: str | None = None,
    note: str | None = None,
    with_actions: bool = True,
):
    """Kirim notifikasi admin tanpa mengubah UX user."""
    try:
        user_label = f"@{user.username}" if user.username else f"User ID: {user.id}"
        quantity = int(order.get("quantity") or 1)
        total = int(order.get("total_price") or quantity * int(product.get("price", 0)))
        admin_text = (
            f"🛒 *Pesanan Baru #{order['id']}*\n\n"
            f"👤 User: {user_label}\n"
            f"📦 Produk: {product['name']}\n"
            f"💰 Harga: Rp {product['price']:,}\n"
            f"🔢 Jumlah: {quantity}\n"
            f"💵 Total: {_format_currency(total)}\n"
            f"📋 Status: {order.get('status', 'pending').title()}"
        )
        if payment_method:
            admin_text += f"\n💳 Metode: {payment_method}"
        if note:
            admin_text += f"\n📝 Catatan: {note}"
        await context.bot.send_message(
            chat_id=PAYMENT_CHANNEL_ID,
            text=admin_text,
            parse_mode="Markdown",
            reply_markup=admin_order_keyboard(order["id"]) if with_actions else None,
        )
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")


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
        qty = int(o.get("quantity") or 1)
        total = int(o.get("total_price") or price * qty)
        lines.append(
            f"• Order #{o['id']} — {product_name} x{qty} "
            f"(Total {_format_currency(total)}) — *{o['status'].upper()}*"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=order_history_keyboard(),
    )


async def _deliver_account(context: ContextTypes.DEFAULT_TYPE, order: dict, product: dict, refund_on_fail: bool = False) -> bool:
    """Reserve an account and deliver it to the user."""
    price = int(product.get("price", 0))
    quantity = int(order.get("quantity") or 1)
    total_price = price * quantity
    accounts = reserve_product_accounts(product["id"], quantity, order.get("id"))
    if len(accounts) < quantity:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text="⚠️ Stok akun untuk produk ini sedang kosong. Admin akan mengirimkan stok baru secepatnya.",
        )
        update_order_status(order["id"], "waiting_stock")
        if refund_on_fail:
            try:
                increment_user_balance(order["user_id"], total_price)
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text=f"Saldo kamu dikembalikan Rp {total_price:,} karena stok kosong. Kamu bisa mencoba lagi nanti.",
                )
                update_order_status(order["id"], "refunded")
            except Exception as exc:  # pragma: no cover
                logger.error("Failed to refund user %s: %s", order["user_id"], exc)
        return False

    lines = [f"🎁 *Akun kamu siap!* ({quantity} akun)\n"]
    for idx, account in enumerate(accounts, start=1):
        credential = account.get("credential", "-")
        lines.append(f"{idx}. {credential}")
    lines.append("\nTerima kasih sudah berbelanja. Jangan bagikan data ini ke orang lain.")
    message = "\n".join(lines)
    await context.bot.send_message(
        chat_id=order["user_id"],
        text=message,
        parse_mode="Markdown",
    )
    update_order_status(order["id"], "delivered")
    return True


async def pay_with_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prepare confirmation receipt for balance payment."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[2])
    user = query.from_user
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    available = get_available_stock(product_id)
    quantity = _get_quantity(context, product_id)
    if available <= 0:
        await query.edit_message_text("❌ Stok produk ini sedang habis. Silakan pilih produk lain.")
        return
    if quantity > available:
        quantity = min(quantity, available)
        context.user_data.setdefault("quantities", {})[product_id] = quantity

    balance = get_user_balance(user.id)
    price = int(product.get("price", 0))
    total = price * quantity
    if balance < total:
        await query.edit_message_text(
            f"❌ Saldo kamu kurang.\nHarga per akun: {_format_currency(price)}\n"
            f"Jumlah: {quantity}\nTotal: {_format_currency(total)}\nSaldo saat ini: {_format_currency(balance)}\n\n"
            "Silakan top-up saldo terlebih dahulu.",
            parse_mode="Markdown",
        )
        return

    final_balance = balance - total
    text = (
        "🧾 *Konfirmasi Pembayaran Saldo*\n\n"
        f"Produk: *{product['name']}*\n"
        f"Jumlah: {quantity}\n"
        f"Harga satuan: {_format_currency(price)}\n"
        f"Total: {_format_currency(total)}\n\n"
        f"Saldo awal: {_format_currency(balance)}\n"
        f"Terpotong: {_format_currency(total)}\n"
        f"Saldo akhir: {_format_currency(final_balance)}\n\n"
        "Lanjutkan pembayaran?"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Konfirmasi bayar",
                    callback_data=f"confirm_balance_{product_id}_{quantity}",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Batal", callback_data=f"product_{product_id}"
                )
            ],
        ]
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def confirm_balance_payment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Deduct balance and process order after user confirmation."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    product_id = int(parts[2])
    try:
        quantity = int(parts[3])
    except (IndexError, ValueError):
        quantity = _get_quantity(context, product_id)
    quantity = max(1, quantity)

    user = query.from_user
    product = fetch_product(product_id)
    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    available = get_available_stock(product_id)
    if available < quantity:
        await query.edit_message_text(
            f"❌ Stok tidak mencukupi. Stok tersedia: {available}.",
            parse_mode="Markdown",
        )
        return

    balance = get_user_balance(user.id)
    price = int(product.get("price", 0))
    total = price * quantity
    if balance < total:
        await query.edit_message_text(
            f"❌ Saldo kamu kurang. Total {_format_currency(total)}, saldo {_format_currency(balance)}.",
            parse_mode="Markdown",
        )
        return

    order = create_order(
        user_id=user.id,
        product_id=product_id,
        username=user.username,
        quantity=quantity,
        payment_method="Saldo",
        total_price=total,
    )
    increment_user_balance(user.id, -total, username=user.username)
    update_order_status(order["id"], "paid_balance")

    delivered = await _deliver_account(context, {**order, "quantity": quantity}, product, refund_on_fail=True)
    status_line = (
        f"✅ Pembayaran berhasil. Saldo dipotong {_format_currency(total)}.\n"
        f"Pesanan #{order['id']} diproses otomatis."
    )
    await query.edit_message_text(status_line, parse_mode="Markdown")

    if PAYMENT_CHANNEL_ID:
        note = (
            "Pembayaran otomatis dengan saldo. Sudah dikirim."
            if delivered
            else "Pembayaran saldo sukses, menunggu stok."
        )
        context.application.create_task(
            _send_admin_notification(
                context,
                user,
                {**order, "status": "paid_balance", "quantity": quantity, "total_price": total},
                product,
                payment_method="Saldo",
                note=note,
                with_actions=False,
            )
        )


async def pay_with_qris_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send QR code for payment and mark order waiting verification."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[2])
    user = query.from_user
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    available = get_available_stock(product_id)
    quantity = _get_quantity(context, product_id)
    if available <= 0:
        await query.edit_message_text("❌ Stok produk ini sedang habis. Silakan pilih produk lain.")
        return
    if quantity > available:
        await query.edit_message_text(
            f"❌ Stok tidak cukup untuk jumlah tersebut. Stok tersedia: {available}.",
            parse_mode="Markdown",
        )
        return

    total_price = int(product.get("price", 0)) * quantity
    order = create_order(
        user_id=user.id,
        product_id=product_id,
        username=user.username,
        quantity=quantity,
        payment_method="QRIS",
        total_price=total_price,
    )
    update_order_status(order["id"], "waiting_qris")

    qr_payload = f"ORDER#{order['id']}|{product['name']}|{total_price}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=320x320&data={quote_plus(qr_payload)}"

    text = (
        "💳 *Pembayaran QRIS*\n\n"
        f"📦 {product['name']}\n"
        f"🔢 Jumlah: {quantity}\n"
        f"💰 Harga: Rp {int(product.get('price', 0)):,}\n"
        f"💵 Total: {_format_currency(total_price)}\n"
        f"📝 {product.get('description', '-')}\n\n"
        "Scan QR di bawah ini dengan aplikasi pembayaran kamu. "
        "Setelah pembayaran terverifikasi oleh admin, akun akan dikirim otomatis."
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    await context.bot.send_photo(
        chat_id=query.message.chat_id,
        photo=qr_url,
        caption=f"QRIS untuk Order #{order['id']}",
    )

    if PAYMENT_CHANNEL_ID:
        context.application.create_task(
            _send_admin_notification(
                context,
                user,
                {**order, "status": "waiting_qris", "quantity": quantity, "total_price": total_price},
                product,
                payment_method="QRIS",
                note="Menunggu verifikasi pembayaran QRIS.",
            )
        )
