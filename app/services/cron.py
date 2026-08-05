"""
Cron-сервис для периодических задач:
- Напоминания о подписках за 2 дня до списания
- Ежемесячный отчёт о личной инфляции на 1-е число
- Еженедельный анализ микро-расходов
"""
import asyncio
import logging
from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.db import User, Transaction, Subscription
from app.services.subscriptions import get_due_reminders, calculate_subscriptions_summary
from app.services.intelligence import (
    calculate_personal_inflation,
    auto_detect_recurring_micro_expenses,
    calculate_payday_and_runway
)

logger = logging.getLogger(__name__)


async def send_subscription_reminders(bot: Bot):
    """Отправить напоминания о подписках, которые спишутся через 2 дня"""
    async with AsyncSessionLocal() as session:
        due_subs = await get_due_reminders(session, days_ahead=2)
        
        if not due_subs:
            logger.info("Нет подписок для напоминания")
            return
        
        # Get all users to notify
        stmt = select(User)
        result = await session.execute(stmt)
        users = list(result.scalars().all())
        
        for sub in due_subs:
            message = (
                f"🔔 **Напоминание о подписке**\n\n"
                f"Через 2 дня спишется:\n"
                f"• **{sub.name}**: {sub.amount:,.0f} ₽\n"
                f"• Дата списания: {sub.next_billing.strftime('%d.%m.%Y')}\n\n"
                f"Проверьте, актуальна ли ещё эта подписка!"
            )
            
            for user in users:
                try:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                    logger.info(f"Отправлено напоминание пользователю {user.telegram_id} о {sub.name}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания пользователю {user.telegram_id}: {e}")


async def send_monthly_inflation_report(bot: Bot):
    """Отправить отчёт о личной инфляции 1-го числа каждого месяца"""
    async with AsyncSessionLocal() as session:
        data = await calculate_personal_inflation(session)
        
        sign = "+" if data["overall_inflation_pct"] > 0 else ""
        
        message = (
            f"📊 **Ваша личная инфляция**\n\n"
            f"Сравнение с прошлым месяцем:\n\n"
            f"• Прошлый месяц: {data['prev_month_total']:,.0f} ₽\n"
            f"• Текущий месяц: {data['curr_month_total']:,.0f} ₽\n"
            f"• Изменение: {sign}{data['overall_inflation_pct']}%\n\n"
        )
        
        if data["categories"]:
            message += "**По категориям:**\n"
            for cat in data["categories"][:5]:
                c_sign = "+" if cat["diff_pct"] > 0 else ""
                message += f"• {cat['category']}: {c_sign}{cat['diff_pct']}%\n"
        
        message += "\n💡 *Отслеживайте свою личную инфляцию — она может отличаться от официальной!*"
        
        # Get all users to notify
        stmt = select(User)
        result = await session.execute(stmt)
        users = list(result.scalars().all())
        
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"Отправлен отчёт об инфляции пользователю {user.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки отчёта пользователю {user.telegram_id}: {e}")


async def send_weekly_micro_expense_insights(bot: Bot):
    """Отправить еженедельный анализ микро-расходов"""
    async with AsyncSessionLocal() as session:
        insights = await auto_detect_recurring_micro_expenses(session, days=30)
        
        if not insights:
            logger.info("Нет микро-расходов для анализа")
            return
        
        total_monthly = sum(i['monthly_estimate'] for i in insights)
        
        message = (
            f"📊 **Анализ микро-расходов за неделю**\n\n"
            f"Найдено повторяющихся мелких трат: {len(insights)}\n\n"
        )
        
        for insight in insights[:5]:
            message += f"• {insight['name']}: ~{insight['monthly_estimate']:,.0f} ₽/мес\n"
        
        if len(insights) > 5:
            message += f"... и ещё {len(insights) - 5}\n"
        
        message += (
            f"\n💸 **Итого:** ~{total_monthly:,.0f} ₽/мес уходит на мелкие траты\n\n"
            f"💡 *Проверьте команду /insights для подробностей*"
        )
        
        # Get all users to notify
        stmt = select(User)
        result = await session.execute(stmt)
        users = list(result.scalars().all())
        
        for user in users:
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"Отправлен анализ микро-расходов пользователю {user.telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки анализа пользователю {user.telegram_id}: {e}")


