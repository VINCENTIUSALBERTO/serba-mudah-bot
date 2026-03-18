"""Reusable InlineKeyboardMarkup builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.config import ADMIN_USERNAME


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main-menu keyboard."""
    buttons = [
        [InlineKeyboardButton("🛒 Katalog Produk", callback_data="catalog")],
        [
            InlineKeyboardButton("📦 Pesanan Saya", callback_data="my_orders"),
            InlineKeyboardButton("ℹ️ Bantuan", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def catalog_keyboard(products: list[dict]) -> InlineKeyboardMarkup:
    """Build a keyboard with one button per product."""
    buttons = [
        [
            InlineKeyboardButton(
                f"{p['name']} — Rp {p['price']:,}",
                callback_data=f"product_{p['id']}",
            )
        ]
        for p in products
    ]
    buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def help_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the help page."""
    buttons = [
        [InlineKeyboardButton("📞 Hubungi Admin", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def order_history_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the order history page."""
    buttons = [
        [InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)


def product_detail_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown on a product-detail page."""
    buttons = [
        [
            InlineKeyboardButton("➖", callback_data=f"decrease_{product_id}"),
            InlineKeyboardButton("1", callback_data="quantity_placeholder"),
            InlineKeyboardButton("➕", callback_data=f"increase_{product_id}"),
        ],
        [
            InlineKeyboardButton("💰 Saldo", callback_data=f"order_{product_id}"
            ),
            InlineKeyboardButton("💳 QRIS", callback_data=f"order_{product_id}")
        ],
        [InlineKeyboardButton("🔙 Kembali", callback_data="catalog")],
    ]
    return InlineKeyboardMarkup(buttons)


def confirm_order_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Keyboard for order confirmation step."""
    buttons = [
        [InlineKeyboardButton("✅ Konfirmasi", callback_data=f"confirm_{product_id}")],
        [InlineKeyboardButton("❌ Batalkan", callback_data=f"confirm_{product_id}")],
    ]
    return InlineKeyboardMarkup(buttons)

def payment_method_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing payment method."""
    buttons = [
        [InlineKeyboardButton("🔙 Menu utama", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Keyboard for admin to approve or reject an order."""
    buttons = [
        [
            InlineKeyboardButton(
                "✅ Setujui", callback_data=f"admin_approve_{order_id}"
            ),
            InlineKeyboardButton(
                "❌ Tolak", callback_data=f"admin_reject_{order_id}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def admin_topup_keyboard(topup_id: int) -> InlineKeyboardMarkup:
    """Keyboard for admin to approve or reject a top-up."""
    buttons = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"topup_approve_{topup_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"topup_reject_{topup_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)
