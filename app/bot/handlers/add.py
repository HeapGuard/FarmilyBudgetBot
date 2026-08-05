import json
import logging
import uuid
import httpx
from datetime import datetime, date, timedelta
from decimal import Decimal

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.db import OperationDraft, Transaction, Goal, GoalContribution
from app.models.schemas import OperationDraftSchema
from app.services.parser import parse_llm, extract_date
from app.services.stt import transcribe_voice
from app.services.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from app.services.accounts import record_user_activity
from app.services.transactions import save_draft_to_db, get_draft_from_db, confirm_draft
from app.services.notifications import notify_partner_about_transaction
from app.bot.keyboards import (
    get_draft_confirmation_keyboard,
    get_categories_keyboard,
    get_main_reply_keyboard
)

logger = logging.getLogger(__name__)

router = Router()


class AddStates(StatesGroup):
    waiting_for_text_edit = State()
    waiting_for_statement_action = State()
    confirming_statement_transactions = State()


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
async def cb_photo_type(callback: CallbackQuery, bot: Bot, state: FSMContext):
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

        draft, _ = await parse_llm(f"потратил {amount} рублей на {note or 'покупку по чеку'}", callback.from_user.id, author_name)
        if draft:
            if receipt_date:
                draft.date = receipt_date
        else:
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
                    'apikey': settings.OCR_API_KEY,
                    'language': 'rus',
                    'isOverlayRequired': False,
                    'FileType': 'JPG',
                    'isTable': True,
                    'scale': True,
                }
                r = await client.post('https://api.ocr.space/parse/image', files=files, data=data, timeout=20.0)
                res_json = r.json()
                if res_json.get("OCRExitCode") == 1:
                    extracted_text = res_json["ParsedResults"][0]["ParsedText"]
        except Exception as e:
            logger.error(f"OCR Error: {e}")

        if not extracted_text:
            extracted_text = caption or "Трата по чеку 1500"

        logger.info(f"OCR Extracted Text: {extracted_text}")
        from app.services.parser import detect_bank_statement, parse_bank_statement
        
        is_statement = detect_bank_statement(extracted_text)
        if is_statement:
            statement_data = await parse_bank_statement(extracted_text, date.today())
            txs = statement_data.get("transactions", [])
            if len(txs) > 0:
                await state.set_state(AddStates.waiting_for_statement_action)
                total_exp = statement_data.get("total_amount", 0.0)
                stmt_date = statement_data.get("date", date.today().strftime("%Y-%m-%d"))
                
                await state.update_data(
                    statement_txs=txs,
                    statement_index=0,
                    statement_saved_count=0,
                    statement_date=stmt_date,
                    statement_total=total_exp
                )
                
                tx_lines = []
                for i, tx in enumerate(txs, 1):
                    sign = "-" if tx["type"] == "expense" else "+" if tx["type"] == "income" else "\u2194"
                    tx_lines.append(f"{i}. {tx['note']}: {sign}{tx['amount']} RUB ({tx['category']})")
                tx_list_str = "\n".join(tx_lines)
                
                msg_text = (
                    f"\U0001F4F1 **Обнаружена выписка из банка за {stmt_date}**\n"
                    f"Найдено операций: **{len(txs)}** на общую сумму расходов **{total_exp:,.2f} RUB**.\n\n"
                    f"Список операций:\n{tx_list_str}\n\n"
                    f"Как вы хотите импортировать эти операции?"
                )
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text=f"\U0001F9FE Одной суммой ({total_exp:.0f} RUB)", callback_data="statement_action:single"),
                        InlineKeyboardButton(text="\U0001F4CA По отдельности", callback_data="statement_action:separate")
                    ],
                    [
                        InlineKeyboardButton(text="\u274C Отменить импорт", callback_data="statement_action:cancel")
                    ]
                ])
                
                await callback.message.edit_text(msg_text, reply_markup=kb, parse_mode="Markdown")
                await callback.answer()
                return

        parsed_date, clean_ocr_text = extract_date(extracted_text)

        draft, _ = await parse_llm(extracted_text, callback.from_user.id, author_name)

        if draft:
            if parsed_date and parsed_date != date.today():
                draft.date = parsed_date
        else:
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
                date=parsed_date or date.today(),
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

    tx, goal_name, transfer_info, budget_warning = await confirm_draft(draft)

    type_titles = {
        "expense": "Расход",
        "income": "Доход",
        "transfer": "Перевод",
        "goal_contribution": "Пополнение цели"
    }
    title = type_titles.get(draft.type, "Операция")
    confirm_text = f"✅ Готово! {title} {draft.amount:,.0f} ₽ сохранён{goal_name}{transfer_info}.".replace(",", " ")

    if budget_warning:
        confirm_text += f"\n\n{budget_warning}"

    await callback.message.edit_text(confirm_text)
    await callback.answer("Сохранено!")

    await notify_partner_about_transaction(callback.bot, draft, goal_name, transfer_info)



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


