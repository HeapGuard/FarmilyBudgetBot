import logging
from decimal import Decimal
from aiogram import Bot

from app.config import settings
from app.models.schemas import OperationDraftSchema

logger = logging.getLogger(__name__)


async def notify_partner_about_transaction(
    bot: Bot,
    draft: OperationDraftSchema,
    goal_name: str = "",
    transfer_info: str = ""
) -> None:
    """
    Sends a Telegram notification to household partners when a transaction exceeds NOTIFY_THRESHOLD.
    """
    notify_threshold = Decimal(str(settings.NOTIFY_THRESHOLD))
    if draft.amount < notify_threshold or draft.type not in ("expense", "income", "transfer"):
        return

    partner_ids = settings.ALLOWED_TELEGRAM_IDS - {draft.author_telegram_id}
    if not partner_ids:
        return

    type_titles = {
        "expense": "Расход",
        "income": "Доход",
        "transfer": "Перевод",
        "goal_contribution": "Пополнение цели"
    }
    title = type_titles.get(draft.type, "Операция")
    author_name_str = draft.author_name or "Партнёр"
    emoji_map = {"expense": "🛒", "income": "📈", "transfer": "🔄"}
    emoji = emoji_map.get(draft.type, "📋")
    cat_str = f" ({draft.category})" if draft.category and draft.category != "Переводы" else ""

    notify_text = (
        f"{emoji} <b>{author_name_str}</b> добавил(а) {title.lower()}: "
        f"<b>{draft.amount:,.0f} ₽</b>{cat_str}{transfer_info}".replace(",", " ")
    )

    for pid in partner_ids:
        try:
            await bot.send_message(pid, notify_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Failed to send partner notification to {pid}: {e}")
