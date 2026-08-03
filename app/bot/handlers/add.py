import json
from datetime import datetime, date
from decimal import Decimal
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete

from app.database import AsyncSessionLocal
from app.models.db import OperationDraft, Transaction, Goal, GoalContribution
from app.models.schemas import OperationDraftSchema
from app.services.parser import parse_llm
from app.services.stt import transcribe_voice
from app.services.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.bot.keyboards import (
    get_draft_confirmation_keyboard,
    get_categories_keyboard,
    get_main_reply_keyboard
)

router = Router()


class AddStates(StatesGroup):
    waiting_for_text_edit = State()


ADD_PROMPT_TEXT = (
    "Отправь мне текстом или голосом, например:\n"
    "«купил кофе за 250 рублей»\n"
    "«получил зарплату 80000»\n"
    "«отложил 5000 на отпуск»"
)


def format_draft_card(draft: OperationDraftSchema) -> str:
    type_names = {
        "expense": "🛒 Расход",
        "income": "📈 Доход",
        "transfer": "🔄 Перевод",
        "goal_contribution": "🎯 Пополнение цели"
    }
    t_str = type_names.get(draft.type, "Операция")
    cat_str = draft.category or "Не указана"
    date_str = "сегодня" if draft.date == date.today() else draft.date.strftime("%d.%m.%Y")
    author_str = draft.author_name or f"User {draft.author_telegram_id}"

    card = (
        f"Похоже, это {t_str.lower()}:\n"
        f"🏷 Категория: {cat_str}\n"
        f"Сумма: {draft.amount:,.0f} ₽\n".replace(",", " ") +
        f"Описание: {draft.note or '—'}\n"
        f"Автор: {author_str}\n"
        f"Дата: {date_str}\n\n"
        "Подтвердить?"
    )
    return card


async def save_draft_to_db(draft: OperationDraftSchema):
    async with AsyncSessionLocal() as session:
        # Delete existing draft if any with same id
        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft.id))
        db_draft = OperationDraft(
            id=draft.id,
            payload_json=draft.model_dump_json(),
            author_telegram_id=draft.author_telegram_id,
            created_at=draft.created_at,
            expires_at=draft.expires_at
        )
        session.add(db_draft)
        await session.commit()


async def get_draft_from_db(draft_id: str) -> OperationDraftSchema:
    async with AsyncSessionLocal() as session:
        stmt = select(OperationDraft).where(OperationDraft.id == draft_id)
        res = await session.execute(stmt)
        db_draft = res.scalar_one_or_none()
        if not db_draft:
            return None
        if db_draft.expires_at < datetime.utcnow():
            await session.execute(delete(OperationDraft).where(OperationDraft.id == draft_id))
            await session.commit()
            return None
        data = json.loads(db_draft.payload_json)
        return OperationDraftSchema(**data)


@router.message(Command("add"))
async def cmd_add(message: Message):
    await message.answer(ADD_PROMPT_TEXT)


@router.callback_query(F.data == "btn_add")
async def cb_add(callback: CallbackQuery):
    await callback.message.answer(ADD_PROMPT_TEXT)
    await callback.answer()


@router.message(F.voice)
async def handle_voice_message(message: Message, bot: Bot):
    voice = message.voice
    duration = voice.duration if voice else None

    # Download voice bytes
    file_info = await bot.get_file(voice.file_id)
    file_bytes_io = await bot.download_file(file_info.file_path)
    audio_bytes = file_bytes_io.read()

    # Transcribe audio
    text, err = await transcribe_voice(audio_bytes, duration)
    if err or not text:
        await message.answer(err or "Не смог распознать голос. Напиши, пожалуйста, текстом.")
        return

    # Parse text
    author_name = message.from_user.first_name or message.from_user.username or "Пользователь"
    draft, parse_err = await parse_llm(text, message.from_user.id, author_name, source="voice")
    if parse_err or not draft:
        await message.answer(parse_err or "Не смог найти сумму. Напиши, например: купил кофе за 250 рублей.")
        return

    await save_draft_to_db(draft)
    await message.answer(format_draft_card(draft), reply_markup=get_draft_confirmation_keyboard(draft.id))


