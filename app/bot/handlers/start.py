from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.db import User
from app.bot.keyboards import get_main_reply_keyboard
from app.config import settings

import logging

logger = logging.getLogger(__name__)

router = Router()

START_TEXT = (
    "👋 **Привет! Я твой семейный финансовый бот-помощник** 🤖\n\n"
    "Я помогу вам с партнёром вести совместный бюджет легко, быстро и наглядно!\n\n"
    "⚙️ **Что я умею:**\n"
    "• 📊 **Семейный Mini Web App**: Интерактивный дашборд со счетами, целями, бюджетами категорий и наглядными графиками трат.\n"
    "• 🗣 **Голосовой ввод**: Просто запиши аудиосообщение (например, *«потратили 3000 на продукты»*), и я автоматически занесу операцию.\n"
    "• 📁 **Импорт банковских выписок**: Отправь мне скриншот выписки или чека из Т-Банка, Альфа-Банка или Сбербанка — я распознаю его и предложу сохранить операции по отдельности или одной суммой.\n"
    "• 🎯 **Управление целями**: Создавайте цели для накоплений, планируйте взносы и рассчитывайте сложный процент.\n"
    "• 💡 **ИИ-финансовый советник**: Персональные рекомендации и анализ вашего бюджета в реальном времени."
)

HELP_TEXT = (
    "📌 <b>Доступные команды:</b>\n\n"
    "/start — Главное меню\n"
    "/help — Справка по боту\n"
    "/timezone — Настройка часового пояса\n"
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
    last_name = message.from_user.last_name

    # Check authorization (allowed config ids or exists in db)
    is_authorized = False
    if not settings.ALLOWED_TELEGRAM_IDS or user_id in settings.ALLOWED_TELEGRAM_IDS:
        is_authorized = True
    else:
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == user_id)
            db_user = (await session.execute(stmt)).scalar_one_or_none()
            if db_user is not None:
                is_authorized = True

    if is_authorized:
        # Save or update username/first_name/last_name for authorized user
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.telegram_id == user_id)
            res = await session.execute(stmt)
            db_user = res.scalar_one_or_none()
            if not db_user:
                db_user = User(telegram_id=user_id, username=username, first_name=first_name, last_name=last_name)
                session.add(db_user)
            else:
                db_user.username = username
                db_user.first_name = first_name
                db_user.last_name = last_name
            await session.commit()

        url = f"{settings.BASE_URL.rstrip('/')}/app"
        btn = InlineKeyboardButton(text="🌐 Открыть Веб-приложение", web_app=WebAppInfo(url=url)) if url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть Веб-приложение", url=url)
        kb = InlineKeyboardMarkup(inline_keyboard=[[btn]])

        await message.answer("Главное меню доступно на кнопках снизу ⬇️", reply_markup=get_main_reply_keyboard(user_id=user_id))
        await message.answer(START_TEXT, reply_markup=kb, parse_mode="Markdown")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Запросить доступ к бюджету", callback_data="request_join")]
        ])
        await message.answer(START_TEXT, parse_mode="Markdown")
        await message.answer(
            "⚠️ **Доступ ограничен**\n\n"
            "Вы не добавлены в Семейный Бюджет. Нажмите кнопку ниже, чтобы отправить запрос владельцу бюджета.",
            reply_markup=kb,
            parse_mode="Markdown"
        )


@router.callback_query(F.data == "request_join")
async def cb_request_join(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = callback.from_user.username or "нет"
    first_name = callback.from_user.first_name or ""
    last_name = callback.from_user.last_name or ""
    
    admin_ids = settings.ALLOWED_TELEGRAM_IDS if settings.ALLOWED_TELEGRAM_IDS else {1530744928}
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Разрешить", callback_data=f"approve_user:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"deny_user:{user_id}")
        ]
    ])
    
    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔔 **Запрос доступа к Семейному Бюджету!**\n\n"
                    f"• **Telegram ID**: `{user_id}`\n"
                    f"• **Имя**: {first_name} {last_name}\n"
                    f"• **Username**: @{username}\n\n"
                    f"Разрешить доступ этому пользователю?"
                ),
                reply_markup=admin_kb,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to notify owner {admin_id} about join request: {e}")
        
    await callback.message.edit_text(
        "⏳ **Запрос отправлен администратору.**\n\n"
        "Пожалуйста, ожидайте подтверждения доступа. Бот уведомит вас, как только запрос будет рассмотрен.",
        reply_markup=None,
        parse_mode="Markdown"
    )
    await callback.answer("Запрос отправлен!")


