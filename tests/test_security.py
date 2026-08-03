import pytest
from decimal import Decimal
from app.config import settings
from app.services.parser import parse_rule_based, sanitize_text_for_llm, VALID_OPERATION_TYPES, MAX_AMOUNT


def test_allowed_ids_parsing():
    settings_obj = settings
    # Ensure allowed telegram ids set
    assert isinstance(settings_obj.ALLOWED_TELEGRAM_IDS, set)


def test_invalid_amount_rejection():
    # Negative amount
    draft, err = parse_rule_based("купил кофе за -200 рублей", 12345, "TestUser")
    assert draft is None


def test_sanitize_text_removes_control_chars():
    """Ensure control characters are stripped from LLM input."""
    dirty = "купил кофе\x00\x01\x02 за 300 рублей\x7f"
    cleaned = sanitize_text_for_llm(dirty)
    assert "\x00" not in cleaned
    assert "\x01" not in cleaned
    assert "\x7f" not in cleaned
    assert "купил кофе" in cleaned
    assert "300" in cleaned


def test_sanitize_text_truncates_long_input():
    """Ensure overly long input is truncated."""
    long_text = "а" * 1000
    cleaned = sanitize_text_for_llm(long_text)
    assert len(cleaned) <= 500


def test_valid_operation_types_whitelist():
    """Ensure only known operation types are allowed."""
    assert "expense" in VALID_OPERATION_TYPES
    assert "income" in VALID_OPERATION_TYPES
    assert "transfer" in VALID_OPERATION_TYPES
    assert "goal_contribution" in VALID_OPERATION_TYPES
    assert "admin_override" not in VALID_OPERATION_TYPES
    assert "drop_table" not in VALID_OPERATION_TYPES


def test_amount_ceiling():
    """Ensure unreasonably large amounts are capped."""
    assert MAX_AMOUNT == Decimal("10000000")


def test_input_validation_schemas():
    """Test that Pydantic schemas reject invalid data."""
    from pydantic import ValidationError

    # Import the schemas from routes
    import sys
    import importlib

    # Test ChatRequestSchema
    from app.web.routes import ChatRequestSchema, OperationCreateSchema

    # Empty question should fail
    with pytest.raises(ValidationError):
        ChatRequestSchema(question="")

    # Too long question should fail
    with pytest.raises(ValidationError):
        ChatRequestSchema(question="x" * 501)

    # Valid question
    schema = ChatRequestSchema(question="Сколько я трачу в день?")
    assert schema.question == "Сколько я трачу в день?"

    # Invalid operation type should fail
    with pytest.raises(ValidationError):
        OperationCreateSchema(type="hack", amount=Decimal("100"))

    # Negative amount should fail
    with pytest.raises(ValidationError):
        OperationCreateSchema(type="expense", amount=Decimal("-100"))

    # Amount exceeding limit should fail
    with pytest.raises(ValidationError):
        OperationCreateSchema(type="expense", amount=Decimal("99999999"))

    # Valid operation
    op = OperationCreateSchema(type="expense", amount=Decimal("1500"))
    assert op.type == "expense"
    assert op.amount == Decimal("1500")
