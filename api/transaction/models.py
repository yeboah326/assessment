from sqlmodel import SQLModel, Field
from datetime import datetime
from transaction.enums import TransactionType
from sqlalchemy import Column, DateTime


class TransactionBase(SQLModel):
    user_id: int
    full_name: str
    transaction_date: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    transaction_amount: float
    transaction_type: TransactionType


class Transaction(TransactionBase, table=True):
    id: int = Field(default=None, nullable=False, primary_key=True)


class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(TransactionBase):
    pass