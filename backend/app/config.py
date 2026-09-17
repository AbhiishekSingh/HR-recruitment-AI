from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "change-me"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "gpt5"
    openai_api_key: str = ""
    llm_model_name: str = "gpt-5"

    embedding_provider: str = "openai"
    embedding_model_name: str = "text-embedding-3-large"
    embedding_api_key: str = ""

    upload_dir: str = "/app/uploads"

    default_top_k: int = 150
    hybrid_dense_weight: float = 0.7
    hybrid_keyword_weight: float = 0.3


settings = Settings()