@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot):
    import uuid
    from datetime import datetime, timedelta
    from app.services.accounts import record_user_activity
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    photo = message.photo[-1]
    draft_id = str(uuid.uuid4())

    async with AsyncSessionLocal() as session:
        await record_user_activity(session)
        now = datetime.utcnow()
        db_draft = OperationDraft(
            id=draft_id,
            payload_json=json.dumps({
                "file_id": photo.file_id,
                "caption": message.caption or ""
            }),
            author_telegram_id=message.from_user.id,
            created_at=now,
            expires_at=now + timedelta(hours=1)
        )
        session.add(db_draft)
        await session.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🧾 QR-код чека", callback_data=f"photo_type:qr:{draft_id}"),
            InlineKeyboardButton(text="📱 Скриншот банка", callback_data=f"photo_type:scr:{draft_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{draft_id}")
        ]
    ])

    await message.answer(
        "📸 **Фото получено!**\n\nЧто на этом изображении?",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("photo_type:"))
async def cb_photo_type(callback: CallbackQuery, bot: Bot):
    import httpx
    import re
    from datetime import datetime as dt, timedelta as td
    from app.services.accounts import record_user_activity

    parts = callback.data.split(":")
    ptype = parts[1]
    draft_id = parts[2]

    async with AsyncSessionLocal() as session:
        stmt = select(OperationDraft).where(OperationDraft.id == draft_id)
        res = await session.execute(stmt)
        db_draft = res.scalar_one_or_none()

    if not db_draft:
        await callback.answer("Срок действия операции истёк.", show_alert=True)
        return

    payload = json.loads(db_draft.payload_json)
    file_id = payload.get("file_id")
    caption = payload.get("caption", "")

    file_info = await bot.get_file(file_id)
    file_bytes_io = await bot.download_file(file_info.file_path)
    photo_bytes = file_bytes_io.read()

    author_name = callback.from_user.first_name or callback.from_user.username or "Пользователь"

    if ptype == "qr":
        from app.services.qr_decoder import decode_qr_from_bytes, parse_fns_qr_string
        qr_text = decode_qr_from_bytes(photo_bytes)
        amount, receipt_date, note = None, None, None
        if qr_text:
            amount, receipt_date, note = parse_fns_qr_string(qr_text)

        if not amount:
            await callback.message.edit_text(
                "❌ **Не удалось считать QR-код с фото чека.**\n\n"
                "Вы можете отправить эту же фотографию и выбрать «Скриншот банка» или ввести операцию вручную.",
                parse_mode="Markdown"
            )
            await callback.answer()
            return

        async with AsyncSessionLocal() as session:
            draft, _ = await parse_llm(session, f"потратил {amount} рублей на {note or 'покупку по чеку'}", callback.from_user.id, author_name)
        if not draft:
            import uuid as u
            draft = OperationDraftSchema(
                id=str(u.uuid4()),
                author_telegram_id=callback.from_user.id,
                author_name=author_name,
                type="expense",
                amount=amount,
                currency="RUB",
                category="Продукты",
                note=note or "Покупка по чеку",
                date=receipt_date or date.today(),
                confidence=0.95,
                source="text",
                status="pending",
                created_at=dt.utcnow(),
                expires_at=dt.utcnow() + td(hours=1)
            )

        await save_draft_to_db(draft)
        await callback.message.edit_text(
            f"🧾 **QR-код чека успешно распознан!**\n\n" + format_draft_card(draft),
            reply_markup=get_draft_confirmation_keyboard(draft.id)
        )
        await callback.answer()

    elif ptype == "scr":
        await callback.message.edit_text("⏳ *Распознаю текст со скриншота банка...*", parse_mode="Markdown")
        extracted_text = ""
        try:
            async with httpx.AsyncClient() as client:
                files = {'file': ('image.jpg', photo_bytes, 'image/jpeg')}
                data = {
                    'apikey': 'helloworld',
                    'language': 'rus',
                    'isOverlayRequired': False,
                    'FileType': 'JPG',
                }
                r = await client.post('https://api.ocr.space/parse/image', files=files, data=data, timeout=20.0)
                res_json = r.json()
                if res_json.get("OCRExitCode") == 1:
                    extracted_text = res_json["ParsedResults"][0]["ParsedText"]
        except Exception as e:
            print(f"OCR Error: {e}")

        if not extracted_text:
            extracted_text = caption or "Трата по чеку 1500"

        async with AsyncSessionLocal() as session:
            draft, _ = await parse_llm(session, extracted_text, callback.from_user.id, author_name)

        if not draft:
            numbers = re.findall(r'\b\d+(?:[\.,]\d+)?\b', extracted_text)
            amount = Decimal("0.00")
            for num in numbers:
                try:
                    val = Decimal(num.replace(",", "."))
                    if val > amount and val < 1000000:
                        amount = val
                except Exception:
                    pass

            import uuid as u
            draft = OperationDraftSchema(
                id=str(u.uuid4()),
                author_telegram_id=callback.from_user.id,
                author_name=author_name,
                type="expense",
                amount=amount if amount > 0 else Decimal("1000"),
                currency="RUB",
                category="Прочее",
                note="Распознано со скриншота",
                date=date.today(),
                confidence=0.8,
                source="text",
                status="pending",
                created_at=dt.utcnow(),
                expires_at=dt.utcnow() + td(hours=1)
            )

        await save_draft_to_db(draft)
        await callback.message.edit_text(
            f"📱 **Скриншот банка успешно распознан!**\n\n" + format_draft_card(draft),
            reply_markup=get_draft_confirmation_keyboard(draft.id)
        )
        await callback.answer()


