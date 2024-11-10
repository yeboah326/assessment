from enum import Enum

class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"