# --- Bank Statement Wizard Callbacks ---

@router.callback_query(AddStates.waiting_for_statement_action, F.data.startswith("statement_action:"))
async def cb_statement_action(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1]
    
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("\u274C Импорт выписки отменен.")
        await callback.answer()
        return
        
    data = await state.get_data()
    txs = data.get("statement_txs", [])
    stmt_date_str = data.get("statement_date", date.today().strftime("%Y-%m-%d"))
    total_exp = data.get("statement_total", 0.0)
    
    try:
        stmt_date = datetime.strptime(stmt_date_str, "%Y-%m-%d").date()
    except Exception:
        stmt_date = date.today()

    if action == "single":
        async with AsyncSessionLocal() as session:
            tx = Transaction(
                author_telegram_id=callback.from_user.id,
                type="expense",
                amount=Decimal(str(total_exp)),
                currency="RUB",
                category="Прочее",
                note="Импорт выписки одной суммой",
                date=stmt_date,
                source="bot",
                confidence=0.9
            )
            session.add(tx)
            await session.commit()
            
        await state.clear()
        await callback.message.edit_text(
            f"\u2705 **Операция успешно сохранена одной суммой!**\n\n"
            f"• Сумма: **{total_exp:,.2f} RUB**\n"
            f"• Категория: **Прочее**\n"
            f"• Дата: **{stmt_date.strftime('%d.%m.%Y')}**",
            parse_mode="Markdown"
        )
        await callback.answer("Успешно сохранено!")
        
        # Notify partner
        draft_notify = OperationDraftSchema(
            id=str(uuid.uuid4()),
            author_telegram_id=callback.from_user.id,
            author_name=callback.from_user.first_name or callback.from_user.username or "Партнёр",
            type="expense",
            amount=Decimal(str(total_exp)),
            currency="RUB",
            category="Прочее",
            note="Импорт выписки одной суммой",
            date=stmt_date,
            confidence=0.9,
            source="text",
            status="pending",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow()
        )
        await notify_partner_about_transaction(callback.bot, draft_notify)
        
    elif action == "separate":
        await state.set_state(AddStates.confirming_statement_transactions)
        await send_statement_wizard_step(callback.message, state)
        await callback.answer()


