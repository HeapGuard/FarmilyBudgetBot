from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.subscriptions import (
    get_all_subscriptions,
    calculate_subscriptions_summary,
    auto_detect_subscriptions,
    delete_subscription
)

router = Router()


@router.message(Command("subscriptions", "subs"))
async def cmd_subscriptions(message: Message, session: AsyncSession):
    subs = await get_all_subscriptions(session)
    app_url = f"{settings.BASE_URL.rstrip('/')}/app#subs"
    btn_webapp = InlineKeyboardButton(text="🌐 Открыть в WebApp", web_app=WebAppInfo(url=app_url)) if app_url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть в WebApp", url=app_url)

    if not subs:
        text = (
            "📱 **Управление подписками**\n\n"
            "У вас пока нет сохранённых подписок.\n"
            "Вы можете добавить их вручную или запустить автодетект из истории трат."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти подписки в истории", callback_data="subs_autodetect")],
            [btn_webapp]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")
        return

    summary = calculate_subscriptions_summary(subs)
    lines = ["📱 **Ваши подписки:**\n"]
    for s in subs:
        status_icon = "🟢" if s.is_active else "⏸"
        period_str = "мес" if s.period == "monthly" else ("год" if s.period == "yearly" else "кв")
        billing_str = f" (след. {s.next_billing.strftime('%d.%m')})" if s.next_billing else ""
        lines.append(f"{status_icon} **{s.name}**: {s.amount:,.0f} ₽/{period_str}{billing_str}")

    lines.append("\n─────────────────")
    lines.append(f"💸 **Итого в месяц:** {summary['total_monthly']:,.0f} ₽")
    lines.append(f"📅 **Итого в год:** {summary['total_yearly']:,.0f} ₽")

    kb_buttons = [
        [InlineKeyboardButton(text="🔍 Автодетект подписок", callback_data="subs_autodetect")],
        [btn_webapp]
    ]
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="Markdown")


@router.callback_query(F.data == "subs_autodetect")
async def cb_subs_autodetect(callback: CallbackQuery, session: AsyncSession):
    detected = await auto_detect_subscriptions(session)
    if not detected:
        await callback.answer("Повторяющихся подписок в истории трат не найдено.", show_alert=True)
        return

    text_lines = ["🔍 **Найдены повторяющиеся платежи:**\n"]
    for item in detected:
        text_lines.append(f"• **{item['name']}**: ~{item['amount']:,.0f} ₽ ({item['count']} совпадений)")
    text_lines.append("\nДобавьте их через WebApp во вкладке «Подписки».")

    app_url = f"{settings.BASE_URL.rstrip('/')}/app#subs"
    btn_webapp = InlineKeyboardButton(text="🌐 Открыть WebApp", web_app=WebAppInfo(url=app_url)) if app_url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть WebApp", url=app_url)

    kb = InlineKeyboardMarkup(inline_keyboard=[[btn_webapp]])
    await callback.message.answer("\n".join(text_lines), reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


# --- Subscription Payments Confirmation Handlers ---

from datetime import date, timedelta
import calendar

def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

@router.callback_query(F.data.startswith("sub_pay:paid:"))
async def cb_sub_pay_paid(callback: CallbackQuery, session: AsyncSession):
    sub_id = int(callback.data.split("sub_pay:paid:")[1])
    from app.models.db import Subscription, SubscriptionPayment, Transaction, Account
    from sqlalchemy import select

    sub = await session.get(Subscription, sub_id)
    if not sub:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    # Create transaction
    # Find default card
    stmt_acc = select(Account).where(Account.type == "card", Account.is_active == True)
    card = (await session.execute(stmt_acc)).scalars().first()
    
    tx = Transaction(
        author_telegram_id=callback.from_user.id,
        type="expense",
        amount=sub.amount,
        currency="RUB",
        category=sub.category or "Подписки",
        note=f"Оплата подписки «{sub.name}»",
        date=date.today(),
        source="bot",
        confidence=1.0,
        account_id=card.id if card else None
    )
    session.add(tx)
    if card:
        card.balance -= sub.amount
        session.add(card)

    # Log payment status
    payment = SubscriptionPayment(
        subscription_id=sub.id,
        date=date.today(),
        status="paid"
    )
    session.add(payment)

    # Advance next_billing date
    base_date = sub.next_billing or date.today()
    sub.next_billing = add_months(base_date, 1)
    session.add(sub)

    await session.commit()

    await callback.message.edit_text(f"✅ Подписка **«{sub.name}»** отмечена как оплаченная! Расход {sub.amount:,.0f} ₽ добавлен.".replace(",", " "))
    await callback.answer("Сохранено!")


@router.callback_query(F.data.startswith("sub_pay:postpone:"))
async def cb_sub_pay_postpone(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_pay:postpone:")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Единоразово (перенести на дату)", callback_data=f"sub_pay:postpone_once:{sub_id}")],
        [InlineKeyboardButton(text="⚙️ Насовсем (изменить день)", callback_data=f"sub_pay:postpone_perm:{sub_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"sub_pay:cancel:{sub_id}")]
    ])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sub_pay:cancel:"))
