"""Entry point for Serba Mudah Bot.

Run with:
    python main.py
"""

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
)

from bot.config import BOT_TOKEN
from bot.handlers.admin import (
    admin_approve_callback,
    admin_reject_callback,
    admin_stats_command,
    add_product_command,
    delete_product_command,
    edit_product_command,
    list_products_command,
)
from bot.handlers.catalog import catalog_callback, product_detail_callback
from bot.handlers.order import (
    confirm_order_callback,
    my_orders_callback,
    order_callback,
)
from bot.handlers.start import help_callback, main_menu_callback, start
from bot.handlers.wallet import (
    addsaldo_command,
    admin_topup_approve_callback,
    admin_topup_reject_callback,
    balance_command,
    topup_command,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application() -> Application:
    """Construct and configure the Telegram Application."""
    app = Application.builder().token(BOT_TOKEN).build()

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", admin_stats_command))
    app.add_handler(CommandHandler(["balance", "saldo"], balance_command))
    app.add_handler(CommandHandler("topup", topup_command))
    app.add_handler(CommandHandler("addsaldo", addsaldo_command))
    app.add_handler(CommandHandler("add_product", add_product_command))
    app.add_handler(CommandHandler("edit_product", edit_product_command))
    app.add_handler(CommandHandler("delete_product", delete_product_command))
    app.add_handler(CommandHandler("list_products", list_products_command))

    # ------------------------------------------------------------------
    # Inline-button (CallbackQuery) handlers
    # ------------------------------------------------------------------
    # Navigation
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))

    # Catalog
    app.add_handler(CallbackQueryHandler(catalog_callback, pattern="^catalog$"))
    app.add_handler(
        CallbackQueryHandler(product_detail_callback, pattern=r"^product_\d+$")
    )

    # Orders
    app.add_handler(CallbackQueryHandler(order_callback, pattern=r"^order_\d+$"))
    app.add_handler(
        CallbackQueryHandler(confirm_order_callback, pattern=r"^confirm_\d+$")
    )
    app.add_handler(CallbackQueryHandler(my_orders_callback, pattern="^my_orders$"))

    # Admin
    app.add_handler(
        CallbackQueryHandler(admin_approve_callback, pattern=r"^admin_approve_\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(admin_reject_callback, pattern=r"^admin_reject_\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(admin_topup_approve_callback, pattern=r"^topup_approve_\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(admin_topup_reject_callback, pattern=r"^topup_reject_\d+$")
    )

    return app


def main() -> None:
    """Start the bot using long-polling."""
    logger.info("Starting Serba Mudah Bot…")
    app = build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
