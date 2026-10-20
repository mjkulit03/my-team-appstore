"""Product catalog for the storefront.

The Marketing and Sales AI employees read ``description``/``audience`` directly
from here, so this is the single source of truth for what each product claims.
"""

from .products import (
    CATEGORIES,
    PRODUCTS,
    find_product,
    list_categories,
    list_products,
    products_in_category,
)

__all__ = [
    "PRODUCTS",
    "CATEGORIES",
    "list_products",
    "list_categories",
    "products_in_category",
    "find_product",
]