import pytest
from decimal import Decimal
from app.config import settings
from app.services.parser import parse_rule_based


def test_allowed_ids_parsing():
    settings_obj = settings
    # Ensure allowed telegram ids set
    assert isinstance(settings_obj.ALLOWED_TELEGRAM_IDS, set)


def test_invalid_amount_rejection():
    # Negative amount
    draft, err = parse_rule_based("купил кофе за -200 рублей", 12345, "TestUser")
    assert draft is None
