from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, func
from json import loads, dumps


from redis_client import get_client
from redis import Redis
from db import get_session
from datetime import datetime

from transaction.models import Transaction, TransactionCreate, TransactionUpdate

transaction_router = APIRouter(prefix="/core", tags=["Core"])

TRANSACTIONS_ANALYTICS_TTL_SECONDS = 300
TRANSACTIONS_HISTORY_TTL_SECONDS = 120

REDIS_KEY_AVERAGE_TRANSACTION_VALUE = "analytics:{0}:average_transaction_value"
REDIS_KEY_DAY_OF_HIGHEST_NUMBER_OF_TRANSACTIONS = (
    "analytics:{0}:day_of_highest_number_of_transactions"
)
REDIS_KEY_HIGHEST_NUMBER_OF_TRANSACTIONS_IN_A_DAY = (
    "analytics:{0}:highest_number_of_transaction_in_a_day"
)
REDIS_KEY_TOTAL_DEBIT_VALUE = "analytics:{0}:total_debit_value:{1}:{2}"
REDIS_KEY_TOTAL_CREDIT_VALUE = "analytics:{0}:total_credit_value:{1}:{2}"


@transaction_router.post("/")
async def create_transaction(
    payload: TransactionCreate,
    session: AsyncSession = Depends(get_session),
    rc: Redis = Depends(get_client),
):
    # TODO - Handle when an error occurs while creating the transaction

    transaction = Transaction.model_validate(payload)
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)

    return transaction


@transaction_router.get("/")
async def read_transactions(
    session: AsyncSession = Depends(get_session),
    rc: Redis = Depends(get_client),
    user_id: int = Query(None),
    page: int = Query(1),
):
    transactions = []

    if not user_id:
        user_id = "all"

    cache_data = rc.get(f"transactions:{user_id}:{page}")

    if cache_data:
        transactions = loads(cache_data)

    else:
        query = select(Transaction)

        if user_id != "all":
            query = query.where(Transaction.user_id == user_id)

        results = await session.exec(query)
        transactions = results.all()

        rc.set(
            f"transactions:{user_id}:{page}",
            dumps(jsonable_encoder(transactions)),
            TRANSACTIONS_HISTORY_TTL_SECONDS,
        )

    return transactions


@transaction_router.get("/{id}")
async def read_transaction(
    id: int,
    session: AsyncSession = Depends(get_session),
    rc: Redis = Depends(get_client),
):
    transaction = None

    cache_data = rc.get(f"transaction:{id}")

    if cache_data:
        transaction = loads(cache_data)

    else:
        query = select(Transaction).where(Transaction.id == id)
        results = await session.exec(query)
        transaction = results.first()
        rc.set(
            f"transaction:{id}",
            dumps(jsonable_encoder(transaction)),
            TRANSACTIONS_HISTORY_TTL_SECONDS,
        )

    return transaction


@transaction_router.put("/{id}")
async def update_transaction(
    id: int,
    payload: TransactionUpdate,
    session: AsyncSession = Depends(get_session),
    rc: Redis = Depends(get_client),
):
    transaction = None

    query = select(Transaction).where(Transaction.id == id)
    results = await session.exec(query)
    transaction = results.first()

    if not transaction:
        raise HTTPException(404, "Transaction with the given ID does not exist")

    transaction_data = payload.model_dump(
        exclude_unset=True,
        exclude_defaults=True,
    )

    for key, value in transaction_data.items():
        setattr(transaction, key, value)

    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)

    rc.delete(f"transaction:{id}")

    for key in rc.scan_iter(match=f"transactions:{transaction.user_id}:*"):
        rc.delete(key)

    for key in rc.scan_iter(f"analytics:{transaction.user_id}:*"):
        rc.delete(key)

    return transaction


@transaction_router.delete("/{id}", status_code=204)
async def delete_transaction(
    id: int,
    session: AsyncSession = Depends(get_session),
    rc: Redis = Depends(get_client),
):
    transaction = None

    query = select(Transaction).where(Transaction.id == id)
    results = await session.exec(query)
    transaction = results.first()

    if not transaction:
        raise HTTPException(404, "Transaction with the given ID does not exist")

    await session.delete(transaction)
    await session.commit()

    rc.delete(f"transaction:{id}")

    for key in rc.scan_iter(match=f"transactions:{transaction.user_id}:*"):
        rc.delete(key)

    for key in rc.scan_iter(f"analytics:{transaction.user_id}:*"):
        rc.delete(key)

    return


