import pytest
import redis
from redis_client import get_client
from json import loads
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from settings import settings
from httpx import AsyncClient
from datetime import datetime, timedelta

engine = create_async_engine(
    settings.TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_client():
    with redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        protocol=settings.REDIS_PROTOCOL,
    ) as client:
        yield client


@pytest.fixture
def sample_transaction():
    return {
        "user_id": 1,
        "full_name": "John Doe",
        "transaction_date": datetime.now().isoformat(),
        "transaction_amount": 100.50,
        "transaction_type": "credit",
    }


@pytest.mark.asyncio
async def test_invalid_transaction_type():
    invalid_transaction = {
        "user_id": 1,
        "full_name": "John Doe",
        "transaction_date": datetime.now().isoformat(),
        "transaction_amount": 100.50,
        "transaction_type": "invalid_type",
    }

    async with AsyncClient(base_url="http://localhost:8000") as ac:
        response = await ac.post(f"/core/", json=invalid_transaction)
        response_json = response.json()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_read_transactions_no_cache():
    async for rc in get_client():
        for key in rc.scan_iter(match="transactions:*"):
            rc.delete(key)

        page = 1
        user_id = 1

        cache_data = rc.get(f"transactions:{user_id}:{page}")
        assert cache_data == None

        async with AsyncClient(base_url="http://localhost:8000") as ac:
            response = await ac.get(f"/core/?user_id={user_id}&page={page}")
            response_json = response.json()

        cache_data = rc.get(f"transactions:{user_id}:{page}")
        cache_data_json = loads(cache_data)

        assert response.status_code == 200
        assert len(cache_data_json) == len(response_json)


@pytest.mark.asyncio
async def test_read_transactions_cache():
    assert 1 == 1
    async for rc in get_client():
        for key in rc.scan_iter(match="transactions:*"):
            rc.delete(key)

        page = 1
        user_id = 1

        # We'll first make the API call because we're assuming the request will populate the cache
        async with AsyncClient(base_url="http://localhost:8000") as ac:
            response = await ac.get(f"/core/?user_id={user_id}&page={page}")

        cache_data = rc.get(f"transactions:{user_id}:{page}")
        cache_data_json = loads(cache_data if cache_data else "{}")

        # Here we're checking if the cache was actually populated
        assert cache_data != None

        async with AsyncClient(base_url="http://localhost:8000") as ac:
            response = await ac.get(f"/core/?user_id={user_id}&page={page}")
            response_json = response.json()

        # We're checking the response code and also ensuring that the data from the cache is the same as the data returned from the API call
        assert response.status_code == 200
        assert len(cache_data_json) == len(response_json)


@pytest.mark.asyncio
async def test_update_transaction_success(sample_transaction):
    page = 1
    user_id = 1
    transaction_id = 6

    update_data = {
        "user_id": 5,
        "full_name": "James Bond",
        "transaction_date": "2024-11-10",
        "transaction_amount": 30.50,
        "transaction_type": "credit",
    }

    async with AsyncClient(base_url="http://localhost:8000") as ac:
        response = await ac.put(f"/core/{transaction_id}", json=update_data)

    assert response.status_code == 200
    data = response.json()

    assert data["transaction_amount"] == update_data["transaction_amount"]
    assert data["transaction_type"] == update_data["transaction_type"]


@pytest.mark.asyncio
async def test_update_nonexistent_transaction():
    transaction_id = 300000

    update_data = {
        "user_id": 5,
        "full_name": "James Bond",
        "transaction_date": "2024-11-10",
        "transaction_amount": 30.50,
        "transaction_type": "credit",
    }
    async with AsyncClient(base_url="http://localhost:8000") as ac:
        response = await ac.put(f"/core/{transaction_id}", json=update_data)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_transaction_type():
    invalid_transaction = {
        "user_id": 1,
        "full_name": "John Doe",
        "transaction_date": datetime.now().isoformat(),
        "transaction_amount": 100.50,
        "transaction_type": "invalid_type",  # Should be 'credit' or 'debit'
    }

    async with AsyncClient(base_url="http://localhost:8000") as ac:
        response = await ac.post(f"/core/", json=invalid_transaction)

    assert response.status_code == 422

# Test cases for Delete Transaction
# @pytest.mark.asyncio
# async def test_delete_transaction_success():
    

#     async for rc in get_client():
#         for key in rc.scan_iter(match="analytics:*"):
#             rc.delete(key)

#         for key in rc.scan_iter(match="transactions:*"):
#             rc.delete(key)

#         async with AsyncClient(base_url="http://localhost:8000") as ac:
#             response = await ac.post(
#                 f"/core/",
#                 json={
#                     "user_id": 1,
#                     "full_name": "John Doe",
#                     "transaction_date": datetime.now().isoformat(),
#                     "transaction_amount": 100.50,
#                     "transaction_type": "credit",  # Should be 'credit' or 'debit'
#                 },
#             )
#         print(f"RESPONSE - {response.json()}")
#         transaction_id = response['id']

#         async with AsyncClient(base_url="http://localhost:8000") as ac:
#             response = await ac.get(f"/core/{transaction_id}")

#         # Check if data was loaded in the cache after get
#         assert rc.get(f"transaction:{transaction_id}") != None

#         async with AsyncClient(base_url="http://localhost:8000") as ac:
#             response = await ac.delete(f"/core/{transaction_id}")

#         assert response.status_code == 204
#         assert response.json() is None
#         assert rc.get(f"transaction:{transaction_id}") == None

# # Test cases for Analytics
@pytest.mark.asyncio
async def test_analytics_no_cache():
    async for rc in get_client():
        for key in rc.scan_iter(match="analytics:*"):
            rc.delete(key)

        user_id = 1

        async with AsyncClient(base_url="http://localhost:8000") as ac:
            response = await ac.get(f"/core/{user_id}/analytics")

        assert response.status_code == 200
        data = response.json()

        assert "average_transaction_value" in data
        assert "day_of_highest_number_of_transactions" in data
        assert "highest_number_of_transactions_in_a_day" in data
        assert "total_debit_value" in data
        assert "total_credit_value" in data

# # Test edge cases and error handling
@pytest.mark.asyncio
async def test_analytics_no_transactions():
    page = 1
    user_id = 101

    async with AsyncClient(base_url="http://localhost:8000") as ac:
        response = await ac.get(f"/core/{user_id}/analytics")

    assert response.status_code == 200
    data = response.json()

    assert data["average_transaction_value"] == 0
    assert data["highest_number_of_transactions_in_a_day"] == 0
    assert data["total_debit_value"] == 0
    assert data["total_credit_value"] == 0


@pytest.mark.asyncio
async def test_analytics_with_date_range():
    async for rc in get_client():
        for key in rc.scan_iter(match="analytics:*"):
            rc.delete(key)

        base_date = datetime(2024, 1, 1)
        user_id = 1

        # Test with date range
        start_date = base_date
        end_date = base_date + timedelta(days=300)

        async with AsyncClient(base_url="http://localhost:8000") as ac:
            response = await ac.get(
                f"/core/1/analytics?transaction_value_start_date={start_date.strftime('%Y-%m-%d')}&transaction_value_end_date={end_date.strftime('%Y-%m-%d')}&user_id={user_id}"
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_debit_value"] == 44_512.33
        assert data["total_credit_value"] == 25_469.59
