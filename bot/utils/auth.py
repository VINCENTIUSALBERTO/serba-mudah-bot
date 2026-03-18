"""Simple auth-related helpers."""

from bot.config import ADMIN_IDS


def is_admin(user_id: int) -> bool:
    """Return True if the given Telegram user ID is an admin."""
    return user_id in ADMIN_IDS
