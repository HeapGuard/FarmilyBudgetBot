from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.db import User
from app.bot.keyboards import get_main_menu_keyboard, get_main_reply_keyboard

router = Router()

START_TEXT = (
    "Привет! Я считаю доходы и расходы, помогаю копить на цели и даю советы только когда ты этого захочешь."
)

HELP_TEXT = (
    "📌 <b>Доступные команды:</b>\n\n"
    "/start — Главное меню\n"
    "/help — Справка по боту\n"
    "/add — Добавить операцию текстом или голосом\n"
    "/balance — Показать балансы счетов\n"
    "/accounts — Настройка счетов (Основной, Накопительный, Вклад)\n"
    "/set_balance — Установить стартовый баланс\n"
    "/report — Отчёт за текущий месяц\n"
    "/goals — Список целей\n"
    "/goal_new — Мастер создания новой цели\n"
    "/advice — Получить персональные советы\n"
    "/open_app — Ссылка на Mini Web App\n"
    "/export — Выгрузить CSV с данными\n"
    "/privacy — Справка о приватности\n"
    "/delete_all — Удалить все данные"
)

PRIVACY_TEXT = (
    "🔒 <b>Приватность и безопасность:</b>\n\n"
    "Данные хранятся только в этом боте и в Mini App. Мы не подключаем банки, "
    "не запрашиваем пароли, seed-фразы и коды. Голосовые сообщения обрабатываются "
    "для распознавания и не сохраняются. Ты можешь удалить все данные командой /delete_all."
)


@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == user_id)
        res = await session.execute(stmt)
        db_user = res.scalar_one_or_none()
        if not db_user:
            db_user = User(telegram_id=user_id, username=username, first_name=first_name)
            session.add(db_user)
        else:
            db_user.username = username
            db_user.first_name = first_name
        await session.commit()

    # Send persistent reply keyboard first or with message
    await message.answer("Главное меню доступно на кнопках снизу ⬇️", reply_markup=get_main_reply_keyboard(user_id=user_id))
    await message.answer(START_TEXT, reply_markup=get_main_menu_keyboard(user_id=user_id))


@router.callback_query(F.data == "btn_main_menu")
async def cb_main_menu(callback: CallbackQuery):
    user_id = callback.from_user.id if callback.from_user else None
    await callback.message.answer(START_TEXT, reply_markup=get_main_menu_keyboard(user_id=user_id))
    await callback.answer()



@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(PRIVACY_TEXT)


@router.message(Command("open_app"))
async def cmd_open_app(message: Message):
    from app.config import settings
    from aiogram.types import WebAppInfo
    user_id = message.from_user.id if message.from_user else None
    url = f"{settings.BASE_URL.rstrip('/')}/app"
    if user_id:
        url += f"?uid={user_id}"
    btn = InlineKeyboardButton(text="🌐 Открыть Веб-приложение", web_app=WebAppInfo(url=url)) if url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть Веб-приложение", url=url)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_main_menu")]
    ])
    await message.answer("🌐 Нажмите на кнопку ниже, чтобы открыть веб-приложение:", reply_markup=kb)


@router.callback_query(F.data == "btn_app_info")
async def cb_app_info(callback: CallbackQuery):
    from app.config import settings
    from aiogram.types import WebAppInfo
    user_id = callback.from_user.id if callback.from_user else None
    url = f"{settings.BASE_URL.rstrip('/')}/app"
    if user_id:
        url += f"?uid={user_id}"
    btn = InlineKeyboardButton(text="🌐 Открыть Веб-приложение", web_app=WebAppInfo(url=url)) if url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть Веб-приложение", url=url)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [btn],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_main_menu")]
    ])
    await callback.message.answer(
        f"🌐 <b>Веб-приложение</b>\n\nСсылка: {url}",
        reply_markup=kb
    )
    await callback.answer()



@router.callback_query(F.data == "btn_settings")
async def cb_settings(callback: CallbackQuery):
    await callback.message.answer(
        "⚙️ <b>Настройки:</b>\n\n"
        "• Валюта: RUB\n"
        "• Настройки баланса: /set_balance\n"
        "• Экспорт данных: /export\n"
        "• Полная очистка: /delete_all"
    )
    await callback.answer()
