import pytest
from decimal import Decimal
from app.services.goals import required_monthly, projected_value, months_to_goal


def test_required_monthly_with_apy():
    # current=100000, target=300000, months=8, apy=16%
    req = required_monthly(Decimal("100000"), Decimal("300000"), 8, apy=16.0)
    assert req is not None
    # Expected value around 22600 - 22800
    assert 22500 <= req <= 23000


def test_required_monthly_zero_apy():
    # current=100000, target=300000, months=8, apy=0
    req = required_monthly(Decimal("100000"), Decimal("300000"), 8, apy=0.0)
    assert req == Decimal("25000.00")


def test_goal_already_reached():
    req = required_monthly(Decimal("350000"), Decimal("300000"), 8, apy=10.0)
    assert req == Decimal("0.00")


def test_months_to_goal_zero_monthly():
    m = months_to_goal(Decimal("100000"), Decimal("300000"), Decimal("0"), apy=10.0)
    assert m is None


def test_months_to_goal_normal():
    m = months_to_goal(Decimal("100000"), Decimal("300000"), Decimal("25000"), apy=0.0)
    assert m == 8