@router.callback_query(F.data.startswith("approve_user:"))
async def cb_approve_user(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if settings.ALLOWED_TELEGRAM_IDS and admin_id not in settings.ALLOWED_TELEGRAM_IDS:
        await callback.answer("У вас нет прав для этого действия!", show_alert=True)
        return
        
    target_user_id = int(callback.data.split(":")[1])
    
    try:
        chat = await callback.bot.get_chat(target_user_id)
        username = chat.username
        first_name = chat.first_name
        last_name = chat.last_name
    except Exception:
        username = None
        first_name = "Пользователь"
        last_name = None
        
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == target_user_id)
        db_user = (await session.execute(stmt)).scalar_one_or_none()
        if not db_user:
            db_user = User(
                telegram_id=target_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(db_user)
        else:
            db_user.username = username
            db_user.first_name = first_name
            db_user.last_name = last_name
        await session.commit()
        
    try:
        url = f"{settings.BASE_URL.rstrip('/')}/app"
        btn = InlineKeyboardButton(text="🌐 Открыть Веб-приложение", web_app=WebAppInfo(url=url)) if url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть Веб-приложение", url=url)
        kb = InlineKeyboardMarkup(inline_keyboard=[[btn]])
        
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 **Доступ подтвержден!**\n\n"
                f"Администратор одобрил ваш доступ к Семейному Бюджету.\n"
                f"Теперь вы можете полноценно пользоваться ботом!"
            ),
            reply_markup=get_main_reply_keyboard(user_id=target_user_id),
            parse_mode="Markdown"
        )
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=START_TEXT,
            reply_markup=kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to notify approved user {target_user_id}: {e}")
        
    username_str = f" @{username}" if username else ""
    name_str = f" {first_name or ''} {last_name or ''}".strip()
    await callback.message.edit_text(
        f"✅ **Доступ разрешен** для {name_str}{username_str} (ID: `{target_user_id}`).",
        reply_markup=None,
        parse_mode="Markdown"
    )
    await callback.answer("Пользователь одобрен!")


@router.callback_query(F.data.startswith("deny_user:"))
async def cb_deny_user(callback: CallbackQuery):
    admin_id = callback.from_user.id
    if settings.ALLOWED_TELEGRAM_IDS and admin_id not in settings.ALLOWED_TELEGRAM_IDS:
        await callback.answer("У вас нет прав для этого действия!", show_alert=True)
        return
        
    target_user_id = int(callback.data.split(":")[1])
    
    try:
        chat = await callback.bot.get_chat(target_user_id)
        username = chat.username
        first_name = chat.first_name
        last_name = chat.last_name
    except Exception:
        username = None
        first_name = "Пользователь"
        last_name = None
        
    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text="❌ К сожалению, ваш запрос на доступ к Семейному Бюджету был отклонен администратором.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to notify denied user {target_user_id}: {e}")
        
    username_str = f" @{username}" if username else ""
    name_str = f" {first_name or ''} {last_name or ''}".strip()
    await callback.message.edit_text(
        f"❌ **Запрос отклонен** для {name_str}{username_str} (ID: `{target_user_id}`).",
        reply_markup=None,
        parse_mode="Markdown"
    )
    await callback.answer("Запрос отклонен.")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(PRIVACY_TEXT, parse_mode="HTML")


@router.message(Command("open_app"))
async def cmd_open_app(message: Message):
    url = f"{settings.BASE_URL.rstrip('/')}/app"
    btn = InlineKeyboardButton(text="🌐 Открыть Веб-приложение", web_app=WebAppInfo(url=url)) if url.startswith("https://") else InlineKeyboardButton(text="🌐 Открыть Веб-приложение", url=url)
    kb = InlineKeyboardMarkup(inline_keyboard=[[btn]])
    await message.answer("🌐 Нажмите на кнопку ниже, чтобы открыть веб-приложение:", reply_markup=kb)


@router.message(Command("timezone"))
async def cmd_timezone(message: Message):
    user_id = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        current_tz = user.timezone if user else "Europe/Moscow"
        
    tz_list = [
        ("Europe/Kaliningrad", "Калининград (UTC+2)"),
        ("Europe/Moscow", "Москва (UTC+3)"),
        ("Europe/Samara", "Самара (UTC+4)"),
        ("Asia/Yekaterinburg", "Екатеринбург (UTC+5)"),
        ("Asia/Omsk", "Омск (UTC+6)"),
        ("Asia/Tomsk", "Томск (UTC+7)"),
        ("Asia/Novosibirsk", "Новосибирск (UTC+7)"),
        ("Asia/Krasnoyarsk", "Красноярск (UTC+7)"),
        ("Asia/Irkutsk", "Иркутск (UTC+8)"),
        ("Asia/Yakutsk", "Якутск (UTC+9)"),
        ("Asia/Vladivostok", "Владивосток (UTC+10)"),
        ("Asia/Magadan", "Магадан (UTC+11)"),
        ("Asia/Kamchatka", "Kamchatka (UTC+12)")
    ]
    
    buttons = []
    row = []
    for tz_code, tz_name in tz_list:
        row.append(InlineKeyboardButton(text=tz_name, callback_data=f"set_tz:{tz_code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        f"⚙️ **Настройка часового пояса**\n\n"
        f"Ваш текущий часовой пояс: `{current_tz}`\n\n"
        f"Выберите ваш город или часовой пояс из списка ниже:",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("set_tz:"))
async def cb_set_tz(callback: CallbackQuery):
    user_id = callback.from_user.id
    new_tz = callback.data.split(":")[1]
    
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.telegram_id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            user.timezone = new_tz
            session.add(user)
            await session.commit()
            
    await callback.message.edit_text(
        f"✅ **Часовой пояс успешно изменен!**\n\n"
        f"Новый часовой пояс: `{new_tz}`\n\n"
        f"Вечерние напоминания о записи расходов будут приходить ровно в **21:00** по вашему местному времени.",
        reply_markup=None,
        parse_mode="Markdown"
    )
    await callback.answer("Часовой пояс изменен!")
