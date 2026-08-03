from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, String, Numeric, Float, Date, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20))  # expense, income
    name: Mapped[str] = mapped_column(String(255))
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    type: Mapped[str] = mapped_column(String(30), index=True)  # expense, income, transfer, goal_contribution
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(20), default="text")  # text, voice, manual, import
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    goal_contributions: Mapped[list["GoalContribution"]] = relationship(back_populates="transaction")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    current_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    apy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    monthly_contribution_plan: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active, paused, done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contributions: Mapped[list["GoalContribution"]] = relationship(back_populates="goal")


class GoalContribution(Base):
    __tablename__ = "goal_contributions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"))
    transaction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    goal: Mapped["Goal"] = relationship(back_populates="contributions")
    transaction: Mapped[Optional["Transaction"]] = relationship(back_populates="goal_contributions")


class OperationDraft(Base):
    __tablename__ = "operation_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    author_telegram_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AdviceLog(Base):
    __tablename__ = "advice_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author_telegram_id: Mapped[int] = mapped_column(BigInteger)
    advice_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