@transaction_router.get("/{user_id}/analytics", status_code=200)
async def analytics(
    user_id: int,
    transaction_value_start_date: datetime = Query(None),
    transaction_value_end_date: datetime = Query(None),
    session: AsyncSession = Depends(get_session),
    rc: Redis = Depends(get_client),
):
    average_transaction_value = rc.get(
        REDIS_KEY_AVERAGE_TRANSACTION_VALUE.format(user_id)
    )

    day_of_highest_number_of_transactions = rc.get(
        REDIS_KEY_DAY_OF_HIGHEST_NUMBER_OF_TRANSACTIONS.format(user_id)
    )
    highest_number_of_transactions_in_a_day = rc.get(
        REDIS_KEY_HIGHEST_NUMBER_OF_TRANSACTIONS_IN_A_DAY.format(user_id)
    )

    total_debit_value = rc.get(
        REDIS_KEY_TOTAL_DEBIT_VALUE.format(
            user_id,
            transaction_value_start_date if transaction_value_start_date else "all",
            transaction_value_end_date if transaction_value_end_date else "all",
        )
    )

    total_credit_value = rc.get(
        REDIS_KEY_TOTAL_CREDIT_VALUE.format(
            user_id,
            transaction_value_start_date if transaction_value_start_date else "all",
            transaction_value_end_date if transaction_value_end_date else "all",
        )
    )

    # AVERAGE TRANSACTION VALUE
    if not average_transaction_value:
        query = select(func.avg(Transaction.transaction_amount)).where(
            Transaction.user_id == user_id
        )
        results = await session.exec(query)
        query_results = results.first()
        average_transaction_value = round(query_results if query_results else 0, 2)

        rc.set(
            REDIS_KEY_AVERAGE_TRANSACTION_VALUE.format(user_id),
            average_transaction_value,
            TRANSACTIONS_HISTORY_TTL_SECONDS,
        )

    # HIGHEST TRANSACTION IN A DAY
    if (
        not day_of_highest_number_of_transactions
        or not day_of_highest_number_of_transactions
    ):
        highest_number_of_transactions_in_a_day = 0
        day_of_highest_number_of_transactions = "None"

        query = (
            select(
                func.count(Transaction.id).label("transaction_count"),
                func.date(Transaction.transaction_date).label("transaction_day"),
            )
            .where(Transaction.user_id == user_id)
            .group_by(func.date(Transaction.transaction_date))
            .order_by(
                func.count(Transaction.id).desc(),
                func.date(Transaction.transaction_date).desc(),
            )
        )
        results = await session.exec(query)
        if query_results := results.first():
            (
                highest_number_of_transactions_in_a_day,
                day_of_highest_number_of_transactions,
            ) = query_results

        rc.set(
            REDIS_KEY_DAY_OF_HIGHEST_NUMBER_OF_TRANSACTIONS.format(user_id),
            str(
                day_of_highest_number_of_transactions,
            ),
            TRANSACTIONS_ANALYTICS_TTL_SECONDS,
        )
        rc.set(
            REDIS_KEY_HIGHEST_NUMBER_OF_TRANSACTIONS_IN_A_DAY.format(user_id),
            highest_number_of_transactions_in_a_day,
            TRANSACTIONS_ANALYTICS_TTL_SECONDS,
        )

    # TRANSACTIONS VALUE
    if not total_credit_value or total_debit_value:
        total_credit_value = 0
        total_debit_value = 0

        query = (
            select(
                Transaction.transaction_type, func.sum(Transaction.transaction_amount)
            )
            .where(Transaction.user_id == user_id)
            .group_by(Transaction.transaction_type)
        )

        if transaction_value_start_date:
            query = query.where(
                Transaction.transaction_date >= transaction_value_start_date
            )

        if transaction_value_end_date:
            query = query.where(
                Transaction.transaction_date <= transaction_value_end_date
            )

        results = await session.exec(query)
        final_results = results.all()

        for x in final_results:
            if x[0] == "debit":
                total_debit_value = round(x[1], 2)
            if x[0] == "credit":
                total_credit_value = round(x[1], 2)

        rc.set(
            REDIS_KEY_TOTAL_CREDIT_VALUE.format(
                user_id,
                transaction_value_start_date if transaction_value_start_date else "all",
                transaction_value_end_date if transaction_value_end_date else "all",
            ),
            total_credit_value,
            TRANSACTIONS_ANALYTICS_TTL_SECONDS,
        )
        rc.set(
            REDIS_KEY_TOTAL_DEBIT_VALUE.format(
                user_id,
                transaction_value_start_date if transaction_value_start_date else "all",
                transaction_value_end_date if transaction_value_end_date else "all",
            ),
            total_debit_value,
            TRANSACTIONS_ANALYTICS_TTL_SECONDS,
        )
    print(
        f"highest_number_of_transactions_in_a_day - {highest_number_of_transactions_in_a_day}"
    )
    print(
        f"day_of_highest_number_of_transactions - {day_of_highest_number_of_transactions}"
    )
    return {
        "average_transaction_value": float(average_transaction_value),
        "day_of_highest_number_of_transactions": day_of_highest_number_of_transactions,
        "highest_number_of_transactions_in_a_day": int(
            highest_number_of_transactions_in_a_day
        ),
        "total_debit_value": float(total_debit_value),
        "total_credit_value": float(total_credit_value),
    }
