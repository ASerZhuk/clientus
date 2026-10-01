from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT.parent / ".env", extra="ignore")

    data_dir: Path = Field(default=API_ROOT / "data", alias="DATA_DIR")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    secret_key: str = Field(default="dev-only-secret-change-me", alias="SECRET_KEY")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    public_origins: str = Field(default="http://localhost:3000", alias="PUBLIC_ORIGINS")
    vapid_public_key: str = Field(default="", alias="VAPID_PUBLIC_KEY")
    vapid_private_key_path: str = Field(default="", alias="VAPID_PRIVATE_KEY_PATH")
    vapid_subject: str = Field(default="mailto:admin@example.com", alias="VAPID_SUBJECT")
    session_days: int = Field(default=14, alias="SESSION_DAYS")
    max_upload_mb: int = Field(default=8, alias="MAX_UPLOAD_MB")
    platform_name: str = Field(default="Clientus", alias="PLATFORM_NAME")  # shown in «Работает на …»
    platform_url: str = Field(default="", alias="PLATFORM_URL")
    platform_hosts: str = Field(default="localhost,127.0.0.1", alias="PLATFORM_HOSTS")  # hosts that serve /s/<slug>/ and /admin
    platform_ips: str = Field(default="", alias="PLATFORM_IPS")  # A-record targets customers must point their domain to
    internal_token: str = Field(default="dev-internal-token", alias="INTERNAL_TOKEN")  # web -> API host lookups
    plans_file: str = Field(default="", alias="PLANS_FILE")
    admin_session_hours: int = Field(default=12, alias="ADMIN_SESSION_HOURS")
    trial_days: int = Field(default=0, alias="TRIAL_DAYS")  # 0 = activation is lifetime (one-time sale)
    admin_enabled: bool = Field(default=True, alias="ADMIN_ENABLED")  # off on a customer's own server
    # optional LLM (OpenAI-compatible API) that phrases assistant answers; without it the assistant stays rule-based
    llm_base_url: str = Field(default="", alias="VSELLM_BASE_URL")
    llm_token: str = Field(default="", alias="VSELLM_TOKEN")
    llm_model: str = Field(default="", alias="VSELLM_MODEL")
    llm_timeout_s: float = Field(default=12.0, alias="LLM_TIMEOUT_S")

    @field_validator("data_dir", "vapid_private_key_path", mode="after")
    @classmethod
    def _relative_to_repo(cls, v):
        """Relative paths in .env are relative to the repository root, whatever the cwd is."""
        if isinstance(v, str):
            return v if not v or Path(v).is_absolute() else str(API_ROOT.parent / v)
        return v if v.is_absolute() else API_ROOT.parent / v

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'app.db'}"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def platform_host_list(self) -> list[str]:
        return [h.strip().lower().split(":")[0] for h in self.platform_hosts.split(",") if h.strip()]

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.public_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
