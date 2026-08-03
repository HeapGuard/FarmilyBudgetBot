import hmac
import hashlib
import json
import time
from urllib.parse import urlencode, quote
from app.web.auth import verify_telegram_init_data


def test_telegram_init_data_validation():
    bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    user_info = {"id": 987654321, "first_name": "Test", "username": "testuser"}
    user_str = json.dumps(user_info)

    # Use current timestamp so it passes the 24h freshness check
    current_auth_date = str(int(time.time()))

    params = {
        "auth_date": current_auth_date,
        "query_id": "AAH...",
        "user": user_str
    }

    # Sort & format data check string
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    valid_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    params["hash"] = valid_hash
    init_data_raw = urlencode(params)

    # Validate valid initData
    res = verify_telegram_init_data(init_data_raw, bot_token)
    assert res is not None
    assert res["id"] == 987654321

    # Validate invalid hash
    params_bad = params.copy()
    params_bad["hash"] = "invalidhash12345"
    init_data_bad = urlencode(params_bad)
    assert verify_telegram_init_data(init_data_bad, bot_token) is None


def test_expired_init_data_rejected():
    """Test that initData with auth_date older than 24 hours is rejected."""
    bot_token = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
    user_info = {"id": 987654321, "first_name": "Test", "username": "testuser"}
    user_str = json.dumps(user_info)

    # Use a timestamp from 2 days ago
    old_auth_date = str(int(time.time()) - 172800)

    params = {
        "auth_date": old_auth_date,
        "query_id": "AAH...",
        "user": user_str
    }

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    valid_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    params["hash"] = valid_hash
    init_data_raw = urlencode(params)

    # Should be rejected because auth_date is too old (replay protection)
    res = verify_telegram_init_data(init_data_raw, bot_token)
    assert res is None
