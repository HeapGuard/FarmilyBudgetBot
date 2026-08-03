from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, ConfigDict


class OperationDraftSchema(BaseModel):
    id: str
    author_telegram_id: int
    author_name: str
    type: Literal["expense", "income", "transfer", "goal_contribution"]
    amount: Decimal = Field(gt=0, le=1000000000)
    currency: Literal["RUB"] = "RUB"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    note: Optional[str] = None
    date: date
    confidence: float = 1.0
    source: Literal["text", "voice"] = "text"
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    target_goal_id: Optional[int] = None
    target_goal_title: Optional[str] = None
    created_at: datetime
    expires_at: datetime


class TransactionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_telegram_id: int
    type: str
    amount: Decimal
    currency: str
    category: Optional[str] = None
    note: Optional[str] = None
    date: date
    source: str
    confidence: Optional[float] = None
    created_at: datetime


class GoalSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    target_amount: Decimal
    current_amount: Decimal
    currency: str
    deadline: Optional[date] = None
    apy: Optional[float] = None
    monthly_contribution_plan: Optional[Decimal] = None
    status: str
    created_at: datetime
    progress_percentage: float = 0.0


class CategoryTopSchema(BaseModel):
    category: str
    amount: Decimal
    percentage: float


class CategoryBudgetSchema(BaseModel):
    category: str
    limit: Decimal
    spent: Decimal
    percentage: float


class BudgetUpdateSchema(BaseModel):
    category: str
    limit: Decimal


class AccountInfoSchema(BaseModel):
    name: str
    type: Literal["main", "savings", "deposit"]
    balance: Decimal
    apy: Optional[float] = None
    months: Optional[int] = None
    monthly_interest: Optional[Decimal] = None
    projected_total: Optional[Decimal] = None
    enabled: bool = True


class AccountsUpdateSchema(BaseModel):
    main_balance: Optional[Decimal] = None
    savings_balance: Optional[Decimal] = None
    savings_apy: Optional[float] = None
    savings_enabled: Optional[bool] = None
    deposit_balance: Optional[Decimal] = None
    deposit_apy: Optional[float] = None
    deposit_months: Optional[int] = None
    deposit_enabled: Optional[bool] = None


class MonthlySummarySchema(BaseModel):
    balance: Decimal
    total_capital: Decimal = Decimal("0.00")
    total_passive_income_monthly: Decimal = Decimal("0.00")
    financial_runway_months: float = 99.0
    income_month: Decimal
    expense_month: Decimal
    free_cash_flow: Decimal
    savings_rate: float
    accounts: List[AccountInfoSchema] = []
    category_budgets: List[CategoryBudgetSchema] = []
    top_expense_categories: List[CategoryTopSchema]
    active_goals: List[GoalSchema]
    recent_transactions: List[TransactionSchema]



