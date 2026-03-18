"""Order flow handlers (place order, confirm, view history)."""

import logging
from urllib.parse import quote_plus

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import PAYMENT_CHANNEL_ID
from bot.database import (
    create_order,
    fetch_order,
    fetch_product,
    fetch_user_orders,
    get_user_balance,
    increment_user_balance,
    reserve_product_account,
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
        "Pilih metode pembayaran:"
    )
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=payment_method_keyboard(product_id),
    )


async def _send_admin_notification(context, user, order, product, payment_method: str | None = None, note: str | None = None):
    """Kirim notifikasi admin tanpa mengubah UX user."""
    try:
        user_label = f"@{user.username}" if user.username else f"User ID: {user.id}"
        admin_text = (
            f"🛒 *Pesanan Baru #{order['id']}*\n\n"
            f"👤 User: {user_label}\n"
            f"📦 Produk: {product['name']}\n"
            f"💰 Harga: Rp {product['price']:,}\n"
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
            reply_markup=admin_order_keyboard(order["id"]),
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
        lines.append(
            f"• Order #{o['id']} — {product_name} "
            f"(Rp {price:,}) — *{o['status'].upper()}*"
        )

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=order_history_keyboard(),
    )


async def _deliver_account(context: ContextTypes.DEFAULT_TYPE, order: dict, product: dict, refund_on_fail: bool = False) -> bool:
    """Reserve an account and deliver it to the user."""
    account = reserve_product_account(product["id"], order.get("id"))
    if not account:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text="⚠️ Stok akun untuk produk ini sedang kosong. Admin akan mengirimkan stok baru secepatnya.",
        )
        update_order_status(order["id"], "waiting_stock")
        if refund_on_fail:
            try:
                increment_user_balance(order["user_id"], int(product.get("price", 0)))
                await context.bot.send_message(
                    chat_id=order["user_id"],
                    text="Saldo kamu dikembalikan karena stok kosong. Kamu bisa mencoba lagi nanti.",
                )
                update_order_status(order["id"], "refunded")
            except Exception as exc:  # pragma: no cover
                logger.error("Failed to refund user %s: %s", order["user_id"], exc)
        return False

    credential = account.get("credential", "-")
    message = (
        "🎁 *Akun kamu siap!*\n\n"
        f"{credential}\n\n"
        "Terima kasih sudah berbelanja. Jangan bagikan data ini ke orang lain."
    )
    await context.bot.send_message(
        chat_id=order["user_id"],
        text=message,
        parse_mode="Markdown",
    )
    update_order_status(order["id"], "delivered")
    return True


async def pay_with_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process payment using user balance."""
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split("_")[2])
    user = query.from_user
    product = fetch_product(product_id)

    if not product:
        await query.edit_message_text("❌ Produk tidak ditemukan.")
        return

    balance = get_user_balance(user.id)
    price = int(product.get("price", 0))
    if balance < price:
        await query.edit_message_text(
            f"❌ Saldo kamu kurang. Harga produk: Rp {price:,}\nSaldo saat ini: Rp {balance:,}\n\n"
            "Silakan top-up saldo terlebih dahulu.",
            parse_mode="Markdown",
        )
        return

    order = create_order(user_id=user.id, product_id=product_id, username=user.username)
    increment_user_balance(user.id, -price, username=user.username)
    update_order_status(order["id"], "paid_balance")

    await query.edit_message_text(
        f"✅ Pembayaran berhasil. Saldo dipotong {price:,}.\nPesanan #{order['id']} diproses otomatis.",
        parse_mode="Markdown",
    )

    delivered = await _deliver_account(context, order, product, refund_on_fail=True)

    if PAYMENT_CHANNEL_ID:
        note = "Pembayaran otomatis dengan saldo. Sudah dikirim." if delivered else "Pembayaran saldo sukses, menunggu stok."
        context.application.create_task(
            _send_admin_notification(context, user, {**order, "status": "paid"}, product, payment_method="Saldo", note=note)
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

    order = create_order(user_id=user.id, product_id=product_id, username=user.username)
    update_order_status(order["id"], "waiting_qris")

    qr_payload = f"ORDER#{order['id']}|{product['name']}|{product.get('price', 0)}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=320x320&data={quote_plus(qr_payload)}"

    text = (
        "💳 *Pembayaran QRIS*\n\n"
        f"📦 {product['name']}\n"
        f"💰 Harga: Rp {int(product.get('price', 0)):,}\n"
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
                {**order, "status": "waiting_qris"},
                product,
                payment_method="QRIS",
                note="Menunggu verifikasi pembayaran QRIS.",
            )
        )
