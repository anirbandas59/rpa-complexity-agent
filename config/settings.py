"""
Configuration management for RPA Complexity Agent.

Uses pydantic-settings to load all configuration from environment
variables and .env file. Settings are validated with model validators
to ensure consistency.
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Configuration
    default_llm_provider: str = Field(
        default="anthropic",
        description="LLM provider: anthropic | openai | watsonx | ollama",
    )
    default_llm_model: str = Field(
        default="claude-sonnet-4-5",
        description="Model name for the chosen provider",
    )

    # Provider API Keys
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key",
    )

    # Watsonx Configuration (optional)
    watsonx_api_key: str = Field(
        default="",
        description="Watsonx API key",
    )
    watsonx_url: str = Field(
        default="",
        description="Watsonx API URL",
    )
    watsonx_project_id: str = Field(
        default="",
        description="Watsonx project ID",
    )

    # Ollama Configuration (optional)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama base URL for local LLM",
    )

    # Application Paths
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    output_dir: str = Field(
        default="data/outputs",
        description="Output directory for generated files",
    )
    temp_dir: str = Field(
        default="data/temp",
        description="Temporary directory for processing",
    )

    # LLM Manager Behaviour
    llm_max_retries: int = Field(
        default=3,
        description="Max retry attempts on rate limit errors",
    )
    llm_retry_base_delay: float = Field(
        default=1.0,
        description="Base delay in seconds for exponential backoff",
    )

    @model_validator(mode="after")
    def validate_provider_keys(self) -> "Settings":
        """Validate that required API keys are set for the chosen provider."""
        provider = self.default_llm_provider.lower()

        if provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when DEFAULT_LLM_PROVIDER=anthropic"
            )

        if provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when DEFAULT_LLM_PROVIDER=openai"
            )

        if provider == "watsonx" and not self.watsonx_api_key:
            raise ValueError(
                "WATSONX_API_KEY and WATSONX_URL required when DEFAULT_LLM_PROVIDER=watsonx"
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load and cache settings. Returns same instance on subsequent calls.

    Returns:
        Settings: Singleton instance of application settings.
    """
    return Settings()
