import warnings
from functools import cached_property
from types import MethodType

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from pathlib import Path

import aioboto3
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk
from langfuse.langchain import CallbackHandler
from langfuse import Langfuse

_PLACEHOLDER = "***"


class ThinkingChatOpenAI(ChatOpenAI):
    """ChatOpenAI that surfaces model reasoning into additional_kwargs['reasoning_content']."""

    def _convert_chunk_to_generation_chunk(self,
                                           chunk: dict,
                                           default_chunk_class: type,
                                           base_generation_info: dict | None) -> ChatGenerationChunk | None:
        gen_chunk = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        if gen_chunk is None:
            return None
        choices = chunk.get("choices", [])
        if choices:
            reasoning = choices[0].get("delta", {}).get("reasoning")
            if reasoning:
                gen_chunk.message.additional_kwargs["reasoning_content"] = reasoning
        return gen_chunk


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_file=".env",
                                      env_file_encoding="utf-8",
                                      case_sensitive=False,
                                      extra="ignore")

    # Application
    APP_NAME: str = "Assistant"
    LOG_LEVEL: str = "DEBUG"
    DEBUG: bool = True
    LOGS_ROTATION: str = "1 week"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    GRPC_ENABLED: bool = True
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50051
    DOMAIN: str = "localhost"  # Domain for CORS configuration

    # Limits (0 = unlimited)
    DAILY_TOKEN_LIMIT: int = 50000
    DAILY_IMAGE_LIMIT: int = 0
    MAX_STUDENTS: int = 0

    OCR_API_KEY: str = "***"
    OCR_LANGUAGE: str = "auto"
    WHISPER_TIMEOUT: int = 120  # seconds

    YOUTUBE_MAX_RETRIES: int = 3

    # Database (PostgreSQL)
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "tutor_assistant"
    DB_USER: str = "***"
    DB_PASSWORD: str = "***"

    # Context Management
    DOC_PREVIEW_CHARS: int = 300
    VOCAB_RECENT_COUNT: int = 50
    VOCAB_RANDOM_COUNT: int = 10

    # Extraction settings
    EXTRACTION_ENABLED: bool = True

    # LLM Settings API
    LLM_API_BASE: str = "***"
    LLM_API_KEY: str = "***"
    LLM_MODEL: str = "***"  # Main model for text and vision
    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.8
    LLM_MAX_CONCURRENT_CALLS: int = 8
    LLM_TIMEOUT: int = 900
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_WAIT: int = Field(
        default=600,
        description="Seconds to wait before attempting to reconnect to a disconnected model.",
    )
    LLM_CHUNK_SIZE: int = 12288 * 3

    # Set for providers that scope API keys to a project/folder (e.g. Yandex Cloud's
    # folder_id). ChatOpenAI has no constructor field for this — applied post-construction
    # onto the underlying openai client in `llm`/`llm_cheap` below.
    LLM_PROJECT_ID: str | None = None

    # Graph
    GRAPH_RECURSION_LIMIT: int = 10

    # Cheap LLM for extraction and chat name generation
    # Can use same or different API endpoint
    LLM_CHEAP_API_BASE: str | None = None  # If None, uses LLM_API_BASE
    LLM_CHEAP_API_KEY: str | None = None  # If None, uses LLM_API_KEY
    LLM_CHEAP_MODEL: str = "***"  # Cheaper model for non-critical tasks
    LLM_CHEAP_TEMPERATURE: float = 0.1

    # Image Generation Settings
    IMAGE_GEN_ENABLED: bool = True
    IMAGE_GEN_API_BASE: str = "***"  # Can be same as LLM_API_BASE
    IMAGE_GEN_API_KEY: str = "***"  # Can be same as LLM_API_KEY
    IMAGE_GEN_MODEL: str = "***"  # Model for image generation
    IMAGE_GEN_MAX_RETRIES: int = 2

    # Stock Photo Search (Pexels)
    STOCK_PHOTO_ENABLED: bool = True
    PEXELS_API_KEY: str = "***"

    # Registration
    REGISTRATION_ENABLED: bool = False

    # JWT Authentication
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Admin seed (used in migration to assign existing data)
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "changeme"

    ENABLE_CLEANUP_TASK: bool = True
    CLEANUP_DELETED_AFTER_DAYS: int = 30
    CLEANUP_INTERVAL_HOURS: int = 24

    # Langfuse
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_HOST: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None

    TEMPLATES_PATH: Path = Path("/app/src/templates")
    STATIC_PATH: Path = Path("/app/src/static")
    LOGS_PATH: Path = Path("/app/logs")

    # S3 / Object Storage
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str | None = None  # None = AWS; set for MinIO / Cloudflare R2
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    S3_KEY_PREFIX: str = "uploads"  # prepended to all object keys; empty = bucket root

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        """Refuse to boot with placeholder/default secrets when DEBUG is False.

        In DEBUG mode the same problems are surfaced as warnings so local dev
        still boots against a half-configured ``.env``.
        """
        problems: list[str] = []

        if self.JWT_SECRET_KEY == "change-me-in-production":
            problems.append("JWT_SECRET_KEY is the default placeholder")
        if self.ADMIN_PASSWORD == "changeme":
            problems.append("ADMIN_PASSWORD is the default placeholder")

        for name in ("S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
            if not getattr(self, name):
                problems.append(f"{name} is empty")

        for name in ("LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL", "DB_USER", "DB_PASSWORD", "OCR_API_KEY"):
            if getattr(self, name) == _PLACEHOLDER:
                problems.append(f"{name} is the {_PLACEHOLDER!r} placeholder")

        if self.IMAGE_GEN_ENABLED:
            for name in ("IMAGE_GEN_API_KEY", "IMAGE_GEN_MODEL", "IMAGE_GEN_API_BASE"):
                if getattr(self, name) == _PLACEHOLDER:
                    problems.append(f"IMAGE_GEN_ENABLED=True but {name} is the {_PLACEHOLDER!r} placeholder")

        if self.STOCK_PHOTO_ENABLED and self.PEXELS_API_KEY == _PLACEHOLDER:
            problems.append(f"STOCK_PHOTO_ENABLED=True but PEXELS_API_KEY is the {_PLACEHOLDER!r} placeholder")

        if self.LANGFUSE_ENABLED:
            for name in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
                if not getattr(self, name):
                    problems.append(f"LANGFUSE_ENABLED=True but {name} is not set")

        if problems:
            msg = "Insecure configuration: " + "; ".join(problems)
            if self.DEBUG:
                warnings.warn(msg, stacklevel=2)
            else:
                raise ValueError(msg)
        return self

    @cached_property
    def s3_session(self) -> aioboto3.Session:
        """aioboto3 session for S3-compatible object storage."""
        return aioboto3.Session(aws_access_key_id=self.S3_ACCESS_KEY,
                                aws_secret_access_key=self.S3_SECRET_KEY,
                                region_name=self.S3_REGION)

    @cached_property
    def llm(self) -> ChatOpenAI:
        """An LLM client with vision support."""
        callbacks = []
        if self.LANGFUSE_ENABLED:
            _ = self.langfuse_client
            callbacks.append(CallbackHandler(public_key=settings.LANGFUSE_PUBLIC_KEY))

        llm = ThinkingChatOpenAI(
            base_url=self.LLM_API_BASE,
            api_key=self.LLM_API_KEY,
            model=self.LLM_MODEL,
            temperature=self.LLM_TEMPERATURE,
            top_p=self.LLM_TOP_P,
            timeout=self.LLM_TIMEOUT,
            stream_usage=True,
            streaming=True,
            extra_body={"chat_template_kwargs": {
                "enable_thinking": True
            }},
            callbacks=callbacks,
        )

        # Add connectivity checks
        # The actual raised exception on timeout is `openai.APITimeoutError`,
        # but we want to fail on any
        def check_connectivity(self: ChatOpenAI) -> bool:
            try:
                self.invoke('Reply with "TEST".', timeout=3)
                return True
            except Exception:
                return False

        async def acheck_connectivity(self: ChatOpenAI) -> bool:
            try:
                await self.ainvoke('Reply with "TEST".', timeout=3)
                return True
            except Exception:
                return False

        llm._check_connectivity = MethodType(check_connectivity, llm)
        llm._acheck_connectivity = MethodType(acheck_connectivity, llm)
        if self.LLM_PROJECT_ID:
            llm.root_client.project = self.LLM_PROJECT_ID
            llm.root_async_client.project = self.LLM_PROJECT_ID
        return llm

    @cached_property
    def llm_cheap(self) -> ChatOpenAI:
        """Cheaper LLM for extraction and chat name generation tasks."""
        callbacks = []
        if self.LANGFUSE_ENABLED:
            _ = self.langfuse_client
            callbacks.append(CallbackHandler(public_key=settings.LANGFUSE_PUBLIC_KEY))

        llm_cheap = ChatOpenAI(
            base_url=self.LLM_CHEAP_API_BASE or self.LLM_API_BASE,
            api_key=self.LLM_CHEAP_API_KEY or self.LLM_API_KEY,
            model=self.LLM_CHEAP_MODEL,
            temperature=self.LLM_CHEAP_TEMPERATURE,
            top_p=self.LLM_TOP_P,
            timeout=self.LLM_TIMEOUT,
            extra_body={"chat_template_kwargs": {
                "enable_thinking": False
            }},
            callbacks=callbacks,
        )
        if self.LLM_PROJECT_ID:
            llm_cheap.root_client.project = self.LLM_PROJECT_ID
            llm_cheap.root_async_client.project = self.LLM_PROJECT_ID
        return llm_cheap

    @cached_property
    def image_gen_llm(self) -> ChatOpenAI:
        """ChatOpenAI client for image generation models."""
        return ChatOpenAI(base_url=self.IMAGE_GEN_API_BASE,
                          api_key=self.IMAGE_GEN_API_KEY,
                          model=self.IMAGE_GEN_MODEL,
                          temperature=0,
                          timeout=60)

    @cached_property
    def langfuse_client(self) -> Langfuse:
        """Langfuse client; a no-op stub when LANGFUSE_ENABLED is False."""
        if not self.LANGFUSE_ENABLED:
            return Langfuse(
                public_key="pass",
                secret_key="pass",  # noqa: S106 — stub credentials for disabled client
                tracing_enabled=False
            )
        return Langfuse(
            public_key=self.LANGFUSE_PUBLIC_KEY,
            secret_key=self.LANGFUSE_SECRET_KEY,
            host=self.LANGFUSE_HOST,
        )


settings = Settings()
