import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import json
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator
import asyncio
from redis import Redis

from main import app  # Adjust import based on your project structure
from db import get_session
from transaction.models import Transaction, TransactionCreate, TransactionUpdate

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


# Setup test database
@pytest.fixture(scope="function")
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session

# Mock Redis client
@pytest.fixture
def mock_redis():
    return Mock(spec=Redis)

# Override dependencies
@pytest.fixture
def client(async_session, mock_redis):
    async def override_get_session():
        async with async_session() as session:
            yield async_session
        # finally:
        #     await async_session.close()

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[Redis] = lambda: mock_redis
    
    return TestClient(app)

# Sample test data
@pytest.fixture
def sample_transaction():
    return {
        "user_id": 1,
        "full_name": "John Doe",
        "transaction_date": datetime.now().isoformat(),
        "transaction_amount": 100.50,
        "transaction_type": "credit"
    }

# Test cases for Create Transaction
@pytest.mark.asyncio
async def test_create_transaction_success(client, sample_transaction):
    response = client.post("/core/", json=sample_transaction)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == sample_transaction["user_id"]
    assert data["transaction_amount"] == sample_transaction["transaction_amount"]
    assert "id" in data

# @pytest.mark.asyncio
# async def test_create_transaction_invalid_data(client):
#     invalid_transaction = {
#         "user_id": "invalid",  # Should be integer
#         "transaction_amount": "invalid_amount"  # Should be float
#     }
#     response = client.post("/core/", json=invalid_transaction)
#     assert response.status_code == 422

# # Test cases for Read Transactions
# @pytest.mark.asyncio
# async def test_read_transactions_no_cache(client, sample_transaction, mock_redis):
#     # Setup: Create a transaction first
#     client.post("/core/", json=sample_transaction)

#     # Mock Redis to return None (cache miss)
#     mock_redis.get.return_value = None

#     response = client.get("/core/")
#     assert response.status_code == 200
#     data = response.json()
#     assert len(data) > 0
#     assert mock_redis.set.called  # Verify cache was set

# @pytest.mark.asyncio
# async def test_read_transactions_with_cache(client, mock_redis):
#     # Mock cached data
#     cached_data = json.dumps([{
#         "id": 1,
#         "user_id": 1,
#         "full_name": "John Doe",
#         "transaction_date": datetime.now().isoformat(),
#         "transaction_amount": 100.50,
#         "transaction_type": "credit"
#     }])
#     mock_redis.get.return_value = cached_data

#     response = client.get("/core/")
#     assert response.status_code == 200
#     assert mock_redis.get.called
#     assert not mock_redis.set.called  # Verify cache wasn't set again

# # Test cases for Update Transaction
# @pytest.mark.asyncio
# async def test_update_transaction_success(client, sample_transaction):
#     # Create a transaction first
#     create_response = client.post("/core/", json=sample_transaction)
#     transaction_id = create_response.json()["id"]

#     update_data = {
#         "transaction_amount": 200.75,
#         "transaction_type": "debit"
#     }

#     response = client.put(f"/core/{transaction_id}", json=update_data)
#     assert response.status_code == 200
#     data = response.json()
#     assert data["transaction_amount"] == update_data["transaction_amount"]
#     assert data["transaction_type"] == update_data["transaction_type"]


