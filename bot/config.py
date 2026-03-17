"""Configuration loader — reads environment variables from .env."""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
BOT_TOKEN: str = os.environ["BOT_TOKEN"]

# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]

# ---------------------------------------------------------------------------
# Admin IDs  (comma-separated list of Telegram user IDs)
# ---------------------------------------------------------------------------
ADMIN_IDS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("ADMIN_IDS", "").split(",")
    if uid.strip().isdigit()
]

# ---------------------------------------------------------------------------
# Optional: payment-confirmation channel / group
# ---------------------------------------------------------------------------
PAYMENT_CHANNEL_ID: int | None = (
    int(os.getenv("PAYMENT_CHANNEL_ID"))
    if os.getenv("PAYMENT_CHANNEL_ID")
    else None
)
