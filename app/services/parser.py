import re
import json
import uuid
import httpx
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any, List

from app.config import settings
from app.models.schemas import OperationDraftSchema
from app.services.categories import CATEGORY_KEYWORDS, EXPENSE_CATEGORIES, INCOME_CATEGORIES


UNSUPPORTED_CURRENCIES = ["usd", "eur", "доллар", "долларов", "евро", "юань", "usdt", "btc", "$", "€"]


def extract_amount_and_text(text: str) -> Tuple[Optional[Decimal], str]:
    """
    Extracts numerical amount from text handling 5k, 1.5k, 2 тыс, 200.50, 200,50, etc.
    Returns (Decimal amount, remaining note text).
    """
    normalized = text.strip()

    # 1) 1.5к, 5к, 80к
    k_match = re.search(r'(-?\d+(?:[\.,]\d+)?)\s*к\b', normalized, re.IGNORECASE)
    if k_match:
        val_str = k_match.group(1).replace(',', '.')
        amount = Decimal(val_str) * 1000
        clean_text = normalized[:k_match.start()] + normalized[k_match.end():]
        return amount, clean_text.strip()

    # 2) 2 тыс, 2.5 тыс
    tys_match = re.search(r'(-?\d+(?:[\.,]\d+)?)\s*тыс', normalized, re.IGNORECASE)
    if tys_match:
        val_str = tys_match.group(1).replace(',', '.')
        amount = Decimal(val_str) * 1000
        clean_text = normalized[:tys_match.start()] + normalized[tys_match.end():]
        return amount, clean_text.strip()

    # 3) Standard numbers: -200, 200, 200.50, 200,50 followed optionally by р, руб, рублей, ₽
    num_match = re.search(r'(-?\d+(?:[\.,]\d+)?)\s*(?:руб(?:лей|ля)?|р|₽)?', normalized, re.IGNORECASE)
    if num_match:
        val_str = num_match.group(1).replace(',', '.')
        try:
            amount = Decimal(val_str)
            clean_text = normalized[:num_match.start()] + normalized[num_match.end():]
            clean_text = re.sub(r'\b(рублей|рубля|руб|р|₽)\b', '', clean_text, flags=re.IGNORECASE).strip()
            return amount, clean_text
        except Exception:
            pass

    return None, normalized


def extract_date(text: str) -> Tuple[date, str]:
    today = date.today()
    lower_text = text.lower()

    if "позавчера" in lower_text:
        return today - timedelta(days=2), re.sub(r'\bпозавчера\b', '', text, flags=re.IGNORECASE).strip()
    elif "вчера" in lower_text:
        return today - timedelta(days=1), re.sub(r'\bвчера\b', '', text, flags=re.IGNORECASE).strip()
    elif "сегодня" in lower_text:
        return today, re.sub(r'\bсегодня\b', '', text, flags=re.IGNORECASE).strip()

    date_match = re.search(r'\b(\d{1,2})[\./](\d{1,2})(?:[\./](\d{4}))?\b', text)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else today.year
        try:
            parsed_date = date(year, month, day)
            if parsed_date > today + timedelta(days=1):
                parsed_date = today
            clean_text = text[:date_match.start()] + text[date_match.end():]
            return parsed_date, clean_text.strip()
        except ValueError:
            pass

    return today, text


