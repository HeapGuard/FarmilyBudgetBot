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
