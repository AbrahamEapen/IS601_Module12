# app/core/config.py
import warnings
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings

_INSECURE_JWT_DEFAULT = "your-super-secret-key-change-this-in-production"
_INSECURE_REFRESH_DEFAULT = "your-refresh-secret-key-change-this-in-production"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/fastapi_db"

    # JWT
    JWT_SECRET_KEY: str = _INSECURE_JWT_DEFAULT
    JWT_REFRESH_SECRET_KEY: str = _INSECURE_REFRESH_DEFAULT
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Security
    BCRYPT_ROUNDS: int = 12
    CORS_ORIGINS: List[str] = ["*"]

    # Redis (optional, for token blacklisting)
    REDIS_URL: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT:
            warnings.warn(
                "JWT_SECRET_KEY is using the insecure default value. "
                "Set a strong secret in your .env file before deploying.",
                stacklevel=2,
            )
        if self.JWT_REFRESH_SECRET_KEY == _INSECURE_REFRESH_DEFAULT:
            warnings.warn(
                "JWT_REFRESH_SECRET_KEY is using the insecure default value. "
                "Set a strong secret in your .env file before deploying.",
                stacklevel=2,
            )


# Module-level singleton (used by non-cached imports)
settings = Settings()


@lru_cache()
def get_settings() -> Settings:
    return Settings()
