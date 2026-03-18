"""Entry point for Serba Mudah Bot.

Run with:
    python main.py                    # Long-polling mode
    python main.py --webhook          # Webhook mode
"""

import os
import sys
import logging
from dotenv import load_dotenv
from telegram.ext import Application

load_dotenv()

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PORT, USE_WEBHOOK
from bot.handlers.admin import (
    ADD_PAYMENT_HOLDER,
    ADD_PAYMENT_NUMBER,
    ADD_PAYMENT_PROVIDER,
    ADD_PAYMENT_QRIS,
    ADD_PRODUCT_ACCOUNTS,
    ADD_PRODUCT_DESC,
    ADD_PRODUCT_NAME,
    ADD_PRODUCT_PRICE,
    ADD_STOCK_ACCOUNTS,
    ADD_STOCK_PRODUCT,
    EDIT_PAYMENT_CHOOSE_FIELD,
    EDIT_PAYMENT_NEW_VALUE,
    admin_approve_callback,
    admin_reject_callback,
    admin_stats_command,
    add_payment_command,
    add_payment_number,
    add_payment_holder,
    add_payment_qris,
    add_stock_command,
    add_stock_product,
    add_product_accounts,
    add_product_command,
    add_product_description,
    add_product_price,
    cancel_add_payment,
    cancel_add_stock,
    cancel_add_product,
    cancel_edit_payment,
    delete_payment_command,
    delete_product_command,
    edit_payment_command,
    edit_payment_choose_field,
    edit_payment_new_value,
    edit_product_command,
    finalize_add_payment,
    finalize_add_product,
    finalize_add_stock,
    list_payments_command,
    list_products_command,
)
from bot.handlers.catalog import (
    catalog_callback,
    decrease_quantity_callback,
    increase_quantity_callback,
    product_detail_callback,
    stockout_callback,
)
from bot.handlers.order import (
    confirm_balance_payment_callback,
    my_orders_callback,
    order_callback,
    pay_with_balance_callback,
    pay_with_qris_callback,
)
from bot.handlers.start import help_callback, help_command, main_menu_callback, start, unknown_command
from bot.handlers.wallet import (
    TOPUP_TYPE_SELECTION,
    WAITING_TOPUP_AMOUNT,
    WAITING_TOPUP_PROOF,
    addsaldo_command,
    admin_topup_approve_callback,
    admin_topup_reject_callback,
    balance_command,
    cancel_topup,
    cancel_topup_callback,
    receive_topup_proof,
    topup_auto_callback,
    topup_command,
    topup_manual_start_callback,
    topup_quick_amount_callback,
    topup_receive_amount,
    topup_start_callback,
)
from bot.handlers.admin import admin_help

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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("stats", admin_stats_command))
    app.add_handler(CommandHandler(["balance", "saldo"], balance_command))
    app.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler("topup", topup_command),
                CallbackQueryHandler(topup_start_callback, pattern="^topup_start$"),
            ],
            states={
                TOPUP_TYPE_SELECTION: [
                    CallbackQueryHandler(topup_auto_callback, pattern="^topup_auto$"),
                    CallbackQueryHandler(topup_manual_start_callback, pattern="^topup_manual$"),
                ],
                WAITING_TOPUP_AMOUNT: [
                    CallbackQueryHandler(
                        topup_quick_amount_callback, pattern=r"^topup_amount_\d+$"
                    ),
                    MessageHandler(
                        filters.TEXT & (~filters.COMMAND), topup_receive_amount
                    ),
                ],
                WAITING_TOPUP_PROOF: [
                    MessageHandler(
                        (filters.PHOTO | filters.Document.ALL | filters.TEXT)
                        & (~filters.COMMAND),
                        receive_topup_proof,
                    )
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_topup),
                CallbackQueryHandler(cancel_topup_callback, pattern="^topup_cancel$"),
            ],
            allow_reentry=True,
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

    # Payment method management (admin)
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("add_payment", add_payment_command)],
            states={
                ADD_PAYMENT_PROVIDER: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_payment_number)
                ],
                ADD_PAYMENT_NUMBER: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_payment_holder)
                ],
                ADD_PAYMENT_HOLDER: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), add_payment_qris)
                ],
                ADD_PAYMENT_QRIS: [
                    MessageHandler(
                        (filters.PHOTO | filters.Document.ALL | filters.TEXT)
                        & (~filters.COMMAND),
                        finalize_add_payment,
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_add_payment)],
        )
    )
    app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("edit_payment", edit_payment_command)],
            states={
                EDIT_PAYMENT_CHOOSE_FIELD: [
                    CallbackQueryHandler(edit_payment_choose_field, pattern=r"^epf_")
                ],
                EDIT_PAYMENT_NEW_VALUE: [
                    MessageHandler(
                        (filters.PHOTO | filters.Document.ALL | filters.TEXT)
                        & (~filters.COMMAND),
                        edit_payment_new_value,
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_edit_payment)],
        )
    )
    app.add_handler(CommandHandler("list_payments", list_payments_command))
    app.add_handler(CommandHandler("delete_payment", delete_payment_command))

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
    app.add_handler(
        CallbackQueryHandler(increase_quantity_callback, pattern=r"^increase_\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(decrease_quantity_callback, pattern=r"^decrease_\d+$")
    )
    app.add_handler(CallbackQueryHandler(stockout_callback, pattern=r"^stockout_\d+$"))

    # Orders
    app.add_handler(CallbackQueryHandler(order_callback, pattern=r"^order_\d+$"))
    app.add_handler(CallbackQueryHandler(pay_with_balance_callback, pattern=r"^pay_balance_\d+$"))
    app.add_handler(
        CallbackQueryHandler(
            confirm_balance_payment_callback, pattern=r"^confirm_balance_\d+_\d+$"
        )
    )
    app.add_handler(CallbackQueryHandler(pay_with_qris_callback, pattern=r"^pay_qris_\d+$"))
    app.add_handler(CallbackQueryHandler(my_orders_callback, pattern=r"^my_orders(?:_\d+)?$"))

    # Admin
    app.add_handler(CallbackQueryHandler(admin_help, pattern="^admin_help$"))
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

    # Unknown commands
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    return app


def main() -> None:
    """Start the bot using either long-polling or webhook."""
    logger.info("Starting Serba Mudah Bot…")
    app = build_application()

    # Check if webhook mode is enabled
    use_webhook = "--webhook" in sys.argv or USE_WEBHOOK

    if use_webhook:
        if not WEBHOOK_URL:
            logger.error("WEBHOOK_URL is not configured in .env!")
            sys.exit(1)

        logger.info(f"Starting bot in WEBHOOK mode on port {WEBHOOK_PORT}")
        logger.info(f"Webhook URL: {WEBHOOK_URL}")

        # Set webhook
        app.run_webhook(
            listen="0.0.0.0",
            port=WEBHOOK_PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        )
    else:
        logger.info("Starting bot in POLLING mode")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
