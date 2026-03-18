"""Supabase client singleton."""
from functools import lru_cache
import time
from supabase import Client, create_client
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

_catalog_cache = {"data": None, "timestamp": None}
CACHE_TTL = 300  # 5 menit


def _invalidate_catalog_cache() -> None:
    """Reset cached catalog to force fresh fetch."""
    global _catalog_cache
    _catalog_cache = {"data": None, "timestamp": None}


def fetch_catalog() -> list[dict]:
    """Return all active products with caching."""
    global _catalog_cache
    now = time.time()

    # Gunakan cache jika masih fresh
    if _catalog_cache["data"] and (now - _catalog_cache["timestamp"]) < CACHE_TTL:
        return _catalog_cache["data"]

    response = get_client().table("products").select("*").eq("is_active", True).execute()
    data = response.data or []

    # Update cache
    _catalog_cache = {"data": data, "timestamp": now}
    return data


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


# ---------------------------------------------------------------------------
# Users & balance
# ---------------------------------------------------------------------------


def fetch_user(user_id: int) -> dict | None:
    """Return a single user row by Telegram ID."""
    response = (
        get_client()
        .table("users")
        .select("*")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def ensure_user(user_id: int, username: str | None = None) -> dict:
    """Ensure a user exists; create if missing and update username if changed."""
    existing = fetch_user(user_id)
    if existing:
        if username and existing.get("username") != username:
            get_client().table("users").update({"username": username}).eq("id", user_id).execute()
            existing["username"] = username
        return existing

    payload = {"id": user_id, "username": username, "balance": 0}
    response = get_client().table("users").insert(payload).execute()
    return response.data[0] if response.data else payload


def get_user_balance(user_id: int) -> int:
    """Return the user's balance (0 if not found)."""
    user = fetch_user(user_id)
    return int(user.get("balance", 0)) if user else 0


def update_user_balance(user_id: int, new_balance: int) -> dict:
    """Set user's balance to a specific value."""
    response = (
        get_client()
        .table("users")
        .update({"balance": new_balance})
        .eq("id", user_id)
        .execute()
    )
    return response.data[0] if response.data else {"id": user_id, "balance": new_balance}


def increment_user_balance(user_id: int, delta: int, username: str | None = None) -> dict:
    """Increase/decrease balance by delta (can be negative)."""
    user = ensure_user(user_id, username=username)
    current = int(user.get("balance", 0) or 0)
    new_balance = current + delta
    return update_user_balance(user_id, new_balance)


# ---------------------------------------------------------------------------
# Top-ups
# ---------------------------------------------------------------------------


def create_topup_request(user_id: int, amount: int, proof_message_id: int | None = None) -> dict:
    """Insert a new top-up request row."""
    payload = {"user_id": user_id, "amount": amount, "status": "pending", "proof_message_id": proof_message_id}
    response = get_client().table("topups").insert(payload).execute()
    return response.data[0]


def fetch_topup(topup_id: int) -> dict | None:
    """Fetch a top-up request by its ID."""
    response = (
        get_client()
        .table("topups")
        .select("*")
        .eq("id", topup_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def update_topup_status(topup_id: int, status: str) -> dict | None:
    """Update status of a top-up."""
    response = (
        get_client()
        .table("topups")
        .update({"status": status})
        .eq("id", topup_id)
        .execute()
    )
    return response.data[0] if response.data else None


def attach_topup_proof(topup_id: int, proof_message_id: int) -> dict | None:
    """Attach proof message ID to a top-up."""
    response = (
        get_client()
        .table("topups")
        .update({"proof_message_id": proof_message_id})
        .eq("id", topup_id)
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


def fetch_order(order_id: int) -> dict | None:
    """Fetch a single order with product relation if available."""
    response = (
        get_client()
        .table("orders")
        .select("*, products(*)")
        .eq("id", order_id)
        .limit(1)
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


# ---------------------------------------------------------------------------
# Product management (admin)
# ---------------------------------------------------------------------------


def fetch_all_products() -> list[dict]:
    """Return all products (active and inactive)."""
    response = get_client().table("products").select("*").order("id", desc=True).execute()
    return response.data or []


def add_product(name: str, price: int, description: str | None = None, is_active: bool = True) -> dict:
    """Create a new product row and invalidate cached catalog."""
    payload = {"name": name, "price": price, "description": description, "is_active": is_active}
    response = get_client().table("products").insert(payload).execute()
    _invalidate_catalog_cache()
    return response.data[0]


def update_product_fields(
    product_id: int,
    *,
    name: str | None = None,
    price: int | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> dict | None:
    """Update selected product fields."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if price is not None:
        updates["price"] = price
    if description is not None:
        updates["description"] = description
    if is_active is not None:
        updates["is_active"] = is_active

    if not updates:
        return fetch_product(product_id)

    response = (
        get_client()
        .table("products")
        .update(updates)
        .eq("id", product_id)
        .execute()
    )
    _invalidate_catalog_cache()
    return response.data[0] if response.data else None


def soft_delete_product(product_id: int) -> dict | None:
    """Mark a product as inactive instead of deleting permanently."""
    return update_product_fields(product_id, is_active=False)


# ---------------------------------------------------------------------------
# Product stock / accounts
# ---------------------------------------------------------------------------


def bulk_insert_accounts(product_id: int, accounts: list[str]) -> list[dict]:
    """Insert multiple account credentials for a product."""
    if not accounts:
        return []
    rows = [{"product_id": product_id, "credential": acc, "is_sold": False} for acc in accounts]
    response = get_client().table("product_accounts").insert(rows).execute()
    return response.data or []


def reserve_product_account(product_id: int, order_id: int | None = None) -> dict | None:
    """Reserve the first available account for a product and mark it sold."""
    candidate = (
        get_client()
        .table("product_accounts")
        .select("*")
        .eq("product_id", product_id)
        .eq("is_sold", False)
        .limit(1)
        .execute()
    )
    if not candidate.data:
        return None

    account = candidate.data[0]
    update_payload = {"is_sold": True}
    if order_id is not None:
        update_payload["order_id"] = order_id

    updated = (
        get_client()
        .table("product_accounts")
        .update(update_payload)
        .eq("id", account["id"])
        .execute()
    )
    return updated.data[0] if updated.data else account
