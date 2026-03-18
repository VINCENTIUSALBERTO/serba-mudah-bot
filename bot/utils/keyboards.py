"""Reusable InlineKeyboardMarkup builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.config import ADMIN_USERNAME


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Return the main-menu keyboard."""
    buttons = [
        [InlineKeyboardButton("📦 Katalog", callback_data="catalog")],
        [InlineKeyboardButton("📋 Pesanan Saya", callback_data="my_orders")],
        [InlineKeyboardButton("💰 Top-Up Saldo", callback_data="topup_start")],
        [InlineKeyboardButton("💵 Cek Saldo", callback_data="balance_check")],
        [InlineKeyboardButton("❓ Bantuan", callback_data="help")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("🛠 Admin", callback_data="admin_help")])
    return InlineKeyboardMarkup(buttons)


def catalog_keyboard(products: list[dict], stock_map: dict[int, int] | None = None) -> InlineKeyboardMarkup:
    """Build a keyboard with one button per product."""
    buttons = []
    for p in products:
        available = (stock_map or {}).get(p["id"], 0)
        if available <= 0:
            label = f"❌ {p['name']} — Stok habis"
            callback = f"stockout_{p['id']}"
        else:
            label = f"{p['name']} — Rp {p['price']:,} (Stok: {available})"
            callback = f"product_{p['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=callback)])
    buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def help_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for the help page."""
    buttons = [
        [InlineKeyboardButton("📞 Hubungi Admin", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(buttons)

def order_history_keyboard(
    offset: int = 0, limit: int = 10, has_prev: bool = False, has_next: bool = False
) -> InlineKeyboardMarkup:
    """Keyboard for the order history page with paging."""
    buttons: list[list[InlineKeyboardButton]] = []
    nav_buttons: list[InlineKeyboardButton] = []
    if has_prev:
        prev_offset = max(0, offset - limit)
        nav_buttons.append(
            InlineKeyboardButton("⬅️ Lebih baru", callback_data=f"my_orders_{prev_offset}")
        )
    if has_next:
        nav_buttons.append(
            InlineKeyboardButton("➡️ Lebih lama", callback_data=f"my_orders_{offset + limit}")
        )
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def product_detail_keyboard(
    product_id: int, quantity: int = 1, available: int = 0, total_price: int | None = None
) -> InlineKeyboardMarkup:
    """Keyboard shown on a product-detail page."""
    if available <= 0:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("❌ Stok habis", callback_data=f"stockout_{product_id}")],
                [InlineKeyboardButton("🔙 Kembali", callback_data="catalog")],
            ]
        )

    total_suffix = f" (Rp {total_price:,})" if total_price is not None else ""
    buttons = [
        [
            InlineKeyboardButton("➖", callback_data=f"decrease_{product_id}"),
            InlineKeyboardButton(str(max(1, quantity)), callback_data="quantity_placeholder"),
            InlineKeyboardButton("➕", callback_data=f"increase_{product_id}"),
        ],
        [
            InlineKeyboardButton(
                f"💰 Saldo{total_suffix}", callback_data=f"pay_balance_{product_id}"
            ),
            InlineKeyboardButton("💳 QRIS", callback_data=f"pay_qris_{product_id}"),
        ],
        [InlineKeyboardButton("🔙 Kembali", callback_data="catalog")],
    ]
    return InlineKeyboardMarkup(buttons)


def payment_method_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Keyboard for choosing payment method."""
    buttons = [
        [
            InlineKeyboardButton("💰 Bayar dengan saldo", callback_data=f"pay_balance_{product_id}"),
            InlineKeyboardButton("💳 Bayar via QRIS", callback_data=f"pay_qris_{product_id}"),
        ],
        [InlineKeyboardButton("🔙 Kembali", callback_data="catalog")],
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
