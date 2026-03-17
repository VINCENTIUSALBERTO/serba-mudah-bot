"""Supabase client singleton."""

from supabase import create_client, Client
from bot.config import SUPABASE_URL, SUPABASE_KEY

_client: Client | None = None


def get_client() -> Client:
    """Return the shared Supabase client, creating it on first call."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ---------------------------------------------------------------------------
# Helper query functions
# ---------------------------------------------------------------------------

def fetch_catalog() -> list[dict]:
    """Return all active products from the *products* table."""
    response = get_client().table("products").select("*").eq("is_active", True).execute()
    return response.data or []


def fetch_product(product_id: int) -> dict | None:
    """Return a single product by its primary key, or None if not found."""
    response = (
        get_client()
        .table("products")
        .select("*")
        .eq("id", product_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def create_order(user_id: int, product_id: int, username: str | None = None) -> dict:
    """Insert a new order and return the created row."""
    payload = {
        "user_id": user_id,
        "product_id": product_id,
        "username": username,
        "status": "pending",
    }
    response = get_client().table("orders").insert(payload).execute()
    return response.data[0]


def update_order_status(order_id: int, status: str) -> dict | None:
    """Update the status of an existing order and return the updated row."""
    response = (
        get_client()
        .table("orders")
        .update({"status": status})
        .eq("id", order_id)
        .execute()
    )
    return response.data[0] if response.data else None


def fetch_user_orders(user_id: int) -> list[dict]:
    """Return all orders for a given Telegram user ID."""
    response = (
        get_client()
        .table("orders")
        .select("*, products(name, price)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []
