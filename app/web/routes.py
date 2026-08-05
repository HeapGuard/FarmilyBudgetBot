from datetime import date, timedelta
import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional, Literal

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, delete

import httpx

from app.config import settings as cfg
from app.database import AsyncSessionLocal
from app.models.db import Transaction, Goal, Setting, User, Account, Subscription, SubscriptionPayment, GoalContribution
from app.models.schemas import (
    MonthlySummarySchema, TransactionSchema, GoalSchema, CategoryTopSchema, AccountsUpdateSchema, BudgetUpdateSchema,
    AccountSchema, AccountCreateSchema
)
from app.services.accounts import get_accounts_info, set_setting_val, get_setting_val, get_user_streak
from app.services.budgets import get_category_budgets_summary, set_category_budget, calculate_financial_runway, check_budget_warning
from app.services.advice import ask_financial_ai
from app.services.qr_decoder import decode_qr_from_bytes, parse_fns_qr_string
from app.services.subscriptions import get_all_subscriptions, calculate_subscriptions_summary, create_subscription, delete_subscription, auto_detect_subscriptions
from app.services.intelligence import get_expense_trends, calculate_personal_inflation, get_author_spending_breakdown
from app.web.auth import get_current_web_user

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# --- Request Schemas with strict validation ---

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB max for QR images


class ChatRequestSchema(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class OperationCreateSchema(BaseModel):
    type: Literal["expense", "income", "transfer"]
    amount: Decimal = Field(gt=0, le=10_000_000)
    category: Optional[str] = Field(default="Прочее", max_length=100)
    note: Optional[str] = Field(default="", max_length=500)
    target_account: Optional[Literal["savings", "deposit", "main_from_savings"]] = None
    date: Optional[datetime.date] = None
    account_id: Optional[int] = None
    target_account_id: Optional[int] = None


class UserSettingsSchema(BaseModel):
    payday_schedule: Optional[str] = Field(default=None, max_length=50)
    payday_day_1: Optional[int] = Field(default=None, ge=1, le=31)
    payday_day_2: Optional[int] = Field(default=None, ge=1, le=31)
    payday_amount: Optional[float] = Field(default=None, ge=0)
    payday_type: Optional[str] = Field(default=None, max_length=50)
    budget_ratio_essential: Optional[int] = Field(default=None, ge=0, le=100)
    budget_ratio_personal: Optional[int] = Field(default=None, ge=0, le=100)
    budget_ratio_savings: Optional[int] = Field(default=None, ge=0, le=100)
    income_sources: Optional[str] = None



# --- Routes ---

@router.get("/healthz")
async def healthcheck():
    return {"status": "ok"}


@router.get("/app", response_class=HTMLResponse)
async def serve_mini_app(request: Request):
    response = templates.TemplateResponse(request=request, name="index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/api/summary", response_model=MonthlySummarySchema)
async def get_summary(scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    user_id = user.get("id")
    today = date.today()
    first_day = today.replace(day=1)

    async with AsyncSessionLocal() as session:
        # Get Accounts breakdown & total capital (shared family data)
        accounts, main_bal, total_capital, total_passive_income = await get_accounts_info(session)
        runway_months = await calculate_financial_runway(session, total_capital)
        category_budgets = await get_category_budgets_summary(session)

        # Current month transactions (filtered by scope)
        stmt_month = select(Transaction).where(Transaction.date >= first_day)
        if scope == "personal" and user_id:
            stmt_month = stmt_month.where(Transaction.author_telegram_id == user_id)
        stmt_month = stmt_month.order_by(desc(Transaction.date), desc(Transaction.id))

        month_txs = list((await session.execute(stmt_month)).scalars().all())

        income_month = sum((tx.amount for tx in month_txs if tx.type == "income"), Decimal("0"))
        expense_month = sum((tx.amount for tx in month_txs if tx.type == "expense"), Decimal("0"))
        free_cash_flow = income_month - expense_month
        savings_rate = float((free_cash_flow / income_month * 100) if income_month > 0 else 0.0)

        # Top 3 expense categories
        cat_totals: Dict[str, Decimal] = {}
        for tx in month_txs:
            if tx.type == "expense" and tx.category:
                cat_totals[tx.category] = cat_totals.get(tx.category, Decimal("0")) + tx.amount

        sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        top_categories = []
        for cat, amt in sorted_cats:
            pct = float((amt / expense_month * 100) if expense_month > 0 else 0.0)
            top_categories.append(CategoryTopSchema(category=cat, amount=amt, percentage=pct))

        # Active goals (shared family goals)
        stmt_goals = select(Goal).where(Goal.status == "active").order_by(Goal.id.asc())
        goals_db = list((await session.execute(stmt_goals)).scalars().all())
        goals_schema = []
        for g in goals_db:
            pct = float((g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 100.0)
            g_item = GoalSchema.model_validate(g)
            g_item.progress_percentage = min(pct, 100.0)
            goals_schema.append(g_item)

        # Recent 20 transactions
        stmt_recent = select(Transaction)
        if scope == "personal" and user_id:
            stmt_recent = stmt_recent.where(Transaction.author_telegram_id == user_id)
        stmt_recent = stmt_recent.order_by(desc(Transaction.date), desc(Transaction.id)).limit(20)

        recent_db = list((await session.execute(stmt_recent)).scalars().all())
        recent_schema = [TransactionSchema.model_validate(tx) for tx in recent_db]

    return MonthlySummarySchema(
        balance=main_bal,
        total_capital=total_capital,
        total_passive_income_monthly=total_passive_income,
        financial_runway_months=runway_months,
        income_month=income_month,
        expense_month=expense_month,
        free_cash_flow=free_cash_flow,
        savings_rate=savings_rate,
        accounts=accounts,
        category_budgets=category_budgets,
        top_expense_categories=top_categories,
        active_goals=goals_schema,
        recent_transactions=recent_schema
    )


@router.post("/api/budgets")
async def update_budget(data: BudgetUpdateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        await set_category_budget(session, data.category, data.limit)
        await session.commit()
    return {"status": "ok"}



@router.post("/api/accounts")
async def update_accounts(data: AccountsUpdateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        if data.main_balance is not None:
            stmt_inc = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "income")
            total_inc = Decimal(str((await session.execute(stmt_inc)).scalar()))
            stmt_exp = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == "expense")
            total_exp = Decimal(str((await session.execute(stmt_exp)).scalar()))
            adjusted_start = data.main_balance - total_inc + total_exp
            await set_setting_val(session, "starting_balance", str(adjusted_start))
        if data.savings_balance is not None:
            await set_setting_val(session, "savings_balance", str(data.savings_balance))
        if data.savings_apy is not None:
            await set_setting_val(session, "savings_apy", str(data.savings_apy))
        if data.savings_enabled is not None:
            await set_setting_val(session, "savings_enabled", "true" if data.savings_enabled else "false")
        if data.deposit_balance is not None:
            await set_setting_val(session, "deposit_balance", str(data.deposit_balance))
        if data.deposit_apy is not None:
            await set_setting_val(session, "deposit_apy", str(data.deposit_apy))
        if data.deposit_months is not None:
            await set_setting_val(session, "deposit_months", str(data.deposit_months))
        if data.deposit_enabled is not None:
            await set_setting_val(session, "deposit_enabled", "true" if data.deposit_enabled else "false")
        await session.commit()
    return {"status": "ok"}


@router.post("/api/chat")
async def chat_ai(data: ChatRequestSchema, user: dict = Depends(get_current_web_user)):
    user_id = user.get("id")
    async with AsyncSessionLocal() as session:
        answer = await ask_financial_ai(session, data.question, user_id=user_id)
    return {"answer": answer}


@router.post("/api/operations")
async def create_operation(data: OperationCreateSchema, user: dict = Depends(get_current_web_user)):
    user_id = user.get("id", 1)
    async with AsyncSessionLocal() as session:
        tx = Transaction(
            author_telegram_id=user_id,
            type=data.type,
            amount=data.amount,
            currency="RUB",
            category=data.category or "Прочее",
            note=data.note or "",
            date=data.date or date.today(),
            source="web",
            confidence=1.0,
            account_id=data.account_id,
            target_account_id=data.target_account_id
        )
        session.add(tx)
        await session.flush()

        source_acc = None
        dest_acc = None

        if data.type == "transfer":
            if data.target_account_id:
                dest_acc = await session.get(Account, data.target_account_id)
            if data.account_id:
                source_acc = await session.get(Account, data.account_id)

            # Legacy fallback
            if not dest_acc and data.target_account in ("savings", "deposit"):
                acc_type = data.target_account
                d_stmt = select(Account).where(Account.type == acc_type, Account.is_active == True)
                dest_acc = (await session.execute(d_stmt)).scalars().first()
            if not source_acc and data.target_account == "main_from_savings":
                s_stmt = select(Account).where(Account.type == "savings", Account.is_active == True)
                source_acc = (await session.execute(s_stmt)).scalars().first()
            
            if not source_acc:
                s_stmt = select(Account).where(Account.type == "card", Account.is_active == True)
                source_acc = (await session.execute(s_stmt)).scalars().first()
            if not dest_acc:
                d_type = "card" if data.target_account == "main_from_savings" else "savings"
                d_stmt = select(Account).where(Account.type == d_type, Account.is_active == True)
                dest_acc = (await session.execute(d_stmt)).scalars().first()
        else:
            if data.account_id:
                source_acc = await session.get(Account, data.account_id)
            else:
                s_stmt = select(Account).where(Account.type == "card", Account.is_active == True)
                source_acc = (await session.execute(s_stmt)).scalars().first()

        if source_acc:
            tx.account_id = source_acc.id
            if data.type == "expense":
                source_acc.balance -= data.amount
            elif data.type == "income":
                source_acc.balance += data.amount
            elif data.type == "transfer":
                source_acc.balance -= data.amount
            session.add(source_acc)

        if data.type == "transfer" and dest_acc:
            tx.target_account_id = dest_acc.id
            dest_acc.balance += data.amount
            session.add(dest_acc)

        # Check budget warning
        warning = None
        if data.type == "expense" and data.category:
            warning = await check_budget_warning(session, data.category, data.amount)

        await session.commit()
    return {"status": "ok", "warning": warning}


@router.delete("/api/operations/{operation_id}")
async def delete_operation(operation_id: int, user: dict = Depends(get_current_web_user)):
    """Delete an operation from the family budget."""
    async with AsyncSessionLocal() as session:
        stmt = select(Transaction).where(Transaction.id == operation_id)
        result = await session.execute(stmt)
        tx = result.scalar_one_or_none()

        if not tx:
            raise HTTPException(status_code=404, detail="Operation not found")

        if tx.account_id:
            source_acc = await session.get(Account, tx.account_id)
            if source_acc:
                if tx.type == "expense":
                    source_acc.balance += tx.amount
                elif tx.type == "income":
                    source_acc.balance -= tx.amount
                elif tx.type == "transfer":
                    source_acc.balance += tx.amount
                session.add(source_acc)

        if tx.type == "transfer" and tx.target_account_id:
            dest_acc = await session.get(Account, tx.target_account_id)
            if dest_acc:
                dest_acc.balance -= tx.amount
                session.add(dest_acc)

        await session.execute(delete(Transaction).where(Transaction.id == operation_id))
        await session.commit()
    return {"status": "ok"}


@router.post("/api/scan_qr")
async def scan_qr_receipt(file: UploadFile = File(...), user: dict = Depends(get_current_web_user)):
    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB.")

    qr_text = decode_qr_from_bytes(contents)

    if not qr_text:
        return {"success": False, "message": "Не удалось распознать QR-код на снимке"}

    amount, receipt_date, note = parse_fns_qr_string(qr_text)
    if not amount:
        return {"success": False, "message": "QR-код найден, но не содержит данных о сумме чека ФНС"}

    return {
        "success": True,
        "amount": float(amount),
        "date": receipt_date.isoformat() if receipt_date else date.today().isoformat(),
        "note": note or "Покупка по чеку"
    }


@router.get("/api/transactions", response_model=List[TransactionSchema])
async def get_transactions(scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    user_id = user.get("id")
    async with AsyncSessionLocal() as session:
        stmt = select(Transaction)
        if scope == "personal" and user_id:
            stmt = stmt.where(Transaction.author_telegram_id == user_id)
        stmt = stmt.order_by(desc(Transaction.date), desc(Transaction.id)).limit(50)
        txs = list((await session.execute(stmt)).scalars().all())
        return [TransactionSchema.model_validate(tx) for tx in txs]


@router.get("/api/profile")
async def get_user_profile(user: dict = Depends(get_current_web_user)):
    user_id = user.get("id", 1)
    raw_fname = user.get("first_name", "")
    first_name = "" if raw_fname == "Пользователь" else raw_fname
    last_name = user.get("last_name", "")
    username = user.get("username", "")
    photo_url = user.get("photo_url", "")
    today = date.today()
    first_day = today.replace(day=1)

    # Fetch avatar and username from Telegram Bot API if not available from initData
    if cfg.BOT_TOKEN and user_id and (not photo_url or not username):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get username via getChat if missing
                if not username:
                    chat_resp = await client.get(
                        f"https://api.telegram.org/bot{cfg.BOT_TOKEN}/getChat",
                        params={"chat_id": user_id}
                    )
                    if chat_resp.status_code == 200:
                        chat_data = chat_resp.json()
                        if chat_data.get("ok"):
                            chat_result = chat_data["result"]
                            username = chat_result.get("username", "")
                            if not first_name:
                                first_name = chat_result.get("first_name", "")
                            if not last_name:
                                last_name = chat_result.get("last_name", "")

                # Get avatar via getUserProfilePhotos if missing
                if not photo_url:
                    photos_resp = await client.get(
                        f"https://api.telegram.org/bot{cfg.BOT_TOKEN}/getUserProfilePhotos",
                        params={"user_id": user_id, "limit": 1}
                    )
                    if photos_resp.status_code == 200:
                        photos_data = photos_resp.json()
                        if photos_data.get("ok") and photos_data["result"]["total_count"] > 0:
                            # Get the smallest photo (last in the array is largest, first is smallest)
                            photo_sizes = photos_data["result"]["photos"][0]
                            # Pick the medium-sized photo (index 1 or last available)
                            target_photo = photo_sizes[-1] if len(photo_sizes) > 0 else None
                            if target_photo:
                                file_resp = await client.get(
                                    f"https://api.telegram.org/bot{cfg.BOT_TOKEN}/getFile",
                                    params={"file_id": target_photo["file_id"]}
                                )
                                if file_resp.status_code == 200:
                                    file_data = file_resp.json()
                                    if file_data.get("ok"):
                                        file_path = file_data["result"]["file_path"]
                                        photo_url = f"https://api.telegram.org/file/bot{cfg.BOT_TOKEN}/{file_path}"
        except Exception as e:
            print(f"Profile Bot API error: {e}")

    async with AsyncSessionLocal() as session:
        # Check User record in DB for accurate first_name and username
        u_stmt = select(User).where(User.telegram_id == user_id)
        user_db = (await session.execute(u_stmt)).scalar_one_or_none()
        
        # Если пользователя нет в БД, создаём его с данными из Telegram
        if not user_db:
            new_user = User(
                telegram_id=user_id,
                username=username or None,
                first_name=first_name or None,
                last_name=last_name or None
            )
            session.add(new_user)
            await session.flush()
            user_db = new_user
        
        if user_db:
            if user_db.first_name:
                first_name = user_db.first_name
            if user_db.last_name:
                last_name = user_db.last_name
            if user_db.username:
                username = user_db.username
            
            # Обновляем данные пользователя в БД, если они пришли из Telegram и отличаются
            if username and user_db.username != username:
                user_db.username = username
            if first_name and user_db.first_name != first_name:
                user_db.first_name = first_name
            if last_name and user_db.last_name != last_name:
                user_db.last_name = last_name
            await session.commit()

        streak_count = await get_user_streak(session)

        # Calculate user's personal monthly stats
        stmt_user = select(Transaction).where(
            Transaction.author_telegram_id == user_id,
            Transaction.date >= first_day
        )
        user_txs = list((await session.execute(stmt_user)).scalars().all())

        user_inc = sum((tx.amount for tx in user_txs if tx.type == "income"), Decimal("0"))
        user_exp = sum((tx.amount for tx in user_txs if tx.type == "expense"), Decimal("0"))
        user_free = user_inc - user_exp
        user_savings_rate = float((user_free / user_inc * 100) if user_inc > 0 else 0.0)

        # Calculate family total to find user's share %
        stmt_fam = select(Transaction).where(Transaction.date >= first_day)
        fam_txs = list((await session.execute(stmt_fam)).scalars().all())
        fam_exp = sum((tx.amount for tx in fam_txs if tx.type == "expense"), Decimal("0"))
        share_pct = float((user_exp / fam_exp * 100) if fam_exp > 0 else 50.0)

        # Calculate total historical personal balance
        stmt_all = select(Transaction).where(Transaction.author_telegram_id == user_id)
        all_txs = list((await session.execute(stmt_all)).scalars().all())
        all_inc = sum((tx.amount for tx in all_txs if tx.type == "income"), Decimal("0"))
        all_exp = sum((tx.amount for tx in all_txs if tx.type == "expense"), Decimal("0"))
        
        pers_start_bal = float(user_db.personal_starting_balance or 0.0)
        personal_balance = pers_start_bal + float(all_inc) - float(all_exp)

        return {
            "telegram_id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "photo_url": photo_url,
            "streak_count": streak_count,
            "personal_income_month": float(user_inc),
            "personal_expense_month": float(user_exp),
            "personal_savings_rate": user_savings_rate,
            "family_share_pct": share_pct,
            "personal_starting_balance": pers_start_bal,
            "personal_balance": personal_balance
        }


@router.post("/api/profile/starting-balance")
async def save_profile_starting_balance(data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    user_id = user["id"]
    val = float(data.get("personal_starting_balance", 0.0))
    async with AsyncSessionLocal() as session:
        u_stmt = select(User).where(User.telegram_id == user_id)
        user_db = (await session.execute(u_stmt)).scalar_one_or_none()
        if user_db:
            user_db.personal_starting_balance = Decimal(str(val))
            await session.commit()
    return {"status": "ok"}



@router.get("/api/user-settings")
async def get_user_settings(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        return {
            "payday_schedule": await get_setting_val(session, "payday_schedule", "2_monthly"),
            "payday_day_1": int(await get_setting_val(session, "payday_day_1", "10")),
            "payday_day_2": int(await get_setting_val(session, "payday_day_2", "25")),
            "payday_amount": float(await get_setting_val(session, "payday_amount", "75000")),
            "payday_type": await get_setting_val(session, "payday_type", "fixed"),
            "budget_ratio_essential": int(await get_setting_val(session, "budget_ratio_essential", "50")),
            "budget_ratio_personal": int(await get_setting_val(session, "budget_ratio_personal", "30")),
            "budget_ratio_savings": int(await get_setting_val(session, "budget_ratio_savings", "20")),
            "income_sources": await get_setting_val(session, "income_sources", ""),
        }


@router.post("/api/user-settings")
async def save_user_settings(data: UserSettingsSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        if data.payday_schedule is not None:
            await set_setting_val(session, "payday_schedule", str(data.payday_schedule))
        if data.payday_day_1 is not None:
            await set_setting_val(session, "payday_day_1", str(data.payday_day_1))
        if data.payday_day_2 is not None:
            await set_setting_val(session, "payday_day_2", str(data.payday_day_2))
        if data.payday_amount is not None:
            await set_setting_val(session, "payday_amount", str(data.payday_amount))
        if data.payday_type is not None:
            await set_setting_val(session, "payday_type", str(data.payday_type))
        if data.budget_ratio_essential is not None:
            await set_setting_val(session, "budget_ratio_essential", str(data.budget_ratio_essential))
        if data.budget_ratio_personal is not None:
            await set_setting_val(session, "budget_ratio_personal", str(data.budget_ratio_personal))
        if data.budget_ratio_savings is not None:
            await set_setting_val(session, "budget_ratio_savings", str(data.budget_ratio_savings))
        if data.income_sources is not None:
            await set_setting_val(session, "income_sources", str(data.income_sources))
        await session.commit()
    return {"status": "ok"}


@router.get("/api/goals", response_model=List[GoalSchema])
async def get_goals(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        stmt = select(Goal).order_by(Goal.id.asc())
        goals_db = list((await session.execute(stmt)).scalars().all())
        res = []
        for g in goals_db:
            pct = float((g.current_amount / g.target_amount * 100) if g.target_amount > 0 else 100.0)
            g_item = GoalSchema.model_validate(g)
            g_item.progress_percentage = min(pct, 100.0)
            res.append(g_item)
        return res


# --- Subscriptions API ---

@router.get("/api/subscriptions")
async def get_subscriptions(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        subs = await get_all_subscriptions(session)
        summary = calculate_subscriptions_summary(subs)
        return {
            "subscriptions": [
                {
                    "id": s.id,
                    "name": s.name,
                    "amount": float(s.amount),
                    "currency": s.currency,
                    "period": s.period,
                    "billing_day": s.billing_day,
                    "category": s.category,
                    "is_active": s.is_active,
                    "next_billing": s.next_billing.isoformat() if s.next_billing else None
                }
                for s in subs
            ],
            "total_monthly": float(summary["total_monthly"]),
            "total_yearly": float(summary["total_yearly"]),
            "active_count": summary["count"]
        }


@router.post("/api/subscriptions")
async def create_new_subscription(data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    from app.models.schemas import SubscriptionCreateSchema
    sub_schema = SubscriptionCreateSchema(
        name=data.get("name", "Подписка"),
        amount=Decimal(str(data.get("amount", 0))),
        period=data.get("period", "monthly"),
        billing_day=int(data.get("billing_day", 1)),
        category=data.get("category", "Подписки")
    )
    async with AsyncSessionLocal() as session:
        sub = await create_subscription(session, sub_schema)
        return {"status": "ok", "id": sub.id}


@router.delete("/api/subscriptions/{sub_id}")
async def remove_subscription(sub_id: int, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        ok = await delete_subscription(session, sub_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return {"status": "ok"}


@router.get("/api/subscriptions/autodetect")
async def autodetect_subs(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        detected = await auto_detect_subscriptions(session)
        return {"detected": detected}


@router.post("/api/subscriptions/blacklist")
async def blacklist_subscription_candidate(data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    name = data.get("name", "").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Name is empty")

    import json
    async with AsyncSessionLocal() as session:
        blacklist_raw = await get_setting_val(session, "sub_blacklist", "[]")
        try:
            blacklist = json.loads(blacklist_raw)
            if not isinstance(blacklist, list):
                blacklist = []
        except Exception:
            blacklist = []
        
        if name not in blacklist:
            blacklist.append(name)
            await set_setting_val(session, "sub_blacklist", json.dumps(blacklist))
        
        return {"status": "ok"}


@router.put("/api/subscriptions/{sub_id}")
async def edit_subscription(sub_id: int, data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        sub = await session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        if "name" in data:
            sub.name = data["name"]
        if "amount" in data:
            sub.amount = Decimal(str(data["amount"]))
        if "period" in data:
            sub.period = data["period"]
        if "billing_day" in data:
            sub.billing_day = int(data["billing_day"])
        if "category" in data:
            sub.category = data["category"]
        if "is_active" in data:
            sub.is_active = bool(data["is_active"])
            
        await session.commit()
        return {"status": "ok"}


@router.get("/api/subscriptions/payments")
async def get_subscription_payments(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        stmt = select(SubscriptionPayment)
        payments = list((await session.execute(stmt)).scalars().all())
        return [
            {
                "id": p.id,
                "subscription_id": p.subscription_id,
                "date": p.date.isoformat(),
                "status": p.status,
                "postponed_to": p.postponed_to.isoformat() if p.postponed_to else None
            }
            for p in payments
        ]


@router.post("/api/subscriptions/payment")
async def log_subscription_payment(data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        sub_id = int(data["subscription_id"])
        payment_date = date.fromisoformat(data["date"])
        status = data["status"]
        postponed_to = date.fromisoformat(data["postponed_to"]) if data.get("postponed_to") else None

        # Check if already exists
        stmt = select(SubscriptionPayment).where(
            SubscriptionPayment.subscription_id == sub_id,
            SubscriptionPayment.date == payment_date
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.status = status
            existing.postponed_to = postponed_to
        else:
            p = SubscriptionPayment(
                subscription_id=sub_id,
                date=payment_date,
                status=status,
                postponed_to=postponed_to
            )
            session.add(p)
        await session.commit()
        return {"status": "ok"}


# --- Analytics API ---

@router.get("/api/analytics/trends")
async def get_trends(period: int = 90, scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    author_id = user.get("id") if scope == "personal" else None
    async with AsyncSessionLocal() as session:
        return await get_expense_trends(session, period_days=period, author_id=author_id)


@router.get("/api/analytics/compare")
async def get_compare(scope: str = Query("family"), user: dict = Depends(get_current_web_user)):
    author_id = user.get("id") if scope == "personal" else None
    async with AsyncSessionLocal() as session:
        return await calculate_personal_inflation(session, author_id=author_id)


@router.get("/api/analytics/authors")
async def get_authors(period: int = 30, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        return await get_author_spending_breakdown(session, days=period)


# --- Goals Management API ---

class GoalCreateSchema(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    target_amount: Decimal = Field(gt=0)
    current_amount: Decimal = Field(ge=0, default=Decimal("0.00"))
    months: Optional[int] = Field(default=None, ge=1, le=120)
    apy: Optional[float] = Field(default=0.0, ge=0.0)


@router.post("/api/goals")
async def create_goal_endpoint(data: GoalCreateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        deadline_date = date.today() + timedelta(days=data.months * 30) if data.months else None
        g = Goal(
            title=data.title.strip(),
            target_amount=data.target_amount,
            current_amount=data.current_amount,
            deadline=deadline_date,
            apy=data.apy,
            status="active"
        )
        session.add(g)
        await session.commit()
        await session.refresh(g)
        return {"status": "ok", "id": g.id}


@router.post("/api/goals/{goal_id}/contribute")
async def contribute_to_goal(goal_id: int, data: Dict[str, Any], user: dict = Depends(get_current_web_user)):
    user_id = user.get("id", 1)
    amount = Decimal(str(data.get("amount", 0)))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")

    async with AsyncSessionLocal() as session:
        g = await session.get(Goal, goal_id)
        if not g:
            raise HTTPException(status_code=404, detail="Цель не найдена")

        g.current_amount += amount
        if g.current_amount >= g.target_amount:
            g.status = "done"

        # Record contribution transaction
        tx = Transaction(
            author_telegram_id=user_id,
            type="goal_contribution",
            amount=amount,
            category="Накопления",
            note=f"Взнос в цель «{g.title}»",
            date=date.today(),
            source="web"
        )
        session.add(tx)
        await session.flush()

        contrib = GoalContribution(
            goal_id=g.id,
            transaction_id=tx.id,
            amount=amount
        )
        session.add(contrib)
        await session.commit()
        return {"status": "ok", "current_amount": float(g.current_amount)}


@router.delete("/api/goals/{goal_id}")
async def delete_goal_endpoint(goal_id: int, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        g = await session.get(Goal, goal_id)
        if not g:
            raise HTTPException(status_code=404, detail="Цель не найдена")
        await session.delete(g)
        await session.commit()
        return {"status": "ok"}


# --- Accounts Management API ---

@router.get("/api/accounts", response_model=List[AccountSchema])
async def get_accounts_api(user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        from app.models.db import Account
        stmt = select(Account).where(Account.is_active == True).order_by(Account.id.asc())
        accounts = list((await session.execute(stmt)).scalars().all())
        return accounts


@router.post("/api/accounts")
async def create_account_api(data: AccountCreateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        from app.models.db import Account
        acc = Account(
            name=data.name.strip(),
            type=data.type,
            bank_name=data.bank_name,
            balance=data.balance,
            apy=data.apy,
            months=data.months
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return {"status": "ok", "id": acc.id}


@router.put("/api/accounts/{account_id}")
async def update_account_api(account_id: int, data: AccountCreateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        from app.models.db import Account
        acc = await session.get(Account, account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Счёт не найден")
        acc.name = data.name.strip()
        acc.type = data.type
        acc.bank_name = data.bank_name
        acc.balance = data.balance
        acc.apy = data.apy
        acc.months = data.months
        await session.commit()
        return {"status": "ok"}


@router.delete("/api/accounts/{account_id}")
async def delete_account_api(account_id: int, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        from app.models.db import Account
        acc = await session.get(Account, account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Счёт не найден")
        acc.is_active = False
        await session.commit()
        return {"status": "ok"}


# --- Operation Management API ---

class OperationUpdateSchema(BaseModel):
    amount: Optional[Decimal] = Field(default=None, gt=0)
    category: Optional[str] = None
    note: Optional[str] = None
    date: Optional[date] = None
    account_id: Optional[int] = None
    target_account_id: Optional[int] = None


@router.put("/api/operations/{operation_id}")
async def update_operation(operation_id: int, data: OperationUpdateSchema, user: dict = Depends(get_current_web_user)):
    async with AsyncSessionLocal() as session:
        tx = await session.get(Transaction, operation_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Операция не найдена")

        from app.models.db import Account
        # 1. Revert old balance
        if tx.account_id:
            old_source = await session.get(Account, tx.account_id)
            if old_source:
                if tx.type == "expense":
                    old_source.balance += tx.amount
                elif tx.type == "income":
                    old_source.balance -= tx.amount
                elif tx.type == "transfer":
                    old_source.balance += tx.amount
                session.add(old_source)

        if tx.type == "transfer" and tx.target_account_id:
            old_dest = await session.get(Account, tx.target_account_id)
            if old_dest:
                old_dest.balance -= tx.amount
                session.add(old_dest)

        # 2. Update values
        if data.amount is not None:
            tx.amount = data.amount
        if data.category is not None:
            tx.category = data.category
        if data.note is not None:
            tx.note = data.note
        if data.date is not None:
            tx.date = data.date
        if data.account_id is not None:
            tx.account_id = data.account_id
        if data.target_account_id is not None:
            tx.target_account_id = data.target_account_id

        # 3. Apply new balance
        if tx.account_id:
            new_source = await session.get(Account, tx.account_id)
            if new_source:
                if tx.type == "expense":
                    new_source.balance -= tx.amount
                elif tx.type == "income":
                    new_source.balance += tx.amount
                elif tx.type == "transfer":
                    new_source.balance -= tx.amount
                session.add(new_source)

        if tx.type == "transfer" and tx.target_account_id:
            new_dest = await session.get(Account, tx.target_account_id)
            if new_dest:
                new_dest.balance += tx.amount
                session.add(new_dest)

        await session.commit()
        return {"status": "ok"}


@router.post("/api/admin/clear-all-data")
async def admin_clear_all_data(user: dict = Depends(get_current_web_user)):
    user_id = user.get("id")
    if user_id != 1530744928:
        raise HTTPException(status_code=403, detail="Доступ запрещен")

    from app.models.db import User, Transaction, Goal, Subscription, Setting, GoalContribution, AuditLog, OperationDraft, AdviceLog, Category
    async with AsyncSessionLocal() as session:
        # Clear all tables in dependency order
        await session.execute(delete(GoalContribution))
        await session.execute(delete(Transaction))
        await session.execute(delete(Goal))
        await session.execute(delete(Subscription))
        await session.execute(delete(Setting))
        await session.execute(delete(AuditLog))
        await session.execute(delete(OperationDraft))
        await session.execute(delete(AdviceLog))
        await session.execute(delete(Category))
        await session.execute(delete(User))
        await session.commit()
    return {"status": "ok"}
