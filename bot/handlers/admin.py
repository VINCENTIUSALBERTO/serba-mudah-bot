"""Admin-only handlers (approve / reject orders, product & payment management)."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from bot.database import (
    add_payment_method,
    add_product,
    bulk_insert_accounts,
    delete_payment_method,
    fetch_all_payment_methods,
    fetch_all_products,
    fetch_order,
    fetch_payment_method,
    fetch_product,
    get_available_stock,
    soft_delete_product,
    update_order_status,
    update_payment_method,
    update_product_fields,
)
from bot.handlers.order import _deliver_account
from bot.utils.auth import is_admin
from bot.utils.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)

(
    ADD_PRODUCT_NAME,
    ADD_PRODUCT_PRICE,
    ADD_PRODUCT_DESC,
    ADD_PRODUCT_ACCOUNTS,
    ADD_STOCK_PRODUCT,
    ADD_STOCK_ACCOUNTS,
    ADD_PAYMENT_PROVIDER,
    ADD_PAYMENT_NUMBER,
    ADD_PAYMENT_HOLDER,
    ADD_PAYMENT_QRIS,
) = range(10)

# Edit-payment conversation uses its own state integers (separate ConversationHandler)
EDIT_PAYMENT_CHOOSE_FIELD = 0
EDIT_PAYMENT_NEW_VALUE = 1


def _admin_help_text() -> str:
    return (
        "🛠 *Menu Admin*\n\n"
        "Perintah dan tombol yang tersedia untuk admin:\n\n"
        "*Produk & Stok*\n"
        "• `/add_product` — Tambah produk baru\n"
        "• `/edit_product` — Ubah harga/deskripsi produk\n"
        "• `/delete_product` — Nonaktifkan produk\n"
        "• `/add_stock` — Tambah stok akun\n"
        "• `/list_products` — Lihat semua produk\n\n"
        "*Metode Pembayaran*\n"
        "• `/add_payment` — Tambah metode pembayaran\n"
        "• `/list_payments` — Lihat semua metode pembayaran\n"
        "• `/edit_payment <id>` — Edit metode pembayaran\n"
        "• `/delete_payment <id>` — Hapus metode pembayaran\n\n"
        "*Lainnya*\n"
        "• `/addsaldo <user_id> <nominal>` — Tambah saldo user\n"
        "• `/stats` — Statistik ringkas\n"
        "• Tombol Approve/Reject pada notifikasi pesanan/top-up\n\n"
        "Gunakan tombol di bawah untuk kembali ke menu utama."
    )


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin-only help, either via /admin or button."""
    if update.message:
        user = update.effective_user
        if not is_admin(user.id):
            await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
            return
        await update.message.reply_text(
            _admin_help_text(),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_admin=True),
        )
        return

    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Kamu bukan admin.", show_alert=True)
        return
    await query.edit_message_text(
        _admin_help_text(),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(is_admin=True),
    )


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
    await update.message.reply_text("🆕 Nama produk? (Ketik /cancel untuk membatalkan)")
    return ADD_PRODUCT_NAME


async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture price from admin."""
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Nama produk tidak boleh kosong. Coba lagi.")
        return ADD_PRODUCT_NAME
    context.user_data.setdefault("add_product", {})["name"] = name
    await update.message.reply_text("💰 Harga produk? (angka)\n/cancel untuk membatalkan")
    return ADD_PRODUCT_PRICE


async def add_product_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture product description."""
    try:
        price = int((update.message.text or "").replace(".", "").replace(",", "").strip())
    except ValueError:
        await update.message.reply_text("Harga harus berupa angka. Coba lagi.")
        return ADD_PRODUCT_PRICE

    context.user_data.setdefault("add_product", {})["price"] = price
    await update.message.reply_text("📝 Deskripsi produk?\n/cancel untuk membatalkan")
    return ADD_PRODUCT_DESC


