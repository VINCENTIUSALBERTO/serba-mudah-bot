"""Entry point for Serba Mudah Bot.

Run with:
    python main.py
"""

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN
from bot.handlers.admin import (
    ADD_PRODUCT_ACCOUNTS,
    ADD_PRODUCT_DESC,
    ADD_PRODUCT_NAME,
    ADD_PRODUCT_PRICE,
    ADD_STOCK_ACCOUNTS,
    ADD_STOCK_PRODUCT,
    admin_approve_callback,
    admin_reject_callback,
    admin_stats_command,
    add_stock_command,
    add_stock_product,
    add_product_accounts,
    add_product_command,
    add_product_description,
    add_product_price,
    cancel_add_stock,
    cancel_add_product,
    delete_product_command,
    edit_product_command,
    finalize_add_product,
    finalize_add_stock,
    list_products_command,
)
from bot.handlers.catalog import catalog_callback, product_detail_callback, stockout_callback
from bot.handlers.order import (
    confirm_balance_payment_callback,
    decrease_quantity_callback,
    increase_quantity_callback,
    my_orders_callback,
    order_callback,
    pay_with_balance_callback,
    pay_with_qris_callback,
)
from bot.handlers.start import help_callback, main_menu_callback, start
from bot.handlers.wallet import (
    WAITING_TOPUP_PROOF,
    addsaldo_command,
    admin_topup_approve_callback,
    admin_topup_reject_callback,
    balance_command,
    cancel_topup,
    receive_topup_proof,
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
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("topup", topup_command)],
            states={
                WAITING_TOPUP_PROOF: [
                    MessageHandler(
                        (filters.PHOTO | filters.Document.ALL | filters.TEXT) & (~filters.COMMAND),
                        receive_topup_proof,
                    )
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel_topup)],
        )
    )
    app.add_handler(CommandHandler("addsaldo", addsaldo_command))
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("add_product", add_product_command)],
            states={
                ADD_PRODUCT_NAME: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_product_price)
                ],
                ADD_PRODUCT_PRICE: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_product_description)
                ],
                ADD_PRODUCT_DESC: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_product_accounts)
                ],
                ADD_PRODUCT_ACCOUNTS: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), finalize_add_product)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_add_product)],
        )
    )
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("add_stock", add_stock_command)],
            states={
                ADD_STOCK_PRODUCT: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_stock_product)
                ],
                ADD_STOCK_ACCOUNTS: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), finalize_add_stock)
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_add_stock)],
        )
    )
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
    app.add_handler(CallbackQueryHandler(stockout_callback, pattern=r"^stockout_\d+$"))
    app.add_handler(CallbackQueryHandler(increase_quantity_callback, pattern=r"^increase_\d+$"))
    app.add_handler(CallbackQueryHandler(decrease_quantity_callback, pattern=r"^decrease_\d+$"))

    # Orders
    app.add_handler(CallbackQueryHandler(order_callback, pattern=r"^order_\d+$"))
    app.add_handler(CallbackQueryHandler(pay_with_balance_callback, pattern=r"^pay_balance_\d+$"))
    app.add_handler(
        CallbackQueryHandler(
            confirm_balance_payment_callback, pattern=r"^confirm_balance_\d+_\d+$"
        )
    )
    app.add_handler(CallbackQueryHandler(pay_with_qris_callback, pattern=r"^pay_qris_\d+$"))
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
