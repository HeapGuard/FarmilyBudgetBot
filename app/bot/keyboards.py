from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from app.config import settings
from app.services.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    web_app_url = f"{settings.BASE_URL.rstrip('/')}/app"

    keyboard = [
        [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="💰 Балансы")],
        [KeyboardButton(text="📊 Отчёт"), KeyboardButton(text="🎯 Цели")],
        [KeyboardButton(text="💡 Совет"), KeyboardButton(text="🏦 Счета")],
        [KeyboardButton(text="⚙️ Настройки")]
    ]
    if web_app_url.startswith("https://"):
        keyboard.append([KeyboardButton(text="🌐 Web App", web_app=WebAppInfo(url=web_app_url))])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    web_app_url = f"{settings.BASE_URL.rstrip('/')}/app"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить операцию", callback_data="btn_add")],
        [InlineKeyboardButton(text="🎯 Цели", callback_data="btn_goals"), InlineKeyboardButton(text="📊 Отчёт", callback_data="btn_report")],
        [InlineKeyboardButton(text="💡 Дай совет", callback_data="btn_advice")],
        [InlineKeyboardButton(text="🏦 Настройка счетов", callback_data="btn_accounts")]
    ]

    if web_app_url.startswith("https://"):
        buttons.append([InlineKeyboardButton(text="🌐 Открыть веб-приложение", web_app=WebAppInfo(url=web_app_url))])
    else:
        buttons.append([InlineKeyboardButton(text="🌐 Веб-приложение (Инфо)", callback_data="btn_app_info")])

    buttons.append([InlineKeyboardButton(text="⚙️ Настройки", callback_data="btn_settings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_accounts_keyboard(savings_enabled: bool = True, deposit_enabled: bool = True) -> InlineKeyboardMarkup:
    sav_toggle_txt = "❌ Отключить Накопительный" if savings_enabled else "🟢 Включить Накопительный"
    dep_toggle_txt = "❌ Отключить Вклад" if deposit_enabled else "🟢 Включить Вклад"

    buttons = [
        [InlineKeyboardButton(text="💳 Настроить Основной счёт", callback_data="edit_acc_main")],
        [
            InlineKeyboardButton(text="📈 Настроить Накопительный", callback_data="edit_acc_savings"),
            InlineKeyboardButton(text=sav_toggle_txt, callback_data="toggle_acc_savings")
        ],
        [
            InlineKeyboardButton(text="🔒 Настроить Вклад", callback_data="edit_acc_deposit"),
            InlineKeyboardButton(text=dep_toggle_txt, callback_data="toggle_acc_deposit")
        ],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)



def get_draft_confirmation_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{draft_id}")],
        [
            InlineKeyboardButton(text="🏷 Изменить категорию", callback_data=f"cat_pick_{draft_id}"),
            InlineKeyboardButton(text="✏️ Исправить текстом", callback_data=f"edit_text_{draft_id}")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_{draft_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_categories_keyboard(draft_id: str, op_type: str = "expense") -> InlineKeyboardMarkup:
    cats = EXPENSE_CATEGORIES if op_type != "income" else INCOME_CATEGORIES
    buttons = []
    row = []
    for cat in cats:
        # Avoid long callback_data, callback format: setcat_<draft_id>_<idx>
        idx = cats.index(cat)
        row.append(InlineKeyboardButton(text=cat, callback_data=f"sc_{draft_id}_{idx}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_draft_{draft_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_all_confirmation_1_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Точно удалить все данные?", callback_data="confirm_delete_1"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")
        ]
    ])


def get_delete_all_confirmation_2_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 Да, удалить безвозвратно", callback_data="confirm_delete_2"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")
        ]
    ])

