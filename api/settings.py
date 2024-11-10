from pydantic_settings import BaseSettings
from pydantic_core import MultiHostUrl
from pydantic import PostgresDsn

from dotenv import load_dotenv
load_dotenv()


class Settings(BaseSettings):
    DATABASE_USER: str
    DATABASE_NAME: str
    DATABASE_SERVER: str
    DATABASE_PASSWORD: str
    DATABASE_PORT: int = 5432

    @property
    def DB_CONNECTION_STRING(self) -> PostgresDsn:
        return MultiHostUrl.build(
            scheme="postgresql+asyncpg",
            path=self.DATABASE_NAME,
            port=self.DATABASE_PORT,
            host=self.DATABASE_SERVER,
            username=self.DATABASE_USER,
            password=self.DATABASE_PASSWORD,
        ).unicode_string()
    
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PROTOCOL: int = 3
    
    TEST_DATABASE_URL: str = 'sqlite+aiosqlite:///:memory'

settings = Settings()