def determine_type_and_category(text: str) -> Tuple[str, Optional[str], float]:
    lower = text.lower()

    if any(w in lower for w in ["отложил", "отложила", "в копилку", "на цель", "пополнил цель", "добавил к цели"]):
        return "goal_contribution", None, 0.9

    if any(w in lower for w in ["перевёл", "перевела", "перевод", "перекинул", "перекинула", "с карты на счёт", "со счёта на карту"]):
        return "transfer", "Переводы", 0.95

    income_keywords = ["получил", "получила", "зарплата", "аванс", "пришли", "поступило", "заработал", "заработала", "доход", "кэшбэк", "кешбек"]
    is_income = any(w in lower for w in income_keywords)

    expense_keywords = ["купил", "купила", "потратил", "потратила", "оплатил", "оплатила", "заплатил", "заплатила", "трата", "расход"]
    is_expense = any(w in lower for w in expense_keywords)

    if is_income and not is_expense:
        op_type = "income"
    else:
        op_type = "expense"

    matched_category = None
    confidence = 0.5

    for category, kw_list in CATEGORY_KEYWORDS.items():
        if any(re.search(r'\b' + re.escape(kw) + r'\b', lower) for kw in kw_list):
            matched_category = category
            confidence = 0.95
            break

    if not matched_category:
        matched_category = "Прочее"
        confidence = 0.5

    return op_type, matched_category, confidence


def parse_rule_based(
    text: str,
    author_id: int,
    author_name: str,
    source: str = "text"
) -> Tuple[Optional[OperationDraftSchema], Optional[str]]:
    lower = text.lower()
    for cur in UNSUPPORTED_CURRENCIES:
        if re.search(r'\b' + re.escape(cur) + r'\b', lower):
            return None, "Пока я поддерживаю только рубли"

    amount, remaining_text = extract_amount_and_text(text)
    if not amount or amount <= 0:
        return None, "Не смог найти сумму или сумма меньше 0. Напиши, например: купил кофе за 250 рублей."

    op_date, note_text = extract_date(remaining_text)
    op_type, category, confidence = determine_type_and_category(text)

    cleaned_note = re.sub(r'\b(купил|купила|потратил|потратила|оплатил|оплатила|заплатил|заплатила|получил|получила|зарплата|аванс|отложил|отложила|перевёл|перевела)\b', '', note_text, flags=re.IGNORECASE).strip()
    if not cleaned_note:
        cleaned_note = text

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    draft = OperationDraftSchema(
        id=str(uuid.uuid4()),
        author_telegram_id=author_id,
        author_name=author_name,
        type=op_type,
        amount=amount,
        currency="RUB",
        category=category,
        note=cleaned_note,
        date=op_date,
        confidence=confidence,
        source="voice" if source == "voice" else "text",
        status="pending",
        created_at=now,
        expires_at=now + timedelta(minutes=10)
    )

    return draft, None


async def parse_llm(
    text: str,
    author_id: int,
    author_name: str,
    source: str = "text"
) -> Tuple[Optional[OperationDraftSchema], Optional[str]]:
    if settings.LLM_PROVIDER == "rule_based":
        return parse_rule_based(text, author_id, author_name, source)

    system_prompt = "Ты — модуль распознавания финансовых операций. Верни только валидный JSON без пояснений."

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if settings.LLM_PROVIDER == "ollama":
                url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1/chat/completions"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "model": settings.OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.1
                }
            elif settings.LLM_PROVIDER == "openrouter":
                if not settings.OPENROUTER_API_KEY:
                    return parse_rule_based(text, author_id, author_name, source)
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": settings.OPENROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.1
                }
            else:
                return parse_rule_based(text, author_id, author_name, source)

            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    if data.get("error") == "unsupported_currency":
                        return None, "Пока я поддерживаю только рубли"

                    amount_val = data.get("amount")
                    if amount_val and float(amount_val) > 0:
                        now = datetime.now(timezone.utc).replace(tzinfo=None)
                        draft = OperationDraftSchema(
                            id=str(uuid.uuid4()),
                            author_telegram_id=author_id,
                            author_name=author_name,
                            type=data.get("type", "expense"),
                            amount=Decimal(str(amount_val)),
                            currency="RUB",
                            category=data.get("category", "Прочее"),
                            note=data.get("note", text),
                            date=date.today(),
                            confidence=float(data.get("confidence", 0.9)),
                            source="voice" if source == "voice" else "text",
                            status="pending",
                            created_at=now,
                            expires_at=now + timedelta(minutes=10)
                        )
                        return draft, None
    except Exception:
        pass

    return parse_rule_based(text, author_id, author_name, source)
