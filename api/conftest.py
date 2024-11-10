import pytest

from redis_client import get_client


@pytest.fixture(scope="function")
async def redis_client():
    async for rc in get_client():
        # Code to run before each test
        print("Setting up test environment")

        rc.delete("transactions:1:1")
        # ... other setup steps

        yield rc  # Yield control back to the test function

        # Code to run after each test
        print("Tearing down test environment")
        rc.flushall()
        # ... cleanup steps