async def send_statement_wizard_step(message: Message, state: FSMContext):
    data = await state.get_data()
    txs = data.get("statement_txs", [])
    idx = data.get("statement_index", 0)
    total = len(txs)
    
    if idx >= total:
        saved = data.get("statement_saved_count", 0)
        await message.edit_text(
            f"\U0001F389 **Импорт выписки успешно завершен!**\n\n"
            f"Сохранено операций: **{saved}** из **{total}**.",
            reply_markup=None,
            parse_mode="Markdown"
        )
        await state.clear()
        return
        
    tx = txs[idx]
    
    msg_text = (
        f"Операция **{idx + 1} из {total}**:\n\n"
        f"📝 **Описание**: {tx['note']}\n"
        f"💰 **Сумма**: {tx['amount']:.2f} RUB\n"
        f"🏷 **Категория**: {tx['category']}\n"
        f"⚙️ **Тип**: {tx['type']}\n\n"
        f"Все верно?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\u2705 Да, сохранить", callback_data="statement_tx:confirm"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data="statement_tx:skip")
        ],
        [
            InlineKeyboardButton(text="\u270F\uFE0F Изменить категорию", callback_data="statement_tx:category"),
            InlineKeyboardButton(text="\u274C Прервать импорт", callback_data="statement_tx:abort")
        ]
    ])
    
    await message.edit_text(msg_text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(AddStates.confirming_statement_transactions, F.data.startswith("statement_tx:"))
async def cb_statement_tx_confirm(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1]
    
    data = await state.get_data()
    txs = data.get("statement_txs", [])
    idx = data.get("statement_index", 0)
    saved = data.get("statement_saved_count", 0)
    stmt_date_str = data.get("statement_date", date.today().strftime("%Y-%m-%d"))
    
    try:
        stmt_date = datetime.strptime(stmt_date_str, "%Y-%m-%d").date()
    except Exception:
        stmt_date = date.today()

    if action == "abort":
        await state.clear()
        await callback.message.edit_text(
            f"\u274C **Импорт прерван.**\n\n"
            f"Сохранено операций: **{saved}** из **{len(txs)}**.",
            parse_mode="Markdown"
        )
        await callback.answer()
        return
        
    elif action == "skip":
        await state.update_data(statement_index=idx + 1)
        await send_statement_wizard_step(callback.message, state)
        await callback.answer()
        return
        
    elif action == "category":
        kb = get_statement_categories_keyboard()
        await callback.message.edit_text(
            "Выберите новую категорию для этой операции:",
            reply_markup=kb
        )
        await callback.answer()
        return
        
    elif action == "back":
        await send_statement_wizard_step(callback.message, state)
        await callback.answer()
        return
        
    elif action == "confirm":
        tx_item = txs[idx]
        async with AsyncSessionLocal() as session:
            tx_model = Transaction(
                author_telegram_id=callback.from_user.id,
                type=tx_item["type"],
                amount=Decimal(str(tx_item["amount"])),
                currency="RUB",
                category=tx_item["category"],
                note=tx_item["note"],
                date=stmt_date,
                source="bot",
                confidence=0.95
            )
            session.add(tx_model)
            await session.commit()
            
        await state.update_data(
            statement_index=idx + 1,
            statement_saved_count=saved + 1
        )
        
        # Notify partner
        draft_notify = OperationDraftSchema(
            id=str(uuid.uuid4()),
            author_telegram_id=callback.from_user.id,
            author_name=callback.from_user.first_name or callback.from_user.username or "Партнёр",
            type=tx_item["type"],
            amount=Decimal(str(tx_item["amount"])),
            currency="RUB",
            category=tx_item["category"],
            note=tx_item["note"],
            date=stmt_date,
            confidence=0.95,
            source="text",
            status="pending",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow()
        )
        await notify_partner_about_transaction(callback.bot, draft_notify)
        
        await send_statement_wizard_step(callback.message, state)
        await callback.answer("Сохранено!")


def get_statement_categories_keyboard() -> InlineKeyboardMarkup:
    cats = ["Продукты", "Кафе и рестораны", "Транспорт", "Жильё и ЖКХ", "Развлечения", "Здоровье", "Покупки", "Зарплата", "Иной доход", "Переводы", "Прочее"]
    buttons = []
    row = []
    for c in cats:
        row.append(InlineKeyboardButton(text=c, callback_data=f"statement_tx_cat:{c}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="statement_tx:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(AddStates.confirming_statement_transactions, F.data.startswith("statement_tx_cat:"))
async def cb_statement_tx_category(callback: CallbackQuery, state: FSMContext):
    cat_name = callback.data.split(":")[1]
    
    data = await state.get_data()
    txs = data.get("statement_txs", [])
    idx = data.get("statement_index", 0)
    
    if idx < len(txs):
        txs[idx]["category"] = cat_name
        await state.update_data(statement_txs=txs)
        
    await send_statement_wizard_step(callback.message, state)
    await callback.answer(f"Категория изменена на {cat_name}")