async def add_product_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for account stock lines."""
    description = (update.message.text or "").strip()
    context.user_data.setdefault("add_product", {})["description"] = description
    await update.message.reply_text(
        "📧 Kirim akun (satu per baris) dengan format `email:pass`.\n"
        "Akun akan otomatis dikirim ke pembeli setelah pembayaran berhasil.\n\n"
        "_Ketik /cancel untuk membatalkan._",
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


async def add_stock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin: start flow to add more stock to an existing product."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return ConversationHandler.END

    context.user_data["add_stock"] = {}
    await update.message.reply_text(
        "🆕 Masukkan ID produk yang ingin ditambah stoknya.\n/cancel untuk membatalkan"
    )
    return ADD_STOCK_PRODUCT


async def add_stock_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture product ID for stock addition."""
    try:
        product_id = int((update.message.text or "").strip())
    except ValueError:
        await update.message.reply_text("ID produk harus berupa angka. Coba lagi.")
        return ADD_STOCK_PRODUCT

    product = fetch_product(product_id)
    if not product:
        await update.message.reply_text("❌ Produk tidak ditemukan. Masukkan ID lain atau /cancel.")
        return ADD_STOCK_PRODUCT

    context.user_data.setdefault("add_stock", {})["product_id"] = product_id
    await update.message.reply_text(
        "📧 Kirim akun baru (satu per baris) dengan format `email:pass`.\n"
        "Ketik /cancel untuk membatalkan.",
        parse_mode="Markdown",
    )
    return ADD_STOCK_ACCOUNTS


async def finalize_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Insert provided accounts as new stock for a product."""
    data = context.user_data.get("add_stock") or {}
    product_id = data.get("product_id")
    if not product_id:
        await update.message.reply_text("Data produk tidak ditemukan. Silakan ulangi /add_stock.")
        return ConversationHandler.END

    accounts_raw = update.message.text or ""
    accounts = [line.strip() for line in accounts_raw.splitlines() if line.strip()]
    if not accounts:
        await update.message.reply_text("Tidak ada akun yang dikirim. /cancel untuk batal atau kirim ulang.")
        return ADD_STOCK_ACCOUNTS

    try:
        inserted = bulk_insert_accounts(product_id, accounts)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to insert new stock for product %s: %s", product_id, exc)
        inserted = []

    new_stock = get_available_stock(product_id)
    await update.message.reply_text(
        f"✅ {len(inserted)} akun baru ditambahkan ke produk ID {product_id}.\n"
        f"Stok tersedia sekarang: {new_stock}"
    )
    context.user_data.pop("add_stock", None)
    return ConversationHandler.END


async def cancel_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel add stock flow."""
    context.user_data.pop("add_stock", None)
    await update.message.reply_text("❌ Penambahan stok dibatalkan.")
    return ConversationHandler.END


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


# ---------------------------------------------------------------------------
# Payment method management
# ---------------------------------------------------------------------------


def _is_image_document(message: Message) -> bool:
    """Return True if the message contains an image document."""
    return bool(
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("image/")
    )