async def send_evening_reminder(bot: Bot):
    """
    Every evening at 21:00 user local time:
    If NO transactions were registered today by the user, send reminder with 'No expenses today' button.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.services.accounts import get_user_streak
    from zoneinfo import ZoneInfo

    async with AsyncSessionLocal() as session:
        stmt_users = select(User)
        users = list((await session.execute(stmt_users)).scalars().all())

        for user in users:
            try:
                user_tz = ZoneInfo(user.timezone or "Europe/Moscow")
            except Exception:
                user_tz = ZoneInfo("Europe/Moscow")

            user_now = datetime.now(user_tz)
            user_today = user_now.date()

            # Only notify if it's 21:00 or later in user's local timezone, and we haven't notified them today yet
            if user_now.hour >= 21 and (user.last_reminder_date is None or user.last_reminder_date < user_today):
                stmt_tx = select(func.count(Transaction.id)).where(
                    Transaction.author_telegram_id == user.telegram_id,
                    Transaction.date == user_today
                )
                tx_count = (await session.execute(stmt_tx)).scalar()

                if tx_count == 0:
                    streak_val = await get_user_streak(session)
                    streak_str = f" 🔥 {streak_val} дн." if streak_val > 0 else ""

                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🟢 За сегодня не было трат", callback_data="no_expenses_today")],
                        [InlineKeyboardButton(text="➕ Добавить трату", callback_data="add_expense_now")]
                    ])

                    msg = (
                        f"🔔 **Вечерняя проверка финансов**\n\n"
                        f"Сегодня у вас пока нет записей трат.{streak_str}\n"
                        f"Если расходов не было, нажмите кнопку ниже, чтобы поддержать стрик активности!"
                    )
                    try:
                        await bot.send_message(user.telegram_id, msg, reply_markup=kb, parse_mode="Markdown")
                        logger.info(f"Evening reminder sent to user {user.telegram_id}")
                    except Exception as e:
                        logger.error(f"Evening reminder error to {user.telegram_id}: {e}")

                # Mark as reminded for today
                user.last_reminder_date = user_today
                session.add(user)
                await session.commit()


async def send_subscription_billing_notifications(bot: Bot):
    """
    Morning check (09:00 user local time):
    Sends reminder to confirm/postpone subscriptions billing today.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from zoneinfo import ZoneInfo

    async with AsyncSessionLocal() as session:
        stmt_users = select(User)
        users = list((await session.execute(stmt_users)).scalars().all())

        for user in users:
            try:
                user_tz = ZoneInfo(user.timezone or "Europe/Moscow")
            except Exception:
                user_tz = ZoneInfo("Europe/Moscow")

            user_now = datetime.now(user_tz)
            user_today = user_now.date()

            # Process at 09:00 or later, once per day
            if user_now.hour >= 9 and (user.last_sub_check_date is None or user.last_sub_check_date < user_today):
                # Query all active subscriptions
                stmt_subs = select(Subscription).where(Subscription.is_active == True)
                subs = list((await session.execute(stmt_subs)).scalars().all())

                for sub in subs:
                    is_due = False
                    if sub.next_billing and sub.next_billing == user_today:
                        is_due = True
                    elif sub.billing_day and sub.billing_day == user_today.day:
                        if not sub.next_billing or sub.next_billing == user_today:
                            is_due = True

                    if is_due:
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="✅ Оплачено", callback_data=f"sub_pay:paid:{sub.id}")],
                            [InlineKeyboardButton(text="🔄 Перенести", callback_data=f"sub_pay:postpone:{sub.id}")]
                        ])

                        msg = (
                            f"🔔 **День подписки!**\n\n"
                            f"Сегодня день списания подписки **«{sub.name}»**.\n"
                            f"Сумма платежа: **{sub.amount:,.0f} ₽**.\n\n"
                            f"Вы уже оплатили её или хотите перенести платёж?"
                        )
                        try:
                            await bot.send_message(user.telegram_id, msg, reply_markup=kb, parse_mode="Markdown")
                            logger.info(f"Subscription billing notification sent to user {user.telegram_id} for sub {sub.id}")
                        except Exception as e:
                            logger.error(f"Subscription billing notification error to {user.telegram_id}: {e}")

                user.last_sub_check_date = user_today
                session.add(user)
                await session.commit()