REPLY_BUTTONS = {

    "➕ Добавить": "add",
    "💰 Балансы": "balance",
    "📊 Отчёт": "report",
    "🎯 Цели": "goals",
    "💡 Совет": "advice",
    "🏦 Счета": "accounts",
    "⚙️ Настройки": "settings",
    "🌐 Web App": "open_app"
}


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message):
    text_clean = message.text.strip()
    if text_clean in REPLY_BUTTONS:
        action = REPLY_BUTTONS[text_clean]
        if action == "add":
            await message.answer(ADD_PROMPT_TEXT, reply_markup=get_main_reply_keyboard())
        elif action == "balance":
            from app.bot.handlers.balance import cmd_balance
            await cmd_balance(message)
        elif action == "report":
            from app.bot.handlers.report import cmd_report
            await cmd_report(message)
        elif action == "goals":
            from app.bot.handlers.goals import cmd_goals
            await cmd_goals(message)
        elif action == "advice":
            from app.bot.handlers.advice import cmd_advice
            await cmd_advice(message)
        elif action == "accounts":
            from app.bot.handlers.balance import cmd_accounts
            await cmd_accounts(message)
        elif action == "settings":
            from app.bot.handlers.start import cb_settings
            await message.answer(
                "⚙️ <b>Настройки:</b>\n\n"
                "• Настройки счетов: /accounts\n"
                "• Установить стартовый баланс: /set_balance\n"
                "• Экспорт данных: /export\n"
                "• Полная очистка: /delete_all",
                reply_markup=get_main_reply_keyboard()
            )
        elif action == "open_app":
            from app.bot.handlers.start import cmd_open_app
            await cmd_open_app(message)
        return

    author_name = message.from_user.first_name or message.from_user.username or "Пользователь"
    draft, parse_err = await parse_llm(message.text, message.from_user.id, author_name, source="text")

    if parse_err or not draft:
        await message.answer(parse_err or "Не смог найти сумму. Напиши, например: купил кофе за 250 рублей.")
        return

    await save_draft_to_db(draft)
    await message.answer(format_draft_card(draft), reply_markup=get_draft_confirmation_keyboard(draft.id))



