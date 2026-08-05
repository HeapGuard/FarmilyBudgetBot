import httpx
import logging
import xml.etree.ElementTree as ET
import json
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.db import Setting

logger = logging.getLogger(__name__)

async def update_cbrf_rates(session: AsyncSession):
    """Fetches latest exchange rates from CBRF and stores in settings"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://www.cbr.ru/scripts/XML_daily.asp", timeout=10.0)
            resp.raise_for_status()
            
        # CBRF XML parsing
        # encoding is usually windows-1251, but ET handles bytes correctly
        root = ET.fromstring(resp.content)
        rates = {"RUB": 1.0}
        
        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode").text
            value_str = valute.find("Value").text.replace(",", ".")
            nominal_str = valute.find("Nominal").text
            
            value = float(value_str)
            nominal = float(nominal_str)
            
            rates[char_code] = value / nominal
            
        # Store in DB
        rates_json = json.dumps(rates)
        
        stmt = select(Setting).where(Setting.key == "currency_rates")
        setting = (await session.execute(stmt)).scalar_one_or_none()
        if not setting:
            setting = Setting(key="currency_rates", value=rates_json)
            session.add(setting)
        else:
            setting.value = rates_json
            
        await session.commit()
        logger.info("Обновлены курсы валют ЦБ РФ")
        return rates
    except Exception as e:
        logger.error(f"Ошибка обновления курсов валют: {e}")
        return None

async def convert_to_rub(session: AsyncSession, amount: Decimal, currency: str) -> Decimal:
    """Converts a given amount in a given currency to RUB"""
    if currency.upper() == "RUB" or not currency:
        return amount
        
    stmt = select(Setting).where(Setting.key == "currency_rates")
    setting = (await session.execute(stmt)).scalar_one_or_none()
    if not setting:
        return amount # Fallback if rates not fetched yet
        
    try:
        rates = json.loads(setting.value)
        rate = rates.get(currency.upper(), 1.0)
        return amount * Decimal(str(rate))
    except Exception as e:
        logger.error(f"Ошибка конвертации валюты: {e}")
        return amount
