from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nullain_model: str = "ollama/llama3.2"
    nullain_embed_model: str = "ollama/nomic-embed-text"
    nullain_whisper_model: str = "base"
    nullain_whisper_device: str = "cpu"
    nullain_whisper_compute_type: str = "int8"
    nullain_piper_voice: str = "pt_BR-faber-medium"
    nullain_piper_model_path: str = ""
    nullain_voice_record_seconds: float = 5.0
    # Token local da API. Vazio = auth desligada (dev). Com valor, REST/WS exigem Bearer.
    nullain_api_token: str = ""
    nullain_confirm_timeout_seconds: float = 120.0


@lru_cache
def get_settings() -> Settings:
    return Settings()