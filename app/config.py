import os
import json
from typing import Set, Literal, Optional
from pydantic import BaseModel, Field

# Try loading dotenv if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def parse_ids_string(v: str) -> Set[int]:
    if not v or not str(v).strip():
        return set()
    v_str = str(v).strip()
    if v_str.startswith("[") and v_str.endswith("]"):
        try:
            return {int(x) for x in json.loads(v_str)}
        except Exception:
            pass
    res = set()
    for item in v_str.split(","):
        try:
            res.add(int(item.strip()))
        except ValueError:
            pass
    return res


try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )

        BOT_TOKEN: str = ""
        RAW_ALLOWED_TELEGRAM_IDS: str = Field(default="", alias="ALLOWED_TELEGRAM_IDS")

        BASE_URL: str = "http://localhost:8000"
        MODE: Literal["polling", "webhook"] = "polling"
        WEBHOOK_PATH: str = "/telegram/webhook"
        WEBHOOK_SECRET: str = "secret"
        SECRET_KEY: str = "change_me_super_secret"

        DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"
        TZ: str = "Europe/Moscow"
        DEBUG: bool = False

        STT_ENGINE: Literal["faster_whisper", "none"] = "faster_whisper"
        WHISPER_MODEL: str = "Systran/faster-whisper-small"
        STT_LANGUAGE: str = "ru"
        MAX_VOICE_DURATION_SECONDS: int = 120

        LLM_PROVIDER: Literal["rule_based", "ollama", "openrouter"] = "rule_based"
        OLLAMA_BASE_URL: str = "http://ollama:11434"
        OLLAMA_MODEL: str = "qwen2.5:3b-instruct"

        OPENROUTER_API_KEY: Optional[str] = None
        OPENROUTER_MODEL: str = "qwen/qwen-2.5-7b-instruct"

        DEFAULT_CURRENCY: str = "RUB"
        OCR_API_KEY: str = "helloworld"
        NOTIFY_THRESHOLD: float = 5000.0

        @property
        def ALLOWED_TELEGRAM_IDS(self) -> Set[int]:
            return parse_ids_string(self.RAW_ALLOWED_TELEGRAM_IDS)

except ImportError:
    class Settings(BaseModel):
        BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
        RAW_ALLOWED_TELEGRAM_IDS: str = os.getenv("ALLOWED_TELEGRAM_IDS", "")

        BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
        MODE: Literal["polling", "webhook"] = os.getenv("MODE", "polling")
        WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
        WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "secret")
        SECRET_KEY: str = os.getenv("SECRET_KEY", "change_me_super_secret")

        DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db")
        TZ: str = os.getenv("TZ", "Europe/Moscow")
        DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")

        STT_ENGINE: Literal["faster_whisper", "none"] = os.getenv("STT_ENGINE", "faster_whisper")
        WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "Systran/faster-whisper-small")
        STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "ru")
        MAX_VOICE_DURATION_SECONDS: int = int(os.getenv("MAX_VOICE_DURATION_SECONDS", "120"))

        LLM_PROVIDER: Literal["rule_based", "ollama", "openrouter"] = os.getenv("LLM_PROVIDER", "rule_based")
        OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
        OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

        OPENROUTER_API_KEY: Optional[str] = os.getenv("OPENROUTER_API_KEY")
        OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-7b-instruct")

        DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "RUB")
        OCR_API_KEY: str = os.getenv("OCR_API_KEY", "helloworld")
        NOTIFY_THRESHOLD: float = float(os.getenv("NOTIFY_THRESHOLD", "5000.0"))

        @property
        def ALLOWED_TELEGRAM_IDS(self) -> Set[int]:
            return parse_ids_string(self.RAW_ALLOWED_TELEGRAM_IDS)


settings = Settings()
