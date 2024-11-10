import asyncio
import pytest
from typing import AsyncGenerator, Generator
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlmodel import SQLModel
from sqlmodel.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel.ext.asyncio.session import AsyncSession
from redis import Redis
from unittest.mock import Mock
import os
import sys
from datetime import datetime, timedelta

# Add project root to Python path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app  # Adjust these imports based on your project structure
from db import get_session
from settings import Settings
from transaction.models import Transaction

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
TEST_REDIS_URL = "redis://localhost:6379/1"  # Use a different database for testing

# Test settings override
@pytest.fixture(scope="session")
def test_settings():
    return Settings(
        DATABASE_URL=TEST_DATABASE_URL,
        REDIS_URL=TEST_REDIS_URL,
        SECRET_KEY="test_secret_key",
        ENCRYPTION_KEY="test_encryption_key"
    )

# Database fixtures
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False  # Set to True for SQL debugging
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()

@pytest.fixture(scope="function")
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with AsyncSession(engine) as session:
        yield session
        # Roll back all changes after each test
        await session.rollback()

@pytest.fixture(scope="function")
async def client(session) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with the test database session."""
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()

# Redis mock fixture
@pytest.fixture(scope="function")
def mock_redis():
    """Create a mock Redis client."""
    mock = Mock(spec=Redis)
    # Configure default mock behavior
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = True
    return mock

# Test data fixtures
@pytest.fixture(scope="function")
def sample_transaction_data():
    """Create sample transaction data."""
    return {
        "user_id": 1,
        "full_name": "John Doe",
        "transaction_date": datetime.now().isoformat(),
        "transaction_amount": 100.50,
        "transaction_type": "credit"
    }

@pytest.fixture(scope="function")
def multiple_transactions_data():
    """Create multiple sample transactions."""
    base_date = datetime.now()
    return [
        {
            "user_id": 1,
            "full_name": "John Doe",
            "transaction_date": base_date.isoformat(),
            "transaction_amount": 100.50,
            "transaction_type": "credit"
        },
        {
            "user_id": 1,
            "full_name": "John Doe",
            "transaction_date": (base_date - timedelta(days=1)).isoformat(),
            "transaction_amount": 200.75,
            "transaction_type": "debit"
        },
        {
            "user_id": 1,
            "full_name": "John Doe",
            "transaction_date": (base_date - timedelta(days=2)).isoformat(),
            "transaction_amount": 150.25,
            "transaction_type": "credit"
        }
    ]

@pytest.fixture(scope="function")
async def create_sample_transactions(session, multiple_transactions_data):
    """Create sample transactions in the database."""
    transactions = []
    for data in multiple_transactions_data:
        transaction = Transaction(**data)
        session.add(transaction)
        transactions.append(transaction)
    
    await session.commit()
    for transaction in transactions:
        await session.refresh(transaction)
    
    return transactions

# Utility fixtures
@pytest.fixture(scope="function")
def mock_encryption():
    """Mock encryption/decryption functions."""
    def mock_encrypt(text: str) -> bytes:
        return f"encrypted_{text}".encode()

    def mock_decrypt(encrypted_text: bytes) -> str:
        return encrypted_text.decode().replace("encrypted_", "")

    return mock_encrypt, mock_decrypt

# Cleanup fixture
@pytest.fixture(autouse=True)
async def cleanup(session):
    """Clean up after each test."""
    yield
    # Clean up the database
    await session.execute("DELETE FROM transaction")
    await session.commit()

# Error simulation fixtures
@pytest.fixture
def db_error_simulation(session):
    """Simulate database errors."""
    async def simulate_error(*args, **kwargs):
        raise Exception("Database error")
    
    # Store original method
    original_commit = session.commit
    # Replace with error simulation
    session.commit = simulate_error
    
    yield session
    
    # Restore original method
    session.commit = original_commit

@pytest.fixture
def redis_error_simulation(mock_redis):
    """Simulate Redis errors."""
    def simulate_error(*args, **kwargs):
        raise Exception("Redis error")
    
    mock_redis.get.side_effect = simulate_error
    mock_redis.set.side_effect = simulate_error
    
    return mock_redis

# Custom markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests"
    )