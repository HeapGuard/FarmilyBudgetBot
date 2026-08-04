# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from app.services.parser import parse_rule_based, extract_amount_and_text, determine_type_and_category


def test_extract_amount():
    amt, text = extract_amount_and_text("купил шоколадку за 200 рублей")
    assert amt == Decimal("200")

    amt, text = extract_amount_and_text("получил зарплату 80к")
    assert amt == Decimal("80000")

    amt, text = extract_amount_and_text("отложил 1.5к в копилку")
    assert amt == Decimal("1500")

    amt, text = extract_amount_and_text("купил кофе за 2.5 тыс")
    assert amt == Decimal("2500")


def test_parser_expense():
    draft, err = parse_rule_based("купил шоколадку за 200 рублей", 12345, "TestUser")
    assert err is None
    assert draft is not None
    assert draft.type == "expense"
    assert draft.amount == Decimal("200")
    assert draft.currency == "RUB"
    assert draft.category in ["Продукты", "Кафе и рестораны", "Прочее"]


def test_parser_income():
    draft, err = parse_rule_based("получил зарплату 80к", 12345, "TestUser")
    assert err is None
    assert draft is not None
    assert draft.type == "income"
    assert draft.amount == Decimal("80000")
    assert draft.category == "Зарплата"


def test_parser_goal_contribution():
    draft, err = parse_rule_based("отложил 5000 на отпуск", 12345, "TestUser")
    assert err is None
    assert draft is not None
    assert draft.type == "goal_contribution"
    assert draft.amount == Decimal("5000")


def test_parser_transfer():
    draft, err = parse_rule_based("перевёл 10000 с карты на счёт", 12345, "TestUser")
    assert err is None
    assert draft is not None
    assert draft.type == "transfer"
    assert draft.amount == Decimal("10000")


def test_parser_unsupported_currency():
    draft, err = parse_rule_based("купил кофе за 5 usd", 12345, "TestUser")
    assert draft is None
    assert err == "Пока я поддерживаю только рубли"


def test_parser_no_amount():
    draft, err = parse_rule_based("купил кофе без денег", 12345, "TestUser")
    assert draft is None
    assert "Не смог найти сумму" in err


def test_detect_bank_statement():
    from app.services.parser import detect_bank_statement
    
    statement_text = (
        "Вчера -601 ₽\n"
        "DDX FITNESS -200 ₽\n"
        "Тренировки +2 Дебетовая карта\n"
        "32links.ru -401,25 ₽\n"
        "Связь Платинум"
    )
    assert detect_bank_statement(statement_text) is True
    
    simple_text = "купил шоколадку за 200 рублей"
    assert detect_bank_statement(simple_text) is False


@pytest.mark.asyncio
async def test_parse_bank_statement():
    from app.services.parser import parse_bank_statement
    from datetime import date
    
    statement_text = (
        "Вчера -601.25 ₽\n"
        "DDX FITNESS -200 ₽\n"
        "Тренировки +2 Дебетовая карта\n"
        "Между своими счетами 401,25 ₽\n"
        "Переводы Black -> Платинум\n"
        "32links.ru -401,25 ₽\n"
        "Связь Платинум"
    )
    
    today = date(2026, 8, 4)
    res = await parse_bank_statement(statement_text, today)
    
    assert res["is_statement"] is True
    assert res["date"] == "2026-08-03"
    assert len(res["transactions"]) == 2
    
    ddx = next(t for t in res["transactions"] if "ddx" in t["note"].lower())
    assert ddx["amount"] == 200.0
    assert ddx["type"] == "expense"
    assert ddx["category"] == "Здоровье"
