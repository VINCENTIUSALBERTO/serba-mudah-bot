"""Common text formatting helpers."""


def format_currency(amount: int) -> str:
    """Return formatted Rupiah string."""
    return f"Rp {int(amount):,}"