async def send_payday_reminder(bot: Bot):
    """
    Morning check (09:00 user local time):
    Checks if today is configured payday date and sends prompt to register salary.
    """
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from app.services.accounts import get_setting_val
    from zoneinfo import ZoneInfo

    async with AsyncSessionLocal() as session:
        stmt_users = select(User)
        users = list((await session.execute(stmt_users)).scalars().all())

        day1 = int(await get_setting_val(session, "payday_day_1", "10"))
        day2 = int(await get_setting_val(session, "payday_day_2", "25"))
        schedule = await get_setting_val(session, "payday_schedule", "2_monthly")
        pay_amount = Decimal(await get_setting_val(session, "payday_amount", "75000"))

        for user in users:
            try:
                user_tz = ZoneInfo(user.timezone or "Europe/Moscow")
            except Exception:
                user_tz = ZoneInfo("Europe/Moscow")

            user_now = datetime.now(user_tz)
            user_today = user_now.date()
            day_num = user_today.day

            # Only notify if it's 09:00 or later in user's local timezone, and we haven't notified them today yet
            if user_now.hour >= 9 and (user.last_payday_reminder_date is None or user.last_payday_reminder_date < user_today):
                is_payday = False
                if schedule == "2_monthly" and (day_num == day1 or day_num == day2):
                    is_payday = True
                elif schedule == "1_monthly" and day_num == day1:
                    is_payday = True
                elif schedule == "daily":
                    is_payday = True

                if is_payday:
                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=f"✅ Внести {pay_amount:,.0f} ₽", callback_data=f"confirm_payday:{int(pay_amount)}")],
                        [InlineKeyboardButton(text="✏️ Другая сумма", callback_data="enter_custom_salary")],
                        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_payday")]
                    ])

                    msg = (
                        f"💰 **День зарплаты!**\n\n"
                        f"Сегодня по вашему графику день получения дохода.\n"
                        f"Ожидаемый оклад: **{pay_amount:,.0f} ₽**.\n\n"
                        f"Хотите зачислить доход и сразу распределить бюджет (50/30/20)?"
                    )
                    try:
                        await bot.send_message(user.telegram_id, msg, reply_markup=kb, parse_mode="Markdown")
                        logger.info(f"Payday reminder sent to user {user.telegram_id}")
                    except Exception as e:
                        logger.error(f"Payday reminder error to {user.telegram_id}: {e}")

                # Mark as reminded for today
                user.last_payday_reminder_date = user_today
                session.add(user)
                await session.commit()


async def run_cron_tasks(bot: Bot):
    """Основной цикл cron-задач"""
    logger.info("Cron-сервис запущен")
    
    last_subscription_check: Optional[date] = None
    last_inflation_report: Optional[int] = None  # month
    last_weekly_insights: Optional[date] = None
    
    while True:
        try:
            now = datetime.now()
            today = now.date()
            
            # Проверка напоминаний о подписках - каждый день в 10:00
            if today != last_subscription_check and now.hour >= 10:
                logger.info(f"Проверка напоминаний о подписках ({today})")
                await send_subscription_reminders(bot)
                last_subscription_check = today
            
            # Напоминание о подписках в день списания
            await send_subscription_billing_notifications(bot)

            # Напоминание о зарплате - утреннее (на основе локального часового пояса пользователя)
            await send_payday_reminder(bot)

            # Вечерняя проверка трат - вечернее (на основе локального часового пояса пользователя)
            await send_evening_reminder(bot)

            # Отчёт об инфляции - 1-го числа в 9:00
            if now.day == 1 and now.month != last_inflation_report and now.hour >= 9:
                logger.info(f"Отправка отчёта об инфляции за {now.strftime('%B %Y')}")
                await send_monthly_inflation_report(bot)
                last_inflation_report = now.month
            
            # Еженедельный анализ микро-расходов - каждый понедельник в 18:00
            if now.weekday() == 0 and today != last_weekly_insights and now.hour >= 18:  # Monday
                logger.info(f"Еженедельный анализ микро-расходов ({today})")
                await send_weekly_micro_expense_insights(bot)
                last_weekly_insights = today
            
            # Sleep 1 minute
            await asyncio.sleep(60)
            
        except asyncio.CancelledError:
            logger.info("Cron-сервис остановлен")
            break
        except Exception as e:
            logger.error(f"Ошибка в cron-задаче: {e}", exc_info=True)
            await asyncio.sleep(60)


async def start_cron_scheduler(bot: Bot):
    """Запустить cron-сервис в фоне"""
    logger.info("Запуск планировщика cron-задач...")
    await run_cron_tasks(bot)
