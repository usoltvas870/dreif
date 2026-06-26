from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "audium"
    postgres_user: str = "audium"
    postgres_password: str = "audium_secret"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def alembic_database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    # Auth
    session_secret: str = "change_me_32_bytes_random_string"

    # ЮKassa
    yukassa_shop_id: str = ""
    yukassa_secret_key: str = ""
    yukassa_webhook_secret: str = ""

    # Sentry
    sentry_dsn: str = ""

    # App
    app_base_url: str = "https://audium.ru"
    debug: bool = False


settings = Settings()
