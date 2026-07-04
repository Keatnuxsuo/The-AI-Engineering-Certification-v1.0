import os
import secrets

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token

from .server import mcp, oauth_provider


def _need_input(missing: list[str], question: str) -> dict:
    """Structured signal telling the client to ask the user for missing info."""
    return {"status": "need_input", "missing": missing, "question": question}


async def _get_username() -> str:
    token = get_access_token()
    if token is None:
        raise ValueError("Not authenticated")
    username = await oauth_provider.get_username_for_token(token.token)
    if username is None:
        raise ValueError("User not found for token")
    return username


def _product_row(row: tuple) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "price": row[3],
        "category": row[4],
        "weight_kg": row[5],
        "length_cm": row[6],
        "width_cm": row[7],
        "height_cm": row[8],
    }


_PRODUCT_SELECT = (
    "SELECT id, name, description, price, category, weight_kg, length_cm, width_cm, height_cm"
)


async def _get_product_shipping(product_id: int) -> dict | None:
    db = await oauth_provider._get_db()
    cursor = await db.execute(
        f"{_PRODUCT_SELECT} FROM products WHERE id = ?",
        (product_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    product = _product_row(row)
    return {
        "product_id": product["id"],
        "product_name": product["name"],
        "weight_kg": product["weight_kg"],
        "length_cm": product["length_cm"],
        "width_cm": product["width_cm"],
        "height_cm": product["height_cm"],
    }


@mcp.tool()
async def list_products(category: str | None = None) -> list[dict]:
    """Browse the cat shop catalog with prices and parcel dimensions (weight_kg, length_cm, width_cm, height_cm).

    Optionally filter by category (toys, beds, food, furniture).
    For shipping cost questions, call estimate_shipping with the product_id and destination."""
    db = await oauth_provider._get_db()
    if category:
        cursor = await db.execute(
            f"{_PRODUCT_SELECT} FROM products WHERE category = ?",
            (category,),
        )
    else:
        cursor = await db.execute(f"{_PRODUCT_SELECT} FROM products")
    rows = await cursor.fetchall()
    return [_product_row(r) for r in rows]


@mcp.tool()
async def get_product(product_id: int) -> dict:
    """Get full product details including weight and parcel dimensions for shipping.

    When the user asks about shipping or delivery cost, always follow up by calling
    estimate_shipping with this product_id and their destination postcode/country."""
    db = await oauth_provider._get_db()
    cursor = await db.execute(
        f"{_PRODUCT_SELECT} FROM products WHERE id = ?",
        (product_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return {"error": "Product not found"}
    product = _product_row(row)
    return {
        **product,
        "next_step_for_shipping": (
            f"Call estimate_shipping(country='AU', postcode='<destination_postcode>', "
            f"product_id={product_id}) for domestic Australia. "
            f"For international, use estimate_shipping(country='<2-letter code>', product_id={product_id})."
        ),
    }


@mcp.tool()
async def add_to_cart(product_id: int, quantity: int = 1) -> dict:
    """Add a product to your shopping cart. If already in cart, quantity is increased."""
    username = await _get_username()
    db = await oauth_provider._get_db()

    cursor = await db.execute("SELECT name FROM products WHERE id = ?", (product_id,))
    product = await cursor.fetchone()
    if product is None:
        return {"error": "Product not found"}

    await db.execute(
        """INSERT INTO cart_items (username, product_id, quantity)
           VALUES (?, ?, ?)
           ON CONFLICT(username, product_id)
           DO UPDATE SET quantity = quantity + excluded.quantity""",
        (username, product_id, quantity),
    )
    await db.commit()
    return {"success": True, "message": f"Added {quantity}x {product[0]} to your cart"}


@mcp.tool()
async def view_cart() -> dict:
    """View everything in your shopping cart with quantities and totals."""
    username = await _get_username()
    db = await oauth_provider._get_db()
    cursor = await db.execute(
        """SELECT p.id, p.name, p.price, c.quantity
           FROM cart_items c JOIN products p ON c.product_id = p.id
           WHERE c.username = ?""",
        (username,),
    )
    rows = await cursor.fetchall()
    items = [
        {
            "product_id": r[0],
            "name": r[1],
            "price": r[2],
            "quantity": r[3],
            "subtotal": round(r[2] * r[3], 2),
        }
        for r in rows
    ]
    total = round(sum(i["subtotal"] for i in items), 2)
    return {"items": items, "total": total, "item_count": len(items)}


async def _get_cart_weight(username: str) -> float:
    """Total weight (kg) of all items in the user's cart, quantity-adjusted."""
    db = await oauth_provider._get_db()
    cursor = await db.execute(
        """SELECT COALESCE(SUM(p.weight_kg * c.quantity), 0)
           FROM cart_items c JOIN products p ON c.product_id = p.id
           WHERE c.username = ?""",
        (username,),
    )
    (weight,) = await cursor.fetchone()
    return round(float(weight), 3)


@mcp.tool()
async def remove_from_cart(product_id: int) -> dict:
    """Remove a product from your shopping cart."""
    username = await _get_username()
    db = await oauth_provider._get_db()
    cursor = await db.execute(
        "DELETE FROM cart_items WHERE username = ? AND product_id = ?",
        (username, product_id),
    )
    await db.commit()
    if cursor.rowcount == 0:
        return {"error": "Item not in cart"}
    return {"success": True, "message": "Item removed from cart"}


@mcp.tool()
async def checkout(country: str | None = None, postcode: str | None = None) -> dict:
    """Complete your purchase, including AusPost shipping in the total.

    Provide the destination so shipping is added to the order:
    - Domestic: country='AU' plus postcode (e.g. Perth=6000, Melbourne=3000).
    - International: 2-letter country code (e.g. NZ, US) and omit postcode.

    Shipping is calculated for the whole cart based on total item weight.
    Do NOT guess the destination. If country/postcode are missing, this tool
    returns a "need_input" question for you to ask the user before charging.
    """
    username = await _get_username()
    db = await oauth_provider._get_db()

    cart = await view_cart()
    if not cart["items"]:
        return {"error": "Your cart is empty"}

    items_total = cart["total"]

    cart_weight = await _get_cart_weight(username)
    shipping = await _calculate_shipping(
        country,
        postcode=postcode,
        weight=cart_weight,
    )
    if shipping.get("status") == "need_input":
        return shipping
    if "error" in shipping:
        return {"error": f"Could not calculate shipping: {shipping['error']}"}
    shipping_cost = shipping["total_cost"]

    grand_total = round(items_total + shipping_cost, 2)

    await db.execute("DELETE FROM cart_items WHERE username = ?", (username,))
    await db.commit()

    order_id = secrets.token_hex(8).upper()
    return {
        "order_id": order_id,
        "status": "confirmed",
        "items": cart["items"],
        "items_total": items_total,
        "shipping_cost": round(shipping_cost, 2),
        "grand_total": grand_total,
        "currency": "AUD",
        "shipping": {
            "service": shipping.get("service"),
            "delivery_time": shipping.get("delivery_time"),
            "destination": postcode or shipping.get("country"),
        },
        "message": f"Order {order_id} confirmed! Thanks {username}, your cats will love their new goodies!",
    }

AUSPOST_BASE_URL = "https://digitalapi.auspost.com.au"
WAREHOUSE_POSTCODE = "2000"
DEFAULT_WEIGHT_KG = 1.0
DEFAULT_LENGTH_CM = 20
DEFAULT_WIDTH_CM = 15
DEFAULT_HEIGHT_CM = 10
DOMESTIC_COUNTRY_CODES = {"AU", "AUS", "AUSTRALIA"}


def _is_domestic(country: str) -> bool:
    return country.strip().upper() in DOMESTIC_COUNTRY_CODES


def _normalize_services(services_payload: dict) -> list[dict]:
    services = services_payload.get("services", {}).get("service", [])
    if isinstance(services, dict):
        return [services]
    return services


async def _auspost_get(
    client: httpx.AsyncClient, path: str, params: dict, api_key: str
) -> dict:
    response = await client.get(
        f"{AUSPOST_BASE_URL}{path}",
        headers={"AUTH-KEY": api_key},
        params=params,
    )
    data = response.json()
    if response.status_code >= 400 or "error" in data:
        error = data.get("error", {})
        message = error.get("errorMessage", response.text or "AusPost API request failed")
        return {"error": message}
    return data


def _pick_service_code(services_payload: dict) -> str | None:
    services = _normalize_services(services_payload)
    if not services:
        return None
    return services[0].get("code")


async def _calculate_shipping(
    country: str | None = None,
    postcode: str | None = None,
    product_id: int | None = None,
    weight: float | None = None,
    length_cm: float | None = None,
    width_cm: float | None = None,
    height_cm: float | None = None,
) -> dict:
    api_key = os.getenv("AUSPOST_API_KEY")
    if not api_key:
        return {"error": "AUSPOST_API_KEY is not set"}

    if not country or not country.strip():
        return _need_input(
            ["country"],
            "Where should this be shipped? Give an Australian postcode for domestic "
            "delivery, or a country (e.g. New Zealand) for international.",
        )

    product_name = None
    if product_id is not None:
        product_shipping = await _get_product_shipping(product_id)
        if product_shipping is None:
            return {"error": "Product not found"}
        product_name = product_shipping["product_name"]
        weight = product_shipping["weight_kg"]
        length_cm = product_shipping["length_cm"]
        width_cm = product_shipping["width_cm"]
        height_cm = product_shipping["height_cm"]
    else:
        weight = weight if weight is not None else DEFAULT_WEIGHT_KG
        length_cm = length_cm if length_cm is not None else DEFAULT_LENGTH_CM
        width_cm = width_cm if width_cm is not None else DEFAULT_WIDTH_CM
        height_cm = height_cm if height_cm is not None else DEFAULT_HEIGHT_CM

    async with httpx.AsyncClient(timeout=30.0) as client:
        if _is_domestic(country):
            if not postcode or not str(postcode).strip():
                return _need_input(
                    ["postcode"],
                    "What Australian postcode should I ship to? "
                    "For example, Perth is 6000, Melbourne 3000, Sydney 2000.",
                )

            parcel_params = {
                "from_postcode": WAREHOUSE_POSTCODE,
                "to_postcode": postcode,
                "length": length_cm,
                "width": width_cm,
                "height": height_cm,
                "weight": weight,
            }
            services = await _auspost_get(
                client,
                "/postage/parcel/domestic/service.json",
                parcel_params,
                api_key,
            )
            if "error" in services:
                return services

            service_code = _pick_service_code(services)
            if not service_code:
                return {"error": "No domestic parcel services available for this destination"}

            result = await _auspost_get(
                client,
                "/postage/parcel/domestic/calculate.json",
                {**parcel_params, "service_code": service_code},
                api_key,
            )
            shipping_type = "domestic"
        else:
            country_code = country.strip().upper()
            service_params = {"country_code": country_code, "weight": weight}
            services = await _auspost_get(
                client,
                "/postage/parcel/international/service.json",
                service_params,
                api_key,
            )
            if "error" in services:
                return services

            service_code = _pick_service_code(services)
            if not service_code:
                return {"error": "No international parcel services available for this destination"}

            result = await _auspost_get(
                client,
                "/postage/parcel/international/calculate.json",
                {**service_params, "service_code": service_code},
                api_key,
            )
            shipping_type = "international"

    if "error" in result:
        return result

    postage = result.get("postage_result", {})
    total_cost = postage.get("total_cost")
    if total_cost is None:
        return {"error": "AusPost response did not include a total cost"}

    return {
        "shipping_type": shipping_type,
        "country": country_code if shipping_type == "international" else "AU",
        "postcode": postcode,
        "product_id": product_id,
        "product_name": product_name,
        "weight_kg": weight,
        "length_cm": length_cm,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "service": postage.get("service"),
        "service_code": service_code,
        "delivery_time": postage.get("delivery_time"),
        "total_cost": float(total_cost),
        "currency": "AUD",
    }


@mcp.tool()
async def estimate_shipping(
    country: str | None = None,
    postcode: str | None = None,
    product_id: int | None = None,
    weight: float | None = None,
    length_cm: float | None = None,
    width_cm: float | None = None,
    height_cm: float | None = None,
) -> dict:
    """Get AusPost postage cost and delivery time for a cat shop parcel.

    ALWAYS use this tool when the user asks about shipping cost, delivery price,
    or postage to a city/postcode/country. Pass product_id from get_product so
    the correct weight and dimensions are used automatically.

    Domestic Australia: country='AU' or 'Australia' plus destination postcode
    (e.g. Perth=6000, Melbourne=3000, Sydney=2000).
    International: 2-letter country code (e.g. NZ, US, GB) and omit postcode.

    Do NOT guess the destination. If the user hasn't given a postcode/country,
    call this tool anyway and it will return a "need_input" question to ask them.
    """
    return await _calculate_shipping(
        country,
        postcode=postcode,
        product_id=product_id,
        weight=weight,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
    )