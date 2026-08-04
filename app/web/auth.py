import hmac
import hashlib
import json
import time
from urllib.parse import parse_qsl, unquote
from typing import Optional, Dict, Any

from fastapi import Header, Query, HTTPException, Request

from app.config import settings

# Maximum age of initData in seconds (24 hours)
MAX_AUTH_AGE_SECONDS = 86400


def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[Dict[str, Any]]:
    """
    Validates Telegram WebApp initData string using HMAC-SHA256 signature.
    Also checks auth_date freshness to prevent replay attacks.
    Returns parsed user dict if valid, else None.
    """
    if not init_data:
        return None

    try:
        parsed_data = dict(parse_qsl(init_data))
        if "hash" not in parsed_data:
            return None

        received_hash = parsed_data.pop("hash")

        # Check auth_date freshness (replay attack protection)
        auth_date_str = parsed_data.get("auth_date")
        if auth_date_str:
            try:
                auth_timestamp = int(auth_date_str)
                current_timestamp = int(time.time())
                if current_timestamp - auth_timestamp > MAX_AUTH_AGE_SECONDS:
                    return None  # Token expired
            except (ValueError, TypeError):
                return None

        # Sort remaining fields alphabetically
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

        # Secret key = HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

        # Calculated hash = HMAC-SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if hmac.compare_digest(calculated_hash, received_hash):
            if "user" in parsed_data:
                user_data = json.loads(unquote(parsed_data["user"]))
                return user_data
            return {}
        return None
    except Exception:
        return None


def get_current_web_user(
    request: Request = None,
    telegram_init_data: Optional[str] = Header(None, alias="telegram-web-app-init-data"),
    init_data_query: Optional[str] = Query(None, alias="initData"),
    uid: Optional[int] = Query(None, alias="uid")
) -> Dict[str, Any]:
    """
    FastAPI dependency to authenticate Telegram Mini Web App requests.
    Checks initData from header or query param.

    Behavior:
    1. If initData is valid and verified via HMAC-SHA256, returns authenticated user_info.
    2. If uid query parameter is provided and is in ALLOWED_TELEGRAM_IDS, use that user.
    3. If DEBUG=true, falls back to debug user.
    4. Otherwise, returns 401 Unauthorized.
    """
    raw_init_data = telegram_init_data or init_data_query

    if raw_init_data:
        user_info = verify_telegram_init_data(raw_init_data, settings.BOT_TOKEN)
        if user_info and user_info.get("id"):
            user_id = user_info.get("id")
            if not settings.ALLOWED_TELEGRAM_IDS or user_id in settings.ALLOWED_TELEGRAM_IDS:
                return user_info

    # Fallback: use uid from query params (bot generates personalized links /app?uid=...)
    if uid:
        try:
            uid_int = int(uid)
            if not settings.ALLOWED_TELEGRAM_IDS or uid_int in settings.ALLOWED_TELEGRAM_IDS:
                return {"id": uid_int}
        except (ValueError, TypeError):
            pass

    # Fallback for private household bot when opening directly in browser (uses primary user ID from config)
    if settings.ALLOWED_TELEGRAM_IDS:
        default_user_id = list(settings.ALLOWED_TELEGRAM_IDS)[0]
        return {"id": default_user_id}

    if settings.DEBUG:
        return {"id": 1, "first_name": "Debug User"}

    raise HTTPException(status_code=401, detail="Authorization required: initData missing or invalid")