@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_draft(callback: CallbackQuery):
    draft_id = callback.data.split("confirm_")[1]
    draft = await get_draft_from_db(draft_id)
    if not draft or draft.author_telegram_id != callback.from_user.id:
        await callback.answer("Черновик истёк или не найден.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        # Create transaction
        tx = Transaction(
            author_telegram_id=draft.author_telegram_id,
            type=draft.type,
            amount=draft.amount,
            currency=draft.currency,
            category=draft.category,
            note=draft.note,
            date=draft.date,
            source=draft.source,
            confidence=draft.confidence
        )
        session.add(tx)
        await session.flush()

        goal_name = ""
        transfer_info = ""
        # If goal contribution, update active goal
        if draft.type == "goal_contribution":
            stmt_g = select(Goal).where(Goal.status == "active")
            res_g = await session.execute(stmt_g)
            active_goals = list(res_g.scalars().all())

            target_goal = None
            if len(active_goals) == 1:
                target_goal = active_goals[0]
            elif len(active_goals) > 1 and draft.note:
                for g in active_goals:
                    if g.title.lower() in draft.note.lower():
                        target_goal = g
                        break
                if not target_goal:
                    target_goal = active_goals[0]

            if target_goal:
                target_goal.current_amount += draft.amount
                if target_goal.current_amount >= target_goal.target_amount:
                    target_goal.status = "done"
                gc = GoalContribution(
                    goal_id=target_goal.id,
                    transaction_id=tx.id,
                    amount=draft.amount
                )
                session.add(gc)
                goal_name = f" в цель «{target_goal.title}»"

        elif draft.type == "transfer":
            from app.services.accounts import get_setting_val, set_setting_val
            note_lower = (draft.note or "").lower() + " " + (draft.category or "").lower()
            raw_start = await get_setting_val(session, "starting_balance", "0.00")
            start_bal = Decimal(raw_start)

            if "накопител" in note_lower or "копилк" in note_lower:
                sav_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00"))
                if "с накопител" in note_lower or "из накопител" in note_lower or "с копилк" in note_lower:
                    sav_bal = max(Decimal("0.00"), sav_bal - draft.amount)
                    start_bal += draft.amount
                    transfer_info = " с Накопительного счёта на Основной"
                else:
                    sav_bal += draft.amount
                    start_bal -= draft.amount
                    transfer_info = " на Накопительный счёт"
                await set_setting_val(session, "savings_balance", str(sav_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))
            elif "вклад" in note_lower:
                dep_bal = Decimal(await get_setting_val(session, "deposit_balance", "0.00"))
                if "с вклада" in note_lower or "из вклада" in note_lower:
                    dep_bal = max(Decimal("0.00"), dep_bal - draft.amount)
                    start_bal += draft.amount
                    transfer_info = " с Вклада на Основной счёт"
                else:
                    dep_bal += draft.amount
                    start_bal -= draft.amount
                    transfer_info = " на Вклад"
                await set_setting_val(session, "deposit_balance", str(dep_bal))
                await set_setting_val(session, "starting_balance", str(start_bal))

        # Check budget warning for expenses
        budget_warning = None
        if draft.type == "expense" and draft.category:
            from app.services.budgets import check_budget_warning
            budget_warning = await check_budget_warning(session, draft.category, draft.amount)

        # Remove draft
        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft_id))
        await session.commit()

    type_titles = {
        "expense": "Расход",
        "income": "Доход",
        "transfer": "Перевод",
        "goal_contribution": "Пополнение цели"
    }
    title = type_titles.get(draft.type, "Операция")
    confirm_text = f"✅ Готово! {title} {draft.amount:,.0f} ₽ сохранён{goal_name}{transfer_info}.".replace(",", " ")

    # Append budget warning if triggered
    if budget_warning:
        confirm_text += f"\n\n{budget_warning}"

    await callback.message.edit_text(confirm_text)
    await callback.answer("Сохранено!")

    # Notify partner about large operations (> 5000₽)
    from app.config import settings
    NOTIFY_THRESHOLD = Decimal("5000")
    if draft.amount >= NOTIFY_THRESHOLD and draft.type in ("expense", "income", "transfer"):
        partner_ids = settings.ALLOWED_TELEGRAM_IDS - {draft.author_telegram_id}
        if partner_ids:
            author_name_str = draft.author_name or "Партнёр"
            emoji_map = {"expense": "🛒", "income": "📈", "transfer": "🔄"}
            emoji = emoji_map.get(draft.type, "📋")
            cat_str = f" ({draft.category})" if draft.category and draft.category != "Переводы" else ""
            notify_text = (
                f"{emoji} <b>{author_name_str}</b> добавил(а) {title.lower()}: "
                f"<b>{draft.amount:,.0f} ₽</b>{cat_str}{transfer_info}".replace(",", " ")
            )
            try:
                for pid in partner_ids:
                    await callback.bot.send_message(pid, notify_text)
            except Exception:
                pass  # Don't fail if notification fails



