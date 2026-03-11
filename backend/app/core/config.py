from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Smart Patient Card System"
    APP_ENV: str = "development"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Africa's Talking
    AT_USERNAME: str = "sandbox"
    AT_API_KEY: str = ""
    AT_SHORTCODE: str = "*123#"
    AT_SENDER_ID: str = "SmartCard"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
