import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any


def get_monthly_rate(apy: float) -> float:
    if apy <= 0:
        return 0.0
    return (1.0 + apy / 100.0) ** (1.0 / 12.0) - 1.0


def projected_value(
    current_amount: Decimal,
    monthly_amount: Decimal,
    months: int,
    apy: float = 0.0
) -> Optional[Decimal]:
    if months <= 0:
        return None

    c = float(current_amount)
    m = float(monthly_amount)
    r = get_monthly_rate(apy)

    if r > 0:
        fv = c * ((1.0 + r) ** months) + m * (((1.0 + r) ** months - 1.0) / r)
    else:
        fv = c + m * months

    return Decimal(str(round(fv, 2)))


def required_monthly(
    current_amount: Decimal,
    target_amount: Decimal,
    months: int,
    apy: float = 0.0
) -> Optional[Decimal]:
    if months <= 0:
        return None

    if target_amount <= current_amount:
        return Decimal("0.00")

    c = float(current_amount)
    t = float(target_amount)
    r = get_monthly_rate(apy)

    if r > 0:
        pmt = (t - c * ((1.0 + r) ** months)) * r / (((1.0 + r) ** months) - 1.0)
    else:
        pmt = (t - c) / months

    if pmt <= 0:
        return Decimal("0.00")

    return Decimal(str(round(pmt, 2)))


def months_to_goal(
    current_amount: Decimal,
    target_amount: Decimal,
    monthly_amount: Decimal,
    apy: float = 0.0
) -> Optional[int]:
    if target_amount <= current_amount:
        return 0

    if monthly_amount <= 0:
        return None

    c = float(current_amount)
    t = float(target_amount)
    m = float(monthly_amount)
    r = get_monthly_rate(apy)

    if r > 0:
        num = t + m / r
        den = c + m / r
        if den <= 0 or num / den <= 0:
            return None
        n = math.log(num / den) / math.log(1.0 + r)
    else:
        n = (t - c) / m

    return math.ceil(n)


def format_goal_progress(
    title: str,
    target_amount: Decimal,
    current_amount: Decimal,
    deadline_months: Optional[int],
    apy: float = 0.0
) -> str:
    percentage = (current_amount / target_amount * 100) if target_amount > 0 else Decimal(100)
    percentage_str = f"{min(float(percentage), 100.0):.0f}%"

    req_monthly_str = "—"
    if deadline_months and deadline_months > 0:
        req = required_monthly(current_amount, target_amount, deadline_months, apy)
        if req is not None:
            req_monthly_str = f"{req:,.0f} ₽/мес".replace(",", " ")

    status_str = "идёт по плану" if percentage >= 50 else "требует внимания"
    if current_amount >= target_amount:
        status_str = "достигнута! 🎉"

    months_info = f"Срок: {deadline_months} месяцев" if deadline_months else "Срок: не указан"

    return (
        f"🎯 <b>Цель:</b> {title}\n"
        f"Нужно: {target_amount:,.0f} ₽\n".replace(",", " ") +
        f"Уже накоплено: {current_amount:,.0f} ₽\n".replace(",", " ") +
        f"Прогресс: {percentage_str}\n"
        f"{months_info}\n"
        f"Требуемый взнос: {req_monthly_str}\n"
        f"Статус: {status_str}"
    )
