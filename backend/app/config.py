from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Learn2Hire"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    demo_mode: bool = True

    # LLM provider: "auto" picks gemini when GEMINI_API_KEY is set,
    # otherwise Bedrock (when AWS creds exist), otherwise the offline fallback.
    llm_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    database_url: str = "sqlite:///./learn2hire.db"

    aws_region: str = "us-east-1"
    s3_bucket: str = "learn2hire-uploads"
    transcribe_role_arn: str = ""
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"

    opensearch_url: str = "http://localhost:9200"
    opensearch_user: str = ""
    opensearch_password: str = ""

    top_k: int = 6
    max_context_chars: int = 6000

    # Bound every Gemini call so a slow/overloaded API degrades to the offline
    # fallback instead of hanging the request indefinitely.
    gemini_timeout_seconds: int = 90

    upload_dir: str = "./data/uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Shared bounded-timeout options for every Gemini generate_content call.
GEMINI_TIMEOUT = {"timeout": settings.gemini_timeout_seconds}