async def add_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin: start interactive flow to add a payment method."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return ConversationHandler.END

    context.user_data["add_payment"] = {}
    await update.message.reply_text(
        "🏦 *Tambah Metode Pembayaran*\n\n"
        "Masukkan nama provider (contoh: BCA, BRI, GoPay, OVO):\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return ADD_PAYMENT_PROVIDER


async def add_payment_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture provider name for new payment method."""
    provider_name = (update.message.text or "").strip()
    if not provider_name:
        await update.message.reply_text("Nama provider tidak boleh kosong. Coba lagi.")
        return ADD_PAYMENT_PROVIDER
    context.user_data.setdefault("add_payment", {})["provider_name"] = provider_name
    await update.message.reply_text(
        f"Nama provider: *{provider_name}*\n\n"
        "Masukkan nomor rekening / nomor e-wallet:\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return ADD_PAYMENT_NUMBER


async def add_payment_holder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture account number for new payment method."""
    account_number = (update.message.text or "").strip()
    if not account_number:
        await update.message.reply_text("Nomor rekening tidak boleh kosong. Coba lagi.")
        return ADD_PAYMENT_NUMBER
    context.user_data.setdefault("add_payment", {})["account_number"] = account_number
    await update.message.reply_text(
        f"No. Rekening: *{account_number}*\n\n"
        "Masukkan nama pemilik rekening:\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return ADD_PAYMENT_HOLDER


async def add_payment_qris(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture account holder name and ask for optional QRIS photo."""
    account_holder = (update.message.text or "").strip()
    if not account_holder:
        await update.message.reply_text("Nama pemilik tidak boleh kosong. Coba lagi.")
        return ADD_PAYMENT_HOLDER
    context.user_data.setdefault("add_payment", {})["account_holder"] = account_holder
    await update.message.reply_text(
        f"Atas Nama: *{account_holder}*\n\n"
        "Upload foto QRIS (opsional). Kirim foto QRIS atau ketik `skip` untuk melewati:\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return ADD_PAYMENT_QRIS


async def finalize_add_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the new payment method (with optional QRIS) to the database."""
    data = context.user_data.get("add_payment") or {}
    if not data.get("provider_name") or not data.get("account_number") or not data.get("account_holder"):
        await update.message.reply_text("Data tidak lengkap. Silakan ulangi /add_payment.")
        return ConversationHandler.END

    qris_file_id: str | None = None

    if update.message.photo:
        # User sent a photo — use the highest-resolution version
        qris_file_id = update.message.photo[-1].file_id
    elif _is_image_document(update.message):
        qris_file_id = update.message.document.file_id
    # If text (e.g. "skip"), qris_file_id remains None

    pm = add_payment_method(
        provider_name=data["provider_name"],
        account_number=data["account_number"],
        account_holder=data["account_holder"],
        qris_file_id=qris_file_id,
    )

    qris_status = "✅ Tersedia" if qris_file_id else "❌ Tidak ada"
    await update.message.reply_text(
        f"✅ Metode pembayaran berhasil ditambahkan (ID {pm['id']}):\n"
        f"• Provider: *{pm['provider_name']}*\n"
        f"• No. Rekening: `{pm['account_number']}`\n"
        f"• Atas Nama: {pm['account_holder']}\n"
        f"• QRIS: {qris_status}",
        parse_mode="Markdown",
    )
    context.user_data.pop("add_payment", None)
    return ConversationHandler.END


async def cancel_add_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel add-payment flow."""
    context.user_data.pop("add_payment", None)
    await update.message.reply_text("❌ Penambahan metode pembayaran dibatalkan.")
    return ConversationHandler.END


async def list_payments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: list all payment methods including inactive ones."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    methods = fetch_all_payment_methods()
    if not methods:
        await update.message.reply_text(
            "Belum ada metode pembayaran.\nGunakan /add_payment untuk menambahkan."
        )
        return

    lines = ["💳 *Daftar Metode Pembayaran*:\n"]
    for m in methods:
        status = "Aktif ✅" if m.get("is_active") else "Nonaktif ⛔"
        qris = "Ada 🖼" if m.get("qris_file_id") else "Tidak ada"
        lines.append(
            f"• ID {m['id']}: *{m['provider_name']}* ({status})\n"
            f"  No. Rekening: `{m['account_number']}`\n"
            f"  Atas Nama: {m['account_holder']}\n"
            f"  QRIS: {qris}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def delete_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: soft-delete (deactivate) a payment method."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Format: /delete_payment <id>")
        return

    try:
        pm_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID harus berupa angka.")
        return

    pm = delete_payment_method(pm_id)
    if not pm:
        await update.message.reply_text("❌ Metode pembayaran tidak ditemukan.")
        return

    await update.message.reply_text(
        f"🗑️ Metode pembayaran ID {pm_id} (*{pm.get('provider_name', '')}*) dinonaktifkan.",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Edit payment method — interactive ConversationHandler
# ---------------------------------------------------------------------------

_EDIT_PAYMENT_FIELDS = {
    "1": ("provider_name", "Nama Provider"),
    "2": ("account_number", "Nomor Rekening"),
    "3": ("account_holder", "Atas Nama"),
    "4": ("qris_file_id", "Foto QRIS"),
}


def _edit_payment_field_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing which field to edit."""
    buttons = [
        [InlineKeyboardButton("1️⃣ Nama Provider", callback_data="epf_1")],
        [InlineKeyboardButton("2️⃣ Nomor Rekening", callback_data="epf_2")],
        [InlineKeyboardButton("3️⃣ Atas Nama", callback_data="epf_3")],
        [InlineKeyboardButton("4️⃣ Foto QRIS", callback_data="epf_4")],
        [InlineKeyboardButton("❌ Batal", callback_data="epf_cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


async def edit_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin: start interactive flow to edit a payment method."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Perintah ini hanya untuk admin.")
        return ConversationHandler.END

    if len(context.args) < 1:
        await update.message.reply_text("Format: /edit_payment <id>")
        return ConversationHandler.END

    try:
        pm_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID harus berupa angka.")
        return ConversationHandler.END

    pm = fetch_payment_method(pm_id)
    if not pm:
        await update.message.reply_text("❌ Metode pembayaran tidak ditemukan.")
        return ConversationHandler.END

    context.user_data["edit_payment"] = {"pm_id": pm_id}
    await update.message.reply_text(
        f"✏️ *Edit Metode Pembayaran ID {pm_id}*\n\n"
        f"• Provider: {pm['provider_name']}\n"
        f"• No. Rekening: `{pm['account_number']}`\n"
        f"• Atas Nama: {pm['account_holder']}\n"
        f"• QRIS: {'Ada 🖼' if pm.get('qris_file_id') else 'Tidak ada'}\n\n"
        "Pilih field yang ingin diubah:",
        parse_mode="Markdown",
        reply_markup=_edit_payment_field_keyboard(),
    )
    return EDIT_PAYMENT_CHOOSE_FIELD


async def edit_payment_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle field selection for edit-payment flow."""
    query = update.callback_query
    await query.answer()

    data = query.data  # e.g. "epf_1", "epf_cancel"
    if data == "epf_cancel":
        context.user_data.pop("edit_payment", None)
        await query.edit_message_text("❌ Edit metode pembayaran dibatalkan.")
        return ConversationHandler.END

    field_key = data.split("_")[1]  # "1", "2", "3", "4"
    if field_key not in _EDIT_PAYMENT_FIELDS:
        await query.answer("Pilihan tidak valid.", show_alert=True)
        return EDIT_PAYMENT_CHOOSE_FIELD

    field_name_db, field_label = _EDIT_PAYMENT_FIELDS[field_key]
    context.user_data.setdefault("edit_payment", {})["field"] = field_name_db

    if field_name_db == "qris_file_id":
        prompt = (
            "Upload foto QRIS baru, atau ketik `hapus` untuk menghapus QRIS yang ada:\n"
            "_Ketik /cancel untuk membatalkan._"
        )
    else:
        prompt = (
            f"Masukkan nilai baru untuk *{field_label}*:\n"
            "_Ketik /cancel untuk membatalkan._"
        )

    await query.edit_message_text(prompt, parse_mode="Markdown")
    return EDIT_PAYMENT_NEW_VALUE


async def edit_payment_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle new value input for the selected payment field."""
    data = context.user_data.get("edit_payment") or {}
    pm_id = data.get("pm_id")
    field = data.get("field")

    if not pm_id or not field:
        await update.message.reply_text("Data sesi tidak valid. Silakan ulangi /edit_payment.")
        return ConversationHandler.END

    updates: dict = {}

    if field == "qris_file_id":
        if update.message.photo:
            updates["qris_file_id"] = update.message.photo[-1].file_id
        elif _is_image_document(update.message):
            updates["qris_file_id"] = update.message.document.file_id
        elif (update.message.text or "").strip().lower() == "hapus":
            updates["qris_file_id"] = None
        else:
            await update.message.reply_text(
                "Kirim foto QRIS baru atau ketik `hapus` untuk menghapus.",
                parse_mode="Markdown",
            )
            return EDIT_PAYMENT_NEW_VALUE
    else:
        new_value = (update.message.text or "").strip()
        if not new_value:
            await update.message.reply_text("Nilai tidak boleh kosong. Coba lagi.")
            return EDIT_PAYMENT_NEW_VALUE
        updates[field] = new_value

    pm = update_payment_method(pm_id, **updates)
    if not pm:
        await update.message.reply_text("❌ Gagal memperbarui. Metode pembayaran tidak ditemukan.")
        context.user_data.pop("edit_payment", None)
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Metode pembayaran ID {pm_id} berhasil diperbarui:\n"
        f"• Provider: *{pm.get('provider_name', '-')}*\n"
        f"• No. Rekening: `{pm.get('account_number', '-')}`\n"
        f"• Atas Nama: {pm.get('account_holder', '-')}\n"
        f"• QRIS: {'Ada 🖼' if pm.get('qris_file_id') else 'Tidak ada'}",
        parse_mode="Markdown",
    )
    context.user_data.pop("edit_payment", None)
    return ConversationHandler.END


async def cancel_edit_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel edit-payment flow."""
    context.user_data.pop("edit_payment", None)
    await update.message.reply_text("❌ Edit metode pembayaran dibatalkan.")
    return ConversationHandler.END