async def cb_sub_pay_cancel(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_pay:cancel:")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплачено", callback_data=f"sub_pay:paid:{sub_id}")],
        [InlineKeyboardButton(text="🔄 Перенести", callback_data=f"sub_pay:postpone:{sub_id}")]
    ])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sub_pay:postpone_once:"))
async def cb_sub_pay_postpone_once(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_pay:postpone_once:")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Завтра", callback_data=f"sub_pay:postpone_once_to:{sub_id}:1")],
        [InlineKeyboardButton(text="Через 3 дня", callback_data=f"sub_pay:postpone_once_to:{sub_id}:3")],
        [InlineKeyboardButton(text="Через неделю", callback_data=f"sub_pay:postpone_once_to:{sub_id}:7")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"sub_pay:postpone:{sub_id}")]
    ])
    await callback.message.edit_text("Выберите срок переноса платежа (единоразово):", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sub_pay:postpone_once_to:"))
async def cb_sub_pay_postpone_once_to(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    sub_id = int(parts[2])
    days = int(parts[3])

    from app.models.db import Subscription, SubscriptionPayment
    sub = await session.get(Subscription, sub_id)
    if not sub:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    new_date = date.today() + timedelta(days=days)

    payment = SubscriptionPayment(
        subscription_id=sub.id,
        date=date.today(),
        status="postponed_once",
        postponed_to=new_date
    )
    session.add(payment)

    # Temporary update sub next_billing
    sub.next_billing = new_date
    session.add(sub)
    await session.commit()

    await callback.message.edit_text(f"🔄 Оплата подписки **«{sub.name}»** перенесена на **{new_date.strftime('%d.%m.%Y')}**.")
    await callback.answer("Перенесено!")


@router.callback_query(F.data.startswith("sub_pay:postpone_perm:"))
async def cb_sub_pay_postpone_perm(callback: CallbackQuery):
    sub_id = int(callback.data.split("sub_pay:postpone_perm:")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5-е число", callback_data=f"sub_pay:postpone_perm_to:{sub_id}:5"),
         InlineKeyboardButton(text="10-е число", callback_data=f"sub_pay:postpone_perm_to:{sub_id}:10")],
        [InlineKeyboardButton(text="15-е число", callback_data=f"sub_pay:postpone_perm_to:{sub_id}:15"),
         InlineKeyboardButton(text="20-е число", callback_data=f"sub_pay:postpone_perm_to:{sub_id}:20")],
        [InlineKeyboardButton(text="25-е число", callback_data=f"sub_pay:postpone_perm_to:{sub_id}:25"),
         InlineKeyboardButton(text="30-е число", callback_data=f"sub_pay:postpone_perm_to:{sub_id}:30")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"sub_pay:postpone:{sub_id}")]
    ])
    await callback.message.edit_text("Выберите новый ежемесячный день списания:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sub_pay:postpone_perm_to:"))
async def cb_sub_pay_postpone_perm_to(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    sub_id = int(parts[2])
    day = int(parts[3])

    from app.models.db import Subscription, SubscriptionPayment
    sub = await session.get(Subscription, sub_id)
    if not sub:
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    sub.billing_day = day
    # Recalculate next_billing based on this day
    today = date.today()
    if today.day <= day:
        sub.next_billing = date(today.year, today.month, day)
    else:
        sub.next_billing = add_months(date(today.year, today.month, day), 1)

    session.add(sub)

    payment = SubscriptionPayment(
        subscription_id=sub.id,
        date=date.today(),
        status="postponed_perm"
    )
    session.add(payment)

    await session.commit()

    await callback.message.edit_text(f"⚙️ День списания подписки **«{sub.name}»** навсегда изменён на **{day}-е число** каждого месяца!")
    await callback.answer("Изменено!")
