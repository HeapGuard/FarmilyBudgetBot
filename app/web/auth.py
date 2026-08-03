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
    init_data_query: Optional[str] = Query(None, alias="initData")
) -> Dict[str, Any]:
    """
    FastAPI dependency to authenticate Telegram Mini Web App requests.
    Checks initData from header or query param.

    Security behavior:
    - DEBUG=true: fallback to first allowed user (for local development only)
    - DEBUG=false (production): return 401 if initData is missing or invalid
    """
    raw_init_data = telegram_init_data or init_data_query

    if not raw_init_data:
        if settings.DEBUG:
            default_user_id = list(settings.ALLOWED_TELEGRAM_IDS)[0] if settings.ALLOWED_TELEGRAM_IDS else 1
            return {"id": default_user_id, "first_name": "Debug User"}
        raise HTTPException(status_code=401, detail="Authorization required: initData missing")

    user_info = verify_telegram_init_data(raw_init_data, settings.BOT_TOKEN)
    if not user_info:
        if settings.DEBUG:
            default_user_id = list(settings.ALLOWED_TELEGRAM_IDS)[0] if settings.ALLOWED_TELEGRAM_IDS else 1
            return {"id": default_user_id, "first_name": "Debug User"}
        raise HTTPException(status_code=401, detail="Authorization failed: invalid or expired initData")

    user_id = user_info.get("id")
    if settings.ALLOWED_TELEGRAM_IDS and user_id not in settings.ALLOWED_TELEGRAM_IDS:
        raise HTTPException(status_code=403, detail="Access denied: user not in allowlist")

    return user_info