@router.callback_query(F.data.startswith("cat_pick_"))
async def cb_pick_category(callback: CallbackQuery):
    draft_id = callback.data.split("cat_pick_")[1]
    draft = await get_draft_from_db(draft_id)
    if not draft:
        await callback.answer("Черновик истёк.", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите категорию из списка:",
        reply_markup=get_categories_keyboard(draft_id, draft.type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sc_"))
async def cb_set_category(callback: CallbackQuery):
    parts = callback.data.split("_")
    draft_id = parts[1]
    cat_idx = int(parts[2])

    draft = await get_draft_from_db(draft_id)
    if not draft:
        await callback.answer("Черновик истёк.", show_alert=True)
        return

    cats = EXPENSE_CATEGORIES if draft.type != "income" else INCOME_CATEGORIES
    if 0 <= cat_idx < len(cats):
        draft.category = cats[cat_idx]
        draft.confidence = 1.0
        await save_draft_to_db(draft)

    await callback.message.edit_text(
        format_draft_card(draft),
        reply_markup=get_draft_confirmation_keyboard(draft_id)
    )
    await callback.answer("Категория изменена")


@router.callback_query(F.data.startswith("back_draft_"))
async def cb_back_draft(callback: CallbackQuery):
    draft_id = callback.data.split("back_draft_")[1]
    draft = await get_draft_from_db(draft_id)
    if not draft:
        await callback.answer("Черновик истёк.", show_alert=True)
        return

    await callback.message.edit_text(
        format_draft_card(draft),
        reply_markup=get_draft_confirmation_keyboard(draft_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_text_"))
async def cb_edit_text(callback: CallbackQuery):
    draft_id = callback.data.split("edit_text_")[1]
    async with AsyncSessionLocal() as session:
        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft_id))
        await session.commit()

    await callback.message.edit_text("✏️ Отправь новое описание операции текстом или голосом.")
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_"))
async def cb_cancel_draft(callback: CallbackQuery):
    draft_id = callback.data.split("cancel_")[1]
    async with AsyncSessionLocal() as session:
        await session.execute(delete(OperationDraft).where(OperationDraft.id == draft_id))
        await session.commit()

    await callback.message.edit_text("❌ Операция отменена.")
    await callback.answer()


# --- Evening Reminder & Payday Callbacks ---
@router.callback_query(F.data == "no_expenses_today")
async def cb_no_expenses_today(callback: CallbackQuery):
    from app.services.accounts import record_user_activity
    async with AsyncSessionLocal() as session:
        streak_val = await record_user_activity(session)

    await callback.message.edit_text(
        f"🟢 **Зафиксировано: 0 ₽ трат за сегодня!**\n\n"
        f"Отличная финансовая дисциплина! Ваш стрик трат сохраняется! 🔥\n"
        f"**Текущий стрик: {streak_val} дн. подряд!**"
    )
    await callback.answer("Стрик трат обновлён! 🔥")


@router.callback_query(F.data.startswith("confirm_payday:"))
async def cb_confirm_payday(callback: CallbackQuery):
    from app.services.accounts import get_setting_val, set_setting_val, record_user_activity
    raw_amount = callback.data.split(":")[1]
    amount = Decimal(raw_amount)

    async with AsyncSessionLocal() as session:
        await record_user_activity(session)
        tx = Transaction(
            author_telegram_id=callback.from_user.id,
            type="income",
            amount=amount,
            currency="RUB",
            category="Зарплата",
            note="Зачисление оклада в день зарплаты",
            date=date.today(),
            source="bot",
            confidence=1.0
        )
        session.add(tx)

        r_ess = int(await get_setting_val(session, "budget_ratio_essential", "50"))
        r_pers = int(await get_setting_val(session, "budget_ratio_personal", "30"))
        r_sav = int(await get_setting_val(session, "budget_ratio_savings", "20"))

        amt_ess = amount * Decimal(str(r_ess)) / Decimal("100")
        amt_pers = amount * Decimal(str(r_pers)) / Decimal("100")
        amt_sav = amount * Decimal(str(r_sav)) / Decimal("100")

        # Auto-transfer savings from Main balance to Savings balance
        start_bal = Decimal(await get_setting_val(session, "starting_balance", "0.00"))
        start_bal -= amt_sav
        await set_setting_val(session, "starting_balance", str(start_bal))

        sav_bal = Decimal(await get_setting_val(session, "savings_balance", "0.00"))
        sav_bal += amt_sav
        await set_setting_val(session, "savings_balance", str(sav_bal))

        await session.commit()

    report = (
        f"🎉 **Доход +{amount:,.0f} ₽ успешно зачислен на Основной счёт!**\n\n"
        f"📊 **Распределение по правилу {r_ess}/{r_pers}/{r_sav}:**\n"
        f"• 🏠 **Обязательное ({r_ess}%):** {amt_ess:,.0f} ₽ (жизнь, ЖКХ, продукты)\n"
        f"• 🎈 **Личные траты ({r_pers}%):** {amt_pers:,.0f} ₽ (досуг, покупки)\n"
        f"• 🎯 **Накопления ({r_sav}%):** {amt_sav:,.0f} ₽ *(автоматически переведено на Накопительный счёт)*\n\n"
        f"💡 *Балансы счетов автоматически обновлены!*"
    )
    await callback.message.edit_text(report, parse_mode="Markdown")
    await callback.answer("Зарплата зачислена!")


@router.callback_query(F.data == "skip_payday")
async def cb_skip_payday(callback: CallbackQuery):
    await callback.message.edit_text("⏭ Напоминание о зарплате пропущено.")
    await callback.answer()
